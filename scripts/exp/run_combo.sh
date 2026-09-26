#!/usr/bin/env bash
# 3번 결합 실험 (실회선 8대, 병목 유형 혼합, 고정 라운드 목표 D) — 같은 D 를 맞추는 데 망을 고치면 폭을 덜 깎는가 — 조건·팔·시드는 원장(conditions.json r8mix_*). 사전등록: docs/02_실험/실험_결합_3번_사전등록.md
#   nohup bash scripts/exp/run_combo.sh > out/combo.log 2>&1 < /dev/null &
# 앞선 실험(정확도 h5acc 등)이 돌고 있으면 끝날 때까지 기다린다. 게이트(규칙 시험) → 스모크 2R → 본 실행. 실패하면 멈춘다.
# 균등 기준선은 조건·시드당 한 번만 돌고(run_real.sh REUSE_UNIFORM) 나머지 팔은 복사해 쓴다.
set -u
cd "$(dirname "$0")/../.."
export PY=${PY:-$HOME/env/bin/python}
CONDS=${CONDS:-"r8mix_rho1 r8mix_rho05 r8mix_rho2"}
ARMS=${ARMS:-"width3 mp both3 bothmp bothmpm"}     # 엣지만(path3)은 2번 스윕에서 이미 봄
while pgrep -f "run_acc_cost.sh|ablate_5.sh|run_net_effect.sh|run_real_sweep.sh" > /dev/null; do sleep 120; done
echo "### COMBO START $(date)  conds=[$CONDS] arms=[$ARMS]"
echo "== 게이트: 규칙 시험 =="
for t in test_plan2 test_cond test_mp_act test_chunker test_fluidsim test_sense; do
  "$PY" tests/$t.py > /dev/null && echo "   $t 통과" || { echo "   $t FAIL — 실험을 걸지 않는다"; exit 1; }
done
run_tag() {  # cond seed arm rounds
  local cond=$1 s=$2 arm=$3 R=$4 tag="${1}_s${2}_${3}"
  echo "## $tag  $(date +%H:%M:%S)"
  COND=$cond ARM=$arm SEED=$s ROUNDS_OVERRIDE=$R TAG="${tag}_" timeout 7200 bash scripts/exp/run_real.sh > "out/$tag.log" 2>&1
  local rc=$?
  bash sfl/net/real_rig.sh down >/dev/null 2>&1
  if [ $rc -ne 0 ] || grep -qE "Traceback|OSError|재조립 불일치|시간 초과" "out/$tag.log" out/${tag}_*_c*.log 2>/dev/null; then
    echo "### $tag 실패 rc=$rc — 멈춘다"; grep -lE "Traceback|OSError" out/${tag}*.log | head -3; return 1
  fi
  grep -E "균등   |계획   |균등 기준선 재사용" "out/$tag.log" | sed 's/^/   /'
}
echo "== 스모크: 손잡이 전부 팔 2R (시드 9) =="
run_tag $(echo $CONDS | cut -d" " -f1) 9 bothmpm 2 || exit 1
for cond in $CONDS; do
  eval "$("$PY" scripts/exp/cond.py --env "$cond")"        # SEEDS ROUNDS
  for s in $SEEDS; do for arm in $ARMS; do
    run_tag $cond $s $arm $ROUNDS || exit 1
  done; done
  SKIP=10 "$PY" scripts/analysis/combo_table.py $cond 2>/dev/null | sed 's/^/   /'
done
echo "### COMBO DONE $(date)"
