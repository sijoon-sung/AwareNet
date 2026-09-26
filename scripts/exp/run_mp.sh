#!/usr/bin/env bash
# 분할 전송 검증 (설계서 §8) — 출구 2개를 소스 주소별 tc 클래스로 재현. root 필요.
set -e
cd "$(dirname "$0")/../.."
PY=/home/sijoon/sflenv/bin/python
IP1=127.0.2.1; IP2=127.0.2.2

tc qdisc del dev lo root 2>/dev/null || true
tc qdisc add dev lo root handle 1: htb default 999
tc class add dev lo parent 1: classid 1:999 htb rate 10gbit
tc class add dev lo parent 1: classid 1:1 htb rate 40mbit ceil 40mbit
tc class add dev lo parent 1: classid 1:2 htb rate 20mbit ceil 20mbit
tc filter add dev lo protocol ip parent 1: prio 1 u32 match ip src $IP1/32 flowid 1:1
tc filter add dev lo protocol ip parent 1: prio 2 u32 match ip src $IP2/32 flowid 1:2

echo "== 조건 2: 출구 1개 (40M) — 기준 =="
"$PY" sfl/experiments/run_mp_test.py --size 35 --sources $IP1
echo "== 조건 1: 출구 2개 (40+20M) — 분할 =="
"$PY" sfl/experiments/run_mp_test.py --size 35 --sources $IP1,$IP2
echo "== 조건 3: 전송 중 급락 (출구1 40→5M) — 적응 =="
( sleep 2; tc class change dev lo parent 1: classid 1:1 htb rate 5mbit ceil 5mbit
  echo "  [급락 주입] 출구1 40→5M" ) &
"$PY" sfl/experiments/run_mp_test.py --size 35 --sources $IP1,$IP2

tc qdisc del dev lo root
echo "== 완료 =="
