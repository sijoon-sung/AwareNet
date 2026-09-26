#!/usr/bin/env bash
# HPC(이노베이션 허브 V100) 에 GPU 실험을 거는 한 방 스크립트 — 로컬(git-bash)에서 실행.
#   전제: RNTier 런처가 켜져 있어 `ssh koren-hpc` 가 되는 상태. 저장소 루트에서:
#     bash scripts/exp/hpc_launch.sh            # 코드 동기화 + 스모크 + R(w) 전체를 nohup 으로
#     bash scripts/exp/hpc_launch.sh sync       # 코드 동기화만
#     bash scripts/exp/hpc_launch.sh status     # 진행 상황
#   결과 회수는 scripts/exp/hpc_fetch.sh (런처가 켜져 있을 때).
set -e
cd "$(dirname "$0")/../.."
H=koren-hpc
MODE="${1:-all}"

ssh -o ConnectTimeout=8 -o BatchMode=yes $H 'echo hpc-ok' >/dev/null || { echo "HPC 접속 불가 — 런처를 켜세요"; exit 1; }

sync_code() {
  echo "── 코드 동기화 → ~/awarenet (추적 파일만, data/out 유지)"
  ssh $H 'cd ~/awarenet && mkdir -p out && find . -maxdepth 1 ! -name data ! -name out ! -name . -exec rm -rf {} +'
  git archive HEAD | ssh $H 'tar -x -C ~/awarenet'
  ssh $H 'cd ~/awarenet && ~/env/bin/python -c "import torch;print(\"torch\", torch.__version__, \"cuda\", torch.cuda.is_available())" && ls data'
}

case "$MODE" in
  sync) sync_code ;;
  status)
    ssh $H 'cd ~/awarenet && echo "== 프로세스 =="; pgrep -af "run_rw|fed_server|run_l" | grep -v pgrep || echo "(없음)"; echo "== rw 로그 =="; tail -5 out/rw_run.log 2>/dev/null; ls out/rw_*.jsonl 2>/dev/null | wc -l; nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader' ;;
  all)
    sync_code
    echo "── 스모크 (폭 1.0 · 시드 1 · 2라운드)"
    ssh $H 'cd ~/awarenet && timeout 900 ~/env/bin/python sfl/experiments/run_rw.py --ps 1.0 --seeds 1 --rounds 2 --batches 2 --force 2>&1 | tail -3'
    echo "── R(w) 전체 (폭 4 × 시드 3 × 30라운드) nohup"
    ssh $H 'cd ~/awarenet; rm -f out/rw_p1.00_s1.jsonl; nohup ~/env/bin/python sfl/experiments/run_rw.py --rounds 30 --batches 6 > out/rw_run.log 2>&1 < /dev/null & echo "PID $!"'
    echo "걸었습니다. 진행: bash scripts/exp/hpc_launch.sh status · 회수: bash scripts/exp/hpc_fetch.sh" ;;
  *) echo "usage: hpc_launch.sh [all|sync|status]"; exit 2 ;;
esac
