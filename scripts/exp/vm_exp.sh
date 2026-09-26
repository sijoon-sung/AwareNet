#!/usr/bin/env bash
# KOREN VM 실험 — 로컬(git-bash)에서 ssh 로 두 VM 을 지휘한다. 결과는 로컬 out/vm/ 으로 회수.
#
#   bash scripts/exp/vm_exp.sh smoke                 # VM1 한 대에서 서버+클라 4대, 2라운드 (환경 확인)
#   bash scripts/exp/vm_exp.sh link [정책] [라운드]    # 서버 VM1 ↔ 클라 4대 VM2 — 실제 VM 간 링크
#                                                     #   정책: uniform | static | ours (기본 uniform,static,ours 순서로 전부)
#   bash scripts/exp/vm_exp.sh twosite [라운드]       # 집계 서버 2곳(VM1·VM2) + 클라 4대(VM2) — 접속 지점 배정 리허설
#   bash scripts/exp/vm_exp.sh fetch                  # out/vm/ 로 로그 회수
#   bash scripts/exp/vm_exp.sh kill                   # 남은 실험 프로세스 정리
#
# 서버 포트는 HPC 범위와 맞춰 12000번대. VM 은 GPU 가 없으므로 --device cpu, 스레드 2 로 고정.
set -e
cd "$(dirname "$0")/../.."
V1=koren-vm; V2=koren-vm2; IP1=116.89.187.190; IP2=116.89.187.189
PY='~/awarenet/.venv/bin/python'
MODE="${1:-smoke}"

srv() {  # srv <host> <port> <policy> <clients> <rounds> <log> [extra]
  ssh "$1" "cd ~/awarenet; nohup env PYTHONPATH=sfl $PY sfl/fed_server.py --clients $4 --rounds $5 --batches 6 --cut 2 \
    --policy $3 --port $2 --device cpu --log out/$6 ${7:-} > out/${6%.jsonl}.srv.log 2>&1 < /dev/null & echo \$!"
}
cli() {  # cli <host> <server ip:port> <clients> <seed> <tag>
  ssh "$1" "cd ~/awarenet; for i in \$(seq 0 $(( $3 - 1 ))); do nohup env PYTHONPATH=sfl $PY sfl/fed_client.py \
    --server $2 --id c\$i --index \$i --clients $3 --cut 2 --seed $4 --device cpu --threads 2 \
    --log out/$5_c\$i.jsonl > out/$5_c\$i.log 2>&1 < /dev/null & done; echo started"
}
wait_port() {  # wait_port <host> <port> — 서버가 듣기 시작할 때까지 (최대 180초)
  ssh "$1" "for i in \$(seq 1 90); do ss -ltn 2>/dev/null | grep -q ':$2 ' && { echo listening; exit 0; }; sleep 2; done; echo NOT_LISTENING; exit 1"
}
wait_srv() {  # wait_srv <host> <log>
  ssh "$1" "cd ~/awarenet; for i in \$(seq 1 720); do grep -q '\"final_acc\"' out/$2 2>/dev/null && break; sleep 5; done; \
    grep -c '\"round\"' out/$2 2>/dev/null || echo 0"
}

case "$MODE" in
  smoke)
    echo "── 스모크: VM1 서버+클라 4대, 2라운드"
    srv $V1 12001 uniform 4 2 vm_smoke.jsonl >/dev/null; wait_port $V1 12001
    cli $V1 127.0.0.1:12001 4 1 vm_smoke >/dev/null
    n=$(wait_srv $V1 vm_smoke.jsonl); echo "라운드 기록 $n 개"
    ssh $V1 'cd ~/awarenet && grep "\"round\"" out/vm_smoke.jsonl | tail -2 | cut -c1-160' ;;
  link)
    POLS="${2:-uniform,static,ours}"; R="${3:-12}"; port=12010
    for P in ${POLS//,/ }; do
      echo "── link/$P: 서버 VM1:$port ← 클라 4대 VM2, ${R}라운드"
      srv $V1 $port $P 4 $R vm_link_$P.jsonl "--preflight" >/dev/null; wait_port $V1 $port
      cli $V2 $IP1:$port 4 1 vm_link_$P >/dev/null
      n=$(wait_srv $V1 vm_link_$P.jsonl); echo "   라운드 기록 $n 개"
      ssh $V1 "cd ~/awarenet && tail -1 out/vm_link_$P.jsonl | cut -c1-200"
      port=$((port + 1))
    done ;;
  twosite)
    R="${2:-12}"
    echo "── twosite: 집계 서버 VM1:12020 + VM2:12021, 클라 4대(VM2) — 학습량×접속 지점(widthpath) 리허설"
    echo "   (현재 fed_server 는 단일 집계 서버라, 두 서버를 따로 띄워 각 서버가 자기 클라를 맡는 형태로 리허설한다)"
    srv $V1 12020 widthpath 2 $R vm_two_A.jsonl "--preflight --paths 40,20" >/dev/null
    srv $V2 12021 widthpath 2 $R vm_two_B.jsonl "--preflight --paths 40,20" >/dev/null; wait_port $V1 12020; wait_port $V2 12021
    cli $V2 $IP1:12020 2 1 vm_two_A >/dev/null
    cli $V2 127.0.0.1:12021 2 1 vm_two_B >/dev/null
    nA=$(wait_srv $V1 vm_two_A.jsonl); nB=$(wait_srv $V2 vm_two_B.jsonl); echo "   A $nA / B $nB 라운드" ;;
  fetch)
    mkdir -p out/vm
    for h in $V1 $V2; do ssh $h 'cd ~/awarenet/out && tar -czf - vm_*.jsonl vm_*.log 2>/dev/null' | tar -xzf - -C out/vm || true; done
    ls out/vm | head -40 ;;
  kill)
    for h in $V1 $V2; do ssh $h 'pkill -f "fed_server.py|fed_client.py|run_rw.py" || true; echo "$(hostname) 정리"'; done ;;
  *) echo "usage: vm_exp.sh smoke|link [정책] [라운드]|twosite [라운드]|fetch|kill"; exit 2 ;;
esac
