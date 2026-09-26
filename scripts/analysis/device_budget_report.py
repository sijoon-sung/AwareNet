"""Describe recorded SFL time components; never replay them as new-policy results.

Usage: python scripts/analysis/device_budget_report.py out/run.jsonl [out/run2.jsonl]
Outputs JSON including observed budget misses when new runtime fields exist.
"""
import argparse
import json
from pathlib import Path
import statistics


def summarize(path, skip_rounds):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [row for row in rows if "round" in row and row["round"] >= skip_rounds]
    pairs, observed = [], []
    for row in rows:
        for k, d in row.get("per_client_detail", {}).items():
            if all(field in d for field in ("cli_fwd", "cli_bwd", "t_round")):
                pairs.append((row.get("plan", {}).get(k, 1.), d))
        observed.extend(v for v in (row.get("budget_outcome") or {}).get("clients", {}).values()
                        if "compute_budget_miss" in v)
    if not rows or not pairs:
        raise ValueError(f"{path}: no usable measured round detail")
    comp = [d["cli_fwd"] + d["cli_bwd"] for _, d in pairs]
    client_round = sum(d["t_round"] for _, d in pairs)
    server = sum(d.get("srv_gpu", 0.) + d.get("lock_wait", 0.) for _, d in pairs)
    xfer = sum(d.get("xfer", 0.) for _, d in pairs)
    return {"file": str(path), "interpretation": "recorded_execution_only",
            "first_round": min(r["round"] for r in rows), "rounds": len(rows),
            "client_rounds": len(pairs), "mean_width": statistics.mean(w for w, _ in pairs),
            "reduced_width_client_rounds": sum(w < 1 for w, _ in pairs),
            "mean_makespan_s": statistics.mean(r["makespan"] for r in rows),
            "median_client_compute_s": statistics.median(comp),
            "compute_fraction_of_summed_client_time": sum(comp) / client_round if client_round else None,
            "server_fraction_of_summed_xfer": server / xfer if xfer else None,
            "observed_budget_client_rounds": len(observed),
            "observed_compute_budget_misses": sum(v["compute_budget_miss"] for v in observed) if observed else None,
            "component_warning": "xfer includes server time in historical logs; overlap invalidates additive interpretation"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", type=Path, nargs="+")
    parser.add_argument("--skip-rounds", type=int, default=4)
    args = parser.parse_args()
    print(json.dumps([summarize(p, args.skip_rounds) for p in args.logs], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
