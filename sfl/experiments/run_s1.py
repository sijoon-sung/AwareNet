# -*- coding: utf-8 -*-
"""S1 — **규모에서 규칙이 무너지는가.** 클라 4대 ~ 1024대 시뮬레이션.

  묻는 것은 하나다: **낙오자를 인식하는 조건이 규모에서 깨지는가.**

  현행 규칙의 인식 조건은 이렇다:
      D = alpha x min(전폭 예상시간)      (alpha = 1.2)
      D 를 넘는 클라를 좁힌다
  이건 **가장 빠른 한 명**을 기준으로 삼는다. N 이 커지면 그 '가장 빠른 한 명'은
  분포의 **극단값**이 된다 — N 이 커질수록 더 극단으로 간다.
  그러면 마감선이 자꾸 아래로 내려가 **점점 더 많은 사람이 낙오자로 찍힌다.**
  극단으로 가면 전원이 낙오자가 되어 규칙이 스스로 무너진다.

  이것이 실험으로 못 얻는 것이다 — 이 기계는 클라 4대가 한계다.

    python sfl/experiments/run_s1.py
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from sim import World, simulate            # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "out")
NS = [4, 8, 16, 32, 64, 128, 256, 512, 1024]
DISTS = ["homogeneous", "uniform_span", "lognormal", "few_stragglers"]


def sweep(dist, seeds=(1, 2, 3), rounds=8):
    rows = []
    for n in NS:
        acc = {}
        for s in seeds:
            w = World(n, seed=s, dist=dist)
            for pol in ("uniform", "ours"):
                r = simulate(w, pol, rounds=rounds)
                a = acc.setdefault(pol, {"ms": [], "p": [], "cut": [], "sp": []})
                a["ms"].append(r["makespan"])
                a["p"].append(r["mean_p"])
                a["cut"].append(r["n_cut"] / n)
                a["sp"].append(r["spread"])
        row = {"n": n}
        for pol, a in acc.items():
            row[pol] = {k: sum(v) / len(v) for k, v in a.items()}
        rows.append(row)
    return rows


def main():
    all_rows = {}
    for dist in DISTS:
        print(f"\n{'='*84}")
        print(f"  분포: {dist}")
        print(f"{'='*84}")
        print(f"{'N':>5s} {'전폭퍼짐':>9s} | {'uniform':>9s} | {'ours makespan':>13s} "
              f"{'평균폭':>7s} {'좁힌비율':>9s} | {'단축':>7s}")
        rows = sweep(dist)
        all_rows[dist] = rows
        for r in rows:
            u, o = r["uniform"], r["ours"]
            gain = (1 - o["ms"] / u["ms"]) * 100
            print(f"{r['n']:5d} {u['sp']:8.2f}배 | {u['ms']:8.1f}s | {o['ms']:12.1f}s "
                  f"{o['p']:6.2f} {o['cut']*100:8.0f}% | {gain:+6.1f}%")

    io.open(os.path.join(OUT, "s1_results.json"), "w", encoding="utf-8").write(
        json.dumps(all_rows, indent=1))

    print(f"\n{'='*84}")
    print("  판정 — 규모에서 무엇이 뒤집히나")
    print(f"{'='*84}")
    for dist, rows in all_rows.items():
        small = rows[0]["ours"]
        big = rows[-1]["ours"]
        print(f"\n  [{dist}]")
        print(f"    좁힌 비율 : N=4 에서 {small['cut']*100:3.0f}%  →  "
              f"N=1024 에서 {big['cut']*100:3.0f}%")
        print(f"    평균 폭   : {small['p']:.2f} → {big['p']:.2f}")
        u4 = (1 - rows[0]['ours']['ms'] / rows[0]['uniform']['ms']) * 100
        u1k = (1 - rows[-1]['ours']['ms'] / rows[-1]['uniform']['ms']) * 100
        print(f"    uniform 대비 단축: {u4:+.1f}% → {u1k:+.1f}%")
        if dist == "homogeneous" and big["cut"] > 0.1:
            print(f"    ★ 균질한데 N 이 커지자 {big['cut']*100:.0f}% 를 좁힌다 — "
                  f"**인식 조건이 규모에서 깨진다**")
        if big["p"] < small["p"] - 0.05:
            print(f"    ★ N 이 커질수록 더 깎는다 — 마감선이 극단값을 따라 내려간 것")


if __name__ == "__main__":
    main()
