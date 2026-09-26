#!/usr/bin/env bash
# HPC 실험 결과 회수 — out/rw_* 와 요약을 로컬 out/ 으로. 런처가 켜져 있을 때 실행.
set -e
cd "$(dirname "$0")/../.."
H=koren-hpc
ssh -o ConnectTimeout=8 -o BatchMode=yes $H 'echo hpc-ok' >/dev/null || { echo "HPC 접속 불가 — 런처를 켜세요"; exit 1; }
mkdir -p out/hpc
ssh $H 'cd ~/awarenet/out && tar -czf - rw_*.jsonl rw_summary.json rw_run.log 2>/dev/null' | tar -xzf - -C out/hpc
ls -la out/hpc | tail -n +2
PYTHONUTF8=1 python - <<'EOF'
import json, os
p = "out/hpc/rw_summary.json"
if os.path.exists(p):
    s = json.load(open(p, encoding="utf-8"))
    print(f"{'폭':>5} {'시드':>4} {'라운드':>6} {'최종 acc':>8} {'라운드당 s':>10}")
    for k, v in sorted(s.items()):
        print(f"{v['p']:5.2f} {v['seed']:4d} {v['rounds']:6d} {v['final_acc']*100 if v['final_acc'] else 0:8.1f} {v['makespan_mean']:10.1f}")
EOF
