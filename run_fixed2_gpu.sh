#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════
#  고정 2연결 비교군 — 한 번 실행으로 끝까지 (GPU 서버 = HPC 에서)
#
#    bash run_fixed2_gpu.sh            # 점검 → 기준선 확인 → 스모크 → 본 실험 → 집계 (백그라운드)
#    bash run_fixed2_gpu.sh status     # 진행 상황
#    bash run_fixed2_gpu.sh check      # 점검만 (GPU·데이터·sudo tc·VM 접속·단위시험)
#    bash run_fixed2_gpu.sh stop       # 중단
#
#  범위 줄이기:  SCEN=traffic bash run_fixed2_gpu.sh        (장면: traffic normal slow vary)
#               SEEDS="1" bash run_fixed2_gpu.sh
#  결과: out/fixed2_compare.csv  ·  로그: out/fixed2_all.log
#  설명: docs/02_실험/실험_고정2연결_비교군.md
# ════════════════════════════════════════════════════════════════════
set -u
cd "$(dirname "$0")"
mkdir -p out
MODE=${1:-start}
LOG=out/fixed2_all.log
export SCEN=${SCEN:-"traffic normal slow vary"}
export SEEDS=${SEEDS:-"1 2 3"}

if [ -z "${PY:-}" ]; then
  for cand in "$HOME/env/bin/python" python3 python; do
    if "$cand" -c "import torch" >/dev/null 2>&1; then PY=$cand; break; fi
  done
fi
export PY=${PY:-python3}

case "$MODE" in
  status)
    echo "== 진행 (최근 25줄) =="; tail -25 "$LOG" 2>/dev/null || echo "(로그 없음)"
    echo "== 실행 중 =="; pgrep -af "run_fixed2|run_scen32|fed_server" | grep -v pgrep || echo "(없음)"
    echo "== 완료된 fixed2 실행 =="; for f in out/wp_scen32_*_bothmp_fixed2.jsonl; do [ -f "$f" ] && echo "  $f  $(grep -c '"round"' "$f") 라운드"; done
    exit 0 ;;
  stop)
    pkill -f "run_fixed2_gpu.sh _run"; pkill -f "scripts/exp/run_fixed2.sh"; pkill -f "scripts/exp/run_scen32.sh"
    for p in $(pgrep -f "sfl/fed_(server|client)[.]py"); do kill $p 2>/dev/null; done
    bash sfl/net/real_rig.sh down >/dev/null 2>&1 || true
    echo "중단했습니다"; exit 0 ;;
  start)
    if pgrep -f "run_fixed2_gpu.sh _run" >/dev/null; then echo "이미 실행 중입니다 — bash run_fixed2_gpu.sh status"; exit 1; fi
    nohup bash "$0" _run > "$LOG" 2>&1 < /dev/null &
    echo "시작했습니다 (PID $!). 장면 [$SCEN] 시드 [$SEEDS]"
    echo "진행:  bash run_fixed2_gpu.sh status    또는    tail -f $LOG"
    exit 0 ;;
  check|_run) ;;
  *) echo "사용법: bash run_fixed2_gpu.sh [start|status|check|stop]"; exit 2 ;;
esac

ok(){ echo "  ✓ $*"; }
fail(){ echo "  ✗ $*"; echo "### 중단 $(date)"; exit 1; }

echo "### 고정 2연결 비교군 $(date)  장면 [$SCEN] 시드 [$SEEDS]  python $PY"
echo "── 1. 점검"
"$PY" -c "import torch; assert torch.cuda.is_available(); print('  ✓ torch', torch.__version__, torch.cuda.get_device_name(0))" \
  || fail "GPU(torch.cuda) 를 쓸 수 없습니다"
sudo -n true 2>/dev/null && command -v tc >/dev/null || fail "비밀번호 없는 sudo 와 tc 가 필요합니다 (회선 상한 설정)"
ok "sudo · tc"
for vm in ${VM1:-116.89.187.190} ${VM2:-116.89.187.189}; do
  ssh -o BatchMode=yes -o ConnectTimeout=10 -p ${VMPORT:-26022} ${VMUSER:-ubuntu}@$vm true 2>/dev/null || fail "KOREN VM $vm 에 ssh 가 안 됩니다 (포트 ${VMPORT:-26022})"
done
ok "KOREN VM 2대 ssh"
if [ ! -d data/cifar10/cifar-10-batches-py ]; then
  echo "  CIFAR-10 이 없어 내려받습니다 (data/cifar10)"
  "$PY" -c "import torchvision; torchvision.datasets.CIFAR10('data/cifar10', train=True, download=True); torchvision.datasets.CIFAR10('data/cifar10', train=False, download=True)" \
    || fail "CIFAR-10 내려받기 실패 — data/cifar10/cifar-10-batches-py 를 직접 넣어 주세요"
fi
ok "CIFAR-10 (data/cifar10)"
PYTHONPATH=sfl "$PY" tests/test_fixed2.py >/dev/null 2>&1 || fail "단위시험 tests/test_fixed2.py 실패"
ok "fixed2 단위시험"
[ "$MODE" = "check" ] && { echo "### 점검 통과 — bash run_fixed2_gpu.sh 로 시작하세요"; exit 0; }

echo "── 2. 기준·AwareNet 결과 확인 (없으면 같은 조건으로 먼저 돌린다)"
for SEED in $SEEDS; do for sc in $SCEN; do
  for arm in uniform widthpath; do
    f=out/wp_scen32_${sc}_s${SEED}_bothmp_${arm}.jsonl
    n=$( [ -f "$f" ] && grep -c '"round"' "$f" || echo 0 )
    if [ "${n:-0}" -lt 24 ]; then
      echo "  $sc 시드 $SEED 의 $arm 결과가 없어 돌립니다 (약 30분)"
      SCEN=$sc SEED=$SEED ONLY=$arm bash scripts/exp/run_scen32.sh || fail "$sc 시드 $SEED $arm 실행 실패"
    fi
  done
done; done
ok "기준·AwareNet 결과 준비"

echo "── 3. 스모크 (정상 장면 3라운드)"
ROUNDS_OVERRIDE=3 SCEN=normal SEEDS=1 bash scripts/exp/run_fixed2.sh
n=$(grep -c '"round"' out/wp_scen32_normal_s1_bothmp_fixed2.jsonl 2>/dev/null || echo 0)
[ "${n:-0}" -ge 3 ] || fail "스모크 실패 — out/scen32_normal_s1_bothmp_fixed2.log 를 확인하세요"
ok "스모크 3라운드 완료"

echo "── 4. 본 실험 (장면·시드마다 약 30분)"
bash scripts/exp/run_fixed2.sh

echo "── 5. 집계"
"$PY" scripts/analysis/fixed2_compare.py
echo "### 끝 $(date) — 결과 out/fixed2_compare.csv"
