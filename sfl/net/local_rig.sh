#!/usr/bin/env bash
# 로컬 리그 — real_rig.sh 와 같은 사용법으로, KOREN VM 엣지 대신 같은 장비의 local_relay.py 를 띄운다 (2026-10-07).
#   bash sfl/net/local_rig.sh up    N  "aA/aB ..."  "c1 c2 c3 c4"    # 중계 기동 (접속 상한·엣지 용량을 중계가 건다)
#   bash sfl/net/local_rig.sh down                                     # 중계 종료
#   bash sfl/net/local_rig.sh edges                                    # 서버 --edges 인자
#   bash sfl/net/local_rig.sh edge  e cap                              # 실행 중 엣지 e(0..3) 용량 변경 (교란)
# 포트 규약은 real_rig.sh 와 같다: P(e, i, x) = BASE + 500·e + 2i + x.  sudo·tc·VM 불필요.
set -u
MODE=${1:-}
BASE=${BASE:-12100}; SRV_PORT=${SRV_PORT:-31900}; HOST=${LOCAL_HOST:-127.0.0.1}
PY=${PY:-python3}
CTL=${LOCAL_RIG_CTL:-out/local_rig_caps.json}; PIDF=${LOCAL_RIG_PID:-out/local_rig.pid}; LOGF=${LOCAL_RIG_LOG:-out/local_relay.log}
mkdir -p out
case "$MODE" in
  edges) echo "1=$HOST:$BASE,2=$HOST:$((BASE+500)),3=$HOST:$((BASE+1000)),4=$HOST:$((BASE+1500))" ;;
  up)
    N=${2:?클라 수}; ACC=${3:?접속 상한}; CAPS=${4:?엣지 용량}
    bash "$0" down >/dev/null 2>&1
    PYTHONPATH=sfl "$PY" sfl/net/local_relay.py --clients "$N" --acc "$ACC" --caps "$CAPS" \
      --upstream "$HOST:$((SRV_PORT+1))" --base "$BASE" --listen "$HOST" --delay-ms "${LOCAL_DELAY_MS:-$(( ${DELAY_MS:-0} / 2 + 2 ))}" --control "$CTL" \
      >> "$LOGF" 2>&1 &
    echo $! > "$PIDF"
    for _ in $(seq 1 50); do grep -q "대기" "$LOGF" 2>/dev/null && break; sleep 0.2; done
    kill -0 "$(cat "$PIDF")" 2>/dev/null || { echo "로컬 중계 기동 실패 — $LOGF"; tail -5 "$LOGF"; exit 1; }
    echo "로컬 중계 기동 (PID $(cat "$PIDF")) 엣지 [$CAPS] 접속 $(echo $ACC | awk '{print $1}')" ;;
  down)
    [ -f "$PIDF" ] && { kill "$(cat "$PIDF")" 2>/dev/null; rm -f "$PIDF"; }
    pkill -f "sfl/net/local_relay[.]py" 2>/dev/null; true ;;
  edge)
    e=${2:?엣지 0..3}; c=${3:?용량}
    PYTHONPATH=sfl "$PY" - "$CTL" "$e" "$c" <<'EOF'
import json, sys
p, e, c = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
d = json.load(open(p, encoding="utf-8"))
d["caps"][e] = c
json.dump(d, open(p, "w", encoding="utf-8"))
EOF
    echo "edge $((e+1)) → ${c} Mbps" ;;
  *) echo "usage: local_rig.sh up|down|edges|edge"; exit 2 ;;
esac
