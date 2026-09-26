#!/usr/bin/env bash
# 실회선 리그 — HPC(클라 에뮬 + 서버) ↔ KOREN VM(엣지). 설계: docs/04_설계기록/설계_실회선_리그.md
#
#   bash sfl/net/real_rig.sh up    N  "aA/aB ..."  "c1 c2 c3 c4"   # 터널 4개(엣지) + HPC egress tc(접속) + VM tc(엣지 용량)
#   bash sfl/net/real_rig.sh down                                    # 터널·tc 정리
#   bash sfl/net/real_rig.sh edges                                   # 서버 --edges 인자 출력
#
# 포트 규약: P(e, i, x) = BASE + e·500 + 2i + x   (e 엣지 0..3, i 클라, x 출구). 엣지 0·1 → VM1, 2·3 → VM2. BASE 12100 (12005~12007 은 iperf3)
# 터널: 엣지마다 ssh -R 하나(포트 2N 개 묶음) → VM 의 포트가 HPC 의 조각 포트(SRV_PORT+1)로 되돌아온다.
# tc:
#   HPC egress(DEV): 클라 i 출구 x 접속 상한 a_{i,x} — 목적지 포트 P(·,i,x) 4개 → 클래스 1:(100+2i+x). (+ netem DELAY_MS)
#   VM ingress(ifb0): 엣지 e 용량 c_e — 목적지 포트 [BASE+500e, +499]. (올리기)
#   VM egress: 엣지 e 용량(부모) + (기기, 출구)별 접속 상한(자식, ceil) — 전달된 클라 연결의 발신 포트 P(e,i,x) 로 구분. (내리기; 터널 자체는 안 건드림)
set -u
MODE=${1:-}
VM1=${VM1:-116.89.187.190}; VM2=${VM2:-116.89.187.189}; VMPORT=${VMPORT:-26022}; VMUSER=${VMUSER:-ubuntu}
BASE=${BASE:-12100}; SRV_PORT=${SRV_PORT:-31900}; DEV=${DEV:-ens160}; DELAY_MS=${DELAY_MS:-0}
CHUNK_PORT=$((SRV_PORT + 1))
vm_of() { [ "$1" -lt 2 ] && echo $VM1 || echo $VM2; }
edges_arg() { echo "1=$VM1:$BASE,2=$VM1:$((BASE+500)),3=$VM2:$((BASE+1000)),4=$VM2:$((BASE+1500))"; }

if [ "$MODE" = "edges" ]; then edges_arg; exit 0; fi

# ── 실행 중 교란 (시연용): 클라 i 접속 상한 바꾸기 / 엣지 e 용량 바꾸기 — 리그를 내리지 않고 tc 클래스만 바꾼다
#   bash sfl/net/real_rig.sh access i aA aB      # HPC egress 클래스 1:(100+2i+x)
#   bash sfl/net/real_rig.sh edge   e cap        # e = 0..3, VM 의 올리기(ifb0 2:21/22)·내리기(ens3 3:31/32) 클래스
if [ "$MODE" = "access" ]; then
  i=${2:?클라 번호}; aA=${3:?aA}; aB=${4:?aB}
  for x in 0 1; do a=$aA; [ $x = 1 ] && a=$aB; cid=$((100 + 2*i + x))
    sudo tc class change dev $DEV parent 1: classid 1:$cid htb rate "${a}mbit" ceil "${a}mbit" || exit 1     # 올리기 (HPC egress)
  done
  for vm in $VM1 $VM2; do                                                                                   # 내리기 (VM egress 자식 클래스, 엣지 2개씩)
    cmd=""
    for x in 0 1; do a=$aA; [ $x = 1 ] && a=$aB
      for k in 0 1; do cid=$((1000 + k*512 + 2*i + x)); cmd="$cmd tc class change dev ens3 parent 3:3$((k+1)) classid 3:$cid htb rate 1mbit ceil ${a}mbit quantum 1514;"; done
    done
    ssh -o BatchMode=yes -o ConnectTimeout=10 -p $VMPORT $VMUSER@$vm "sudo bash -c '$cmd'" || exit 1
  done
  echo "access c$i → $aA/$aB Mbps (올리기·내리기)"; exit 0
fi
if [ "$MODE" = "edge" ]; then
  e=${2:?엣지 번호 0..3}; c=${3:?용량 Mbps}; vm=$(vm_of $e)
  if [ $((e % 2)) = 0 ]; then ci=21; ce=31; else ci=22; ce=32; fi
  ssh -o BatchMode=yes -o ConnectTimeout=10 -p $VMPORT $VMUSER@$vm "sudo tc class change dev ifb0 parent 2: classid 2:$ci htb rate ${c}mbit ceil ${c}mbit && sudo tc class change dev ens3 parent 3: classid 3:$ce htb rate ${c}mbit ceil ${c}mbit" || exit 1
  echo "edge $((e+1)) → ${c} Mbps"; exit 0
fi

if [ "$MODE" = "down" ]; then
  pkill -f "[s]sh .*-R .*:localhost:$CHUNK_PORT" 2>/dev/null; sleep 0.5
  sudo tc qdisc del dev $DEV root 2>/dev/null || true
  for vm in $VM1 $VM2; do
    ssh -o BatchMode=yes -o ConnectTimeout=10 -p $VMPORT $VMUSER@$vm 'sudo tc qdisc del dev ens3 root 2>/dev/null; sudo tc qdisc del dev ens3 ingress 2>/dev/null; sudo tc qdisc del dev ifb0 root 2>/dev/null; echo "$(hostname) tc 정리"' 2>/dev/null
  done
  echo "real_rig: down"; exit 0
fi

if [ "$MODE" = "up" ]; then
  N=${2:?클라 수}; ACC=${3:?"접속 aA/aB 목록"}; CAPS=${4:?"엣지 용량 4개 (Mbps)"}
  set -- $CAPS; C=("$1" "$2" "$3" "$4")
  bash "$0" down >/dev/null 2>&1
  # ── 1) 역터널: 엣지마다 하나 (포트 2N 개). 열기 전후로 VM 쪽 :26022 연결을 비교해 이 터널의 (NAT 뒤) 발신 포트를 얻는다
  #      — HPC 는 NAT 뒤라 HPC 쪽 포트와 VM 이 보는 포트가 다르다. VM egress 의 내리기 엣지 용량 필터 열쇠.
  TP=()
  vm_conns() { ssh -o BatchMode=yes -o ConnectTimeout=10 -p $VMPORT $VMUSER@$1 "ss -tn state established '( sport = :$VMPORT )' | awk 'NR>1{print \$4}' | sed 's/.*://' | sort"; }
  for e in 0 1 2 3; do
    vm=$(vm_of $e); args=""
    for i in $(seq 0 $((N-1))); do for x in 0 1; do p=$((BASE + e*500 + 2*i + x)); args="$args -R 0.0.0.0:$p:localhost:$CHUNK_PORT"; done; done
    if [ "${VMCLI:-0}" = "1" ] && [ $((e % 2)) = 0 ]; then args="$args -R 0.0.0.0:$((BASE-100)):127.0.0.1:$SRV_PORT"; fi   # VM 클라의 제어 연결 (VM:BASE-100 → HPC 서버 포트), VM 마다 하나
    before=$(vm_conns $vm)
    ssh -o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -p $VMPORT -f -N $args $VMUSER@$vm \
      && echo "  엣지 $((e+1)) 터널: $vm 포트 $((BASE+e*500))..$((BASE+e*500+2*N-1)) → HPC:$CHUNK_PORT" || { echo "엣지 $((e+1)) 터널 실패"; exit 1; }
    sleep 1
    after=$(vm_conns $vm)
    TP[$e]=$(comm -13 <(echo "$before") <(echo "$after") | head -1)
    TP[$e]=${TP[$e]:-0}
  done
  echo "  터널의 VM 쪽 발신 포트(NAT 뒤): 엣지1 ${TP[0]} 엣지2 ${TP[1]} 엣지3 ${TP[2]} 엣지4 ${TP[3]}"
  # ── 2) HPC egress: 클라 i 출구 x 접속 상한 (목적지 포트로)
  TOT=0; i=0; for tok in $ACC; do aA=${tok%%/*}; aB=${tok##*/}; TOT=$((TOT + aA + aB)); i=$((i+1)); done
  sudo tc qdisc add dev $DEV root handle 1: htb default 99 r2q 200
  sudo tc class add dev $DEV parent 1: classid 1:1 htb rate 4gbit ceil 4gbit
  sudo tc class add dev $DEV parent 1:1 classid 1:99 htb rate 2gbit ceil 4gbit
  i=0
  for tok in $ACC; do
    aA=${tok%%/*}; aB=${tok##*/}
    for x in 0 1; do
      a=$aA; [ $x = 1 ] && a=$aB
      cid=$((100 + 2*i + x))
      sudo tc class add dev $DEV parent 1: classid 1:$cid htb rate "${a}mbit" ceil "${a}mbit"
      Q=$(( a * 40 / 12 + 2 * a * 2 * 40 / 12 )); [ $Q -lt 50 ] && Q=50            # 왕복 40ms 기준 BDP 큐
      if [ "$DELAY_MS" != "0" ]; then sudo tc qdisc add dev $DEV parent 1:$cid handle $cid: netem delay ${DELAY_MS}ms limit $Q
      else sudo tc qdisc add dev $DEV parent 1:$cid handle $cid: fq_codel; fi
      for e in 0 1 2 3; do
        p=$((BASE + e*500 + 2*i + x))
        sudo tc filter add dev $DEV parent 1: protocol ip prio $((1 + 2*i + x)) u32 match ip dport $p 0xffff flowid 1:$cid
      done
    done
    i=$((i+1))
  done
  echo "  HPC $DEV: 클라 ${N}대 접속 상한 [$ACC] (목적지 포트로 구분)"
  # ── 3) VM: 엣지 용량 — ingress(ifb0, 올리기, 목적지 포트 범위) + egress(내리기, 터널 연결의 HPC 쪽 포트)
  for vm in $VM1 $VM2; do
    if [ "$vm" = "$VM1" ]; then E0=0; CA=${C[0]}; CB=${C[1]}; TPA=${TP[0]}; TPB=${TP[1]}; else E0=2; CA=${C[2]}; CB=${C[3]}; TPA=${TP[2]}; TPB=${TP[3]}; fi
    OE0=$(( (E0 + 2) % 4 )); HALF=$((N / 2))                      # VM 클라 모드: 이 VM 의 클라가 쓰는 "다른 VM" 엣지의 시작 번호, 클라 반쪽
    ssh -o BatchMode=yes -o ConnectTimeout=10 -p $VMPORT $VMUSER@$vm "sudo bash -s" <<EOF
set -e
modprobe ifb numifbs=1 2>/dev/null || true; ip link show ifb0 >/dev/null 2>&1 || ip link add ifb0 type ifb; ip link set ifb0 up
tc qdisc del dev ens3 ingress 2>/dev/null || true; tc qdisc del dev ifb0 root 2>/dev/null || true; tc qdisc del dev ens3 root 2>/dev/null || true
# 올리기(HPC→VM): ingress → ifb0, 목적지 포트 범위로 엣지 클래스
tc qdisc add dev ens3 handle ffff: ingress
tc filter add dev ens3 parent ffff: protocol ip matchall action mirred egress redirect dev ifb0
tc qdisc add dev ifb0 root handle 2: htb default 99 r2q 200
tc class add dev ifb0 parent 2: classid 2:1 htb rate 4gbit ceil 4gbit
tc class add dev ifb0 parent 2:1 classid 2:99 htb rate 2gbit ceil 4gbit
tc class add dev ifb0 parent 2: classid 2:21 htb rate ${CA}mbit ceil ${CA}mbit
tc class add dev ifb0 parent 2: classid 2:22 htb rate ${CB}mbit ceil ${CB}mbit
tc qdisc add dev ifb0 parent 2:21 fq_codel; tc qdisc add dev ifb0 parent 2:22 fq_codel
for p in \$(seq $((BASE + E0*500)) $((BASE + E0*500 + 2*N - 1))); do tc filter add dev ifb0 parent 2: protocol ip prio 1 u32 match ip dport \$p 0xffff flowid 2:21; done
for p in \$(seq $((BASE + (E0+1)*500)) $((BASE + (E0+1)*500 + 2*N - 1))); do tc filter add dev ifb0 parent 2: protocol ip prio 2 u32 match ip dport \$p 0xffff flowid 2:22; done
# 내리기(VM→HPC): egress, 터널(sshd) 연결의 원격 포트로 엣지 구분
tc qdisc add dev ens3 root handle 3: htb default 99 r2q 200
tc class add dev ens3 parent 3: classid 3:1 htb rate 4gbit ceil 4gbit
tc class add dev ens3 parent 3:1 classid 3:99 htb rate 2gbit ceil 4gbit
tc class add dev ens3 parent 3: classid 3:31 htb rate ${CA}mbit ceil ${CA}mbit
tc class add dev ens3 parent 3: classid 3:32 htb rate ${CB}mbit ceil ${CB}mbit
tc qdisc add dev ens3 parent 3:31 fq_codel; tc qdisc add dev ens3 parent 3:32 fq_codel
# 내려받기 바이트는 터널이 아니라 **전달된 클라 연결**(VM:P(e,i,x) → HPC)로 나간다 → VM egress 는 발신 포트로 가른다.
# 엣지 클래스(3:31/3:32) 아래에 (기기 i, 출구 x) 자식 클래스: ceil = 그 출구의 접속 상한 → **내리기 접속 상한**(2026-09-09, 전엔 안 걸었음).
# 자식 id = 3:(1000 + (엣지-E0)*512 + 2i + x). rate 는 명목(1M, quantum 1514), 엣지 용량은 부모 ceil 이 나눈다.
i=0
for tok in $ACC; do
  aA=\${tok%%/*}; aB=\${tok##*/}
  for x in 0 1; do
    a=\$aA; [ \$x = 1 ] && a=\$aB
    for k in 0 1; do
      ee=$((E0))+\$k; ee=\$((ee)); cid=\$((1000 + k*512 + 2*i + x)); p=\$(($BASE + ee*500 + 2*i + x)); par=3:3\$((k+1))
      tc class add dev ens3 parent \$par classid 3:\$cid htb rate 1mbit ceil \${a}mbit quantum 1514
      tc qdisc add dev ens3 parent 3:\$cid fq_codel
      tc filter add dev ens3 parent 3: protocol ip prio 11 u32 match ip sport \$p 0xffff flowid 3:\$cid
    done
  done
  i=\$((i+1))
done
echo "  엣지 $((E0+1))·$((E0+2)) 내리기: 엣지 ${CA}M/${CB}M, 기기·출구별 접속 상한 자식 클래스 \$((i*4))개"
if [ "${VMCLI:-0}" = "1" ]; then
  # VM 클라 모드(2026-09-12): 이 VM 에 사는 클라(i \in 내 몫)가 **다른 VM** 의 엣지로 올리는 바이트에 접속 상한 — egress, 목적지 포트 P(e,i,x) (e = 다른 VM 의 엣지 2개).
  # 클라 VM 이 HPC 의 자리를 대신하므로 HPC egress 규칙과 같은 뜻. 내리기 상한은 위의 자식 클래스(듣는 VM 쪽)가 이미 건다.
  tc class add dev ens3 parent 3: classid 3:40 htb rate 4gbit ceil 4gbit
  i=0
  for tok in $ACC; do
    aA=\${tok%%/*}; aB=\${tok##*/}
    mine=0; if [ $E0 = 0 ] && [ \$i -lt $HALF ]; then mine=1; fi; if [ $E0 = 2 ] && [ \$i -ge $HALF ]; then mine=1; fi
    if [ \$mine = 1 ]; then
      for x in 0 1; do
        a=\$aA; [ \$x = 1 ] && a=\$aB
        cid=\$((3000 + 2*i + x))
        tc class add dev ens3 parent 3:40 classid 3:\$cid htb rate 1mbit ceil \${a}mbit quantum 1514
        tc qdisc add dev ens3 parent 3:\$cid fq_codel
        for k in 0 1; do p=\$(($BASE + ($OE0 + k)*500 + 2*i + x)); tc filter add dev ens3 parent 3: protocol ip prio 21 u32 match ip dport \$p 0xffff flowid 3:\$cid; done
      done
    fi
    i=\$((i+1))
  done
  echo "  \$(hostname): VM 클라 올리기 접속 상한 (다른 VM 엣지 $((OE0+1))·$((OE0+2)) 로, 목적지 포트)"
fi
echo "  \$(hostname): 엣지 $((E0+1))=${CA}M 엣지 $((E0+2))=${CB}M"
EOF
  done
  echo "real_rig: up  --edges $(edges_arg)"
  exit 0
fi
echo "usage: real_rig.sh up N \"aA/aB ...\" \"c1 c2 c3 c4\" | down | edges"; exit 2
