"""Record a reproducible local CNN split-federated demonstration, not a KOREN benchmark."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import urllib.request
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sfl"))
os.environ["AWARENET_ROLL"] = "1"
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
import models

OUT = ROOT / "output/healthcare_enterprise_demo"

def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=20)
    ap.add_argument("--steps", type=int, default=12)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "images").mkdir(exist_ok=True)
    torch.manual_seed(41)
    np.random.seed(41)
    torch.set_num_threads(6)
    torch.backends.cudnn.benchmark = True
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    datafile = ROOT / "data/pneumoniamnist_64.npz"
    if not datafile.exists():
        urllib.request.urlretrieve("https://zenodo.org/records/10519652/files/pneumoniamnist_64.npz?download=1", datafile)
    assert hashlib.md5(datafile.read_bytes()).hexdigest() == "8f4eceb4ccffa70c672198ea285246c6"
    raw = np.load(datafile)
    def dataset(part):
        return SimpleNamespace(data=np.repeat(raw[part + "_images"][..., None], 3, axis=3),
            targets=raw[part + "_labels"].flatten(), classes=["normal", "pneumonia"])
    train, test = dataset("train"), dataset("test")
    rng = np.random.default_rng(41)
    # Disjoint, balanced shards; no test images enter training or model selection.
    inds = [[], [], []]
    labels = np.array(train.targets)
    for cls in range(2):
        chosen = rng.permutation(np.where(labels == cls)[0])
        for c, sub in enumerate(np.array_split(chosen, 3)):
            inds[c].extend(sub.tolist())
    ti = np.arange(len(test.targets))
    mean = torch.tensor([.49, .48, .45], device=dev)[None, :, None, None]
    std = torch.tensor([.25, .24, .26], device=dev)[None, :, None, None]
    def tensor(img):
        return (torch.tensor(img, device=dev).permute(0, 3, 1, 2).float() / 255 - mean) / std
    tx, ty = tensor(test.data[ti]), torch.tensor(np.array(test.targets)[ti], device=dev)
    shard = [(tensor(train.data[idx]), torch.tensor(labels[idx], device=dev)) for idx in inds]
    models.set_norm("gn")
    fc, fs = models.ClientNet(1, 2).to(dev), models.ServerNet(1, 2, num_classes=2).to(dev)
    def evaluate(c, s):
        c.eval(); s.eval()
        with torch.no_grad():
            return torch.cat([s(c(x)).softmax(-1) for x in tx.split(64)]).cpu().numpy()
    initial = evaluate(fc, fs)
    initial_sd = {"front": {k: v.cpu() for k, v in fc.state_dict().items()},
                  "back": {k: v.cpu() for k, v in fs.state_dict().items()}}
    torch.save(initial_sd, OUT / "cnn_initial.pt")
    cfg = dict(kind="new_local_training", date="2026-09-29", model="repository ResNet-18",
               device=torch.cuda.get_device_name(0) if dev == "cuda" else "CPU", cut=2,
               clients=3, widths=[.5, .75, 1.0], rolling=True, seed=41,
               rounds=a.rounds, steps_per_client_round=a.steps, batch=16,
               train_per_client=[len(i) for i in inds], test=len(ti), dataset="PneumoniaMNIST+ 64",
               dataset_url="https://zenodo.org/records/10519652", dataset_license="CC BY 4.0", normalization="GroupNorm",
               network="in-process activation/gradient handoff; no KOREN run",
               optimizer="Adam, lr=0.0006, reset per client per round", classes=test.classes)
    save_json(OUT / "cnn_config.json", cfg)
    save_json(OUT / "cnn_split.json", {"train_indices": inds, "test_indices": ti.tolist()})
    for c, idx in enumerate(inds):
        for j, n in enumerate(rng.choice(idx, 10, replace=False)):
            Image.fromarray(train.data[n]).save(OUT / "images" / f"client_{c}_{j}.png")
    for j, n in enumerate(ti):
        Image.fromarray(test.data[n]).save(OUT / "images" / f"test_{j}.png")
    history = [{"round": 0, "accuracy": float((initial.argmax(1) == ty.cpu().numpy()).mean()), "clients": []}]
    start = time.perf_counter()
    saved_probs = [initial]
    local_probs = []
    for r in range(1, a.rounds + 1):
        models.set_round(r)
        ups_c, ups_s, info = [], [], []
        round_start = time.perf_counter()
        for ci, p in enumerate(cfg["widths"]):
            c, s = models.ClientNet(p, 2).to(dev), models.ServerNet(p, 2, num_classes=2).to(dev)
            c.load_state_dict(models.slice_into(c.state_dict(), fc.state_dict()))
            s.load_state_dict(models.slice_into(s.state_dict(), fs.state_dict()))
            c.train(); s.train()
            opt = torch.optim.Adam(list(c.parameters()) + list(s.parameters()), lr=.0006)
            x, y = shard[ci]
            losses = []
            ct = time.perf_counter()
            for step in range(a.steps):
                # Equal class sampling counteracts the training set's class imbalance.
                ix = torch.cat([torch.where(y == cl)[0][torch.randint(int((y == cl).sum()), (8,), device=dev)] for cl in [0, 1]])
                opt.zero_grad(set_to_none=True)
                h = c(x[ix])
                # Explicit split: server returns the derivative at the cut to the client.
                transfer = h.detach().requires_grad_(True)
                loss = F.cross_entropy(s(transfer), y[ix])
                loss.backward()
                h.backward(transfer.grad)
                torch.nn.utils.clip_grad_norm_(list(c.parameters()) + list(s.parameters()), 5.)
                opt.step()
                losses.append(float(loss.detach()))
            torch.cuda.synchronize() if dev == "cuda" else None
            info.append(dict(client=ci, width=p, losses=losses, loss=float(np.mean(losses)),
                             seconds=time.perf_counter() - ct, activation_shape=list(h.shape),
                             activation_bytes=h.numel() * h.element_size(), samples=a.steps * 16))
            ups_c.append(({k: v.detach().clone() for k, v in c.state_dict().items()}, a.steps * 16))
            ups_s.append(({k: v.detach().clone() for k, v in s.state_dict().items()}, a.steps * 16))
            if r == a.rounds:
                local_probs.append(evaluate(c, s))
                torch.save({"front": {k: v.cpu() for k, v in c.state_dict().items()},
                            "back": {k: v.cpu() for k, v in s.state_dict().items()}, "width": p, "round": r},
                           OUT / f"cnn_client_{ci}_final.pt")
            del opt, c, s, h, transfer, loss
        fc.load_state_dict(models.nested_average(fc.state_dict(), ups_c))
        fs.load_state_dict(models.nested_average(fs.state_dict(), ups_s))
        del ups_c, ups_s
        pr = evaluate(fc, fs)
        saved_probs.append(pr)
        rec = dict(round=r, accuracy=float((pr.argmax(1) == ty.cpu().numpy()).mean()), clients=info,
                   seconds=time.perf_counter() - round_start, elapsed=time.perf_counter() - start)
        history.append(rec)
        save_json(OUT / "cnn_history.json", history)
        print(json.dumps({k: rec[k] for k in ["round", "accuracy", "seconds", "elapsed"]}), flush=True)
    torch.save({"front": {k: v.cpu() for k, v in fc.state_dict().items()},
                "back": {k: v.cpu() for k, v in fs.state_dict().items()}}, OUT / "cnn_global_final.pt")
    np.savez_compressed(OUT / "cnn_predictions.npz", rounds=np.array(saved_probs), clients=np.array(local_probs),
                        labels=ty.cpu().numpy(), test_indices=ti)
    with torch.no_grad():
        h = fc(tx[:12]).cpu().numpy()
    np.save(OUT / "cnn_activations.npy", h)
    save_json(OUT / "cnn_summary.json", dict(initial_accuracy=history[0]["accuracy"],
              final_accuracy=history[-1]["accuracy"], elapsed=time.perf_counter() - start,
              global_sha256=hashlib.sha256((OUT / "cnn_global_final.pt").read_bytes()).hexdigest()))

if __name__ == "__main__":
    main()
