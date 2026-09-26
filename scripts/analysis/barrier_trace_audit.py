"""Audit historical support for a gradient-window hypothesis without inventing events."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[2]


def main():
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument("--pattern", default="wp_r8mix_rho1_s[123]_bothmp_widthpath.jsonl")
    ap.add_argument("--skip-rounds", type=int, default=4)
    args = ap.parse_args()
    records, sources = [], []
    for path in sorted((ROOT / "out").glob(args.pattern)):
        sources.append({"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        for line in path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if "round" not in r or r["round"] < args.skip_rounds:
                continue
            detail = r.get("per_client_detail", {})
            per = r.get("per_client", {})
            means = [d["cli_bwd"]/per[k][0] for k, d in detail.items()
                     if "cli_bwd" in d and k in per and per[k][0] > 0]
            if not means:
                continue
            records.append({"file": path.name, "round": r["round"],
                            "mean_batch_bwd_min_s": min(means), "mean_batch_bwd_max_s": max(means),
                            "makespan_s": r["makespan"],
                            "has_gradient_ready_events": all(bool(d.get("gradient_events")) for d in detail.values()),
                            "has_batch_compute": all(bool((d.get("traffic") or {}).get("batch_compute")) for d in detail.values())})
    if not records:
        raise SystemExit("no matching measurements")
    result = {"scope": "historical aggregates; mean batch backward is NOT the final gradient tail",
              "sources": sources, "rounds": len(records),
              "median_round_min_client_mean_batch_bwd_s": statistics.median(r["mean_batch_bwd_min_s"] for r in records),
              "median_round_max_client_mean_batch_bwd_s": statistics.median(r["mean_batch_bwd_max_s"] for r in records),
              "gradient_ready_event_rounds": sum(r["has_gradient_ready_events"] for r in records),
              "batch_compute_rounds": sum(r["has_batch_compute"] for r in records),
              "ready_queue_overlap": None, "counterfactual_training_speedup": None,
              "reason": "Historical logs do not identify concurrent ready gradients, wire completion, or exact final local tails."}
    out = ROOT / "out/barrier_study"
    out.mkdir(parents=True, exist_ok=True)
    (out / "legacy_audit.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
