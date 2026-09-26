# -*- coding: utf-8 -*-
"""내 PC 시뮬레이션 — 실험 틀(연산 효과 / 경로 효과 / 결합)을 HPC 에 올리기 전에 유체 시뮬로 먼저 돈다.

    python scripts/analysis/sim_study.py                      # 원장 조건 h5 h5m h5m5 h8 + 합성 조건
    python scripts/analysis/sim_study.py h5 h8 --rounds 12 --micro 1,4

읽는 법: 표의 값은 수렴 뒤(앞 2라운드 제외) 평균. 정확도는 시뮬이 말하지 않는다(HPC 실측 rw_long).
"""
import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "sfl"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "exp"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import fluidsim as fs  # noqa: E402

M = 1e6


def _acc(tok):
    """접속 토큰: 50 → 50e6 (한 가닥) / "50/20" → [50e6, 20e6] (두 가닥, 출구 A/B)."""
    t = str(tok)
    return [float(x) * M for x in t.split("/")] if "/" in t else float(t) * M
BYTES_PER_BATCH = 8.39 * M
CPU_FULL = 0.30


def devices_from_ledger(name):
    import cond
    r = cond.resolve(name)
    g = lambda k, d=None: r[k]["v"] if k in r else d
    n = g("clients")
    sp = g("speed_list") or [1] * n
    acc = g("acc_list") or [50] * n
    devs = [fs.Device(f"c{i}", CPU_FULL / max(sp[i], 1e-6), BYTES_PER_BATCH, _acc(acc[i])) for i in range(n)]
    caps = {str(i + 1): c * M for i, c in enumerate(g("caps"))}
    return devs, caps, tuple(g("ladder")), g("batches") or 4


SYNTH = {
    "합성_연산이질": ([0.3 * 6.7, 0.3, 0.3, 0.3], [50, 50, 50, 50], [60, 60]),
    "합성_심한낙오": ([0.3 * 15, 0.3, 0.3, 0.3], [50, 50, 50, 50], [60, 60]),
    "합성_남는용량": ([0.3] * 4, [10, 30, 50, 80], [100, 20]),
}


def table(name, devs, caps, ladder, batches, rounds, micros):
    print(f"\n== {name}: 연산 {[round(d.cpu,2) for d in devs]}s  접속 {[(round(d.access/M) if not isinstance(d.access, list) else [round(x/M) for x in d.access]) for d in devs]}M  경로 {[round(c/M) for c in caps.values()]}M  배치 {batches}")
    print(f"   {'팔':10s} {'m':>2s} {'라운드':>8s} {'총비용':>8s}  {'Δ라운드':>7s} {'Δ총비용':>7s}  이동  폭 / 경로")
    base = None
    for micro in micros:
        for pol in ("uniform", "width", "path", "mp", "both", "bothmp"):
            H = fs.run_policy(devs, caps, pol, rounds=rounds, batches=batches, ladder=ladder, micro=micro)
            s = fs.summarize(H)
            if pol == "uniform" and micro == micros[0]:
                base = s
            dm = 100 * (s["makespan"] / base["makespan"] - 1); dc = 100 * (s["cost"] / base["cost"] - 1)
            print(f"   {pol:10s} {micro:2d} {s['makespan']:8.2f} {s['cost']:8.1f}  {dm:+6.1f}% {dc:+6.1f}%  {s['moves']:3d}   "
                  f"{[s['widths'][k] for k in sorted(s['widths'])]} / {['+'.join(s['sets'][k]) for k in sorted(s['sets'])]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("conds", nargs="*")
    ap.add_argument("--rounds", type=int, default=12)
    ap.add_argument("--micro", default="1")
    a = ap.parse_args()
    micros = [int(x) for x in a.micro.split(",")]
    names = a.conds or ["h5", "h5m", "h5m5", "h8"]
    for n in names:
        try:
            devs, caps, ladder, batches = devices_from_ledger(n)
        except SystemExit as e:
            print(f"(건너뜀 {n}: {e})"); continue
        table(n, devs, caps, ladder, batches, a.rounds, micros)
    if not a.conds:
        for n, (cpu, acc, cp) in SYNTH.items():
            devs = [fs.Device(f"c{i}", cpu[i], BYTES_PER_BATCH, acc[i] * M) for i in range(len(cpu))]
            table(n, devs, {str(i + 1): c * M for i, c in enumerate(cp)}, (0.5, 0.75, 1.0), 4, a.rounds, micros)


if __name__ == "__main__":
    main()
