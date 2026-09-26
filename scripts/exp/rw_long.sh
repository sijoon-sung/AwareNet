#!/usr/bin/env bash
# 폭별 정확도 대가 증명 — 조건은 원장 rw_long. 전원 같은 폭으로 수렴까지 돌려 (a) 같은 라운드 수에서 최종 정확도, (b) 목표 정확도 도달 시간을 낸다.
#   bash scripts/exp/rw_long.sh smoke                                   # 폭 1.0, 시드 1, 3라운드
#   nohup bash scripts/exp/rw_long.sh > out/rw_long.log 2>&1 < /dev/null &   # 본 실행 (V100, 약 3시간)
#   결과: out/rwlong_p{p}_s{seed}.jsonl, out/rwlong_summary.json → 표: python scripts/analysis/rw_table.py --prefix rwlong (있으면)
set -u
cd "$(dirname "$0")/../.."
export PY=${PY:-$HOME/env/bin/python} PYTHONPATH=sfl
eval "$("$PY" scripts/exp/cond.py --env rw_long)"
LRD=$("$PY" -c "import sys; sys.path.insert(0,'scripts/exp'); import cond; print(cond.resolve('rw_long')['lr_decay']['v'])")
PS=$(echo "$LADDER" | tr ' ' ','); SEEDS_CSV=$(echo "$SEEDS" | tr ' ' ',')
echo "### rw_long: rounds=$ROUNDS batches=$BATCHES ps=$PS seeds=$SEEDS_CSV lr_decay=$LRD threads=$THREADS  $(date)"
if [ "${1:-run}" = "smoke" ]; then
  "$PY" sfl/experiments/run_rw.py --ps 1.0 --seeds 1 --rounds 3 --batches "$BATCHES" --device cuda --threads "$THREADS" --lr-decay "$LRD" --prefix rwlong_smoke --force
  exit $?
fi
"$PY" sfl/experiments/run_rw.py --ps "$PS" --seeds "$SEEDS_CSV" --rounds "$ROUNDS" --batches "$BATCHES" --device cuda --threads "$THREADS" --lr-decay "$LRD" --prefix rwlong
echo "RW_LONG_DONE  $(date)"
