# -*- coding: utf-8 -*-
"""망 효과 실험 결과표 — 조건 × 팔, 시드 평균. 균등(전원 경로 1) 대비 라운드·총비용, 이동 횟수, 출구 몫.

    python scripts/analysis/net_effect_table.py h5x h5xm h5x5          # out/wp_<cond>_s<seed>_<arm>_{uniform,widthpath}.jsonl
"""
import glob, io, json, os, re, statistics as st, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
SKIP = int(os.environ.get("SKIP", 2))                       # 수렴 전 라운드 제외 (8대 실회선은 SKIP=6)


def rows(f):
    return [json.loads(l) for l in io.open(f, encoding="utf-8") if '"round"' in l]


def per_cost(r):
    d = r["per_client_detail"]
    return sum(v["xfer"] + v["cli_fwd"] + v["cli_bwd"] for v in d.values())


def summarize(tag):
    U = rows(f"out/wp_{tag}_uniform.jsonl"); W = rows(f"out/wp_{tag}_widthpath.jsonl")
    Uk, Wk = U[SKIP:] or U, W[SKIP:] or W
    moves = sum(1 for a, b in zip(W, W[1:]) if a.get("paths") != b.get("paths"))
    ex_share = []
    for r in Wk:
        for v in r["per_client_detail"].values():
            e = v.get("exits")
            if e and len(e) >= 2 and (e[0]["up"] + e[1]["up"]) > 0:      # 출구 1개짜리(실회선 단일 팔)는 몫 계산에서 제외
                ex_share.append(e[0]["up"] / (e[0]["up"] + e[1]["up"]))
    n_split = sum(1 for k, v in W[-1].get("paths", {}).items() if "+" in str(v))
    return {"u_ms": st.mean(r["makespan"] for r in Uk), "w_ms": st.mean(r["makespan"] for r in Wk),
            "u_cost": st.mean(per_cost(r) for r in Uk), "w_cost": st.mean(per_cost(r) for r in Wk),
            "moves": moves, "exA": (st.mean(ex_share) if ex_share else None), "n_split": n_split,
            "acc_u": U[-1]["acc"], "acc_w": W[-1]["acc"], "final": W[-1].get("paths")}


def main():
    conds = sys.argv[1:] or ["h5x", "h5xm", "h5x5"]
    print(f"{'조건':6s} {'팔':6s} {'n':>2s} {'균등 라운드':>9s} {'계획 라운드':>9s} {'Δ':>7s} {'균등 총비용':>9s} {'계획 총비용':>9s} {'Δ':>7s} {'이동':>4s} {'분할대수':>6s} {'출구A몫':>6s}  최종 배정")
    for c in conds:
        tags = sorted(set(re.sub(r"_(uniform|widthpath)\.jsonl$", "", os.path.basename(f))[3:] for f in glob.glob(f"out/wp_{c}_s*_*_widthpath.jsonl")))
        by_arm = {}
        for t in tags:
            m = re.match(rf"{c}_s(\d+)_(\w+)$", t)
            if not m or m.group(1) == "9":
                continue                                    # 시드 9 = 스모크
            try:
                sm = summarize(t)
            except (OSError, IndexError, ZeroDivisionError, KeyError, ValueError) as e:
                print(f"   ({t}: 건너뜀 — {type(e).__name__}: {e})"); continue
            by_arm.setdefault(m.group(2), []).append(sm)
        for arm, L in sorted(by_arm.items()):
            um, wm = st.mean(x["u_ms"] for x in L), st.mean(x["w_ms"] for x in L)
            uc, wc = st.mean(x["u_cost"] for x in L), st.mean(x["w_cost"] for x in L)
            exA = [x["exA"] for x in L if x["exA"] is not None]
            print(f"{c:6s} {arm:6s} {len(L):2d} {um:9.2f} {wm:9.2f} {100*(wm/um-1):+6.1f}% {uc:9.1f} {wc:9.1f} {100*(wc/uc-1):+6.1f}% {st.mean(x['moves'] for x in L):4.1f} {st.mean(x['n_split'] for x in L):6.1f} {(f'{100*st.mean(exA):5.0f}%' if exA else '   -  ')}  {L[0]['final']}")
    print("(균등 = 전원 경로 1 전폭. 앞 2라운드 제외 평균. 시드 9 는 스모크라 제외)")


if __name__ == "__main__":
    main()
