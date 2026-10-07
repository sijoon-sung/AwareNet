#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════
#  고정 2연결 비교군 — GPU 장비 한 대 버전 (KOREN VM 없이, 로컬 중계로 회선 재현)
#
#    bash run_fixed2_gpu.sh            # 점검 → 스모크 → 기준·고정 2연결·AwareNet 세 방식 → 집계 (백그라운드)
#    bash run_fixed2_gpu.sh status     # 진행 상황
#    bash run_fixed2_gpu.sh check      # 점검만
#    bash run_fixed2_gpu.sh stop       # 중단
#
#  범위:  SCEN="traffic normal slow vary"  SEEDS="1 2 3"   (기본 SCEN=traffic SEEDS=1 — 약 1.5~2시간)
#  결과:  out/fixed2_compare_scen32gpu.csv  ·  로그 out/fixed2_gpu_all.log
#
#  환경: Linux + NVIDIA GPU + python(torch, torchvision). sudo·tc·KOREN VM 불필요.
#  회선: sfl/net/local_relay.py 가 KOREN 실험과 같은 상한을 건다 — 접속 5/2 Mbps(출구 A/B), 엣지 56 Mbps ×4,
#        트래픽 몰림 8~20라운드 엣지 1 → 14 Mbps, 용량 변동 7 Mbps 계단 (conditions.json r32 와 같은 값).
#  주의: 이 결과는 "로컬 GPU 테스트베드" 결과다. KOREN 실측 결과(scen32)와 섞지 않고, 세 방식을 모두 여기서 다시 돌린다.
#  설명: docs/02_실험/실험_고정2연결_비교군.md
# ════════════════════════════════════════════════════════════════════
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1
set -u
cd "$(dirname "$0")"
mkdir -p out
MODE=${1:-start}
LOG=out/fixed2_gpu_all.log
export SCEN=${SCEN:-"traffic"}
export SEEDS=${SEEDS:-"1"}
PREFIX=${PREFIX:-"scen32gpu"}   # KOREN 결과(scen32)와 이름을 나눈다
VARY="8:49,9:42,10:35,11:28,12:21,13:14,14:21,15:28,16:35,17:42,18:49,19:56"

if [ -z "${PY:-}" ]; then
  for cand in "$HOME/env/bin/python" python3 python; do
    if "$cand" -c "import torch" >/dev/null 2>&1; then PY=$cand; break; fi
  done
fi
export PY=${PY:-python}
export BASE=${BASE:-25100}
export RIGSH=sfl/net/local_rig.sh PERTURB_RIGSH=sfl/net/local_rig.sh REUSE_UNIFORM=0 UNIFORM_MP=0

case "$MODE" in
  status)
    echo "== 진행 (최근 25줄) =="; tail -25 "$LOG" 2>/dev/null || echo "(로그 없음)"
    echo "== 실행 중 =="; pgrep -af "run_fixed2_gpu|fed_server|local_relay" 2>/dev/null | grep -v pgrep || echo "(프로세스 목록)"
    echo "== 완료된 실행 =="; for f in out/wp_${PREFIX}_*.jsonl; do [ -f "$f" ] && echo "  $f  $(grep -c '"round"' "$f") 라운드"; done
    exit 0 ;;
  stop)
    pkill -f "run_fixed2_gpu.sh _run" 2>/dev/null || true
    pkill -f "scenario_perturb.sh" 2>/dev/null || true
    "$PY" scripts/clean_proc.py 2>/dev/null || true
    for p in $(pgrep -f "sfl/fed_(server|client)[.]py" 2>/dev/null); do kill $p 2>/dev/null; done
    bash $RIGSH down >/dev/null 2>&1 || true
    echo "중단했습니다"; exit 0 ;;
  start)
    if pgrep -f "run_fixed2_gpu.sh _run" >/dev/null 2>&1; then echo "이미 실행 중입니다 — bash run_fixed2_gpu.sh status"; exit 1; fi
    nohup bash "$0" _run > "$LOG" 2>&1 < /dev/null &
    echo "시작했습니다 (PID $!). 장면 [$SCEN] 시드 [$SEEDS] — 대상 prefix [$PREFIX]"
    echo "진행:  bash run_fixed2_gpu.sh status    또는    tail -f $LOG"
    exit 0 ;;
  smoke) ;;
  check|_run) ;;
  *) echo "사용법: bash run_fixed2_gpu.sh [start|status|check|smoke|stop]"; exit 2 ;;
esac

ok(){ echo "  ✓ $*"; }
fail(){ echo "  ✗ $*"; bash $RIGSH down >/dev/null 2>&1; echo "### 중단 $(date)"; exit 1; }

echo "### 고정 2연결 비교군 — 로컬 GPU 테스트베드 $(date)  장면 [$SCEN] 시드 [$SEEDS]  python $PY"
echo "── 1. 점검"
"$PY" -c "import torch; assert torch.cuda.is_available(); print('  torch', torch.__version__, torch.cuda.get_device_name(0))" \
  || fail "GPU(torch.cuda) 를 쓸 수 없습니다"
if command -v ss >/dev/null 2>&1; then ok "ss"; else ok "ss 없음 (Python 소켓 검사 대체)"; fi
NC=$(nproc 2>/dev/null || echo 1); ok "CPU 코어 $NC (클라 32개를 CPU 에서 돌린다 — 16코어 이상 권장)"
if [ ! -d data/cifar10/cifar-10-batches-py ]; then
  echo "  CIFAR-10 이 없어 내려받습니다 (data/cifar10, 약 170MB)"
  "$PY" -c "import torchvision; torchvision.datasets.CIFAR10('data/cifar10', train=True, download=True); torchvision.datasets.CIFAR10('data/cifar10', train=False, download=True)" \
    || fail "CIFAR-10 내려받기 실패 — data/cifar10/cifar-10-batches-py 를 직접 넣어 주세요"
fi
ok "CIFAR-10 (data/cifar10)"
PYTHONPATH=sfl "$PY" tests/test_fixed2.py >/dev/null 2>&1 || fail "단위시험 tests/test_fixed2.py 실패"
"$PY" tests/test_local_relay.py >/dev/null 2>&1 || fail "로컬 중계 시험 tests/test_local_relay.py 실패"
ok "fixed2·로컬 중계 시험"
[ "$MODE" = "check" ] && { echo "### 점검 통과 — bash run_fixed2_gpu.sh 로 시작하세요"; exit 0; }

run_arm() {  # $1 장면, $2 시드, $3 팔(uniform|fixed2|widthpath), [$4 태그 머리]
  local sc=$1 seed=$2 arm=$3 pre=${4:-$PREFIX}
  local cond=r32; [ "$sc" = "slow" ] && cond=r32_slow
  local tag="${pre}_${sc}_s${seed}_bothmp"
  local log="out/wp_${tag}_${arm}.jsonl"
  if [ "${FORCE_RERUN:-0}" != "1" ] && [ -f "$log" ]; then
    local n_done; n_done=$(grep -c '"round"' "$log" 2>/dev/null || true); n_done=${n_done:-0}
    if [ "$n_done" -ge "${ROUNDS_OVERRIDE:-24}" ]; then
      echo "   ✓ 이미 완료됨 ($n_done 라운드): $log"
      return 0
    fi
  fi
  "$PY" scripts/clean_proc.py 2>/dev/null || true
  for p in $(pgrep -f "sfl/fed_(server|client)[.]py" 2>/dev/null); do kill $p 2>/dev/null; done; sleep 1
  bash $RIGSH down >/dev/null 2>&1 || true
  rm -f "$log"
  local wpid=""
  if [ "$sc" = "traffic" ]; then
    bash scripts/exp/scenario_perturb.sh "$log" 0 14 56 8 20 > "out/${tag}_${arm}_perturb.log" 2>&1 & wpid=$!
  elif [ "$sc" = "vary" ]; then
    bash scripts/exp/scenario_perturb.sh "$log" 0 sched "$VARY" > "out/${tag}_${arm}_perturb.log" 2>&1 & wpid=$!
  fi
  echo "   $(date +%H:%M:%S) $sc 시드 $seed — $arm"
  ROUNDS_OVERRIDE=${ROUNDS_OVERRIDE:-} COND=$cond ARM=bothmp SEED=$seed TAG="${tag}_" ONLY=$arm timeout 9000 bash scripts/exp/run_real.sh > "out/${tag}_${arm}.log" 2>&1
  local rc=$?
  bash $RIGSH down >/dev/null 2>&1 || true
  [ -n "$wpid" ] && { kill $wpid 2>/dev/null; wait $wpid 2>/dev/null; sed 's/^/      /' "out/${tag}_${arm}_perturb.log"; }
  local n; n=$(grep -c '"round"' "$log" 2>/dev/null || true); n=${n:-0}
  if [ $rc -ne 0 ] || ( [ -f "out/${tag}_${arm}.log" ] && grep -qE "Traceback|OSError" "out/${tag}_${arm}.log" ); then
    echo "      ✗ 실패 rc=$rc (라운드 $n) — out/${tag}_${arm}.log"; tail -5 "out/${tag}_${arm}.log" 2>/dev/null | sed 's/^/        /'; return 1
  fi
  "$PY" - "$log" "$n" <<'PYEOF'
import json, statistics as s, sys
R = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8") if '"round"' in l]
T = [r for r in R if r["round"] >= 4] or R
print(f"      완료 라운드 {sys.argv[2]}  평균 라운드 {s.mean(r['makespan'] for r in T):.2f}s  평균 폭 {s.mean(s.mean(r['plan'].values()) for r in T):.3f}")
PYEOF
}

echo "── 2. 스모크 (정상 장면 2라운드: 고정 2연결)"
for arm in ${SMOKE_ARMS:-fixed2}; do
  ROUNDS_OVERRIDE=2 run_arm normal 1 $arm ${PREFIX}smoke || fail "스모크 실패 ($arm)"
done
ok "스모크 통과"
[ "$MODE" = "smoke" ] && { echo "### 스모크 완료"; exit 0; }

echo "── 3. 본 실험 (세 방식, 같은 장비·같은 조건)"
ARMS=${ARMS:-"uniform fixed2 widthpath"}
for seed in $SEEDS; do for sc in $SCEN; do
  for arm in $ARMS; do run_arm $sc $seed $arm || echo "      (다음으로 계속)"; done
done; done

echo "── 4. 집계"
"$PY" scripts/analysis/fixed2_compare.py --prefix $PREFIX
echo "### 끝 $(date) — 결과 out/fixed2_compare_${PREFIX}.csv (로컬 GPU 테스트베드)"
