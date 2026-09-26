#!/usr/bin/env bash
# 32대 실측 3R (균등 + 계획) — 목표 D 결정용. 결과 기기별 연산·전송·라운드 p50/p90.
#   bash scripts/exp/measure_r32.sh > out/meas52.log 2>&1
set -u
cd "$(dirname "$0")/../.."
export BASE=12100 SRV_PORT=31900 DEV=ens160 REUSE_UNIFORM=0 PY=${PY:-$HOME/env/bin/python}
tag="r32_meas52_s1_bothmp"
echo "### MEAS 5/2 START $(date)"
COND=r32 ARM=bothmp SEED=1 ROUNDS_OVERRIDE=3 TAG="${tag}_" timeout 2400 bash scripts/exp/run_real.sh > out/$tag.log 2>&1; rc=$?
bash sfl/net/real_rig.sh down > /dev/null 2>&1
"$PY" - "$tag" <<'PYEOF'
import json, io, sys, statistics as st
tag = sys.argv[1]
for arm in ("uniform", "widthpath"):
    try: R = [json.loads(l) for l in io.open(f"out/wp_{tag}_{arm}.jsonl", encoding="utf-8") if '"round"' in l]
    except OSError: print(f"   {arm}: 없음"); continue
    d = R[-1]["per_client_detail"]
    cpu = sorted(v["cli_fwd"] + v["cli_bwd"] for v in d.values()); tr = sorted(v.get("t_round", 0) for v in d.values()); xf = sorted(v["xfer"] for v in d.values())
    print(f"   {arm}: 라운드 {[round(r['makespan'],1) for r in R]}  연산 p50 {st.median(cpu):.2f} p90 {cpu[int(0.9*len(cpu))-1]:.2f}s  전송 p50 {st.median(xf):.2f} (기대 4×8.4×8/7=38.4)  기기 라운드 p50 {st.median(tr):.2f} p90 {tr[int(0.9*len(tr))-1]:.2f}s")
PYEOF
echo "### MEAS 5/2 DONE $(date) rc=$rc"
