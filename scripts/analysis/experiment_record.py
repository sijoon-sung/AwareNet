# -*- coding: utf-8 -*-
"""실험 상세 데이터 기록 — out/wp_<조건>_s<시드>_<팔>_{uniform,widthpath}.jsonl 을 마크다운 표로 남긴다.

    python scripts/analysis/experiment_record.py h5c h5n h5 > docs/02_실험/데이터_기록_YYYY-MM-DD.md

시드·팔마다: 조건 출처 표(원장), 실행 인자(.args.json), 라운드별 makespan·정확도·폭·배정, 기기별 중앙(연산·전송·바이트),
총비용, 결정 사유(로그). "지금까지 무엇을 어떤 조건으로 돌렸고 숫자가 얼마였나"를 나중에 다시 세울 수 있게 하는 것이 목적.
"""
import ast
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
sys.path.insert(0, os.path.join(ROOT, "scripts", "exp"))
try:
    import cond
except Exception:
    cond = None


def load(p):
    return [json.loads(l) for l in io.open(p, encoding="utf-8") if '"round"' in l]


def assigns_from_log(tag):
    p = os.path.join(OUT, f"{tag}.log")
    if not os.path.exists(p):
        return [], []
    txt = io.open(p, encoding="utf-8", errors="replace").read()
    a = [ast.literal_eval(m.group(1)) for m in re.finditer(r"\] 배정 (\[[^\]]*\]) 폭", txt)]
    why = [m.group(1).strip() for m in re.finditer(r"폭 \[[^\]]*\] — (.*)", txt)]
    return a, why


def per_device(R):
    ks = sorted(R[0]["per_client_detail"])
    rows = []
    for k in ks:
        d = [r["per_client_detail"][k] for r in R]
        rows.append((k, st.median(x["cli_fwd"] + x["cli_bwd"] for x in d), st.median(x["xfer"] for x in d),
                     st.median(x["up_bytes"] + x["dn_bytes"] for x in d) / 1e6, st.median(r["plan"][k] for r in R)))
    return rows


def record(prefix):
    out = []
    files = sorted(glob.glob(os.path.join(OUT, f"wp_{prefix}_s*_*_widthpath.jsonl")))
    if not files:
        return [f"## {prefix} — 결과 없음\n"]
    out.append(f"## 조건 `{prefix}`\n")
    if cond:
        try:
            out.append(cond.table(prefix)); out.append("")
        except SystemExit:
            out.append(f"(원장에 `{prefix}` 없음 — 조건은 로그·args 로만 복원)\n")
    for f in files:
        tag = os.path.basename(f)[3:-len("_widthpath.jsonl")]
        uf = os.path.join(OUT, f"wp_{tag}_uniform.jsonl")
        W = load(f); U = load(uf) if os.path.exists(uf) else []
        if not W:
            continue
        out.append(f"### {tag}\n")
        ap = os.path.join(OUT, f"wp_{tag}_widthpath.args.json")
        if os.path.exists(ap):
            a = json.load(io.open(ap, encoding="utf-8"))
            keys = ("policy", "planner", "ladder", "max_moves", "paths", "access_caps", "alpha", "switch_cost", "rounds", "batches", "cut", "clients", "seed", "preflight")
            out.append("실행 인자: " + ", ".join(f"{k}={a.get(k)}" for k in keys if k in a) + "\n")
        else:
            out.append("실행 인자: (.args.json 없음 — 2026-09-06 이전 실행)\n")
        if U:
            msU = st.mean(r["makespan"] for r in U); msW = st.mean(r["makespan"] for r in W)
            def tot(R): return st.mean(sum(d["cli_fwd"] + d["cli_bwd"] + d["xfer"] for d in r["per_client_detail"].values()) for r in (R[1:] or R))
            out.append(f"요약: makespan 균등 {msU:.2f}s → {msW:.2f}s ({100*(msU-msW)/msU:+.1f}%) · 총비용 {tot(U):.1f}s → {tot(W):.1f}s ({100*(tot(U)-tot(W))/tot(U):+.1f}%) · "
                       f"정확도(마지막) 균등 {U[-1]['acc']*100:.1f}% / widthpath {W[-1]['acc']*100:.1f}% · 평균폭 {st.mean(st.mean(r['plan'].values()) for r in W):.2f}\n")
        # 라운드별
        a_list, why = assigns_from_log(tag)
        out.append("| R | makespan | acc | 폭 | 배정 | 결정 사유 |")
        out.append("|---|---|---|---|---|---|")
        for i, r in enumerate(W):
            w = [r["plan"][k] for k in sorted(r["plan"])]
            asg = a_list[i] if i < len(a_list) else "-"
            wy = why[i] if i < len(why) else "-"
            out.append(f"| {i} | {r['makespan']:.2f} | {r['acc']*100:.1f}% | {w} | {asg} | {wy} |")
        out.append("")
        out.append("기기별 중앙 (라운드 0 제외) — 연산 s / 전송 s / 왕복 MB / 폭:")
        out.append("")
        out.append("| 기기 | widthpath | 균등 |")
        out.append("|---|---|---|")
        pw = per_device(W[1:] or W); pu = per_device(U[1:] or U) if U else []
        for i, (k, c, x, b, w) in enumerate(pw):
            u = f"{pu[i][1]:.2f} / {pu[i][2]:.2f} / {pu[i][3]:.1f} / {pu[i][4]:.2f}" if pu else "-"
            out.append(f"| {k} | {c:.2f} / {x:.2f} / {b:.1f} / {w:.2f} | {u} |")
        out.append("")
    return out


def main(prefixes):
    print(f"# 실험 상세 데이터 기록 (생성: `scripts/analysis/experiment_record.py {' '.join(prefixes)}`)\n")
    print("> 표의 값은 `out/wp_*.jsonl` 에서 그대로 뽑았다. 조건 출처는 원장 `scripts/exp/conditions.json`. 결정 사유는 서버 로그의 컨트롤러 출력.\n")
    for p in prefixes:
        print("\n".join(record(p)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["h5c", "h5n", "h5"]))
