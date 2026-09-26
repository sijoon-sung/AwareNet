"""Paired, past-only 60-window streams with a hidden abrupt drift at window 30."""
import json
from pathlib import Path
import random
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sfl"))
from barrier_schedule import TailHistory, barrier_time, chunk_schedule, completions, plan_window


def main():
    rows = []
    for seed in range(100):
        rng = random.Random(10000+seed)
        history = TailHistory()
        sizes = {f"c{i}": rng.randint(4, 16)*65536 for i in range(8)}
        for step in range(60):
            jobs, trusted = history.predict(sizes)  # No access to this window's tails.
            result = plan_window(jobs, 20e6, completion_error_s=.002)
            actual = {f"c{i}": (.8 if ((i >= 6) if step < 30 else (i < 2)) else .08)*rng.uniform(.9, 1.1)
                      for i in range(8)}
            base = chunk_schedule(jobs, "rr")
            schedules = {"rr": base, "tail": chunk_schedule(jobs, "tail"),
                         "guarded": result["schedule"],
                         "calibrated": result["schedule"] if trusted else base}
            score = {p: barrier_time(completions(seq, 20e6), actual) for p, seq in schedules.items()}
            covered = history.observe(actual)  # Feedback is available only AFTER the decision.
            rows.append({"seed": seed, "step": step, "trusted": trusted,
                         "covered": covered, "intervened": trusted and result["used_tail"], "barrier_s": score})
    phases = {"warmup": range(8), "stable": range(8, 30), "first_drift": range(30, 31),
              "recovery": range(31, 43), "adapted": range(43, 60)}
    summary = {}
    for phase, steps in phases.items():
        selected = [r for r in rows if r["step"] in steps]
        summary[phase] = {"windows": len(selected), "interventions": sum(r["intervened"] for r in selected),
                          "coverage": statistics.mean(r["covered"] for r in selected), "policies": {}}
        for p in ("rr", "tail", "guarded", "calibrated"):
            gains = [100*(1-r["barrier_s"][p]/r["barrier_s"]["rr"]) for r in selected]
            summary[phase]["policies"][p] = {"mean_gain_pct": statistics.mean(gains),
                                            "regressions": sum(g < -1e-8 for g in gains), "worst_gain_pct": min(gains)}
    out = ROOT / "out/barrier_study"
    out.mkdir(parents=True, exist_ok=True)
    (out / "drift_raw.jsonl").write_text("".join(json.dumps(r)+"\n" for r in rows), encoding="utf-8")
    (out / "drift_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
