#!/usr/bin/env bash
# 32대 시나리오 실험 전 검증 (사용자 9/9: "돌리기 전에 먼저 검증") — 본실험 전에 세 가지를 실회선에서 확인한다.
#   ① 리그 자가 검사 A~E (내리기 접속 상한 포함)   ② 시나리오 경로 스모크: r32_smoke 4대 4R, 고른 시작·교란(2R↓ 3R↑)·고정 D
#   ③ 32대 실측 3R (균등): 기기별 연산·라운드 시간 → D 를 실측으로 정한다
#   bash scripts/exp/verify_scen32.sh > out/verify_scen32.log 2>&1
set -u
cd "$(dirname "$0")/../.."
PY=${PY:-$HOME/env/bin/python}
export BASE=12100 SRV_PORT=31900 DEV=ens160 REUSE_UNIFORM=0 UNIFORM_MP=${UNIFORM_MP:-0}
PARTS=${PARTS:-"1 2 3"}     # 돌릴 부분 (예: PARTS="2")
echo "### VERIFY START $(date)  parts=[$PARTS]"
if [[ " $PARTS " == *" 1 "* ]]; then
echo "== ① 자가 검사 (r8_rho1 목록 그대로) =="
bash sfl/net/real_rig.sh up 8 "50/20 50/20 50/20 50/20 50/20 50/20 50/20 50/20" "140 140 140 140" > out/verify_rig.log 2>&1 || { echo "리그 실패"; exit 1; }
timeout 300 "$PY" scripts/measurement/real_selftest.py --cond r8_rho1 --secs 5 2>&1 | grep -E "기대|합계|==" | cut -c1-120
bash sfl/net/real_rig.sh down > /dev/null 2>&1
fi
if [[ " $PARTS " == *" 2 "* ]]; then
echo "== ② 시나리오 경로 스모크 (r32_smoke, 4대 4R, 교란 2R↓/3R↑, 기준선 회선 하나, 계획 opt) =="
tag="scen32_smoke_s1_bothmp"; rm -f out/wp_${tag}_uniform.jsonl out/wp_${tag}_widthpath.jsonl
( bash scripts/exp/scenario_perturb.sh out/wp_${tag}_uniform.jsonl 0 14 56 2 3; bash scripts/exp/scenario_perturb.sh out/wp_${tag}_widthpath.jsonl 0 14 56 2 3 ) > out/${tag}_perturb.log 2>&1 &
WPID=$!
COND=r32_smoke ARM=bothmp SEED=1 TAG="${tag}_" timeout 1200 bash scripts/exp/run_real.sh > out/$tag.log 2>&1; rc=$?
bash sfl/net/real_rig.sh down > /dev/null 2>&1; wait $WPID 2>/dev/null
cat out/${tag}_perturb.log | sed 's/^/   /'
"$PY" - "$tag" <<'PYEOF'
import json, io, sys, os
tag = sys.argv[1]; ok = True
for arm in ("uniform", "widthpath"):
    f = f"out/wp_{tag}_{arm}.jsonl"
    if not os.path.exists(f): print(f"   {arm}: 로그 없음 FAIL"); ok = False; continue
    R = [json.loads(l) for l in io.open(f, encoding="utf-8") if '"round"' in l]
    p0 = R[0].get("paths", {}); rr = [p0.get(f"c{i}") for i in range(4)]
    exp = ["1", "2", "3", "4"] if arm == "uniform" else ["1+1", "2+2", "3+3", "4+4"]        # 균등 = 회선 하나(출구 1개), 계획 = 두 가닥
    print(f"   {arm}: {len(R)}R 완료, 라운드0 배정 {rr} (기대 {exp})  라운드 시간 {[round(r['makespan'],1) for r in R]}")
    ok &= len(R) == 4 and rr == exp
    ex = R[-1]["per_client_detail"]["c0"].get("exits") or []
    print(f"   {arm}: c0 출구 수 {len(ex)} (기대 {1 if arm == 'uniform' else 2})"); ok &= len(ex) == (1 if arm == "uniform" else 2)
    if arm == "widthpath":
        a = json.load(io.open(f.replace(".jsonl", ".args.json"), encoding="utf-8")); print(f"   widthpath args: deadline={a.get('deadline')} lam={a.get('lam')} init={a.get('init_sets')}")
        ok &= a.get("deadline") == "opt" and a.get("lam") == 70
pl = io.open(f"out/{tag}_perturb.log", encoding="utf-8").read()
n_ev = pl.count("[perturb] R"); print(f"   교란 사건 {n_ev}건 (기대 4 = 균등 2 + 계획 2)"); ok &= n_ev == 4
bad = [l for l in io.open(f"out/{tag}.log", encoding="utf-8") if "Traceback" in l or "Error" in l]
print(f"   오류 줄 {len(bad)}개"); ok &= not bad
print("   == 스모크", "통과" if ok else "실패", "==")
PYEOF
fi
if [[ " $PARTS " == *" 3 "* ]]; then
echo "== ③ 32대 실측 3R (균등만) — D 결정용 =="
tag="r32_meas_s1_bothmp"
COND=r32 ARM=bothmp SEED=1 ROUNDS_OVERRIDE=3 TAG="${tag}_" timeout 1500 bash scripts/exp/run_real.sh > out/$tag.log 2>&1; rc=$?
bash sfl/net/real_rig.sh down > /dev/null 2>&1
"$PY" - "$tag" <<'PYEOF'
import json, io, sys, statistics as st
tag = sys.argv[1]
for arm in ("uniform", "widthpath"):
    R = [json.loads(l) for l in io.open(f"out/wp_{tag}_{arm}.jsonl", encoding="utf-8") if '"round"' in l]
    if not R: print(f"   {arm}: 없음"); continue
    d = R[-1]["per_client_detail"]
    cpu = sorted(v["cli_fwd"] + v["cli_bwd"] for v in d.values()); tr = sorted(v.get("t_round", 0) for v in d.values()); xf = sorted(v["xfer"] for v in d.values())
    print(f"   {arm}: 라운드 {[round(r['makespan'],1) for r in R]}  기기 연산 p50 {st.median(cpu):.2f} p90 {cpu[int(0.9*len(cpu))-1]:.2f}s  전송 p50 {st.median(xf):.2f}s  기기 라운드 p50 {st.median(tr):.2f} p90 {tr[int(0.9*len(tr))-1]:.2f}s")
PYEOF
fi
echo "### VERIFY DONE $(date)"
