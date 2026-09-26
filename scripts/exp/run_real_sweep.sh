#!/usr/bin/env bash
# 2층 실회선 실험: ρ 스윕 (HPC 클라 8대 → KOREN VM 엣지 4개 → HPC). 조건·팔은 원장.
#   nohup bash scripts/exp/run_real_sweep.sh > out/real_sweep.log 2>&1 < /dev/null &
# 순서: r8_rho05 / r8_rho1 / r8_rho2 × 팔 path3·mp × 시드 1,2  → r8_rho1m(즉시 내보내기) × 팔 × 시드.  실패하면 멈춘다.
set -u
cd "$(dirname "$0")/../.."
export PY=${PY:-$HOME/env/bin/python}
ROUNDS=${ROUNDS:-16}; SEEDS=${SEEDS:-"1 2"}
echo "### REAL-SWEEP START $(date)  rounds=$ROUNDS seeds=[$SEEDS]"
for cond in r8_rho05 r8_rho1 r8_rho2 r8_rho1m; do
  for s in $SEEDS; do for arm in path3 mp; do
    tag="${cond}_s${s}_${arm}"
    echo "## $tag  $(date +%H:%M:%S)"
    COND=$cond ARM=$arm SEED=$s ROUNDS_OVERRIDE=$ROUNDS TAG="${tag}_" timeout 1800 bash scripts/exp/run_real.sh > "out/$tag.log" 2>&1
    rc=$?
    bash sfl/net/real_rig.sh down >/dev/null 2>&1
    if [ $rc -ne 0 ] || grep -qE "Traceback|OSError|재조립 불일치|시간 초과" "out/$tag.log" out/${tag}_*_c*.log 2>/dev/null; then
      echo "### $tag 실패 rc=$rc — 멈춘다"; grep -lE "Traceback|OSError" out/${tag}*.log | head -3; exit 1
    fi
    grep -E "균등   |계획   " "out/$tag.log" | sed 's/^/   /'
  done; done
  SKIP=6 "$PY" scripts/analysis/net_effect_table.py $cond 2>/dev/null | sed 's/^/   /'
done
echo "### REAL-SWEEP DONE $(date)"
