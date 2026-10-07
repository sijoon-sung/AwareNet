#!/usr/bin/env bash
# 시나리오 교란 감시자 — 라운드 로그(jsonl)를 지켜보다 정해진 라운드에 엣지 e 의 용량을 바꾼다 (리그를 내리지 않고 tc 만).
#   계단:  bash scripts/exp/scenario_perturb.sh <jsonl> <edge 0..3> <낮출 용량> <원래 용량> [R1=8] [R2=20]
#   일정:  bash scripts/exp/scenario_perturb.sh <jsonl> <edge 0..3> sched "8:49,9:42,...,20:56"      # 라운드:용량 쌍 — 변동 장면
# run_scen32.sh 가 실행마다 백그라운드로 띄운다. 마지막 단계를 넘기거나 5분 넘게 로그가 안 움직이면 끝난다. DRY=1 이면 tc 대신 echo.
set -u
LOG=$1; E=$2
cd "$(dirname "$0")/../.."
if [ "${3:-}" = "sched" ]; then
  SCHED=$4
else
  LOW=$3; FULL=$4; R1=${5:-8}; R2=${6:-20}; SCHED="$R1:$LOW,$R2:$FULL"
fi
POLL=${POLL:-5}
apply() { if [ "${DRY:-0}" = "1" ]; then echo "[dry] edge $E -> $1"; else bash ${PERTURB_RIGSH:-sfl/net/real_rig.sh} edge $E $1 > /dev/null 2>&1; fi; }   # PERTURB_RIGSH=sfl/net/local_rig.sh 면 로컬 중계
n() { if [ -f "$LOG" ]; then grep -c '"round"' "$LOG" || true; else echo 0; fi; }   # grep -c 는 0건이면 0 을 찍고 exit 1 (|| echo 0 은 두 줄이 된다)
steps=$(echo "$SCHED" | tr ',' '\n' | sort -t: -k1,1n)
# 로그 파일이 생길 때까지는 기다리기만 한다(계획 팔은 리그 기동 + 사전 프로브가 10분 넘게 걸린다 — 9/9 03~06시 실행에서 5분 idle 에 감시자가 먼저 죽어
# 계획 팔에 교란이 안 걸렸다). 파일이 생긴 뒤 IDLE_MAX(기본 20분) 동안 라운드가 안 늘면 끝난다.
IDLE_MAX=${IDLE_MAX:-240}
while [ ! -f "$LOG" ]; do sleep $POLL; done
idle=0; last=-1
for st in $steps; do
  R=${st%%:*}; CAP=${st##*:}
  while true; do
    r=$(n)
    if [ "$r" -eq "$last" ]; then idle=$((idle+1)); else idle=0; last=$r; fi
    [ "$r" -ge "$R" ] && break
    [ $idle -ge $IDLE_MAX ] && { echo "[perturb] 로그 정지 — 종료 (R$r 에서 멈춤)"; exit 0; }
    sleep $POLL
  done
  apply "$CAP" && echo "[perturb] R$r 엣지 $((E+1)) 용량 → ${CAP}M  $(date +%H:%M:%S)"
done
