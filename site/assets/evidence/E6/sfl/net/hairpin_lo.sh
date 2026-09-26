#!/bin/sh
# 접속 회선 + 공유 경로 리그 (lo 위) — 2026-09-07 두 단계 판.
#
#   물리 모형: 기기 i 는 자기 접속 회선(상한 a_i, 하드, **한 가닥**)을 거쳐 공유 경로 p(용량 c_p) 로 간다.
#     · 접속 회선은 어느 경로를 골라도, 출구를 몇 개 열어도 **합쳐서 a_i** — 분할 전송해도 접속 회선은 안 늘어난다.
#     · 공유 경로는 붙은 기기(출구)들이 **균등하게** 나눈다 (TCP 흐름 공정성). 상한이 몫보다 작은 쪽은 자기 상한만.
#
#   왜 두 단계인가 (자가 검사 D 가 잡은 결함, 2026-09-07): 접속 상한을 (경로,기기) 클래스 ceil 로 두면
#   출구 2개(경로 1·2)를 연 기기는 접속 회선이 2배(95Mbps)가 된다. HTB 는 나무라서 "기기 합계 ≤ a_i" 와
#   "경로 합계 ≤ c_p" 를 한 나무에 못 넣는다 → 패킷이 두 번 지나는 두 qdisc 로 나눈다.
#
#   1단계  lo 송신(egress)  HTB 1:  접속 회선. 토큰 "a" 한 가닥 → 클래스 1:(100+i) 에 출구 A(127.0.0.i)·B(127.0.1.i) 둘 다.
#                            토큰 "aA/aB" 두 가닥(2026-09-07 결정) → 출구 A 는 1:(100+i) rate aA, 출구 B 는 1:(300+i) rate aB.
#                            + netem 접속 편도 지연 DELAY_MS.  (setup 때 고정, assign 과 무관)
#   2단계  lo 수신(ingress) → ifb0 로 넘겨 HTB 2:  경로 p 클래스 2:(20+p) rate=ceil=c_p
#                            └ (경로 p, 기기 i) 리프 2:(p·1000+i) rate=c_p/N(균등) ceil=min(a_i,c_p) + netem 경로 편도 지연·큐
#          assign 은 2단계 필터만 바꾼다: 출구 A → 경로 p, 출구 B → 경로 q.
#   큐(2단계 리프): limit = 지연 중 대기(R·d) + QUEUE_BDP_MULT × BDP(RTT).  1500B 패킷 수 = Mbit×ms/12.
#          (netem limit 은 지연 대기 패킷까지 세므로 limit=BDP 만 두면 실제 큐가 0 → TCP 가 주저앉는다)
#
#   sudo env DELAY_MS=10 PATH_DELAYS="5 5" QUEUE_BDP_MULT=1 sh hairpin_lo.sh setup "60 60" "50 50 10 50"
#   sudo sh hairpin_lo.sh assign "1 1+2 2 1"     # 기기 i 토큰: "p" = 출구 둘 다 경로 p / "p+q" = A→p, B→q (분할 전송)
#   sudo sh hairpin_lo.sh clear
#   sudo sh hairpin_lo.sh show                   # 2단계 클래스별 전송 바이트
set -e
MODE=${1:?setup|assign|clear|show}
IFB=${IFB:-ifb0}
if [ "$MODE" = "clear" ]; then
  tc qdisc del dev lo root 2>/dev/null || true; tc qdisc del dev lo ingress 2>/dev/null || true
  tc qdisc del dev $IFB root 2>/dev/null || true; echo cleared; exit 0
fi
if [ "$MODE" = "show" ]; then tc -s class show dev $IFB | awk '/class htb 2:[12][0-9][0-9][0-9] /{cls=$3} /Sent/{if(cls!=""){print cls, $2; cls=""}}'; exit 0; fi

if [ "$MODE" = "setup" ]; then
  CAPS=${2:?경로 용량들(Mbps)}; ACC=${3:?기기별 접속 회선 상한들(Mbps)}
  DELAY_MS=${DELAY_MS:-10}; PATH_DELAYS=${PATH_DELAYS:-}; QUEUE_BDP_MULT=${QUEUE_BDP_MULT:-1}; QLIM=${QLIM:-}
  N=0; for tok in $ACC; do N=$((N + 1)); done
  TOT=0; for c in $CAPS; do TOT=$((TOT + c)); done
  MAXPD=0; for d in $PATH_DELAYS; do [ "$d" -gt "$MAXPD" ] && MAXPD=$d; done
  modprobe ifb numifbs=1 2>/dev/null || true
  ip link show $IFB >/dev/null 2>&1 || ip link add $IFB type ifb
  ip link set $IFB up
  tc qdisc del dev lo root 2>/dev/null || true; tc qdisc del dev lo ingress 2>/dev/null || true
  tc qdisc del dev $IFB root 2>/dev/null || true

  # ── 1단계: 접속 회선 (lo egress)
  tc qdisc add dev lo root handle 1: htb default 99 r2q 200
  tc class add dev lo parent 1: classid 1:1 htb rate "$((TOT * 4))mbit" ceil "$((TOT * 4))mbit"
  tc class add dev lo parent 1:1 classid 1:99 htb rate "${TOT}mbit" ceil "$((TOT * 4))mbit"
  i=1
  DT=$((DELAY_MS + MAXPD))                                    # 접속 큐는 넉넉히 — 병목 큐는 2단계에
  for tok in $ACC; do
    aA=${tok%%/*}; aB=${tok##*/}                              # "50" → aA=aB=50 (한 가닥, 클래스 하나) / "50/20" → 두 가닥
    AID=$((100 + i)); BID=$((300 + i))
    tc class add dev lo parent 1: classid 1:$AID htb rate "${aA}mbit" ceil "${aA}mbit"
    QA=$(( aA * DELAY_MS / 12 + 2 * QUEUE_BDP_MULT * aA * 2 * DT / 12 )); [ "$QA" -lt 50 ] && QA=50
    tc qdisc add dev lo parent 1:$AID handle $AID: netem delay "${DELAY_MS}ms" limit $QA
    for pr in $i $((i + 100)) $((i + 200)) $((i + 300)); do tc filter del dev lo parent 1: prio $pr 2>/dev/null || true; done
    tc filter add dev lo parent 1: protocol ip prio $i         u32 match ip dst 127.0.0.$i/32 flowid 1:$AID
    tc filter add dev lo parent 1: protocol ip prio $((i+100)) u32 match ip src 127.0.0.$i/32 flowid 1:$AID
    if [ "$tok" != "${tok#*/}" ]; then                        # 두 가닥: 출구 B 는 자기 클래스
      tc class add dev lo parent 1: classid 1:$BID htb rate "${aB}mbit" ceil "${aB}mbit"
      QB=$(( aB * DELAY_MS / 12 + 2 * QUEUE_BDP_MULT * aB * 2 * DT / 12 )); [ "$QB" -lt 50 ] && QB=50
      tc qdisc add dev lo parent 1:$BID handle $BID: netem delay "${DELAY_MS}ms" limit $QB
      tc filter add dev lo parent 1: protocol ip prio $((i+200)) u32 match ip dst 127.0.1.$i/32 flowid 1:$BID
      tc filter add dev lo parent 1: protocol ip prio $((i+300)) u32 match ip src 127.0.1.$i/32 flowid 1:$BID
    else
      tc filter add dev lo parent 1: protocol ip prio $((i+200)) u32 match ip dst 127.0.1.$i/32 flowid 1:$AID
      tc filter add dev lo parent 1: protocol ip prio $((i+300)) u32 match ip src 127.0.1.$i/32 flowid 1:$AID
    fi
    i=$((i + 1))
  done

  # ── 2단계: 공유 경로 (lo ingress → ifb0)
  tc qdisc add dev lo handle ffff: ingress
  tc filter add dev lo parent ffff: protocol ip matchall action mirred egress redirect dev $IFB
  tc qdisc add dev $IFB root handle 2: htb default 99 r2q 200
  tc class add dev $IFB parent 2: classid 2:1 htb rate "$((TOT * 4))mbit" ceil "$((TOT * 4))mbit"
  tc class add dev $IFB parent 2:1 classid 2:99 htb rate "${TOT}mbit" ceil "$((TOT * 4))mbit"
  p=1
  for c in $CAPS; do
    PD=0; [ -n "$PATH_DELAYS" ] && PD=$(echo $PATH_DELAYS | cut -d" " -f$p); [ -z "$PD" ] && PD=0
    D=$((DELAY_MS + PD))                                     # 기기→경로 편도 지연 (BDP 계산용)
    SHARE=$((c / N)); [ "$SHARE" -lt 1 ] && SHARE=1          # 균등 몫 (보장 rate)
    tc class add dev $IFB parent 2: classid 2:$((20 + p)) htb rate "${c}mbit" ceil "${c}mbit"
    i=1
    for tok in $ACC; do
      aA=${tok%%/*}; aB=${tok##*/}; a=$aA; [ "$tok" != "${tok#*/}" ] && a=$((aA + aB))   # 두 가닥이면 두 출구가 한 리프를 지날 수 있으니 합
      CID=$((p * 1000 + i))
      CEIL=$a; [ "$CEIL" -gt "$c" ] && CEIL=$c
      RATE=$SHARE; [ "$RATE" -gt "$CEIL" ] && RATE=$CEIL
      tc class add dev $IFB parent 2:$((20 + p)) classid 2:$CID htb rate "${RATE}mbit" ceil "${CEIL}mbit"
      INFL=$(( CEIL * PD / 12 )); BUF=$(( QUEUE_BDP_MULT * CEIL * 2 * D / 12 ))
      QP=$(( INFL + BUF )); [ "$QP" -lt 20 ] && QP=20; [ -n "$QLIM" ] && QP=$QLIM
      tc qdisc add dev $IFB parent 2:$CID handle $CID: netem delay "${PD}ms" limit $QP
      i=$((i + 1))
    done
    echo "  경로 $p: 공유 ${c}Mbps, 편도 ${D}ms(접속 ${DELAY_MS}+경로 ${PD}), 기기 ${N}대 보장 ${SHARE}M 씩, 접속 상한 [$ACC]"
    p=$((p + 1))
  done
  echo "hairpin_lo(2단계): paths=[$CAPS] access=[$ACC](출구 합산) queue=inflight+${QUEUE_BDP_MULT}xBDP"
  exit 0
fi

# assign — 2단계(ifb0) 필터만 교체. 토큰 "p": 출구 A·B 둘 다 경로 p / "p+q": A→p, B→q
#   prio 규약: A dst i / src i+100, B dst i+200 / src i+300
ASSIGN=${2:?assign list}
i=1
for tok in $ASSIGN; do
  p=${tok%%+*}; q=${tok##*+}
  CA=$((p * 1000 + i)); CB=$((q * 1000 + i))
  for pr in $i $((i + 100)) $((i + 200)) $((i + 300)); do tc filter del dev $IFB parent 2: prio $pr 2>/dev/null || true; done
  tc filter add dev $IFB parent 2: protocol ip prio $i         u32 match ip dst 127.0.0.$i/32 flowid 2:$CA
  tc filter add dev $IFB parent 2: protocol ip prio $((i+100)) u32 match ip src 127.0.0.$i/32 flowid 2:$CA
  tc filter add dev $IFB parent 2: protocol ip prio $((i+200)) u32 match ip dst 127.0.1.$i/32 flowid 2:$CB
  tc filter add dev $IFB parent 2: protocol ip prio $((i+300)) u32 match ip src 127.0.1.$i/32 flowid 2:$CB
  i=$((i + 1))
done
echo "assigned: [$ASSIGN]"
