# -*- coding: utf-8 -*-
"""
time_to_accuracy.py — 저장된 실행 기록에서 "목표 정확도 도달 시간"을 다시 계산한다

[왜 라운드 시간이 아니라 이 지표인가]
  라운드를 짧게 만드는 가장 쉬운 방법은 **빠른 노드만 부르는 것**이다. 그러면 라운드는
  짧아지지만 배우는 게 줄어 목표 정확도까지 라운드가 더 많이 필요해진다. 그래서 연합학습
  문헌의 주 지표는 라운드 수도 라운드 시간도 아닌 **목표 정확도까지의 누적 시간**이다
  (Oort, OSDI '21이 이 지표로 1.2~14.1배를 보고한다).

  이 스크립트는 실험을 다시 돌리지 않는다. 저장된 acc_hist(라운드별 정확도)와
  rt_hist(라운드별 전송 시간)만으로 임의의 목표에 대해 다시 계산한다 — 목표값을
  결과를 본 뒤에 고르는 것을 막기 위해, 목표 격자는 고정해 두고 전부 출력한다.

[도달 판정]
  정확도는 라운드마다 출렁이므로 "한 번 스친 것"을 도달로 치면 우연이 섞인다.
  **sustain회 연속으로 목표 이상**을 유지한 첫 시점을 도달로 본다(기본 2회).

사용:
  python scripts/analysis/time_to_accuracy.py out/v2core_sweep_results.json
  python scripts/analysis/time_to_accuracy.py out/v2core_results.json --sustain 2
"""
import argparse
import json
import sys

import numpy as np

TARGETS = [50, 60, 65, 70, 75, 78, 80, 82]


def tta(acc, rt, target, sustain):
    cum, run = np.cumsum(rt), 0
    for i, a in enumerate(acc):
        run = run + 1 if a >= target else 0
        if run >= sustain:
            return float(cum[i])
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--sustain", type=int, default=2)
    ap.add_argument("--ours", default="AwareNet-full")
    args = ap.parse_args()

    for path in args.files:
        d = json.load(open(path, encoding="utf-8"))
        runs = d.get("runs") or {}
        if not runs or "rt_hist" not in next(iter(runs.values()))[0]:
            print(f"[건너뜀] {path} — 라운드별 기록(rt_hist)이 없다. 최신 코드로 재실행 필요")
            continue

        p = d.get("params", {})
        print("=" * 96)
        print(f" {path}")
        print(f" {p.get('nodes')}노드 · {p.get('classes')}클래스(배타 {p.get('excl')}) · "
              f"총량 {p.get('total')}Mbps · {p.get('rounds')}라운드 · 시드 {p.get('seeds')}개 "
              f"· 도달 판정 {args.sustain}회 연속")
        print("=" * 96)

        hdr = f"{'비교군':<16}{'최고정확도':>11}"
        print(hdr + "".join(f"{'≥'+str(t)+'%':>10}" for t in TARGETS))
        print("-" * 96)

        table = {}
        for name, rs in runs.items():
            best = float(np.mean([max(r["acc_hist"]) for r in rs]))
            cells, row = [], {}
            for t in TARGETS:
                vals = [tta(r["acc_hist"], r["rt_hist"], t, args.sustain) for r in rs]
                hit = [v for v in vals if v is not None]
                if not hit:
                    cells.append("—"); row[t] = None
                else:
                    m = float(np.mean(hit))
                    # 도달 시드 수를 함께 적는다. 3개 중 1개만 닿은 평균은
                    # "빠르다"가 아니라 "운이 좋았다"일 수 있기 때문이다.
                    cells.append(f"{m:.0f}s" + ("" if len(hit) == len(vals) else f"^{len(hit)}"))
                    row[t] = (m, len(hit), len(vals))
            table[name] = row
            print(f"{name:<16}{best:>10.1f}%" + "".join(f"{c:>10}" for c in cells))

        print()
        print(" — = 50라운드 안에 그 정확도에 (연속) 도달하지 못함")
        print(" ^n = 3개 시드 중 n개만 도달. 값은 도달한 시드의 평균 (전 시드 도달은 표기 없음)")
        print()

        ours = table.get(args.ours)
        if not ours:
            continue
        print(f" [대조] {args.ours} vs 모든 기준선 중 최선")
        print(f"{'목표':>8}{'본 과제':>14}{'기준선 최선':>26}{'판정':>18}")
        print("-" * 96)
        for t in TARGETS:
            o = ours.get(t)
            rivals = [(nm, v[t]) for nm, v in table.items()
                      if nm != args.ours and v.get(t)]
            # 전 시드 도달을 우선하고, 그 다음 시간으로 최선을 고른다
            rivals.sort(key=lambda x: (-(x[1][1] / x[1][2]), x[1][0]))
            if not o and not rivals:
                print(f"{'≥'+str(t)+'%':>8}{'미달':>14}{'전부 미달':>26}{'아무도 도달 못함':>18}")
            elif o and not rivals:
                print(f"{'≥'+str(t)+'%':>8}{o[0]:>13.0f}s{'전부 미달':>26}"
                      f"{'★ 본 과제만 도달':>18}")
            elif not o and rivals:
                nm, v = rivals[0]
                print(f"{'≥'+str(t)+'%':>8}{'미달':>14}{nm+' '+format(v[0],'.0f')+'s':>26}{'기준선 승':>18}")
            else:
                nm, v = rivals[0]
                r = v[0] / o[0]
                verdict = f"{r:.2f}배 {'빠름' if r > 1 else '느림'}"
                print(f"{'≥'+str(t)+'%':>8}{o[0]:>13.0f}s{nm+' '+format(v[0],'.0f')+'s':>26}{verdict:>18}")
        print()


if __name__ == "__main__":
    sys.exit(main())
