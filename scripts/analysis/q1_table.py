# -*- coding: utf-8 -*-
"""멘토링 질문 ① 표 — 비교 방식 3 (uniform / static / ours) × 조건 2 (고정 / 변동).

  사전 등록 판정:
    (가) 고정 환경 (--profile static): static ≈ ours — 되재도 개입 0회, 손해 없음
        → |makespan(static) − makespan(ours)| / makespan(ours) ≤ 10%(계측 불확도)
    (나) 변동 환경 (--profile step, R4 에 c3 80→16Mbps): ours > static
        → makespan(ours) < makespan(static) 이고 차이 > 10%
  개입 횟수 = 라운드 사이에 배정(plan)이 바뀐 횟수. static 은 정의상 1 이하, uniform 은 0.

    python scripts/analysis/q1_table.py            # out/g2_{static,step}_s1_results.json
    python scripts/analysis/q1_table.py --seed 2
"""
import argparse
import io
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "out")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

POLS = ["uniform", "static", "ours"]
PROFILES = [("static", "(가) 고정 환경"), ("step", "(나) 변동 환경 R4 c3 80→16M")]


def interventions(plans):
    """배정이 바뀐 라운드 수."""
    n = 0
    for a, b in zip(plans, plans[1:]):
        if any(a[k] != b[k] for k in a):
            n += 1
    return n


def rounds_of(profile, pol, seed):
    p = os.path.join(OUT, f"g2_{profile}_s{seed}_{pol}.jsonl")
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in io.open(p, encoding="utf-8") if '"round"' in l]


def aggregate(seeds):
    """여러 시드 평균 — 방식 × 조건별 평균(최소~최대). 판정은 평균으로."""
    import statistics as st
    for prof, title in PROFILES:
        per = {}                                  # pol → list of (ms, acc, iv, tta)
        used = []
        for s in seeds:
            fn = os.path.join(OUT, f"g2_{prof}_s{s}_results.json")
            if not os.path.exists(fn):
                continue
            used.append(s)
            for r in json.load(io.open(fn, encoding="utf-8")):
                per.setdefault(r["policy"], []).append(
                    (r["makespan_mean"], r["final_acc"] * 100,
                     interventions(r.get("plans", [])), r.get("tta")))
        print(f"\n{'=' * 78}\n  {title}   시드 {used} 평균 (최소~최대)\n{'=' * 78}")
        if not used:
            print("  (아직 없음)")
            continue
        print(f"  {'방식':8s} {'평균 makespan':>22s} {'최종 acc':>16s} {'개입':>9s} {'TTA 도달':>9s}")
        mean_ms = {}
        for pol in POLS:
            v = per.get(pol)
            if not v:
                print(f"  {pol:8s} {'—':>22s}")
                continue
            ms = [x[0] for x in v]; ac = [x[1] for x in v]; iv = [x[2] for x in v]
            hit = sum(1 for x in v if x[3])
            mean_ms[pol] = st.mean(ms)
            print(f"  {pol:8s} {st.mean(ms):8.2f}s ({min(ms):5.2f}~{max(ms):5.2f}) "
                  f"{st.mean(ac):6.1f}% ({min(ac):4.1f}~{max(ac):4.1f}) "
                  f"{st.mean(iv):5.1f}회   {hit}/{len(v)}")
        s_, o_, u_ = mean_ms.get("static"), mean_ms.get("ours"), mean_ms.get("uniform")
        if s_ and o_:
            gap = (s_ - o_) / o_
            print()
            if prof == "static":
                print(f"  판정 (가): static 대비 ours {gap * 100:+.1f}%  → "
                      f"{'PASS — static ≈ ours' if abs(gap) <= 0.10 else 'FAIL — 10% 밖'}")
            else:
                print(f"  판정 (나): ours 가 static 보다 {gap * 100:+.1f}% 빠름  → "
                      f"{'PASS — 되재는 것의 가치' if gap > 0.10 else 'FAIL — 차이 10% 이하'}")
            if u_:
                print(f"  참고: uniform 대비 ours {(1 - o_ / u_) * 100:+.1f}% 단축")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--seeds", default="", help="예: 1,2,3 — 시드 평균표 (단일 시드 표 대신)")
    a = ap.parse_args()
    if a.seeds:
        aggregate([int(x) for x in a.seeds.split(",")])
        return

    for prof, title in PROFILES:
        fn = os.path.join(OUT, f"g2_{prof}_s{a.seed}_results.json")
        print(f"\n{'=' * 78}\n  {title}   [{os.path.basename(fn)}]\n{'=' * 78}")
        if not os.path.exists(fn):
            print("  (아직 없음)")
            continue
        # ★ 파일 시각을 반드시 보인다 — 옛 결과를 새 결과로 읽은 사고가 이 저장소에 두 번 있었다
        import time
        age_min = (time.time() - os.path.getmtime(fn)) / 60
        print(f"  결과 파일 시각: {time.strftime('%m-%d %H:%M', time.localtime(os.path.getmtime(fn)))}"
              f"  ({age_min:.0f}분 전){'  ★ 오래됨 — 오늘 실행분인지 확인' if age_min > 180 else ''}")
        rows = {r["policy"]: r for r in json.load(io.open(fn, encoding="utf-8"))}
        print(f"  {'방식':8s} {'평균 makespan':>13s} {'최종 acc':>9s} {'TTA(s)':>8s} {'개입':>5s}  {'마지막 배정'}")
        for pol in POLS:
            r = rows.get(pol)
            if not r:
                print(f"  {pol:8s} {'—':>13s}")
                continue
            plans = r.get("plans", [])
            last = plans[-1] if plans else {}
            tta = f"{r['tta']:.0f}" if r.get("tta") else "미달"
            print(f"  {pol:8s} {r['makespan_mean']:12.2f}s {r['final_acc'] * 100:8.1f}% "
                  f"{tta:>8s} {interventions(plans):5d}  "
                  f"{[last[k] for k in sorted(last)] if last else ''}")

        u, s, o = rows.get("uniform"), rows.get("static"), rows.get("ours")
        if s and o:
            gap = (s["makespan_mean"] - o["makespan_mean"]) / o["makespan_mean"]
            print()
            if prof == "static":
                ok = abs(gap) <= 0.10
                print(f"  판정 (가): static 대비 ours {gap * 100:+.1f}%  → "
                      f"{'PASS — static ≈ ours (되재도 손해 없음)' if ok else 'FAIL — 10% 밖'}")
            else:
                ok = gap > 0.10
                print(f"  판정 (나): ours 가 static 보다 {gap * 100:+.1f}% 빠름  → "
                      f"{'PASS — 되재는 것의 가치가 변동에서 드러남' if ok else 'FAIL — 차이 10% 이하'}")
            if u:
                print(f"  참고: uniform 대비 ours {(1 - o['makespan_mean'] / u['makespan_mean']) * 100:+.1f}% 단축")
            # ★ 진짜 지표는 TTA — 라운드가 빨라도 목표 도달이 늦을 수 있다 (시드1 (가): ours 만 30% 미달).
            #   makespan 판정은 사전 등록대로 두고, TTA 를 나란히 보여 정확도 대가를 숨기지 않는다.
            tt = {p: rows[p].get("tta") for p in POLS if p in rows}
            reached = {p: t for p, t in tt.items() if t}
            if reached:
                best = min(reached, key=reached.get)
                print(f"  TTA(목표 정확도 도달): " + "  ".join(
                    f"{p} {f'{t:.0f}s' if t else '미달'}" for p, t in tt.items())
                    + f"  → 최속 {best}" + ("  ★ ours 미달 — 정확도 대가" if "ours" not in reached else ""))

        # 변동 환경은 교란 전후 라운드 시간을 보여준다
        if prof == "step":
            print("\n  라운드별 makespan (R2~R9, 교란 = R4):")
            print(f"  {'':8s}" + "".join(f"{'R' + str(i):>7s}" for i in range(2, 10)))
            for pol in POLS:
                rr = rounds_of(prof, pol, a.seed)
                if rr:
                    ms = {r["round"]: r["makespan"] for r in rr}
                    print(f"  {pol:8s}" + "".join(f"{ms.get(i, float('nan')):7.1f}" for i in range(2, 10)))


if __name__ == "__main__":
    main()
