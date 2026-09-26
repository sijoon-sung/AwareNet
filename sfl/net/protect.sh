#!/bin/sh
# 지키기(보호) — 외부 트래픽이 밀려들 때 학습 트래픽의 몫을 HTB로 보장.
# 학습끼리 재분배가 아니라 '학습 밖'에서 지키는 것 — 망 개입 3관문 중 ③ 통과 노브.
#   sudo sh protect.sh <iface> <total_mbit> <learn_mbit> [server_port=29500]
# 예: sudo sh protect.sh eth0 100 60        # 총 100M 중 학습에 60M 보장(빌림은 상한까지)
set -e
IF=${1:?iface}; TOT=${2:?total mbit}; LRN=${3:?learn mbit}; PORT=${4:-29500}
tc qdisc del dev "$IF" root 2>/dev/null || true
tc qdisc add dev "$IF" root handle 1: htb default 20
tc class add dev "$IF" parent 1: classid 1:1 htb rate "${TOT}mbit" ceil "${TOT}mbit"
# 1:10 학습 클래스 — rate 보장, ceil 총량(남으면 빌려 씀 = work-conserving 유지)
tc class add dev "$IF" parent 1:1 classid 1:10 htb rate "${LRN}mbit" ceil "${TOT}mbit" prio 0
# 1:20 배경 클래스 — 남는 것만
tc class add dev "$IF" parent 1:1 classid 1:20 htb rate "$((TOT-LRN))mbit" ceil "${TOT}mbit" prio 1
tc filter add dev "$IF" parent 1: protocol ip u32 match ip dport "$PORT" 0xffff flowid 1:10
tc filter add dev "$IF" parent 1: protocol ip u32 match ip sport "$PORT" 0xffff flowid 1:10
echo "protect: $IF total=${TOT}M learn>=${LRN}M (port $PORT -> 1:10)"
