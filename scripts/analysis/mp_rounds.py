# -*- coding: utf-8 -*-
"""분할 전송 실험 라운드별 보기 — 경로 집합·전송 시간·총비용.  python scripts/analysis/mp_rounds.py h5m5_s1_path3 [...]"""
import io, json, statistics as st, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def rows(f):
    return [json.loads(l) for l in io.open(f, encoding="utf-8") if '"round"' in l]

def per(r, k):
    d = r["per_client_detail"][k]
    return d["xfer"], d["cli_fwd"] + d["cli_bwd"]

def cost(rs, ks):
    return st.mean(sum(sum(per(r, k)) for k in ks) for r in rs)

import re, os
def sets(r, ks, tag):
    ps = r.get("paths")
    if ps:
        return [str(ps.get(k, "?")) for k in ks]
    # 구 기록(2026-09-07 새벽 이전)은 경로를 jsonl 에 안 남겼다 — 실행 로그의 계획 줄에서 읽는다
    if not hasattr(sets, "_cache"):
        sets._cache = {}
    if tag not in sets._cache:
        lines = []
        try:
            for l in io.open(f"out/{tag}.log", encoding="utf-8", errors="replace"):
                m = re.search(r"\[widthpath[^\]]*\] (?:경로|배정) (\[.*?\])", l)
                if m:
                    lines.append(eval(m.group(1)))
        except OSError:
            pass
        sets._cache[tag] = lines
    L = sets._cache[tag]
    return [str(x) for x in L[r["round"]]] if r["round"] < len(L) else ["?"] * len(ks)

for tag in sys.argv[1:]:
    try:
        U = rows(f"out/wp_{tag}_uniform.jsonl")
    except OSError:
        U = []
    W = rows(f"out/wp_{tag}_widthpath.jsonl")
    ks = sorted(W[0]["per_client_detail"])
    print(f"== {tag}: 라운드 균등 {len(U)} / 계획 {len(W)}")
    if U:
        print(f"  균등   평균 라운드 {st.mean(r['makespan'] for r in U):6.2f}s  총비용/라운드 {cost(U, ks):6.1f}s  최종 정확도 {U[-1]['acc']*100:.1f}%")
    print(f"  계획   평균 라운드 {st.mean(r['makespan'] for r in W):6.2f}s  총비용/라운드 {cost(W, ks):6.1f}s  최종 정확도 {W[-1]['acc']*100:.1f}%")
    for r in W:
        print(f"   R{r['round']:2d} {r['makespan']:5.1f}s  경로 {sets(r, ks, tag)}  전송 {[round(per(r, k)[0], 1) for k in ks]}")
        for k in ks:                                             # 분할 전송 기기: 출구별 올린/내린 MB (가닥별 부하 분배)
            ex = r["per_client_detail"][k].get("exits")
            if ex:
                print(f"        {k}: " + "  ".join(f"출구{'AB'[i]} 올림 {e['up']/1e6:4.1f}MB 내림 {e['dn']/1e6:4.1f}MB" for i, e in enumerate(ex)))
