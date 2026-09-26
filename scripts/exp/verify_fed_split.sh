#!/usr/bin/env bash
# 연합 분할 LoRA 발산 재현/수정 검증 — HPC 안에서 서버·기기 3대 모두 GPU (VM 없이 빠르게). 2026-09-13
#   LR=1e-3 CLIP=0 TAG=v_old bash scripts/exp/verify_fed_split.sh    # 1차 설정 (발산 재현 시도)
#   LR=3e-4 CLIP=1.0 TAG=v_new bash scripts/exp/verify_fed_split.sh  # 수정 설정
# 판정: R3 이후 어떤 라운드든 기기 최대 손실 > 2.0 이면 "발산". 결과 한 줄을 끝에 출력.
set -u
cd "$(dirname "$0")/../.."
PY=${PY:-$HOME/env/bin/python}; PORT=${PORT:-31957}; LR=${LR:-3e-4}; CLIP=${CLIP:-1.0}; TAG=${TAG:-verify}; ROUNDS=${ROUNDS:-16}; STEPS=${STEPS:-30}
mkdir -p out/fed_split
rm -f out/fed_split/server_${TAG}.jsonl out/fed_split/device_${TAG}_c*.jsonl
PYTHONPATH=sfl $PY sfl/experiments/run_fed_split_lora.py server --clients 3 --rounds $ROUNDS --local-steps $STEPS --lr $LR --clip $CLIP --device cuda --port $PORT --tag $TAG > out/fed_split/srv_${TAG}.log 2>&1 &
SP=$!
w=0; while ! ss -ltn | grep -q ":$PORT "; do kill -0 $SP 2>/dev/null || { echo "서버 죽음"; tail -3 out/fed_split/srv_${TAG}.log; exit 1; }; sleep 1; w=$((w+1)); [ $w -ge 300 ] && { echo "포트 미개방"; kill $SP; exit 1; }; done
i=0; for d in B1 B2 B3; do
  x=""; [ $i = 0 ] && x="--canary"
  PYTHONPATH=sfl $PY sfl/experiments/run_fed_split_lora.py device --id c$i --domain $d --server 127.0.0.1:$PORT --lr $LR --clip $CLIP --device cuda --threads 2 --tag $TAG $x > out/fed_split/dev_${TAG}_c$i.log 2>&1 &
  i=$((i+1))
done
wait $SP
wait
PYTHONPATH=sfl $PY - "$TAG" <<'PYEOF'
import json, sys
tag = sys.argv[1]
rows = [json.loads(l) for l in open(f"out/fed_split/server_{tag}.jsonl", encoding="utf-8") if l.strip()]
worst = max((max(r["loss_max"].values()), r["round"]) for r in rows if r["round"] >= 3)
for r in rows:
    print(f"  R{r['round']:2d} 평균 " + " ".join(f"{k}:{v:.4f}" for k, v in r["losses"].items()) + " | 최대 " + " ".join(f"{k}:{v:.3f}" for k, v in r["loss_max"].items()))
print(f"결과 {tag}: R3 이후 최대 손실 {worst[0]:.3f} (R{worst[1]}) → {'발산' if worst[0] > 2.0 else '안정'}")
PYEOF
