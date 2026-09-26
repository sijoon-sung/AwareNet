#!/usr/bin/env bash
# 32대 시나리오 실험 (실회선, 사용자 9/9): "정상 / 트래픽 몰림 / 연산 느림 / 변동" 각각에서 균등(회선 하나) vs 계획기(폭+엣지+분할, D=84s) 의 라운드 시간축.
#   nohup bash scripts/exp/run_scen32.sh > out/scen32.log 2>&1 < /dev/null &
# 시나리오
#   normal  : r32, 고른 시작, 교란 없음                       — 계획기가 멀쩡한 판을 망치지 않는가
#   traffic : r32, 8R 에 엣지 1 용량 56→14M(1/4), 20R 복구       — 몰린 엣지의 8대가 다른 엣지로 옮겨 가는가 (scenario_perturb.sh)
#   slow    : r32_slow, 엣지마다 1대씩 4대 속도 0.15            — 느린 4대만 폭이 줄어 D 를 지키는가
#   vary    : r32, 엣지 1 용량을 8~14R 에 56→14 로 한 칸(7M)씩 내리고 14~20R 에 되올림 — 변동을 따라가는가 (사용자 9/9 제안)
# 각 시나리오는 run_real.sh 가 균등·계획 두 번 돈다 (균등 재사용 끔 — 교란이 같아야 하므로). 결과: out/wp_scen32_<시나리오>_s1_bothmp_{uniform,widthpath}.jsonl
set -u
cd "$(dirname "$0")/../.."
export PY=${PY:-$HOME/env/bin/python} REUSE_UNIFORM=0 UNIFORM_MP=${UNIFORM_MP:-0}   # 균등 = 회선 하나 (9/9 결정)
# ONLY=uniform|widthpath 를 주면 그 팔만 다시 돈다 (run_real.sh)
SCEN=${SCEN:-"normal traffic slow vary slow_l18 slow_l280"}
SEED=${SEED:-1}   # 시드 (9/10 후속: 2·3 반복)   # slow_l18/l280 = 연산 느림 장면, 계획 팔만 λ 바꿔서 (기준선은 slow 의 것 복사)
VARY="8:49,9:42,10:35,11:28,12:21,13:14,14:21,15:28,16:35,17:42,18:49,19:56"
echo "### SCEN32 START $(date)  [$SCEN] seed=$SEED"
for sc in $SCEN; do
  cond=r32; [ "$sc" = "slow" ] && cond=r32_slow; [ "$sc" = "slow_l18" ] && cond=r32_slow_l18; [ "$sc" = "slow_l280" ] && cond=r32_slow_l280
  tag="scen32_${sc}_s${SEED}_bothmp"
  ONLYARM=""; case "$sc" in slow_l*) ONLYARM=widthpath;; esac
  for p in $(pgrep -f "sfl/fed_(server|client)[.]py"); do kill $p 2>/dev/null; done; sleep 1      # 앞 장면의 잔재가 포트를 막지 않게
  echo "## $sc ($cond)  $(date +%H:%M:%S)"
  WPID=""
  if [ "$sc" = "traffic" ]; then
    [ "${ONLY:-}" != "widthpath" ] && rm -f out/wp_${tag}_uniform.jsonl; [ "${ONLY:-}" != "uniform" ] && rm -f out/wp_${tag}_widthpath.jsonl
    ( [ "${ONLY:-}" != "widthpath" ] && bash scripts/exp/scenario_perturb.sh out/wp_${tag}_uniform.jsonl 0 14 56 8 20; [ "${ONLY:-}" != "uniform" ] && bash scripts/exp/scenario_perturb.sh out/wp_${tag}_widthpath.jsonl 0 14 56 8 20 ) > out/${tag}_perturb.log 2>&1 &
    WPID=$!
  elif [ "$sc" = "vary" ]; then
    [ "${ONLY:-}" != "widthpath" ] && rm -f out/wp_${tag}_uniform.jsonl; [ "${ONLY:-}" != "uniform" ] && rm -f out/wp_${tag}_widthpath.jsonl
    ( [ "${ONLY:-}" != "widthpath" ] && bash scripts/exp/scenario_perturb.sh out/wp_${tag}_uniform.jsonl 0 sched "$VARY"; [ "${ONLY:-}" != "uniform" ] && bash scripts/exp/scenario_perturb.sh out/wp_${tag}_widthpath.jsonl 0 sched "$VARY" ) > out/${tag}_perturb.log 2>&1 &
    WPID=$!
  fi
  COND=$cond ARM=bothmp SEED=$SEED TAG="${tag}_" ONLY=${ONLY:-$ONLYARM} timeout 7200 bash scripts/exp/run_real.sh > "out/$tag.log" 2>&1
  rc=$?
  bash sfl/net/real_rig.sh down > /dev/null 2>&1
  [ -n "$WPID" ] && { wait $WPID 2>/dev/null; cat out/${tag}_perturb.log | sed 's/^/   /'; }
  if [ $rc -ne 0 ] || grep -qE "Traceback|OSError" "out/$tag.log"; then echo "### $sc 실패 rc=$rc — 멈춘다"; exit 1; fi
  case "$sc" in slow_l*) for ext in jsonl args.json profile.json; do [ -f out/wp_scen32_slow_s${SEED}_bothmp_uniform.$ext ] && cp out/wp_scen32_slow_s${SEED}_bothmp_uniform.$ext out/wp_${tag}_uniform.$ext; done;; esac   # 기준선은 slow 와 물리적으로 같은 조건
  grep -E "균등   |계획   " "out/$tag.log" | sed 's/^/   /'
done
"$PY" scripts/analysis/scen32_report.py 2>/dev/null || true
echo "### SCEN32 DONE $(date)"
