#!/usr/bin/env bash
# 시연(실증 플랫폼) 검증 — 실회선 위에서 라이브 화면을 켜고, 라운드가 흐르는지·교란 버튼이 실제 tc 를 바꾸는지·복구되는지·정리되는지를 자동으로 확인한다.
#   bash scripts/exp/verify_demo.sh [cond=demo8] > out/verify_demo.log 2>&1
# 통과 조건: 3라운드 안에 상태 API 가 라운드를 내놓고, 교란 뒤 tc 클래스가 바뀌고, 복구 뒤 원래 값으로, 종료 뒤 fed_* 프로세스가 없다.
set -u
cd "$(dirname "$0")/../.."
COND=${1:-demo8}; PY=${PY:-$HOME/env/bin/python}; HTTP=${HTTP:-8778}
export BASE=12100 DEV=ens160
get() { "$PY" - "$1" <<'PY'
import json, sys, urllib.request
s = json.load(urllib.request.urlopen(f"http://localhost:{sys.argv[1]}/state", timeout=5))
r = s["rows"][-1] if s["rows"] else None
print(json.dumps({"mode": s["mode"], "lam": s.get("lam"), "D": s.get("D"), "rows": len(s["rows"]), "acc_c4": s["acc"][4] if len(s["acc"]) > 4 else None,
                  "last": ({"r": r["r"], "ms": r["ms"], "wsum": r["wsum"], "c4": r["devs"].get("c4")} if r else None), "events": s["events"]}, ensure_ascii=False))
PY
}
post() { "$PY" - "$1" "$2" "$3" <<'PY'
import sys, urllib.request
req = urllib.request.Request(f"http://localhost:{sys.argv[1]}{sys.argv[2]}", data=sys.argv[3].encode(), headers={"Content-Type": "application/json"})
print(urllib.request.urlopen(req, timeout=5).read().decode())
PY
}
ok=1
echo "### VERIFY-DEMO START $(date)  cond=$COND"
pkill -f "run_demo_real[.]py" 2>/dev/null; sleep 1; rm -f out/demo_real.jsonl     # 옛 라운드 로그가 남아 있으면 "3라운드 도달"을 잘못 읽는다 (9/10 00:32 검증 실패 원인)
nohup "$PY" sfl/demo/run_demo_real.py --cond "$COND" --arm bothmp --rounds 40 --http $HTTP > out/verify_demo_server.log 2>&1 < /dev/null &
for i in $(seq 1 90); do sleep 10; n=$(grep -c '"round"' out/demo_real.jsonl 2>/dev/null || true); [ "${n:-0}" -ge 3 ] && break; done
for i in $(seq 1 30); do "$PY" -c "import urllib.request,sys; urllib.request.urlopen('http://localhost:$HTTP/state', timeout=3)" 2>/dev/null && break; sleep 5; done   # 화면 서버(리그 기동 뒤 뜬다)가 응답할 때까지
echo "-- 라운드 $n 개 ($(date +%H:%M:%S))"; [ "${n:-0}" -ge 3 ] || { echo "FAIL: 15분 안에 3라운드 못 옴"; ok=0; }
S1=$(get $HTTP); echo "-- 상태: $S1"
echo "-- 교란: c4 회선 절반"; post $HTTP /perturb '{"kind":"access","idx":4,"factor":0.5}'; sleep 10    # HPC tc 는 즉시, VM 내리기 자식 클래스는 ssh 로 몇 초
cls=$(sudo tc class show dev $DEV | grep -E "1:108 " | grep -oE "rate [0-9]+[MK]bit" | head -1); echo "-- tc 1:108 $cls"; echo "$cls" | grep -q "25Mbit" || { echo "FAIL: 교란이 tc 에 안 걸림"; ok=0; }
vmc=$(ssh -o BatchMode=yes -p 26022 ubuntu@116.89.187.190 'sudo tc class show dev ens3 | grep -E "3:1008 " | grep -oE "ceil [0-9]+[MK]bit"' 2>/dev/null | head -1); echo "-- VM1 내리기 자식 3:1008 $vmc"; echo "$vmc" | grep -q "25Mbit" || { echo "FAIL: 내리기 자식 클래스 안 바뀜"; ok=0; }
m0=$n; for i in $(seq 1 60); do sleep 10; m=$(grep -c '"round"' out/demo_real.jsonl 2>/dev/null || true); [ "${m:-0}" -ge $((m0+2)) ] && break; done
S2=$(get $HTTP); echo "-- 교란 뒤 2라운드: $S2"
echo "-- 복구"; post $HTTP /reset '{}'; sleep 10
cls=$(sudo tc class show dev $DEV | grep -E "1:108 " | grep -oE "rate [0-9]+[MK]bit" | head -1); echo "-- tc 1:108 $cls"; echo "$cls" | grep -q "50Mbit" || { echo "FAIL: 복구 안 됨"; ok=0; }
pkill -TERM -f "run_demo_real[.]py"; sleep 8
left=$(pgrep -f "sfl/fed_(server|client)[.]py|run_demo_real[.]py" | wc -l); echo "-- 종료 뒤 남은 프로세스 $left"; [ "$left" -eq 0 ] || { echo "FAIL: 정리 안 됨"; bash sfl/net/real_rig.sh down > /dev/null 2>&1; ok=0; }
grep -qE "Traceback" out/verify_demo_server.log && { echo "FAIL: 서버 Traceback"; ok=0; }
echo "### VERIFY-DEMO $([ $ok -eq 1 ] && echo 통과 || echo 실패) $(date)"
