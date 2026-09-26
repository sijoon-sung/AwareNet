#!/usr/bin/env bash
# 9/10 후속 배치 — 순서대로: ① 새 인지(출구별 활동 구간)·망 변화 라운드 폭 유지 검증(몰림·변동 계획 팔, 시드 1) → ② 시드 2·3 (정상·몰림·연산 느림·변동, 두 팔) → ③ 정확도 축(8대 200R λ 스윕).
#   nohup bash scripts/exp/followup_batch.sh > out/followup.log 2>&1 < /dev/null &
# 로그: out/scen32_final_rerun5.log (①), out/scen32_s2.log, out/scen32_s3.log (②), out/acc_lambda.log (③)
set -u
cd "$(dirname "$0")/../.."
echo "### FOLLOWUP START $(date)"
while pgrep -f "run_scen32[.]sh|verify_demo[.]sh|run_real[.]sh|run_demo_real[.]py" > /dev/null; do sleep 30; done
mkdir -p out/scen32_final_try7 && for sc in traffic vary; do cp out/wp_scen32_${sc}_s1_bothmp_widthpath.* out/scen32_${sc}_s1_bothmp.log "out/scen32_final_try7/" 2>/dev/null; done
echo "## ① 검증 재실행 (traffic vary, seed 1, 계획 팔) $(date)"
SCEN="traffic vary" SEED=1 ONLY=widthpath bash scripts/exp/run_scen32.sh > out/scen32_final_rerun5.log 2>&1
grep -qE "실패|Traceback" out/scen32_final_rerun5.log && { echo "### ① 실패 — 멈춘다"; exit 1; }
for sd in 2 3; do
  echo "## ② 시드 $sd (normal traffic slow vary, 두 팔) $(date)"
  SCEN="normal traffic slow vary" SEED=$sd bash scripts/exp/run_scen32.sh > out/scen32_s${sd}.log 2>&1
  grep -qE "실패|Traceback" out/scen32_s${sd}.log && { echo "### ② 시드 $sd 실패 — 멈춘다"; exit 1; }
done
echo "## ③ 정확도 축 $(date)"
bash scripts/exp/run_acc_lambda.sh > out/acc_lambda.log 2>&1
echo "### FOLLOWUP DONE $(date)"
