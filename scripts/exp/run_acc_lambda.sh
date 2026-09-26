#!/usr/bin/env bash
# 정확도 축 (9/10 후속 §4): 8대 혼합(r8mix_acc) 200R 에서 λ ∈ {18, 70, 280} 의 (평균 폭, 라운드, 마지막 50R 정확도). 균등 기준선은 시드마다 한 번.
#   nohup bash scripts/exp/run_acc_lambda.sh > out/acc_lambda.log 2>&1 < /dev/null &
# 결과: out/wp_r8mix_acc{,_l18,_l280}_s<시드>_bothmp_{uniform,widthpath}.jsonl → scripts/analysis/acc_lambda_table.py
set -u
cd "$(dirname "$0")/../.."
export PY=${PY:-$HOME/env/bin/python} UNIFORM_MP=0 REUSE_UNIFORM=1
SEEDS=${SEEDS:-"1 2"}
echo "### ACC-LAMBDA START $(date)  seeds=[$SEEDS]"
for sd in $SEEDS; do
  for p in $(pgrep -f "sfl/fed_(server|client)[.]py"); do kill $p 2>/dev/null; done; sleep 1
  echo "## seed $sd  균등 + λ=70  $(date +%H:%M:%S)"
  COND=r8mix_acc ARM=bothmp SEED=$sd timeout 10800 bash scripts/exp/run_real.sh > out/acc_lambda_s${sd}_l70.log 2>&1; rc=$?
  bash sfl/net/real_rig.sh down > /dev/null 2>&1
  if [ $rc -ne 0 ] || grep -qE "Traceback|OSError" out/acc_lambda_s${sd}_l70.log; then echo "### seed $sd λ70 실패 rc=$rc — 멈춘다"; exit 1; fi
  for lc in l18 l280; do
    for p in $(pgrep -f "sfl/fed_(server|client)[.]py"); do kill $p 2>/dev/null; done; sleep 1
    echo "## seed $sd  λ ${lc#l}  $(date +%H:%M:%S)"
    for ext in jsonl args.json profile.json; do [ -f out/wp_r8mix_acc_s${sd}_bothmp_uniform.$ext ] && cp out/wp_r8mix_acc_s${sd}_bothmp_uniform.$ext out/wp_r8mix_acc_${lc}_s${sd}_bothmp_uniform.$ext; done   # 기준선은 물리적으로 같은 조건
    COND=r8mix_acc_$lc ARM=bothmp SEED=$sd ONLY=widthpath timeout 10800 bash scripts/exp/run_real.sh > out/acc_lambda_s${sd}_${lc}.log 2>&1; rc=$?
    bash sfl/net/real_rig.sh down > /dev/null 2>&1
    if [ $rc -ne 0 ] || grep -qE "Traceback|OSError" out/acc_lambda_s${sd}_${lc}.log; then echo "### seed $sd $lc 실패 rc=$rc — 멈춘다"; exit 1; fi
  done
done
"$PY" scripts/analysis/acc_lambda_table.py 2>/dev/null || true
echo "### ACC-LAMBDA DONE $(date)"
