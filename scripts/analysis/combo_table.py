# -*- coding: utf-8 -*-
"""3번(결합) 결과표 — 조건 × 팔: 균등 대비 라운드·총비용, 폭 합(정확도 대가의 대리), 기기 유형별 손잡이 대응.

    SKIP=10 python scripts/analysis/combo_table.py r8mix_rho1 r8mix_rho05 r8mix_rho2

유형은 원장의 speed_list/acc_list 에서 읽는다: 연산 낙오자 = 속도 < 1, 접속 병목 = 접속 합이 최소, 나머지 = 정상(혼잡 피해자).
손잡이 대응 판정(사전등록): 낙오자 → 폭 < 1, 접속 병목 → 분할(출구 2개)·폭 1.0, 정상 → 엣지 분산·폭 1.0."""
import glob, io, json, os, re, statistics as st, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts", "exp"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import cond  # noqa: E402
SKIP = int(os.environ.get("SKIP", 10))
ORDER = ["width3", "path3", "mp", "both3", "bothmp", "bothmpm"]
NAME = {"width3": "폭만", "path3": "엣지만", "mp": "엣지+분할", "both3": "폭+엣지", "bothmp": "폭+엣지+분할", "bothmpm": "전부+즉시"}


def rows(f):
    return [json.loads(l) for l in io.open(f, encoding="utf-8") if '"round"' in l]


def per_cost(r):
    return sum(v["xfer"] + v["cli_fwd"] + v["cli_bwd"] for v in r["per_client_detail"].values())


def deadline_of(c):
    r = cond.resolve(c)
    return float(r["deadline_s"]["v"]) if "deadline_s" in r else None


def types(c):
    r = cond.resolve(c); sp = r["speed_list"]["v"]; acc = r["acc_list"]["v"]
    tot = [sum(float(x) for x in str(a).split("/")) for a in acc]
    lo = min(tot)
    T = {}
    for i, (s, t) in enumerate(zip(sp, tot)):
        T[f"c{i}"] = "낙오자" if s < 1 else ("접속병목" if t == lo and lo < max(tot) else "정상")
    return T


def summarize(tag, T, D=None):
    U = rows(f"out/wp_{tag}_uniform.jsonl"); W = rows(f"out/wp_{tag}_widthpath.jsonl")
    Uk, Wk = U[SKIP:] or U, W[SKIP:] or W
    last = W[-1]; widths = last.get("plan") or {}; paths = last.get("paths") or {}
    n = len(widths) or 1
    moves = sum(1 for a, b in zip(W, W[1:]) if a.get("paths") != b.get("paths"))
    flips = sum(1 for a, b in zip(W, W[1:]) if a.get("plan") != b.get("plan"))
    # 손잡이 대응
    ok = {"낙오자": [], "접속병목": [], "정상": []}
    edges_normal = set()
    for k, ty in T.items():
        w = float(widths.get(k, 1.0)); p = str(paths.get(k, "1")); split = "+" in p and len(set(p.split("+"))) >= 1
        if ty == "낙오자":
            ok[ty].append(w < 1.0)
        elif ty == "접속병목":
            ok[ty].append(("+" in p) and w >= 1.0)
        else:
            ok[ty].append(w >= 1.0); edges_normal.update(p.split("+"))
    def meet(R):
        tot = [v.get("t_round", r["makespan"]) for r in R for v in r["per_client_detail"].values()]
        return (sum(1 for x in tot if x <= D) / max(1, len(tot))) if D else None
    def acc_tail(R, n=20):
        a = [r.get("acc") for r in R[-n:] if r.get("acc") is not None]
        return st.mean(a) if a else None
    return {"u_ms": st.mean(r["makespan"] for r in Uk), "w_ms": st.mean(r["makespan"] for r in Wk),
            "meet_u": meet(Uk), "meet_w": meet(Wk), "acc_tail_u": acc_tail(U), "acc_tail_w": acc_tail(W),
            "u_cost": st.mean(per_cost(r) for r in Uk), "w_cost": st.mean(per_cost(r) for r in Wk),
            "wsum": sum(float(v) for v in widths.values()) / n, "moves": moves, "flips": flips,
            "ok": {t: (sum(v), len(v)) for t, v in ok.items()}, "n_edges_normal": len(edges_normal),
            "widths": widths, "paths": paths, "acc_u": U[-1].get("acc"), "acc_w": W[-1].get("acc")}


def main():
    conds = sys.argv[1:] or ["r8mix_rho1"]
    for c in conds:
        T = types(c); D = deadline_of(c)
        print(f"\n== {c}  유형 {T}  목표 D={D}s  (앞 {SKIP}R 제외 평균, 균등 = 전원 엣지 1 전폭 m=1)")
        print(f"   {'팔':12s} {'n':>1s} {'균등':>6s} {'계획':>6s} {'Δ라운드':>7s} {'Δ총비용':>7s} {'폭합/N':>6s} {'D충족':>5s} {'이동':>4s} {'폭변경':>4s}  낙오자폭 접속병목분할 정상전폭 정상엣지수  정확도 마지막20R(균등→계획)")
        tags = sorted(set(re.sub(r"_(uniform|widthpath)\.jsonl$", "", os.path.basename(f))[3:] for f in glob.glob(f"out/wp_{c}_s*_*_widthpath.jsonl")))
        by = {}
        for t in tags:
            m = re.match(rf"{c}_s(\d+)_(\w+)$", t)
            if not m or m.group(1) == "9":
                continue
            try:
                by.setdefault(m.group(2), []).append(summarize(t, T, D))
            except (OSError, IndexError, ZeroDivisionError, KeyError, ValueError) as e:
                print(f"   ({t}: 건너뜀 — {type(e).__name__}: {e})")
        for arm in [a for a in ORDER if a in by] + [a for a in by if a not in ORDER]:
            L = by[arm]
            um, wm = st.mean(x["u_ms"] for x in L), st.mean(x["w_ms"] for x in L)
            uc, wc = st.mean(x["u_cost"] for x in L), st.mean(x["w_cost"] for x in L)
            f = lambda ty: f"{sum(x['ok'][ty][0] for x in L)}/{sum(x['ok'][ty][1] for x in L)}"
            accs = " ".join(f"{100*x['acc_tail_u']:.1f}→{100*x['acc_tail_w']:.1f}" for x in L if x["acc_tail_u"] is not None)
            mw = [x["meet_w"] for x in L if x["meet_w"] is not None]
            meet_s = f"{100*st.mean(mw):4.0f}%" if mw else "   - "
            print(f"   {NAME.get(arm, arm):12s} {len(L):1d} {um:6.2f} {wm:6.2f} {100*(wm/um-1):+6.1f}% {100*(wc/uc-1):+6.1f}% {st.mean(x['wsum'] for x in L):6.2f} {meet_s:>5s} {st.mean(x['moves'] for x in L):4.1f} {st.mean(x['flips'] for x in L):4.1f}   "
                  f"{f('낙오자'):>6s} {f('접속병목'):>10s} {f('정상'):>8s} {st.mean(x['n_edges_normal'] for x in L):8.1f}   {accs}")
        for arm in by:
            x = by[arm][0]
            print(f"      {NAME.get(arm, arm)} 시드1 마지막 폭 {[x['widths'].get(k) for k in sorted(x['widths'])]} 경로 {[x['paths'].get(k) for k in sorted(x['paths'])]}")
    print("(D충족 = 기기·라운드 중 라운드 시간 ≤ D 비율(계획 팔). 폭합/N = 마지막 라운드 폭 평균 — 1.0 이면 폭을 안 깎음. 낙오자폭 = 폭<1 인 낙오자 수/전체, 접속병목분할 = 출구 2개+전폭, 정상전폭 = 폭 1.0 인 정상 기기)")


if __name__ == "__main__":
    main()
