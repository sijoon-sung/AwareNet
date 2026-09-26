"""Summarize actual network-policy logs. Predictions are never measured gains."""
import argparse
import json
import math
from pathlib import Path
import statistics


def percentile(values, q):
    if not values:
        return None
    return sorted(values)[max(0, math.ceil(len(values) * q) - 1)]


def summarize(path, skip):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [r for r in rows if "round" in r and r["round"] >= skip]
    if not rows:
        raise ValueError(f"no rounds at/after {skip}: {path}")
    exchanges, messages, payload = [], 0, 0
    receipts = []
    for r in rows:
        receipts.extend(v["status"] for v in (r.get("route_receipts") or {}).values())
        for d in r.get("per_client_detail", {}).values():
            traffic = d.get("traffic") or {}
            exchanges.extend(traffic.get("exchange_completion_s", []))
            messages += traffic.get("activation_messages", 0)
            payload += traffic.get("activation_payload_bytes", 0)
    return {"file": str(path), "rounds": len(rows), "sampled_exchanges": len(exchanges),
            "round_p50_s": statistics.median(r["makespan"] for r in rows),
            "round_p95_s": percentile([r["makespan"] for r in rows], .95),
            "exchange_p50_s": statistics.median(exchanges) if exchanges else None,
            "exchange_p95_s": percentile(exchanges, .95),
            "activation_messages": messages if exchanges else None,
            "activation_payload_bytes": payload if exchanges else None,
            "unverified_receipts": sum(s != "round_completed" for s in receipts) if receipts else None,
            "last_accuracy": rows[-1].get("acc"),
            "widths": [r.get("plan") for r in rows],
            "measurement_scope": "app send start to gradient consumption; includes server and client scheduling; not wire latency"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", type=Path, nargs="+")
    parser.add_argument("--skip-rounds", type=int, default=4)
    args = parser.parse_args()
    results = [summarize(p, args.skip_rounds) for p in args.logs]
    print(json.dumps({"runs": results,
        "same_recorded_width_schedule": all(r["widths"] == results[0]["widths"] for r in results),
        "comparison_note": "Matching widths alone does not establish equal data, seed or available network resources."}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
