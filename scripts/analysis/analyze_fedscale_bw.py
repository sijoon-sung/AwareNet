# =============================================================================
# AwareNet v2 — FedScale client_device_capacity bandwidth analysis
# =============================================================================
# Loads the FedScale client_device_capacity dataset and reports the bandwidth
# statistics quoted in the design docs:
#   - P5 / P50 / P95 (Mbps), P95/P5 heterogeneity ratio
#   - % of clients below 3 Mbps
#   - Pearson correlation between bandwidth and computation speed
#
# Expected data format (FedScale's device capacity trace):
#   pickle: {client_id: {"communication": <kbps>, "computation": <float>}}
#   csv   : columns client_id,communication,computation  (communication in kbps)
#
# The repo does not ship the dataset; pass --path to a local copy, e.g.
#   python scripts/analysis/analyze_fedscale_bw.py --path client_device_capacity
# Download reference: https://github.com/SymbioticLab/FedScale
#   (benchmark/dataset/data/device_info/client_device_capacity)
# =============================================================================

import argparse
import csv
import json
import math
import os
import pickle
import sys


def load_capacity(path):
    """Return list of (bandwidth_kbps, computation) tuples."""
    if not os.path.exists(path):
        sys.exit(f"[ERROR] file not found: {path}\n"
                 "Download FedScale's client_device_capacity and pass --path.")
    rows = []
    if path.endswith(".csv"):
        with open(path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rows.append((float(row["communication"]), float(row["computation"])))
    else:
        with open(path, "rb") as f:
            data = pickle.load(f)
        for _, rec in data.items():
            rows.append((float(rec["communication"]), float(rec["computation"])))
    if not rows:
        sys.exit("[ERROR] dataset is empty or in an unexpected format.")
    return rows


def percentile(sorted_xs, p):
    k = (len(sorted_xs) - 1) * p / 100.0
    lo, hi = int(k), min(int(k) + 1, len(sorted_xs) - 1)
    return sorted_xs[lo] + (sorted_xs[hi] - sorted_xs[lo]) * (k - lo)


def pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return float("nan")
    return cov / (sx * sy)


def main():
    ap = argparse.ArgumentParser(description="FedScale bandwidth distribution analysis")
    ap.add_argument("--path", required=True,
                    help="local client_device_capacity pickle or csv")
    ap.add_argument("--out", default="out/fedscale_bw_analysis.json")
    args = ap.parse_args()

    rows = load_capacity(args.path)
    bw_mbps = sorted(kbps / 1000.0 for kbps, _ in rows)   # kbps -> Mbps
    comp = [c for _, c in rows]
    bw_unsorted = [kbps / 1000.0 for kbps, _ in rows]

    p5 = percentile(bw_mbps, 5)
    p50 = percentile(bw_mbps, 50)
    p95 = percentile(bw_mbps, 95)
    below3 = 100.0 * sum(1 for b in bw_mbps if b < 3.0) / len(bw_mbps)
    corr = pearson(bw_unsorted, comp)

    result = {
        "n_clients": len(rows),
        "bandwidth_mbps": {
            "p5": round(p5, 3),
            "p50": round(p50, 3),
            "p95": round(p95, 3),
            "min": round(bw_mbps[0], 3),
            "max": round(bw_mbps[-1], 3),
        },
        "p95_over_p5_ratio": round(p95 / p5, 2) if p5 > 0 else None,
        "pct_below_3mbps": round(below3, 2),
        "pearson_bw_vs_computation": round(corr, 4),
    }

    print(json.dumps(result, indent=2))
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"[OK] saved -> {args.out}")


if __name__ == "__main__":
    main()
