#!/bin/sh
# 클라이언트별 회선 이질성 — lo 위에 클라 IP별 HTB 클래스.
#
#   클라 i 는 **자기 주소를 127.0.0.i 로 bind** 하고 서버(127.0.0.100)에 접속한다.
#   업로드(활성값)와 다운로드(그래디언트)가 같은 클래스에 들어가야 하므로
#   **src·dst 양쪽에 필터를 건다. 두 필터는 prio 를 갈라야 한다** (같은 prio 면 한 체인에
#   묶여 뒤엣것이 안 걸린다 — 실측으로 확인).
#
#   ※ 함정 둘, 둘 다 실측으로 잡았다:
#     ① 클라가 bind 없이 접속하면 소스가 전부 127.0.0.1 이 되어 다운로드가 한 클래스로 몰린다
#     ② 서버 주소가 어떤 클라 주소와 겹치면 그 클라의 dst 필터가 전 트래픽을 삼킨다
#        → 서버는 127.0.0.100 처럼 겹치지 않는 주소를 쓴다
#
#   sudo sh hetero.sh setup "20 40 60 80" 200
#   sudo sh hetero.sh clear
set -e
MODE=${1:?setup|clear}
if [ "$MODE" = "clear" ]; then
  tc qdisc del dev lo root 2>/dev/null || true
  echo cleared
  exit 0
fi
RATES=${2:?rates}
TOT=0
for r in $RATES; do TOT=$((TOT + r)); done
SHARED=${3:-$TOT}

tc qdisc del dev lo root 2>/dev/null || true
tc qdisc add dev lo root handle 1: htb default 99 r2q 100
tc class add dev lo parent 1: classid 1:1 htb rate "${SHARED}mbit" ceil "${SHARED}mbit"

i=1
for r in $RATES; do
  CID=$((10 + i))
  tc class add dev lo parent 1:1 classid 1:$CID htb rate "${r}mbit" ceil "${r}mbit"
  tc qdisc add dev lo parent 1:$CID handle $CID: netem delay 10ms limit 2000
  tc filter add dev lo parent 1: protocol ip prio $i u32 \
     match ip dst 127.0.0.$i/32 flowid 1:$CID
  tc filter add dev lo parent 1: protocol ip prio $((i + 100)) u32 \
     match ip src 127.0.0.$i/32 flowid 1:$CID
  i=$((i + 1))
done
tc class add dev lo parent 1:1 classid 1:99 htb rate "${SHARED}mbit" ceil "${SHARED}mbit"

N=$(tc filter show dev lo | grep -c flowid)
echo "hetero: rates=[$RATES] Mbps, shared=${SHARED}M, 필터 ${N}개 (클라당 2개여야 정상)"
