#!/bin/sh
# 교란 주입 — 2단 응답 실험(보호 없이 p만 / 보호만 / 둘 다)의 교란 쪽 버튼.
#   sudo sh perturb.sh <iface> netem <delay_ms> <rate_mbit>   # 링크 열화 (G0 스윕용)
#   sudo sh perturb.sh <iface> flood <server_ip> <sec>        # iperf3 배경 트래픽 (G2/G4용)
#   sudo sh perturb.sh <iface> clear
set -e
IF=${1:?iface}; MODE=${2:?netem|flood|clear}
case "$MODE" in
  netem)
    D=${3:?delay ms}; R=${4:?rate mbit}
    tc qdisc replace dev "$IF" root netem delay "${D}ms" rate "${R}mbit"
    echo "netem: $IF delay=${D}ms rate=${R}M" ;;
  flood)
    IPADDR=${3:?server ip}; SEC=${4:-60}
    iperf3 -c "$IPADDR" -t "$SEC" -P 4 &
    echo "flood: iperf3 -> $IPADDR ${SEC}s x4" ;;
  clear)
    tc qdisc del dev "$IF" root 2>/dev/null || true
    echo "clear: $IF" ;;
esac
