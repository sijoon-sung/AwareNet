"""Paired additional-dataset pilot using the repository's split/aggregation code.

Actual local training, not a KOREN or network-scheduler experiment. All arms use
the same full-model initialization, disjoint IID shards and minibatch indices.
No test-set tuning or early stopping. Results include unsuccessful arms.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sfl"))
import numpy as np
import torch
import torch.nn.functional as F
from torchvision.datasets import FashionMNIST
import models


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/followup_20261001/fashion")
    ap.add_argument("--rounds", type=int, default=20)
    ap.add_argument("--steps", type=int, default=8)
    ap.add_argument("--seeds", default="41,42,43")
    args = ap.parse_args()
    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    if (out / "manifest.json").exists():
        raise RuntimeError("Use a new output directory; existing runs are never overwritten")
    torch.set_num_threads(4)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    # Author-maintained mirror, with torchvision's published resource checksums.
    FashionMNIST.mirrors = ["https://raw.githubusercontent.com/zalandoresearch/fashion-mnist/master/data/fashion/"]
    train = FashionMNIST(ROOT / "data", train=True, download=True)
    test = FashionMNIST(ROOT / "data", train=False, download=True)
    seeds = [int(x) for x in args.seeds.split(",")]
    manifest = dict(kind="new_local_training_pilot", dataset="Fashion-MNIST",
        source="https://github.com/zalandoresearch/fashion-mnist", train_count=len(train), test_count=len(test),
        torch=torch.__version__, python=platform.python_version(), device=torch.cuda.get_device_name(0) if dev == "cuda" else "CPU",
        model="repository split ResNet18", cut=2, normalization="GroupNorm", batch=32,
        rounds=args.rounds, steps=args.steps, seeds=seeds, clients=3, partition="disjoint stratified IID",
        optimizer="Adam lr=0.0006, reset per client per round", input="28x28 grayscale replicated to RGB, normalized (x/255-0.5)/0.5",
        arms={"full": [1.,1.,1.], "prefix": [.5,.75,1.], "rolling": [.5,.75,1.]},
        evaluation="full global model on all 10000 official test samples after fixed final round",
        network="in-process activation/gradient handoff, no network or KOREN measurement",
        primary="final test accuracy; paired differences across three seeds",
        secondary="actual local sequential training wall time and activation payload bytes",
        code_sha256={p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ["sfl/models.py", "scripts/analysis/fashion_followup.py"]})
    write(out / "manifest.json", manifest)
    models.set_norm("gn")
    xtrain = train.data.to(dev).float().unsqueeze(1).repeat(1,3,1,1) / 127.5 - 1
    ytrain = train.targets.to(dev)
    xtest = test.data.to(dev).float().unsqueeze(1).repeat(1,3,1,1) / 127.5 - 1
    ytest = test.targets.to(dev)
    labels = train.targets.numpy()
    results = []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        shards = [[] for _ in range(3)]
        for cl in range(10):
            for ci, indices in enumerate(np.array_split(rng.permutation(np.where(labels == cl)[0]), 3)):
                shards[ci].extend(indices.tolist())
        assert len(set(sum(shards, []))) == len(train)
        batches = {ci: rng.choice(shards[ci], size=(args.rounds,args.steps,32), replace=True) for ci in range(3)}
        np.savez_compressed(out / f"seed_{seed}_batches.npz", **{f"c{k}": v for k,v in batches.items()})
        write(out / f"seed_{seed}_partition.json", shards)
        # Rotated run order limits systematic warm-up/order effects across arms.
        arms = list(manifest["arms"])
        offset = seeds.index(seed) % 3
        arms = arms[offset:] + arms[:offset]
        for arm in arms:
            torch.manual_seed(seed); np.random.seed(seed); random.seed(seed)
            models.ROLL = arm == "rolling"
            models.set_round(0)
            fc = models.ClientNet(1., 2).to(dev)
            fs = models.ServerNet(1., 2, num_classes=10).to(dev)
            initial_hash = hashlib.sha256(b"".join(t.detach().cpu().numpy().tobytes() for mod in (fc,fs) for t in mod.state_dict().values())).hexdigest()
            run = out / f"s{seed}_{arm}"
            run.mkdir()
            start = time.perf_counter()
            payload = 0
            for rnd in range(args.rounds):
                models.set_round(rnd + 1)
                ups_c, ups_s, losses = [], [], []
                t0 = time.perf_counter()
                for ci, width in enumerate(manifest["arms"][arm]):
                    c = models.ClientNet(width,2).to(dev)
                    s = models.ServerNet(width,2,num_classes=10).to(dev)
                    c.load_state_dict(models.slice_into(c.state_dict(),fc.state_dict()))
                    s.load_state_dict(models.slice_into(s.state_dict(),fs.state_dict()))
                    c.train(); s.train()
                    opt = torch.optim.Adam(list(c.parameters())+list(s.parameters()), lr=.0006)
                    for step in range(args.steps):
                        ix = torch.as_tensor(batches[ci][rnd,step],device=dev)
                        opt.zero_grad(set_to_none=True)
                        h = c(xtrain[ix]); transfer = h.detach().requires_grad_(True)
                        loss = F.cross_entropy(s(transfer),ytrain[ix])
                        loss.backward(); h.backward(transfer.grad)
                        torch.nn.utils.clip_grad_norm_(list(c.parameters())+list(s.parameters()),5.)
                        opt.step()
                        losses.append(float(loss.detach()))
                        payload += 2*h.numel()*h.element_size()
                    ups_c.append(({k:v.detach().clone() for k,v in c.state_dict().items()}, args.steps*32))
                    ups_s.append(({k:v.detach().clone() for k,v in s.state_dict().items()}, args.steps*32))
                    del c,s,opt,h,transfer,loss
                fc.load_state_dict(models.nested_average(fc.state_dict(),ups_c))
                fs.load_state_dict(models.nested_average(fs.state_dict(),ups_s))
                del ups_c,ups_s
                if dev == "cuda": torch.cuda.synchronize()
                rec = dict(seed=seed,arm=arm,round=rnd+1,mean_loss=float(np.mean(losses)),
                    wall_s=time.perf_counter()-t0,activation_gradient_bytes_cumulative=payload)
                with (run / "rounds.jsonl").open("a",encoding="utf-8") as f: f.write(json.dumps(rec)+"\n")
                print(json.dumps(rec),flush=True)
            train_seconds = time.perf_counter()-start
            fc.eval(); fs.eval()
            with torch.no_grad():
                pred = torch.cat([fs(fc(x)).argmax(1) for x in xtest.split(128)])
            correct = int((pred==ytest).sum())
            np.savez_compressed(run / "predictions.npz", predictions=pred.cpu().numpy(),labels=test.targets.numpy())
            torch.save({"front":fc.cpu().state_dict(),"back":fs.cpu().state_dict()},run/"global_final.pt")
            row = dict(seed=seed,arm=arm,correct=correct,test_count=len(test),accuracy=correct/len(test),
                training_wall_s=train_seconds,activation_gradient_bytes=payload,initial_sha256=initial_hash)
            write(run/"summary.json",row)
            results.append(row); write(out/"results.json",results)
            print("RESULT " + json.dumps(row),flush=True)
            del fc,fs,pred
    write(out/"complete.json",dict(runs=len(results),expected=3*len(seeds)))


if __name__ == "__main__":
    main()
