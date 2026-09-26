"""Reproducible falsification study, NOT a packet/WAN/training simulator."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sfl"))
from barrier_schedule import GradientJob, barrier_time, chunk_schedule, completions, plan_window


def workload(case, seed, count):
    rng = random.Random(seed)
    sizes = [rng.randint(4, 16)*65536 for _ in range(count)]
    tails = [rng.uniform(.03, .12) if i < count-2 else rng.uniform(.4, 1.2) for i in range(count)]
    if case == "homogeneous":
        tails = [.1]*count
    estimates = [q*rng.uniform(.9, 1.1) for q in tails]
    intervals = [(max(0., .8*q), 1.2*q) for q in tails]
    if case == "homogeneous":
        estimates, intervals = list(tails), [(q, q) for q in tails]
    if case in ("inverted_estimate", "uncovered_drift"):
        estimates.reverse()
        intervals = [(max(0., .8*q), 1.2*q) for q in estimates]
    if case in ("inverted_estimate", "wide_uncertainty"):
        intervals = [(0., 1.5)]*count
    jobs = [GradientJob(f"c{i}", sizes[i], estimates[i], *intervals[i]) for i in range(count)]
    rng.shuffle(jobs)
    return jobs, {f"c{i}": q for i, q in enumerate(tails)}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/barrier_study.json")
    parser.add_argument("--out", type=Path, default=ROOT / "out/barrier_study")
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    for case in cfg["cases"]:
        for seed in range(cfg["seeds"]):
            jobs, actual = workload(case, seed, cfg["clients"])
            cap, quantum = cfg["capacity_bps"], cfg["quantum_bytes"]
            guarded = plan_window(jobs, cap, quantum_bytes=quantum, completion_error_s=cfg["completion_error_s"])
            scores = {}
            for policy in ("rr", "fifo", "sjf", "tail", "guarded", "oracle_tail"):
                js = jobs
                if policy == "oracle_tail":
                    js = [GradientJob(j.cid, j.size_bytes, actual[j.cid], actual[j.cid], actual[j.cid]) for j in jobs]
                seq = guarded["schedule"] if policy == "guarded" else chunk_schedule(js, "tail" if policy == "oracle_tail" else policy, quantum)
                done = completions(seq, cap)
                if case == "independent_links":
                    # Independent senders, no common bottleneck: a global queue is
                    # inapplicable. Every policy must leave the links parallel.
                    done = {j.cid: j.size_bytes*8/cap for j in jobs}
                scores[policy] = {"barrier_s": barrier_time(done, actual),
                                  "mean_gradient_completion_s": statistics.mean(done.values()),
                                  "completion_s": done}
            covered = all(j.tail_low_s <= actual[j.cid] <= j.tail_high_s for j in jobs)
            rows.append({"case": case, "seed": seed, "jobs": [vars(j) for j in jobs],
                         "actual_tails_s": actual, "all_intervals_cover": covered,
                         "used_tail": guarded["used_tail"] if case != "independent_links" else False,
                         "total_payload_bytes": sum(j.size_bytes for j in jobs), "scores": scores})
    with (args.out / "raw.jsonl").open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row)+"\n")
    summary = {}
    for case in cfg["cases"]:
        selected = [r for r in rows if r["case"] == case]
        summary[case] = {"runs": len(selected), "interval_coverage": statistics.mean(r["all_intervals_cover"] for r in selected),
                         "interventions": sum(r["used_tail"] for r in selected), "policies": {}}
        for p in selected[0]["scores"]:
            gain = [100*(1-r["scores"][p]["barrier_s"]/r["scores"]["rr"]["barrier_s"]) for r in selected]
            summary[case]["policies"][p] = {
                "mean_barrier_s": statistics.mean(r["scores"][p]["barrier_s"] for r in selected),
                "mean_paired_gain_pct": statistics.mean(gain),
                "min_gain_pct": min(gain), "max_gain_pct": max(gain),
                "regressions": sum(g < -1e-8 for g in gain)}
    artifact = {"scope": cfg["scope"], "config": cfg, "summary": summary,
                "sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in (Path(__file__), args.config, ROOT / "sfl/barrier_schedule.py")}}
    (args.out / "summary.json").write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
