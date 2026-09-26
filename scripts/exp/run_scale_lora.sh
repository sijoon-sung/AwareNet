#!/usr/bin/env bash
# 분할 + LoRA 대형 모델 실험 (HPC 에서 실행, 2026-09-13). 사전등록: docs/02_실험/실험_대형모델_분할LoRA_사전등록_2026-09-13.md
#   nohup bash scripts/exp/run_scale_lora.sh > out/scale_lora.log 2>&1 < /dev/null &
# A) 비용 사다리 — 기기(VM1, CPU) 는 local/front, 서버(HPC) 는 back.  B) 실제 분할 학습 — VM1 기기 ↔ HPC 서버 (역터널 31950).
set -u
cd "$(dirname "$0")/../.."
PY=${PY:-$HOME/env/bin/python}; VM=${VM:-116.89.187.190}; VMP=${VMP:-26022}; VMU=${VMU:-ubuntu}
PORT=${PORT:-31950}; TAG=${TAG:-$(date +%m%d)}
PHASE=${PHASE:-"A B"}
vm() { ssh -o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=30 -p $VMP $VMU@$VM "cd ~/awarenet && PYTHONPATH=sfl $*"; }
echo "### SCALE-LORA START $(date) [$PHASE] tag=$TAG"
mkdir -p out/scale_lora
if [[ " $PHASE " == *" A "* ]]; then
  echo "## A1 기기(VM1) LLM 사다리 local/front  $(date +%T)"
  vm ".venv/bin/python sfl/experiments/run_scale_lora.py cost --family llm --parts local,front --models Qwen/Qwen2.5-0.5B,Qwen/Qwen2.5-1.5B,Qwen/Qwen2.5-3B,Qwen/Qwen2.5-7B --cut 2 --steps 3 --tag ${TAG}_vm --timeout 1500"
  echo "## A2 기기(VM1) DiT 사다리 local/front  $(date +%T)"
  vm ".venv/bin/python sfl/experiments/run_scale_lora.py cost --family dit --parts local,front --models S,B,L,XL --cut 2 --steps 3 --tag ${TAG}_vm --timeout 1500"
  echo "## A3 서버(HPC GPU) back  $(date +%T)"
  PYTHONPATH=sfl $PY sfl/experiments/run_scale_lora.py cost --family llm --parts back --models Qwen/Qwen2.5-0.5B,Qwen/Qwen2.5-1.5B,Qwen/Qwen2.5-3B --cut 2 --steps 3 --device cuda --fp16 --tag ${TAG}_hpc
  PYTHONPATH=sfl $PY sfl/experiments/run_scale_lora.py cost --family llm --parts back --models Qwen/Qwen2.5-7B --cut 2 --steps 3 --device cpu --tag ${TAG}_hpc --timeout 2400
  PYTHONPATH=sfl $PY sfl/experiments/run_scale_lora.py cost --family dit --parts back --models S,B,L,XL --cut 2 --steps 3 --device cuda --tag ${TAG}_hpc
  echo "## A4 서버(HPC CPU) 전체 사다리 local/front/back — 참고(같은 기계에서 세 부분)  $(date +%T)"
  PYTHONPATH=sfl $PY sfl/experiments/run_scale_lora.py cost --family llm --parts local,front,back --models Qwen/Qwen2.5-0.5B,Qwen/Qwen2.5-1.5B,Qwen/Qwen2.5-3B,Qwen/Qwen2.5-7B --cut 2 --steps 3 --device cpu --threads 8 --tag ${TAG}_hpccpu --timeout 2400
  scp -q -P $VMP $VMU@$VM:~/awarenet/out/scale_lora/cost_*_${TAG}_vm.jsonl out/scale_lora/ 2>/dev/null
fi
if [[ " $PHASE " == *" B "* ]]; then
  echo "## B 실제 분할 학습 (VM1 기기 ↔ HPC 서버)  $(date +%T)"
  pkill -f "R 0.0.0.0:$PORT:127.0.0.1:$PORT" 2>/dev/null; sleep 0.5
  ssh -o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -p $VMP -f -N -R 0.0.0.0:$PORT:127.0.0.1:$PORT $VMU@$VM || { echo "역터널 실패"; exit 1; }
  e2e() {  # $1 family $2 model $3 server device $4 steps $5 extra-server $6 extra-device
    local fam=$1 model=$2 sdev=$3 steps=$4 sx=${5:-} dx=${6:-}; local t="${TAG}_$(echo $model | tr '/' '_')"
    echo "-- $fam $model 서버 $sdev $steps 스텝  $(date +%T)"
    PYTHONPATH=sfl $PY sfl/experiments/run_scale_lora.py server --family $fam --model $model --cut 2 --port $PORT --device $sdev --tag $t $sx > out/scale_lora/srv_${t}.log 2>&1 &
    local SP=$!
    local w=0; while ! ss -ltn 2>/dev/null | grep -q ":$PORT "; do kill -0 $SP 2>/dev/null || { echo "서버 죽음"; tail -3 out/scale_lora/srv_${t}.log; return 1; }; sleep 2; w=$((w+2)); [ $w -ge 900 ] && { echo "서버 포트 미개방"; kill $SP; return 1; }; done
    vm ".venv/bin/python sfl/experiments/run_scale_lora.py device --family $fam --model $model --cut 2 --server 127.0.0.1:$PORT --steps $steps --tag $t $dx" | tee out/scale_lora/dev_${t}.log
    wait $SP; grep -E "준비|끝" out/scale_lora/srv_${t}.log
  }
  e2e llm Qwen/Qwen2.5-0.5B cuda 30
  e2e llm Qwen/Qwen2.5-3B cpu 20
  e2e llm Qwen/Qwen2.5-7B cpu 10
  e2e dit XL cuda 30
  scp -q -P $VMP $VMU@$VM:~/awarenet/out/scale_lora/device_*_${TAG}_*.jsonl out/scale_lora/ 2>/dev/null
  pkill -f "R 0.0.0.0:$PORT:127.0.0.1:$PORT" 2>/dev/null
fi
echo "### SCALE-LORA DONE $(date)"
