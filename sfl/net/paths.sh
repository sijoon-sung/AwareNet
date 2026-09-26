#!/bin/sh
# 경로 에뮬레이션 — lo 위에 '경로' HTB 클래스. hetero.sh(클라별 클래스)의 경로판.
#
#   클라 i 는 127.0.0.i 로 bind (hetero 와 동일). 배정 = 클라 필터를 경로 클래스로.
#   재배정은 필터 교체뿐이라 학습 중에도 즉시 적용된다 (연결 유지).
#
#   sudo sh paths.sh setup "100 20"        # 경로 1(100M)·2(20M) 생성
#   sudo sh paths.sh assign "1 1 1 2"      # 클라 1..N → 경로 번호
#   sudo sh paths.sh clear
set -e
MODE=${1:?setup|assign|clear}

if [ "$MODE" = "clear" ]; then
  tc qdisc del dev lo root 2>/dev/null || true
  echo cleared
  exit 0
fi

if [ "$MODE" = "setup" ]; then
  CAPS=${2:?caps}
  DELAY_MS=${DELAY_MS:-10}                 # 편도 지연 (ms) — 전 경로 공통 기본값
  DELAYS=${DELAYS:-}                       # 경로별 편도 지연 목록, 예 "2 10" (있으면 DELAY_MS 보다 우선)
  QLIM=${QLIM:-}                           # 큐 길이를 직접 줄 때만
  QUEUE_BDP_MULT=${QUEUE_BDP_MULT:-1}      # 버퍼 = mult × BDP(RTT). netem limit 은 지연 대기 패킷(R·d)도 세므로 그만큼 더한다 (2026-09-06)
  tc qdisc del dev lo root 2>/dev/null || true
  tc qdisc add dev lo root handle 1: htb default 99 r2q 100
  TOT=0; for c in $CAPS; do TOT=$((TOT + c)); done
  tc class add dev lo parent 1: classid 1:1 htb rate "${TOT}mbit" ceil "${TOT}mbit"
  p=1
  for c in $CAPS; do
    CID=$((20 + p))
    tc class add dev lo parent 1:1 classid 1:$CID htb rate "${c}mbit" ceil "${c}mbit"
    # 큐 길이는 대역×지연 곱에 맞춘다. 고정 2000패킷을 쓰면 느린 경로일수록 과다 완충이 되어
    # (10Mbps 에서 240배) 비교가 왜곡된다. 축약 실험에서는 버퍼도 함께 줄여야 한다 (SHRiNK 조건).
    D=$DELAY_MS
    if [ -n "$DELAYS" ]; then D=$(echo $DELAYS | cut -d" " -f$p); [ -z "$D" ] && D=$DELAY_MS; fi
    QP=$(( c * D / 12 + QUEUE_BDP_MULT * c * 2 * D / 12 ))   # 지연 대기(R·d) + 버퍼(mult × R·RTT), 1500B 패킷 수
    [ "$QP" -lt 20 ] && QP=20
    [ -n "$QLIM" ] && QP=$QLIM
    tc qdisc add dev lo parent 1:$CID handle $CID: netem delay ${D}ms limit $QP
    echo "  경로 $p: ${c}Mbps, 지연 ${D}ms, 큐 ${QP}패킷 (지연 대기 + ${QUEUE_BDP_MULT}×BDP)"
    p=$((p + 1))
  done
  tc class add dev lo parent 1:1 classid 1:99 htb rate "${TOT}mbit" ceil "${TOT}mbit"
  echo "paths: caps=[$CAPS] Mbps"
  exit 0
fi

# assign — 클라 i 의 src·dst 필터(prio i / i+100, hetero 와 동일 규약)를 경로로
ASSIGN=${2:?assign list}
i=1
for p in $ASSIGN; do
  CID=$((20 + p))
  tc filter del dev lo parent 1: prio $i 2>/dev/null || true
  tc filter del dev lo parent 1: prio $((i + 100)) 2>/dev/null || true
  tc filter add dev lo parent 1: protocol ip prio $i u32 \
     match ip dst 127.0.0.$i/32 flowid 1:$CID
  tc filter add dev lo parent 1: protocol ip prio $((i + 100)) u32 \
     match ip src 127.0.0.$i/32 flowid 1:$CID
  i=$((i + 1))
done
echo "assigned: [$ASSIGN]"
