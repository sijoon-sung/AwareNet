"""Falsify the all-ready assumption with independently released gradients.

Single constant-rate serializer, independent local tails, no TCP or model
feedback. The guarded arm NEVER waits to manufacture a ready cohort. It uses
RR until all outstanding gradients have arrived, then checks the final window.
"""
from collections import deque
import json
from pathlib import Path
import random
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sfl"))
from barrier_schedule import GradientJob, plan_window
from barrier_study import workload


def replay(jobs, release, actual, policy, cap=20e6, quantum=65536):
    rank = {j.cid: i for i, j in enumerate(jobs)}
    waiting = deque(sorted(jobs, key=lambda j: (release[j.cid], rank[j.cid])))
    ready = deque()
    remaining = {j.cid: j.size_bytes for j in jobs}
    by_id = {j.cid: j for j in jobs}
    t, done, final_schedule, intervention, eligible_bytes = 0., {}, None, False, 0
    def arrivals():
        while waiting and release[waiting[0].cid] <= t+1e-12:
            ready.append(waiting.popleft().cid)
    while len(done) < len(jobs):
        arrivals()
        if not ready and not final_schedule:
            t = release[waiting[0].cid]
            arrivals()
        if policy == "guarded" and not waiting and final_schedule is None:
            window = [GradientJob(k, remaining[k], by_id[k].tail_estimate_s,
                                  by_id[k].tail_low_s, by_id[k].tail_high_s) for k in ready]
            plan = plan_window(window, cap, quantum_bytes=quantum, completion_error_s=.002)
            final_schedule = deque(plan["schedule"])
            intervention = plan["used_tail"]
            eligible_bytes = sum(remaining[k] for k in ready) if len(ready) > 1 else 0
        if final_schedule:
            k, _, n = final_schedule.popleft()
        else:
            if policy == "tail":
                k = max(ready, key=lambda cid: by_id[cid].tail_estimate_s)
                ready.remove(k)
            else:
                k = ready.popleft()
            n = min(quantum, remaining[k])
        t += n*8/cap
        remaining[k] -= n
        if remaining[k] == 0:
            done[k] = t
        if final_schedule is None:
            arrivals()
            if remaining[k]:
                ready.append(k)
    return {"barrier_s": max(done[k]+actual[k] for k in done),
            "intervention": intervention, "eligible_bytes": eligible_bytes,
            "completion_s": done}


def main():
    rows = []
    for case in ("burst", "server_spaced", "sparse", "slow_clients_late"):
        for seed in range(100):
            jobs, actual = workload("heterogeneous", seed, 8)
            avg_service = statistics.mean(j.size_bytes*8/20e6 for j in jobs)
            rng = random.Random(seed+999)
            release = {j.cid: 0. if case == "burst" else
                       i*avg_service*.5 if case == "server_spaced" else
                       i*avg_service*3 if case == "sparse" else
                       actual[j.cid]*3+rng.random()*.01 for i, j in enumerate(jobs)}
            score = {p: replay(jobs, release, actual, p) for p in ("rr", "tail", "guarded")}
            # Scoped certificate must survive this independent arrival evaluator.
            if score["guarded"]["barrier_s"] > score["rr"]["barrier_s"]+1e-9:
                raise AssertionError("closed-final-window intervention regressed")
            if case == "sparse" and abs(score["tail"]["barrier_s"]-score["rr"]["barrier_s"]) > 1e-9:
                raise AssertionError("invented scheduling gain without overlap")
            rows.append({"case": case, "seed": seed, "release_s": release, "score": score})
    summary = {}
    for case in ("burst", "server_spaced", "sparse", "slow_clients_late"):
        selected = [r for r in rows if r["case"] == case]
        summary[case] = {}
        for p in ("rr", "tail", "guarded"):
            gains = [100*(1-r["score"][p]["barrier_s"]/r["score"]["rr"]["barrier_s"]) for r in selected]
            summary[case][p] = {"mean_gain_pct": statistics.mean(gains),
                                "regressions": sum(g < -1e-8 for g in gains),
                                "interventions": sum(r["score"][p]["intervention"] for r in selected)}
    out = ROOT / "out/barrier_study"
    out.mkdir(parents=True, exist_ok=True)
    (out / "arrival_raw.jsonl").write_text("".join(json.dumps(r)+"\n" for r in rows), encoding="utf-8")
    (out / "arrival_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
