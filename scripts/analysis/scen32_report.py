# -*- coding: utf-8 -*-
"""32대 시나리오 결과 — 시나리오별 균등 vs 계획기의 라운드 시간축과 기기별 마지막 손잡이. 시각화용 JSON 도 남긴다.
    python scripts/analysis/scen32_report.py            # out/wp_scen32_*_{uniform,widthpath}.jsonl → 표 + out/scen32_viz.json"""
import glob, io, json, os, re, statistics as st, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
NAME = {"normal": "정상", "traffic": "트래픽 몰림 (8~20R 엣지 1 용량 1/4)", "slow": "연산 느림 (4대 속도 0.15)", "vary": "변동 (엣지 1 용량 8~20R 56→14→56 한 칸씩)", "slow_l18": "연산 느림, λ=18 (관대)", "slow_l280": "연산 느림, λ=280 (엄격)"}


def rows(f):
    return [json.loads(l) for l in io.open(f, encoding="utf-8") if '"round"' in l]


def main():
    viz = {}
    for sc in ("normal", "traffic", "slow", "vary", "slow_l18", "slow_l280"):
        fu, fw = f"out/wp_scen32_{sc}_s1_bothmp_uniform.jsonl", f"out/wp_scen32_{sc}_s1_bothmp_widthpath.jsonl"
        if not (os.path.exists(fu) and os.path.exists(fw)):
            continue
        U, W = rows(fu), rows(fw)
        D = None
        try:
            args = json.load(io.open(fw.replace(".jsonl", ".args.json"), encoding="utf-8")); D = args.get("deadline_s")
        except OSError:
            pass
        print(f"\n== {NAME[sc]}  (D={D}s)")
        print(f"   {'라운드':>4s} {'균등':>7s} {'계획':>7s} {'계획 폭합/N':>9s} {'이동':>4s}")
        prev = None
        for r in range(min(len(U), len(W))):
            u, w = U[r], W[r]
            plan = w.get("plan") or {}; paths = w.get("paths") or {}
            mv = sum(1 for k in paths if prev and prev.get(k) != paths.get(k)) if prev else 0
            prev = paths
            print(f"   {r:4d} {u['makespan']:7.2f} {w['makespan']:7.2f} {sum(plan.values())/max(1,len(plan)):9.2f} {mv:4d}")
        um = st.mean(x["makespan"] for x in U[4:]); wm = st.mean(x["makespan"] for x in W[4:])
        print(f"   평균(앞 4R 제외): 균등 {um:.2f}s  계획 {wm:.2f}s  ({100*(wm/um-1):+.0f}%)")
        if D:
            mu = sum(1 for x in U[4:] for v in x["per_client_detail"].values() if v.get("t_round", x["makespan"]) <= D)
            mw = sum(1 for x in W[4:] for v in x["per_client_detail"].values() if v.get("t_round", x["makespan"]) <= D)
            tot = sum(len(x["per_client_detail"]) for x in U[4:])
            print(f"   D 충족(기기·라운드): 균등 {100*mu/tot:.0f}%  계획 {100*mw/tot:.0f}%")
        last = W[-1]
        print(f"   계획 마지막 폭 {[last['plan'][k] for k in sorted(last['plan'], key=lambda s: int(s[1:]))]}")
        print(f"   계획 마지막 경로 {[last['paths'][k] for k in sorted(last['paths'], key=lambda s: int(s[1:]))]}")
        viz[sc] = {"D": D, "uniform": [{"r": x["round"], "ms": x["makespan"], "dev": {k: v.get("t_round") for k, v in x["per_client_detail"].items()}} for x in U],
                   "plan": [{"r": x["round"], "ms": x["makespan"], "w": x.get("plan"), "paths": x.get("paths"), "dev": {k: v.get("t_round") for k, v in x["per_client_detail"].items()}} for x in W]}
    json.dump(viz, io.open("out/scen32_viz.json", "w", encoding="utf-8"), ensure_ascii=False)
    print("\n→ out/scen32_viz.json")


if __name__ == "__main__":
    main()
