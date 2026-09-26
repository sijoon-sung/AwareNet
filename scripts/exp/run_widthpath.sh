#!/usr/bin/env bash
# 폭 × 경로 온라인 공동 판단 검증 — 경로 2개(100/20M) 리그, root 필요
#   조건 A: uniform (전원 빠른 경로, 전폭) — 기준
#   조건 B: widthpath (컨트롤러가 라운드마다 폭·경로 함께 판단, 사전 진단 포함)
# 판정: B 의 평균 라운드 시간 < A, 그리고 최종 배정이 공짜 유배 형태
#   (느린 경로 배정자는 폭 축소)면 온라인판 성립.
set -e
cd "$(dirname "$0")/../.."
PY=${PY:-/home/sijoon/sflenv/bin/python}
SUDO=${SUDO:-}                           # tc 에 sudo 가 필요하면 SUDO=sudo
# ── 조건 원장 (scripts/exp/conditions.json) — COND 를 주면 모든 조건값을 거기서 읽는다. 숫자를 여기 쓰지 않는다.
#    예: COND=h5 ARM=width SEED=1 bash scripts/exp/run_widthpath.sh
#    COND 가 없으면 아래 기본값(구판 호환)으로 돈다 — 새 실험은 반드시 COND 로.
if [ -n "${COND:-}" ]; then
  eval "$("$PY" scripts/exp/cond.py --env "$COND" ${ARM:+--arm "$ARM"} ${SEED:+--seed "$SEED"})"
  echo "  조건 원장: COND=$COND ARM=${ARM:-} SEED=${SEED:-} → RIG=$RIG CLIENTS=$CLIENTS CAPS=[$CAPS_SETUP] ACC=[$ACC_LIST] SPEED=[$SPEED_LIST]"
  [ -n "${ROUNDS_OVERRIDE:-}" ] && { ROUNDS=$ROUNDS_OVERRIDE; echo "  (스모크) ROUNDS 덮어씀 → $ROUNDS"; }
fi
SEED=${SEED:-1}
ROUNDS=${ROUNDS:-12}
CLIENTS=${CLIENTS:-4}
BATCHES=${BATCHES:-4}
CUT=${CUT:-2}
PORT=${PORT:-31900}
QUEUE_BDP_MULT=${QUEUE_BDP_MULT:-1}
export PYTHONPATH=sfl
PS=sfl/net/paths.sh
RIG=${RIG:-paths}                        # paths = lo 위 독립 상자(구판) / hairpin = 접속 회선 + 공유 경로 (hairpin_lo.sh)
[ "$RIG" = "hairpin" ] && PS=sfl/net/hairpin_lo.sh
ACC_DIST=${ACC_DIST:-}                   # hairpin: "uniform" 이면 클라별 접속 회선을 U(ACC_LO,ACC_HI) Mbps 에서 시드로 뽑는다
ACC_LO=${ACC_LO:-20}; ACC_HI=${ACC_HI:-50}; ACC_FIX=${ACC_FIX:-35}
CAPS_SETUP=${CAPS_SETUP:-"100 20"}      # 경로 용량 (Mbps) — 병목 세기 조절
CAPS_ARG=${CAPS_ARG:-"100,20"}
TAG=${TAG:-""}
EXTRA=${EXTRA:-""}
THREADS=${THREADS:-4}                    # 클라당 CPU 스레드 — 16대면 1 로
SLOW_N=${SLOW_N:-0}                      # 연산 낙오자 수 — 마지막 SLOW_N 대는 SLOW_THREADS 로 (이질성 주입)
SLOW_THREADS=${SLOW_THREADS:-1}
SPEED_DIST=${SPEED_DIST:-}               # "uniform" 이면 기기별 속도를 U(0.1,1.0) 에서 시드로 뽑는다 (Aergia). 비우면 전원 1.0
SPEED_LO=${SPEED_LO:-0.1}; SPEED_HI=${SPEED_HI:-1.0}
DELAYS=${DELAYS:-}                       # 경로별 편도 지연 "2 10" (paths.sh 로 전달)
DELAY_MS=${DELAY_MS:-10}
STATIC_ASSIGN=${STATIC_ASSIGN:-}         # 정적 분배 기준선: "1 1 1 1 2 2 2 2" 처럼 처음부터 고정 배정, 정책은 uniform
SPEED_LIST=${SPEED_LIST:-}               # 기기별 속도 고정 목록 "0.25 1 1 1" — 있으면 SPEED_DIST 보다 우선 (5판 병목 유형 혼합)
ACC_LIST=${ACC_LIST:-}                   # 기기별 접속 회선 고정 목록(Mbps) "50 50 20 50" — hairpin 에서 ACC_DIST 보다 우선

nth() { echo "$1" | tr -s ' ' '\n' | sed -n "$(( $2 + 1 ))p"; }   # 공백 목록의 i번째(0부터)

run_one() {  # $1 policy, $2 로그 이름, 이후 인자 = 서버 추가 옵션
  P="$1"; LOGN="$2"; shift 2
  if [ "$RIG" = "hairpin" ]; then
    ACC=""; i=0
    while [ $i -lt $CLIENTS ]; do
      if [ -n "$ACC_LIST" ]; then a=$(nth "$ACC_LIST" $i)
      elif [ "$ACC_DIST" = "uniform" ]; then a=$("$PY" -c "import random; print(int(round(random.Random($SEED*7919+$i).uniform($ACC_LO,$ACC_HI))))"); else a=$ACC_FIX; fi
      ACC="$ACC $a"; i=$((i+1))
    done
    echo "  접속 회선(Mbps):$ACC"
    $SUDO env DELAY_MS="$DELAY_MS" PATH_DELAYS="$DELAYS" QUEUE_BDP_MULT="$QUEUE_BDP_MULT" sh $PS setup "$CAPS_SETUP" "$ACC"
  else
    $SUDO env DELAYS="$DELAYS" DELAY_MS="$DELAY_MS" QUEUE_BDP_MULT="$QUEUE_BDP_MULT" sh $PS setup "$CAPS_SETUP"     # sudo 가 환경을 버리므로 env 로 넘긴다
  fi
  if [ -n "${ASSIGN_INIT:-}" ]; then A="$ASSIGN_INIT"; else A=""; i=0; while [ $i -lt $CLIENTS ]; do A="$A 1"; i=$((i+1)); done; fi
  $SUDO sh $PS assign "$A"
  "$PY" sfl/fed_server.py --clients $CLIENTS --rounds $ROUNDS --batches $BATCHES --seed $SEED --cut $CUT \
    --policy "$P" --port $PORT --device cuda --log "out/wp_$TAG$LOGN.jsonl" ${NORM_FLAG:-} "$@" &
  SRV=$!
  sleep 10
  i=0
  while [ $i -lt $CLIENTS ]; do          # 대수를 CLIENTS 로 맞춘다. 4대로 고정해 두면
    TH=$THREADS; [ $i -ge $((CLIENTS - SLOW_N)) ] && TH=$SLOW_THREADS
    SP=1.0
    if [ -n "$SPEED_LIST" ]; then
      SP=$(nth "$SPEED_LIST" $i)
    elif [ "$SPEED_DIST" = "uniform" ]; then
      SP=$("$PY" -c "import random; print(round(random.Random($SEED*1000+$i).uniform($SPEED_LO,$SPEED_HI),3))")
    fi
    BIND="127.0.0.$((i+1))"
    [ "${MP:-0}" = "1" ] && BIND="127.0.0.$((i+1)),127.0.1.$((i+1))"     # 분할 전송: 출구 2개 (hairpin assign "p+q" 규약)
    echo "  client c$i threads=$TH speed=$SP bind=$BIND"
    "$PY" sfl/fed_client.py --server 127.0.0.100:$PORT --bind "$BIND" \
      --id c$i --index $i --clients $CLIENTS --cut $CUT --threads $TH --speed $SP ${NORM_FLAG:-} &
    i=$((i+1))                           # 서버가 8대를 기다리다 영원히 멈춘다.
  done
  wait $SRV
}

echo "== A: uniform (전원 빠른 경로) =="
# 같은 조건·시드의 균등 기준선이 이미 완주해 있으면 다시 돌리지 않고 복사한다 — 균등 실행은 팔과 무관하게 같다
# (즉시 내보내기 --micro 도 계획 팔 EXTRA 에만 붙는다). 끄려면 REUSE_UNIFORM=0. 2026-09-08: h5acc 400R 에서 팔당 2.6h 절약.
REUSE=""
if [ "${REUSE_UNIFORM:-1}" = "1" ] && [ -n "${COND:-}" ]; then
  for f in out/wp_${COND}_s${SEED}_*_uniform.jsonl; do
    [ -f "$f" ] || continue
    [ "$f" = "out/wp_${TAG}uniform.jsonl" ] && continue
    n=$(grep -c '"round"' "$f" || true)
    want="${NORM_FLAG:-bn}"; have="bn"; grep -q '"norm": "gn"' "${f%.jsonl}.args.json" 2>/dev/null && have="--norm gn"   # 정규화가 같은 균등만 재사용
    [ "$want" = "$have" ] && [ "${n:-0}" -ge "$ROUNDS" ] && { REUSE="$f"; break; }
  done
fi
if [ -n "$REUSE" ]; then
  echo "  균등 기준선 재사용: $REUSE (${ROUNDS}R 완주) → out/wp_${TAG}uniform.jsonl"
  cp "$REUSE" "out/wp_${TAG}uniform.jsonl"
  b=${REUSE%.jsonl}
  for ext in args.json profile.json; do [ -f "$b.$ext" ] && cp "$b.$ext" "out/wp_${TAG}uniform.$ext"; done
else
  run_one uniform uniform
fi
if [ -n "$STATIC_ASSIGN" ]; then
  echo "== A2: static (처음부터 고정 분배 $STATIC_ASSIGN) =="
  ASSIGN_INIT="$STATIC_ASSIGN" run_one uniform static
fi
echo "== B: widthpath (온라인 공동 판단) =="
run_one widthpath widthpath --paths "$CAPS_ARG" --preflight --path-exec "$SUDO sh $PS assign '{assign}'" ${EXTRA:-}
$SUDO sh $PS clear
"$PY" - <<'PYEOF'
import json, io
import os
pre=os.environ.get("TAG","")
for tag in ("uniform", "widthpath"):
    rows=[json.loads(l) for l in io.open(f"out/wp_{pre}{tag}.jsonl",encoding="utf-8") if "round" in l]
    ms=sum(r["makespan"] for r in rows)/len(rows)
    print(f"{tag:10s} 평균 라운드 {ms:6.2f}s  마지막 폭 {list(rows[-1]['plan'].values())}")
PYEOF
