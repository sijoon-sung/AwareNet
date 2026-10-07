#!/usr/bin/env bash
# 고정 2연결 비교군 (2026-10-07) — 32대 시나리오(run_scen32.sh)와 같은 조건에서 fixed2 팔만 돌린다. HPC 에서 실행.
#   목적: 기준(1연결) → AwareNet(2연결) 단축을 "연결 수 효과"와 "폭·경로 판단 효과"로 나눈다.
#     기준(uniform, 출구 A 한 가닥) → fixed2 = 연결 수를 늘린 효과
#     fixed2 → AwareNet(widthpath)    = 스케줄러 판단의 효과
#   fixed2 = 전폭 고정, 출구 A 는 균등과 같은 엣지, 출구 B 는 다른 VM 의 엣지에 고정, 조각은 접속 상한 비율(5:2)로 고정 분할, 이동 없음.
#
#   nohup bash scripts/exp/run_fixed2.sh > out/fixed2.log 2>&1 < /dev/null &
#   SCEN="traffic" SEEDS="1" bash scripts/exp/run_fixed2.sh        # 한 장면·한 시드만 (스모크·시간 부족 시)
#   ROUNDS_OVERRIDE=3 SCEN=normal SEEDS=1 bash scripts/exp/run_fixed2.sh   # 3라운드 스모크
# 결과: out/wp_scen32_<장면>_s<시드>_bothmp_fixed2.jsonl  (기존 uniform·widthpath 파일 옆에 놓인다)
# 집계: python scripts/analysis/fixed2_compare.py   (실행 끝에 자동으로 한 번 돈다)
# 소요: 장면·시드 하나에 약 30분 (24라운드 × 약 70초) → 기본 4장면 × 3시드 ≈ 6시간. 우선순위가 높은 것은 traffic.
set -u
cd "$(dirname "$0")/../.."
export PY=${PY:-$HOME/env/bin/python} REUSE_UNIFORM=0
SCEN=${SCEN:-"traffic normal slow vary"}
SEEDS=${SEEDS:-"1 2 3"}
VARY="8:49,9:42,10:35,11:28,12:21,13:14,14:21,15:28,16:35,17:42,18:49,19:56"   # run_scen32.sh 와 같은 일정
echo "### FIXED2 START $(date)  장면 [$SCEN] 시드 [$SEEDS]"
for SEED in $SEEDS; do
for sc in $SCEN; do
  cond=r32; [ "$sc" = "slow" ] && cond=r32_slow
  tag="scen32_${sc}_s${SEED}_bothmp"
  log="out/wp_${tag}_fixed2.jsonl"
  for p in $(pgrep -f "sfl/fed_(server|client)[.]py"); do kill $p 2>/dev/null; done; sleep 1
  bash sfl/net/real_rig.sh down > /dev/null 2>&1 || true            # 앞 실행이 남긴 터널·tc 정리
  echo "## $sc 시드 $SEED ($cond)  $(date +%H:%M:%S)"
  rm -f "$log"
  WPID=""
  if [ "$sc" = "traffic" ]; then
    bash scripts/exp/scenario_perturb.sh "$log" 0 14 56 8 20 > "out/${tag}_fixed2_perturb.log" 2>&1 &
    WPID=$!
  elif [ "$sc" = "vary" ]; then
    bash scripts/exp/scenario_perturb.sh "$log" 0 sched "$VARY" > "out/${tag}_fixed2_perturb.log" 2>&1 &
    WPID=$!
  fi
  COND=$cond ARM=bothmp SEED=$SEED TAG="${tag}_" ONLY=fixed2 timeout 7200 bash scripts/exp/run_real.sh > "out/${tag}_fixed2.log" 2>&1
  rc=$?
  bash sfl/net/real_rig.sh down > /dev/null 2>&1 || true
  [ -n "$WPID" ] && { kill $WPID 2>/dev/null; wait $WPID 2>/dev/null; sed 's/^/   /' "out/${tag}_fixed2_perturb.log"; }
  if [ $rc -ne 0 ] || grep -qE "Traceback|OSError" "out/${tag}_fixed2.log"; then
    echo "### $sc 시드 $SEED 실패 rc=$rc — 로그: out/${tag}_fixed2.log (다음 장면으로 계속)"; tail -5 "out/${tag}_fixed2.log" | sed 's/^/   /'
    continue
  fi
  grep -E "\[fixed2\]" "out/${tag}_fixed2.log" | head -1 | sed 's/^/   /'
  n=$(grep -c '"round"' "$log" || true); echo "   완료 라운드 $n"
done
done
"$PY" scripts/analysis/fixed2_compare.py || true
echo "### FIXED2 DONE $(date)"
