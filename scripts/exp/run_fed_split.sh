#!/usr/bin/env bash
# 분할 + LoRA 연합 학습 증명 배치 (HPC 에서, 2026-09-13). 기기 = VM1(c0 B1+카나리아, c1 B2) + VM2(c2 B3), 서버 = HPC GPU.
#   nohup bash scripts/exp/run_fed_split.sh > out/fed_split.log 2>&1 < /dev/null &
# A) 연합 3대 16×30  B) 단독 1대(B1) 16×30  C) 평가(베이스/단독/연합 실제 문답) → out/fed_split/eval_<TAG>.md
set -u
cd "$(dirname "$0")/../.."
PY=${PY:-$HOME/env/bin/python}; VM1=${VM1:-116.89.187.190}; VM2=${VM2:-116.89.187.189}; VMP=26022; VMU=ubuntu
PORT=${PORT:-31955}; TAG=${TAG:-$(date +%m%d)}; ROUNDS=${ROUNDS:-16}; STEPS=${STEPS:-30}
PHASE=${PHASE:-"A B C"}; EVAL_TAG=${EVAL_TAG:-$TAG}   # V = 뒷단 어댑터도 기기별로 두고 평균(SplitFed v1) 대조 (2026-09-13 사전등록 §8)
mkdir -p out/fed_split
echo "### FED-SPLIT START $(date) tag=$TAG rounds=$ROUNDS steps=$STEPS phase=[$PHASE] eval_tag=$EVAL_TAG"
vm() { local h=$1; shift; ssh -o BatchMode=yes -o ConnectTimeout=15 -p $VMP $VMU@$h "cd ~/awarenet && $*"; }
tunnel_up() { for h in $VM1 $VM2; do ssh -o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -p $VMP -f -N -R 0.0.0.0:$PORT:127.0.0.1:$PORT $VMU@$h || { echo "역터널 실패 $h"; exit 1; }; done; }
tunnel_down() { pkill -f "R 0.0.0.0:$PORT:127.0.0.1:$PORT" 2>/dev/null; sleep 0.5; }
launch_dev() {  # host id domain tag extra
  vm $1 "(setsid nohup env PYTHONPATH=sfl .venv/bin/python sfl/experiments/run_fed_split_lora.py device --id $2 --domain $3 --server 127.0.0.1:$PORT --tag $4 $5 > out/fed_split_${4}_$2.log 2>&1 < /dev/null &)"
}
run_fed() {  # tag nclients [server extra args]
  local t=$1 n=$2 sx=${3:-}
  PYTHONPATH=sfl $PY sfl/experiments/run_fed_split_lora.py server --clients $n --rounds $ROUNDS --local-steps $STEPS --device cuda --port $PORT --tag $t $sx > out/fed_split/srv_$t.log 2>&1 &
  local SP=$!; local w=0
  while ! ss -ltn 2>/dev/null | grep -q ":$PORT "; do kill -0 $SP 2>/dev/null || { echo "서버 죽음"; tail -3 out/fed_split/srv_$t.log; return 1; }; sleep 2; w=$((w+2)); [ $w -ge 600 ] && { echo "포트 미개방"; kill $SP; return 1; }; done
  vm $VM1 "mkdir -p out"; launch_dev $VM1 c0 B1 $t --canary
  if [ $n -ge 3 ]; then launch_dev $VM1 c1 B2 $t ""; launch_dev $VM2 c2 B3 $t ""; fi
  wait $SP; local rc=$?
  grep -E "접속|R ?[0-9]+ |끝|Traceback|Error" out/fed_split/srv_$t.log | tail -22
  for h in $VM1 $VM2; do vm $h "pkill -f 'run_fed_split_lora[.]py' 2>/dev/null; true"; done
  return $rc
}
tunnel_down; tunnel_up
if [[ " $PHASE " == *" A "* ]]; then echo "## A 연합 3대 (뒷단 공유)  $(date +%T)"; run_fed fed3_$TAG 3 || { tunnel_down; echo "### 실패 A"; exit 1; }; fi
if [[ " $PHASE " == *" B "* ]]; then echo "## B 단독 1대(B1)  $(date +%T)"; run_fed single1_$TAG 1 || { tunnel_down; echo "### 실패 B"; exit 1; }; fi
if [[ " $PHASE " == *" V "* ]]; then echo "## V 연합 3대 (뒷단도 기기별·평균)  $(date +%T)"; run_fed fed3v1_$TAG 3 "--back-mode avg" || { tunnel_down; echo "### 실패 V"; exit 1; }; fi
tunnel_down
for h in $VM1 $VM2; do scp -q -P $VMP $VMU@$h:~/awarenet/out/fed_split/device_*_$TAG*.jsonl out/fed_split/ 2>/dev/null; scp -q -P $VMP $VMU@$h:~/awarenet/out/fed_split_*_$TAG*.log out/fed_split/ 2>/dev/null; done
echo "## C 평가 (실제 문답)  $(date +%T)"
SETS="단독(B1)=out/fed_split/single1_$TAG,연합(B1+B2+B3)=out/fed_split/fed3_$TAG"
[ -f out/fed_split/fed3v1_${TAG}_back.pt ] && SETS="$SETS,연합·뒷단도 평균(v1)=out/fed_split/fed3v1_$TAG"
echo "   평가 세트: $SETS"
PYTHONPATH=sfl $PY sfl/experiments/fed_split_eval.py --sets "$SETS" --domains B1,B2,B3 --device cuda --per-domain 3 --tag $EVAL_TAG 2>&1 | grep -v Warning
echo "### FED-SPLIT DONE $(date)"
