#!/usr/bin/env bash
# 실회선 리그 실험 드라이버 (HPC 에서 실행). 조건은 원장(conditions.json, rig=real)에서.
#   COND=r8_rho1 ARM=mp SEED=1 bash scripts/exp/run_real.sh          # 균등 + 계획 팔 각 1회
#   결과: out/wp_<TAG>{uniform,widthpath}.jsonl
# 흐름: real_rig up (터널 4개 + tc) → 서버(--edges) → 클라 N 대 (bind 없음, 출구는 서버가 준 엣지 종점) → down
set -e
cd "$(dirname "$0")/../.."
PY=${PY:-$HOME/env/bin/python}
[ -n "${COND:-}" ] || { echo "COND 필요"; exit 2; }
eval "$("$PY" scripts/exp/cond.py --env "$COND" ${ARM:+--arm "$ARM"} ${SEED:+--seed "$SEED"})"
[ "$RIG" = "real" ] || { echo "COND $COND 의 rig 가 real 이 아님"; exit 2; }
[ -n "${ROUNDS_OVERRIDE:-}" ] && ROUNDS=$ROUNDS_OVERRIDE
SEED=${SEED:-1}; TAG=${TAG:-"${COND}_s${SEED}_${ARM:-x}_"}
export PYTHONPATH=sfl
export BASE=${BASE:-12100} SRV_PORT=$PORT DEV=${DEV:-ens160} DELAY_MS=${DELAY_MS:-0}
RIGSH=sfl/net/real_rig.sh
EDGE_GROUPS=""; [ "${VMCLI:-0}" = "1" -o "${SAME_GROUPS:-0}" = "1" ] && EDGE_GROUPS="--edge-groups 3,4:0-$((CLIENTS/2-1));1,2:$((CLIENTS/2))-$((CLIENTS-1))"   # VM 클라는 다른 VM 의 엣지만 (같은 VM 은 lo 라 tc 가 안 걸림)

run_one() {  # $1 policy, $2 로그 이름, 이후 서버 추가 옵션
  P="$1"; LOGN="$2"; shift 2
  bash $RIGSH up "$CLIENTS" "$ACC_LIST" "$CAPS_SETUP" || { echo "리그 기동 실패"; exit 1; }
  EDGES=$(bash $RIGSH edges)
  "$PY" sfl/fed_server.py --clients $CLIENTS --rounds $ROUNDS --batches $BATCHES --seed $SEED --cut $CUT \
    --policy "$P" --port $PORT --device cuda --log "out/wp_$TAG$LOGN.jsonl" --edges "$EDGES" $EDGE_GROUPS "$@" &
  SRV=$!
  w=0; while ! ss -ltn 2>/dev/null | grep -q ":$PORT "; do   # 서버는 테스트셋을 먼저 읽고 포트를 연다(10초 넘길 수 있음) → 들을 때까지 기다린 뒤 클라 기동 (2026-09-12)
    kill -0 $SRV 2>/dev/null || { echo "서버가 포트를 열기 전에 죽음"; bash $RIGSH down >/dev/null 2>&1; exit 1; }
    sleep 1; w=$((w+1)); [ $w -ge 180 ] && { echo "서버 포트 $PORT 180초 내 미개방"; kill $SRV; bash $RIGSH down >/dev/null 2>&1; exit 1; }
  done; sleep 2
  i=0
  while [ $i -lt $CLIENTS ]; do
    TH=$THREADS; SP=$(echo "$SPEED_LIST" | tr -s ' ' '\n' | sed -n "$((i+1))p"); SP=${SP:-1.0}
    if [ "${VMCLI:-0}" = "1" ]; then                     # VM 클라 모드(2026-09-12): 앞 절반은 VM1, 뒤 절반은 VM2 에서 돈다. 제어 연결은 VM:BASE-100 터널로.
      # (…) 안에 &: 괄호 없이 쓰면 'cd && … && nohup … &' 전체가 서브셸로 뒤에 남아 ssh 가 클라 수명 내내 안 돌아온다 → 다음 클라가 안 뜸
      host=${VM1:-116.89.187.190}; [ $i -ge $((CLIENTS/2)) ] && host=${VM2:-116.89.187.189}
      ssh -o BatchMode=yes -o ConnectTimeout=10 -p ${VMPORT:-26022} ${VMUSER:-ubuntu}@$host "cd ~/awarenet && mkdir -p out && (setsid nohup env PYTHONPATH=sfl .venv/bin/python sfl/fed_client.py --server 127.0.0.1:$((BASE-100)) --id c$i --index $i --clients $CLIENTS --cut $CUT --threads $TH --speed $SP --device cpu > out/${TAG}${LOGN}_c$i.log 2>&1 < /dev/null &)" || echo "  클라 c$i 기동 실패 ($host)"
    else
      "$PY" sfl/fed_client.py --server 127.0.0.1:$PORT --id c$i --index $i --clients $CLIENTS --cut $CUT --threads $TH --speed $SP > "out/${TAG}${LOGN}_c$i.log" 2>&1 &
    fi
    i=$((i+1))
  done
  wait $SRV
  if [ "${VMCLI:-0}" = "1" ]; then
    for host in ${VM1:-116.89.187.190} ${VM2:-116.89.187.189}; do ssh -o BatchMode=yes -o ConnectTimeout=10 -p ${VMPORT:-26022} ${VMUSER:-ubuntu}@$host "pkill -f 'sfl/fed_client[.]py' 2>/dev/null; true"; done
  fi
  bash $RIGSH down >/dev/null 2>&1 || true
}

# ONLY=uniform|widthpath 면 그 팔만 돈다 (재실행용). UNIFORM_MP=0 이면 균등 팔은 출구 A 한 가닥(--multipath 없음) = 일반 분할학습의 회선 하나.
#   9/9 발견: 균등 팔이 두 가닥을 가중치 없이(먼저-한가한 순) 쓰면 느린 가닥(2M)에 39% 가 실려 5:2 계획(71:29)보다 2배 느렸다 — 우리 채널의 성질이지 "일반"이 아님.
ONLY=${ONLY:-}; UNIFORM_MP=${UNIFORM_MP:-1}
UMP="--multipath"; [ "$UNIFORM_MP" = "0" ] && UMP=""
# ONLY=fixed2 (2026-10-07): 고정 2연결 비교군만 돈다 — 전폭, 출구 A·B 를 서로 다른 엣지에 고정, 조각은 접속 상한 비율로 고정 분할.
#   비율은 FIXED_WEIGHTS(예 '5,2')를 주지 않으면 ACC_LIST 첫 기기의 'aA/aB' 에서 읽는다.
if [ "$ONLY" = "fixed2" ]; then
  FW=${FIXED_WEIGHTS:-$(echo "$ACC_LIST" | awk '{print $1}' | tr '/' ',')}
  echo "== $COND $ARM 시드 $SEED: 고정 2연결 (분할 $FW) =="
  run_one fixed2 fixed2 --multipath --fixed-weights "$FW" ${MICRO_FLAG:-} ${INIT_FLAG:-}
  exit 0
fi
if [ "$ONLY" != "widthpath" ]; then
echo "== $COND $ARM 시드 $SEED: 균등 (${UMP:-출구 A 한 가닥}) =="
# 같은 조건·시드의 균등 기준선이 완주해 있으면 복사한다 — 균등 실행은 팔과 무관하게 같다 (조건 micro 는 균등에도 붙으므로 같은 조건이면 같다). 끄려면 REUSE_UNIFORM=0
REUSE=""
if [ "${REUSE_UNIFORM:-1}" = "1" ]; then
  for f in out/wp_${COND}_s${SEED}_*_uniform.jsonl; do
    [ -f "$f" ] || continue
    [ "$f" = "out/wp_${TAG}uniform.jsonl" ] && continue
    n=$(grep -c '"round"' "$f" || true)
    [ "${n:-0}" -ge "$ROUNDS" ] && { REUSE="$f"; break; }
  done
fi
if [ -n "$REUSE" ]; then
  echo "  균등 기준선 재사용: $REUSE (${ROUNDS}R 완주) → out/wp_${TAG}uniform.jsonl"
  cp "$REUSE" "out/wp_${TAG}uniform.jsonl"; b=${REUSE%.jsonl}
  for ext in args.json profile.json; do [ -f "$b.$ext" ] && cp "$b.$ext" "out/wp_${TAG}uniform.$ext"; done
else
  run_one uniform uniform $UMP ${MICRO_FLAG:-} ${INIT_FLAG:-}
fi
fi
if [ "$ONLY" != "uniform" ]; then
echo "== $COND $ARM 시드 $SEED: 계획 =="
run_one widthpath widthpath --paths "$CAPS_ARG" --preflight ${INIT_FLAG:-} ${EXTRA:-}
fi
"$PY" scripts/analysis/mp_rounds.py "${TAG%_}" | grep -E "^==|균등|계획" || true
