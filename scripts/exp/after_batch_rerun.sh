#!/usr/bin/env bash
# 다른 리그 작업(run_scen32 / verify_demo / run_real / run_demo_real)이 끝나기를 기다렸다가 지정한 장면의 계획 팔을 다시 돈다.
#   SCEN="traffic vary" ARCHIVE=out/scen32_final_try3 nohup bash scripts/exp/after_batch_rerun.sh > out/scen32_final_rerun.log 2>&1 < /dev/null &
set -u
cd "$(dirname "$0")/../.."
SCEN=${SCEN:-traffic}; ARCHIVE=${ARCHIVE:-out/scen32_prev_$(date +%m%d_%H%M)}
echo "### AFTER-BATCH WAIT $(date)  [$SCEN] → 이전 자료 $ARCHIVE"
while pgrep -f "run_scen32[.]sh|verify_demo[.]sh|run_real[.]sh|run_demo_real[.]py" > /dev/null; do sleep 30; done
sleep 10
mkdir -p "$ARCHIVE"
for sc in $SCEN; do cp out/wp_scen32_${sc}_s1_bothmp_widthpath.* out/scen32_${sc}_s1_bothmp.log out/scen32_${sc}_s1_bothmp_perturb.log "$ARCHIVE"/ 2>/dev/null; done
echo "### AFTER-BATCH RERUN $(date)"
SCEN="$SCEN" ONLY=widthpath bash scripts/exp/run_scen32.sh
echo "### AFTER-BATCH DONE $(date)"
