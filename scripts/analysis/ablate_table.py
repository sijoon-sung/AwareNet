# -*- coding: utf-8 -*-
"""절제 실험 결과표 — out/wp_<조건>_s<시드>_<팔>_{uniform,widthpath}.jsonl 을 모아 조건×팔 표를 만든다.

    python scripts/analysis/ablate_table.py            # 전부
    python scripts/analysis/ablate_table.py c4_10050   # 조건 접두어로 거르기

열:
  makespan 이득   = 1 − 평균 라운드시간(widthpath) / 평균 라운드시간(uniform)
  단위 작업당 이득 = 1 − (makespan_wp ÷ 평균폭) / makespan_uniform    ← 폭을 깎아 번 시간을 학습량으로 되갚은 값
  평균폭          = 라운드별 기기 평균 폭의 평균
  Δacc            = 마지막 라운드 정확도 차(widthpath − uniform), 시드 평균. 3시드 ±5%p 는 잡음
  오염            = 팔이 자기 손잡이 밖을 쓴 흔적 (폭만인데 경로 이동 / 경로만인데 폭<1). .args.json 이 있으면 플래그로,
                    없으면(2판 이전) 로그 문구로 판정한다.
"""
import collections
import glob
import io
import json
import os
import re
import statistics as st
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "out")
PAT = re.compile(r"^(?P<cond>[a-z0-9_]+?)_s(?P<seed>\d+)_(?P<arm>path|width|joint|joint2|twostage|both|bothv1)$")
ARMS = ["path", "width", "joint", "joint2", "twostage", "both", "bothv1"]
ARM_KO = {"path": "경로만", "width": "폭만", "joint": "둘다(구판)", "joint2": "둘다(구판)", "twostage": "둘다(2단계)", "both": "둘다(개정판)", "bothv1": "둘다(구판v1)"}


def load(p):
    return [json.loads(l) for l in io.open(p, encoding="utf-8") if '"round"' in l]


def contaminated(tag, arm, W):
    """팔이 자기 손잡이 밖을 썼나. 반환 (오염 여부, 근거)."""
    argp = os.path.join(OUT, f"wp_{tag}_widthpath.args.json")
    if os.path.exists(argp):
        a = json.load(io.open(argp, encoding="utf-8"))
        if a.get("planner") == "two-stage-v1" and arm != "bothv1":
            return True, "args planner=two-stage-v1"
        if arm == "width" and int(a.get("max_moves", 1)) != 0:
            return True, f"args max_moves={a.get('max_moves')}"
        if arm == "path" and a.get("ladder") not in ("1.0", "1", "1.0,"):
            return True, f"args ladder={a.get('ladder')}"
    logp = os.path.join(OUT, f"{tag}.log")
    if os.path.exists(logp):
        txt = io.open(logp, encoding="utf-8", errors="replace").read()
        if arm == "width" and ("경로 이동" in txt or "이동 1명" in txt or re.search(r"이동 \d+명", txt)):
            return True, "로그에 경로 이동"
    if arm == "path" and any(v < 1.0 for r in W for v in r["plan"].values()):
        return True, "폭<1.0 관측"
    if arm == "width" and any(len(set(r.get("assign", {}).values())) > 1 for r in W if "assign" in r):
        return True, "배정 2종 관측"
    return False, ""


def main(prefix=""):
    agg = collections.defaultdict(list)
    for f in sorted(glob.glob(os.path.join(OUT, "wp_*_widthpath.jsonl"))):
        tag = os.path.basename(f)[3:-len("_widthpath.jsonl")]
        m = PAT.match(tag)
        if not m or not tag.startswith(prefix):
            continue
        uf = os.path.join(OUT, f"wp_{tag}_uniform.jsonl")
        if not os.path.exists(uf):
            continue
        W, U = load(f), load(uf)
        if not W or not U:
            continue
        msU = st.mean(r["makespan"] for r in U)
        msW = st.mean(r["makespan"] for r in W)
        # 총 비용 = 기기별 (연산+전송) 시간의 합 — 망 효과 갈래(경로 단계 목적 = 총합)의 주지표
        def tot(R): return st.mean(sum(d["cli_fwd"] + d["cli_bwd"] + d["xfer"] for d in r["per_client_detail"].values()) for r in R[1:] or R)
        cU, cW = tot(U), tot(W)
        avgw = st.mean(st.mean(r["plan"].values()) for r in W)
        bad, why = contaminated(tag, m["arm"], W)
        agg[(m["cond"], m["arm"])].append(dict(
            seed=m["seed"], gain=100 * (msU - msW) / msU, unit=100 * (1 - (msW / avgw) / msU), cost=100 * (cU - cW) / cU,
            avgw=avgw, dacc=(W[-1]["acc"] - U[-1]["acc"]) * 100, n=len(W[0]["plan"]), bad=bad, why=why))

    print(f"{'조건':12s} {'팔':10s} {'n':>2s} {'makespan':>9s} {'단위작업':>8s} {'총비용':>7s} {'평균폭':>6s} {'Δacc':>7s}  시드별 (오염은 ×)")
    for cond in sorted({c for c, _ in agg}):
        for arm in ARMS:
            v = agg.get((cond, arm))
            if not v:
                continue
            ok = [x for x in v if not x["bad"]]
            src = ok if ok else v
            g = st.mean(x["gain"] for x in src); u = st.mean(x["unit"] for x in src); co = st.mean(x["cost"] for x in src)
            w = st.mean(x["avgw"] for x in src); d = st.mean(x["dacc"] for x in src)
            seeds = " ".join(f"s{x['seed']}:{x['gain']:+.1f}{'×' if x['bad'] else ''}" for x in v)
            flag = "" if ok and len(ok) == len(v) else ("  [전부 오염]" if not ok else f"  [유효 {len(ok)}/{len(v)}]")
            print(f"{cond:12s} {ARM_KO[arm]:10s} {len(src):2d} {g:+8.1f}% {u:+7.1f}% {co:+6.1f}% {w:6.2f} {d:+6.1f}p  {seeds}{flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
