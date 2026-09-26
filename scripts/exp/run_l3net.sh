#!/usr/bin/env bash
# LoRA 본 실험 — 실소켓·실경로(30/10M) 위 어댑터 연합, 기준 vs 온라인 경로 판단
# root 로 실행 (tc 필요), HF 캐시는 sijoon 것을 지정
set -e
cd "$(dirname "$0")/../.."
PY=${PY:-/home/sijoon/sflenv/bin/python}
SUDO=${SUDO:-}
export HF_HOME=${HF_HOME:-/home/sijoon/.cache/huggingface}
export PYTHONPATH=sfl
PS=sfl/net/paths.sh

for POL in uniform widthpath; do
  echo "== $POL =="
  $SUDO sh $PS setup "40 20"
  $SUDO sh $PS assign "1 1 1"
  "$PY" sfl/experiments/run_l3_net.py --policy $POL --paths 40,20 --rounds 6 --local-steps 10
done
$SUDO sh $PS clear
"$PY" - <<'PYEOF'
import json, io
for tag in ("uniform", "widthpath"):
    rows = [json.loads(l) for l in io.open(f"out/l3net_{tag}.jsonl", encoding="utf-8")]
    up = sum(r["upload_wall"] for r in rows) / len(rows)
    print(f"{tag:10s} 평균 업로드 구간 {up:6.2f}s  마지막 배정 {list(rows[-1]['assign'].values())}")
PYEOF
