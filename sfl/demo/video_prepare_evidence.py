"""Check predictions against saved CNN weights and prepare transparent video statistics."""
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/healthcare_enterprise_demo"
os.environ["AWARENET_ROLL"] = "1"
sys.path.insert(0, str(ROOT / "sfl"))
import numpy as np
import torch
import models

def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

def main():
    cfg = json.loads((OUT / "cnn_config.json").read_text(encoding="utf-8"))
    data = np.load(OUT / "cnn_predictions.npz")
    y = data["labels"]
    pred = data["rounds"][-1].argmax(1)
    initial = data["rounds"][0].argmax(1)
    cm = [[int(((y == i) & (pred == j)).sum()) for j in range(2)] for i in range(2)]
    cases = []
    # Fixed transparent selection: first normal corrected, first pneumonia correct,
    # first error in each class. All 624 results remain available.
    for label, mask in [("normal_corrected", (y == 0) & (pred == 0) & (initial != 0)),
                        ("pneumonia_correct", (y == 1) & (pred == 1)),
                        ("normal_error", (y == 0) & (pred != 0)),
                        ("pneumonia_error", (y == 1) & (pred != 1))]:
        idx = np.where(mask)[0]
        if len(idx):
            n = int(idx[0])
            cases.append(dict(kind=label, index=n, test_index=int(data["test_indices"][n]), label=int(y[n]),
                              initial=initial[n].item(), predicted=pred[n].item(),
                              initial_probs=data["rounds"][0, n].tolist(), final_probs=data["rounds"][-1, n].tolist()))
    models.set_norm("gn")
    torch.set_num_threads(6)
    fc, fs = models.ClientNet(1, 2).cuda().eval(), models.ServerNet(1, 2, num_classes=2).cuda().eval()
    state = torch.load(OUT / "cnn_global_final.pt", map_location="cpu", weights_only=True)
    fc.load_state_dict(state["front"]); fs.load_state_dict(state["back"])
    raw = np.load(ROOT / "data/pneumoniamnist_64.npz")["test_images"]
    xs = torch.tensor(np.repeat(raw[..., None], 3, axis=3)).permute(0, 3, 1, 2).cuda().float() / 255
    xs = (xs - torch.tensor([.49, .48, .45]).cuda()[None, :, None, None]) / torch.tensor([.25, .24, .26]).cuda()[None, :, None, None]
    with torch.no_grad():
        probs = torch.cat([fs(fc(x)).softmax(-1) for x in xs.split(64)]).cpu().numpy()
    assert np.array_equal(probs.argmax(1), pred), "Saved model and saved labels differ"
    metrics = dict(n=len(y), initial_accuracy=float((initial == y).mean()), accuracy=float((pred == y).mean()),
        correct=int((pred == y).sum()), errors=int((pred != y).sum()), confusion_matrix=cm,
        sensitivity=cm[1][1] / sum(cm[1]), specificity=cm[0][0] / sum(cm[0]),
        selection="first example meeting each condition in the fixed test order", cases=cases,
        checkpoint_reloaded=True, inference_max_abs_difference=float(np.abs(probs - data["rounds"][-1]).max()))
    write("cnn_verified_metrics.json", metrics)
    # Real convolution weights to depict aggregation. Small views only; source tensor named.
    initial_state = torch.load(OUT / "cnn_initial.pt", map_location="cpu", weights_only=True)
    weights = dict(initial=initial_state["front"]["stem.0.weight"].flatten(1).numpy(),
                   global_weights=state["front"]["stem.0.weight"].flatten(1).numpy())
    for c in range(3):
        sd = torch.load(OUT / f"cnn_client_{c}_final.pt", map_location="cpu", weights_only=True)
        weights[f"client_{c}"] = sd["front"]["stem.0.weight"].flatten(1).numpy()
    np.savez_compressed(OUT / "cnn_weights.npz", **weights)
    print(json.dumps(metrics, ensure_ascii=False), flush=True)

if __name__ == "__main__":
    main()
