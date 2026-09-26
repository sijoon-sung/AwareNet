#!/usr/bin/env bash
# KOREN VM 2대에 현행 코드를 배포하고 환경을 점검한다 — 로컬(git-bash)에서 실행.
#   bash scripts/exp/vm_deploy.sh          # 코드 동기화 + 환경 점검 + FAST 테스트 (VM1)
#   bash scripts/exp/vm_deploy.sh status   # 두 VM 상태만
# 전제: ~/.ssh/config 의 koren-vm(116.89.187.190) · koren-vm2(116.89.187.189), 허용 IP 에서 실행.
# VM 쪽 배치: ~/awarenet (코드) · ~/awarenet/.venv (torch CPU) · ~/awarenet/data/cifar10
set -e
cd "$(dirname "$0")/../.."
VMS="koren-vm koren-vm2"
MODE="${1:-all}"

for h in $VMS; do
  ssh -o ConnectTimeout=8 -o BatchMode=yes $h 'echo ok' >/dev/null || { echo "$h 접속 불가 (허용 IP 에서 실행 중인지 확인)"; exit 1; }
done

status() {
  for h in $VMS; do
    echo "== $h =="
    ssh $h 'cd ~/awarenet 2>/dev/null || { echo "(미배포)"; exit 0; }
      .venv/bin/python -c "import torch, torchvision; print(\"torch\", torch.__version__, torchvision.__version__)" 2>&1 | tail -1
      [ -d data/cifar10/cifar-10-batches-py ] && echo "cifar10 ok" || echo "cifar10 없음"
      echo "프로세스: $(pgrep -af "fed_server|fed_client|run_" | grep -v pgrep | wc -l)개"
      uptime | sed "s/.*load/load/"'
  done
}

if [ "$MODE" = "status" ]; then status; exit 0; fi

for h in $VMS; do
  echo "── $h 코드 동기화 (추적 파일만, data/out/.venv 유지)"
  ssh $h 'mkdir -p ~/awarenet/out ~/awarenet/data && cd ~/awarenet && find . -maxdepth 1 ! -name data ! -name out ! -name .venv ! -name . -exec rm -rf {} +'
  git archive HEAD | ssh $h 'tar -x -C ~/awarenet'
done
status
echo "── FAST 테스트 (VM1)"
ssh koren-vm 'cd ~/awarenet && PY=.venv/bin/python bash scripts/run_tests.sh fast 2>&1 | tail -4'
