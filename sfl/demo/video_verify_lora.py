"""Run real generation from archived adapters and preserve complete demo evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/training_demo"
os.environ["HF_HOME"] = str(ROOT / "data/huggingface_demo")
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_XET"] = "1"
sys.path[:0] = [str(ROOT / "sfl"), str(ROOT / "sfl/experiments")]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true")
    a = ap.parse_args()
    from huggingface_hub import snapshot_download
    location = snapshot_download("Qwen/Qwen2.5-0.5B", allow_patterns=["*.json", "*.safetensors", "*.txt"])
    print("Base model downloaded:", location, flush=True)
    if a.download:
        return
    import numpy as np
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from models_llm import inject_lora, freeze_except_lora
    from run_scale_lora import LLM_TARGETS
    from lora_corpus import load, split
    from eval_grid import answer
    from fed_split_eval import load_set, zero_adapters
    torch.set_num_threads(6)
    torch.manual_seed(41)
    model = AutoModelForCausalLM.from_pretrained(location, dtype=torch.float32, attn_implementation="sdpa")
    inject_lora(model.model.layers, 16, LLM_TARGETS)
    freeze_except_lora(model)
    model = model.to("cuda").eval()
    tok = AutoTokenizer.from_pretrained(location)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    old = json.loads((ROOT / "out/fed_split/eval_0913.json").read_text(encoding="utf-8"))["grid"]
    names = list(old)
    sets = [("base", names[0], None), ("single", names[1], "single1_0913"), ("federated", names[2], "fed3_0913")]
    result = dict(kind="new_local_inference_from_historical_checkpoints", model="Qwen/Qwen2.5-0.5B",
                  base_revision=Path(location).name, rank=16, cut=2, date="2026-09-29",
                  training="out/fed_split, 2026-09-13, three logical clients, 16 rounds x 30 steps",
                  scoring="keyword plus archived strict correction only for identical output", models=[],
                  evaluation_scope="18 unseen phrasings of training facts; not a general QA benchmark")
    strict = json.loads((ROOT / "out/fed_split/strict_0913v1.json").read_text(encoding="utf-8"))
    for key, name, prefix in sets:
        if prefix:
            load_set(model, str(ROOT / "out/fed_split" / prefix), 2)
        else:
            zero_adapters(model)
        row = dict(key=key, name=name, questions=[], checkpoint_hashes={})
        if prefix:
            for part in ["front", "back"]:
                p = ROOT / "out/fed_split" / f"{prefix}_{part}.pt"
                row["checkpoint_hashes"][str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
        for dom in ["B1", "B2", "B3"]:
            for item in split(load(dom))[1]:
                t = time.perf_counter()
                gen = answer(model, tok, item["q"], "cuda", max_new=32)
                archived = next(x for x in old[name][dom]["detail"] if x["q"] == item["q"])
                ok = any(k.lower() in gen.lower() for k in item["keywords"])
                identical = gen == archived["gen"]
                correction = strict.get(name, {}).get(item["q"])
                if correction is not None and identical:
                    ok = correction
                row["questions"].append(dict(domain=dom, q=item["q"], expected=item["a"], keys=item["keywords"],
                    answer=gen, correct=ok, seconds=time.perf_counter() - t, matches_archive=identical))
                print(key, dom, item["q"], "->", gen.replace("\n", " "), "correct=", ok, flush=True)
        row["correct"] = sum(x["correct"] for x in row["questions"])
        row["n"] = len(row["questions"])
        result["models"].append(row)
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "lora_inference.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    # Heatmap reflects real saved LoRA weights, never randomly generated values.
    sd = torch.load(ROOT / "out/fed_split/fed3_0913_front.pt", map_location="cpu", weights_only=True)
    arrays = {k: v.numpy() for k, v in list(sd.items())[:4]}
    np.savez_compressed(OUT / "lora_adapter_matrices.npz", **arrays)
    print("FINISHED", [(m["key"], m["correct"], m["n"]) for m in result["models"]], flush=True)

if __name__ == "__main__":
    main()
