# -*- coding: utf-8 -*-
"""고정 2연결 비교군 집계 (2026-10-07) — 기준(1연결) / 고정 2연결 / AwareNet 의 평균 라운드 시간과 평균 폭.

    python scripts/analysis/fixed2_compare.py                 # out/ 의 scen32 파일 전부
    python scripts/analysis/fixed2_compare.py --skip 4        # 초기 제외 라운드 (보고서 기준 4)

집계 기준은 보고서 그림 5 와 같다: 시드마다 '초기 SKIP 라운드를 뺀 makespan 평균'을 구한 뒤, fixed2 가 있는 시드끼리만 평균한다.
분해:  기준 → AwareNet 단축(%) = 연결 수 효과(기준 → fixed2) + 판단 효과(fixed2 → AwareNet), 둘 다 기준 시간 대비 %.
결과는 화면과 out/fixed2_compare.csv 에 남는다.
"""
import argparse
import csv
import io
import json
import os
import statistics as st
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ARMS = ("uniform", "fixed2", "widthpath")
NAMES = {"uniform": "기준(1연결)", "fixed2": "고정 2연결", "widthpath": "AwareNet"}
LABEL = {"normal": "정상", "traffic": "트래픽 몰림", "slow": "연산 지연", "vary": "용량 변동"}


def rows(path):
    with io.open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if '"round"' in l]


def summary(path, skip):
    R = [r for r in rows(path) if r["round"] >= skip]
    if not R:
        return None
    w = [st.mean(r["plan"].values()) for r in R if r.get("plan")]
    return {"time": st.mean(r["makespan"] for r in R), "width": st.mean(w) if w else float("nan"),
            "acc": rows(path)[-1].get("acc", float("nan")), "rounds": len(R) + skip}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out")
    ap.add_argument("--skip", type=int, default=4)
    ap.add_argument("--min-rounds", type=int, default=24, help="이 라운드 수를 못 채운 실행은 뺀다")
    a = ap.parse_args()
    table = []
    for sc in ("normal", "traffic", "slow", "vary"):
        per_seed = {}
        for seed in range(1, 10):
            fs = {arm: os.path.join(a.out, f"wp_scen32_{sc}_s{seed}_bothmp_{arm}.jsonl") for arm in ARMS}
            if not all(os.path.exists(f) for f in fs.values()):
                continue
            s = {arm: summary(f, a.skip) for arm, f in fs.items()}
            if any(v is None or v["rounds"] < a.min_rounds for v in s.values()):
                print(f"  ({LABEL[sc]} 시드 {seed}: 라운드 부족 — 제외 "
                      f"{ {arm: (v['rounds'] if v else 0) for arm, v in s.items()} })")
                continue
            per_seed[seed] = s
        if not per_seed:
            continue
        m = {arm: {k: st.mean(per_seed[sd][arm][k] for sd in per_seed) for k in ("time", "width", "acc")} for arm in ARMS}
        u, f, w = m["uniform"]["time"], m["fixed2"]["time"], m["widthpath"]["time"]
        row = {"scenario": LABEL[sc], "seeds": ",".join(map(str, sorted(per_seed))),
               "uniform_s": u, "fixed2_s": f, "awarenet_s": w,
               "total_pct": (u - w) / u * 100, "conn_pct": (u - f) / u * 100, "sched_pct": (f - w) / u * 100,
               "sched_vs_fixed2_pct": (f - w) / f * 100,
               "width_fixed2": m["fixed2"]["width"], "width_awarenet": m["widthpath"]["width"]}
        table.append(row)
        print(f"== {LABEL[sc]} (시드 {row['seeds']})")
        for arm in ARMS:
            print(f"   {NAMES[arm]:10s} 평균 라운드 {m[arm]['time']:7.2f}s  평균 폭 {m[arm]['width']:.3f}  마지막 정확도 {m[arm]['acc']*100:5.1f}%")
        print(f"   기준 대비 전체 단축 {row['total_pct']:5.1f}% = 연결 수 효과 {row['conn_pct']:5.1f}%p + 판단 효과 {row['sched_pct']:5.1f}%p"
              f"   (고정 2연결 대비 AwareNet {row['sched_vs_fixed2_pct']:5.1f}% 단축)")
    if not table:
        print("fixed2 결과가 아직 없다 — scripts/exp/run_fixed2.sh 를 먼저 돌린다")
        return
    path = os.path.join(a.out, "fixed2_compare.csv")
    with io.open(path, "w", encoding="utf-8-sig", newline="") as fp:
        wr = csv.DictWriter(fp, fieldnames=list(table[0]))
        wr.writeheader()
        for r in table:
            wr.writerow({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()})
    print(f"→ {path}")


if __name__ == "__main__":
    main()
