# -*- coding: utf-8 -*-
"""32대 시나리오 시드 요약 (9/10 후속 §1): 장면 × 시드의 균등/계획 평균, 교란 중 안정 구간, 폭 축소 라운드, 이동, 되돌아감 → 표 + 시드 평균±범위.
    python scripts/analysis/scen32_seeds.py [시드 목록: 기본 1 2 3]"""
import io, json, os, statistics as st, sys
from collections import Counter
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def rows(f):
    return [json.loads(l) for l in io.open(f, encoding="utf-8") if '"round"' in l] if os.path.exists(f) else []


def edge1(r):
    return Counter(str(p).split("+")[0] for p in r["paths"].values())["1"]


def summ(sc, sd):
    U = rows(f"out/wp_scen32_{sc}_s{sd}_bothmp_uniform.jsonl"); W = rows(f"out/wp_scen32_{sc}_s{sd}_bothmp_widthpath.jsonl")
    if len(U) < 24 or len(W) < 24:
        return None
    mu = st.mean(r["makespan"] for r in U[4:]); mw = st.mean(r["makespan"] for r in W[4:])
    plat = st.mean(r["makespan"] for r in W[12:20]) if sc in ("traffic",) else None
    peak_u = max(r["makespan"] for r in U); peak_w = max(r["makespan"] for r in W)
    cutR = sum(1 for r in W if any(float(v) < 1 for v in r["plan"].values()))
    mv = sum(1 for a, b in zip(W, W[1:]) for k in b["paths"] if a["paths"][k] != b["paths"][k])
    back = sum(1 for a, b in zip(W, W[1:]) if 8 < b["round"] < 20 and edge1(b) > edge1(a)) if sc == "traffic" else None
    rec = st.mean(r["makespan"] for r in W[20:]) if sc == "vary" else None
    return dict(mu=mu, mw=mw, d=100 * (mw / mu - 1), plat=plat, peak_u=peak_u, peak_w=peak_w, cutR=cutR, mv=mv, back=back, rec=rec)


def main():
    seeds = [int(x) for x in sys.argv[1:]] or [1, 2, 3]
    NAME = {"normal": "정상", "traffic": "몰림", "slow": "연산 느림", "vary": "변동"}
    print(f"{'장면':6s} {'시드':>3s} {'균등':>6s} {'계획':>6s} {'차이':>5s} {'최고U':>5s} {'최고P':>5s} {'폭축소R':>6s} {'이동':>4s} {'비고':>10s}")
    agg = {}
    for sc in ("normal", "traffic", "slow", "vary"):
        for sd in seeds:
            s = summ(sc, sd)
            if not s:
                print(f"{NAME[sc]:6s} {sd:3d}  미완"); continue
            agg.setdefault(sc, []).append(s)
            note = f"안정 {s['plat']:.0f}s 되돌아감 {s['back']}" if sc == "traffic" else (f"회복 뒤 {s['rec']:.0f}s" if sc == "vary" else "")
            print(f"{NAME[sc]:6s} {sd:3d} {s['mu']:6.1f} {s['mw']:6.1f} {s['d']:+4.0f}% {s['peak_u']:5.0f} {s['peak_w']:5.0f} {s['cutR']:6d} {s['mv']:4d}  {note}")
    print("\n시드 평균 ± 범위 (앞 4R 제외 평균):")
    for sc, L in agg.items():
        mu = [s["mu"] for s in L]; mw = [s["mw"] for s in L]; d = [s["d"] for s in L]
        print(f"  {NAME[sc]:6s} 균등 {st.mean(mu):6.1f} ({min(mu):.1f}~{max(mu):.1f})  계획 {st.mean(mw):6.1f} ({min(mw):.1f}~{max(mw):.1f})  차이 {st.mean(d):+4.0f}% ({min(d):+.0f}~{max(d):+.0f})  n={len(L)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
