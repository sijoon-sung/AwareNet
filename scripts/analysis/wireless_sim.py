# -*- coding: utf-8 -*-
"""무선 확장 1 — 무선 가닥(출구 B)의 속도가 흔들릴 때 계획기의 이득이 얼마나 남는가 (fluidsim).

    python scripts/analysis/wireless_sim.py --frac 0,0.25,0.5,0.75 --period 2,10

흔들림: 출구 B 상한이 period 초마다 [1-frac, 1+frac]×20M 으로 바뀐다. 계획기는 기준 20M 만 알고(프로브), 관측 효율 계수로만 따라간다.
조건: h5x 와 같음 (4대 50/20, 경로 150/150). 팔: 균등 / 엣지만 / 분할. 12R, 앞 4R 제외."""
import argparse, os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "sfl"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import fluidsim as fs  # noqa: E402
M = 1e6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frac", default="0,0.25,0.5,0.75"); ap.add_argument("--period", default="2,10")
    ap.add_argument("--n", type=int, default=4); ap.add_argument("--rounds", type=int, default=12)
    a = ap.parse_args()
    caps = {"1": 150 * M, "2": 150 * M}
    print(f"== 무선 흔들림 시뮬: {a.n}대 50/20, 경로 150/150, {a.rounds}R (앞 4R 제외)")
    print(f"   {'주기':>4s} {'±폭':>5s} {'균등':>7s} {'엣지만':>7s} {'Δ':>7s} {'분할':>7s} {'Δ':>7s} {'분할 vs 엣지만':>12s}  {'분할 이동':>6s}")
    for period in [float(x) for x in a.period.split(",")]:
        for frac in [float(x) for x in a.frac.split(",")]:
            res = {}
            for pol in ("uniform", "path", "mp"):
                devs = [fs.Device(f"c{i}", 0.3, 8.39 * M, [50 * M, 20 * M], wobble=((1, period, frac, i + 1) if frac > 0 else None)) for i in range(a.n)]
                res[pol] = fs.summarize(fs.run_policy(devs, caps, pol, rounds=a.rounds, batches=4), skip=4)
            u, p, m = res["uniform"], res["path"], res["mp"]
            print(f"   {period:4.0f}s {frac*100:4.0f}% {u['makespan']:7.2f} {p['makespan']:7.2f} {100*(p['makespan']/u['makespan']-1):+6.1f}% {m['makespan']:7.2f} {100*(m['makespan']/u['makespan']-1):+6.1f}% {100*(1-m['makespan']/p['makespan']):+11.1f}%  {m['moves']:6d}")


if __name__ == "__main__":
    main()
