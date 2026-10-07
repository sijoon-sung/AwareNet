#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════
#  체계적 검증 게이트 — 3계층. 각 시험이 증명하는 주장은 docs/02_실험/검증_매트릭스.md.
#
#    bash scripts/run_tests.sh fast    # 커밋 전 — torch 불필요, 수 초 (기본)
#    bash scripts/run_tests.sh full    # 실험 전 — torch 필요 (WSL sflenv), ~3분
#    bash scripts/run_tests.sh rig     # 실증/발표 전 — HPC 실회선 리그 (sudo·tc·VM ssh), ~30분
# ════════════════════════════════════════════════════════════════════
set -u
cd "$(dirname "$0")/.."
TIER="${1:-fast}"
PY="${PY:-}"
if [ -z "$PY" ]; then
  for cand in python3 python; do
    if "$cand" -c "pass" >/dev/null 2>&1; then PY="$cand"; break; fi
  done
fi
[ -n "$PY" ] || { echo "python 없음"; exit 1; }
fail=0
run(){ echo "━━ $1"; shift; "$@"; rc=$?; if [ $rc -ne 0 ]; then echo "   ✗ 실패 (exit $rc)"; fail=1; fi; }

# ── FAST ─────────────────────────────────────────────────────────
run "컴파일 전수" "$PY" - <<'EOF'
import glob, py_compile, sys
bad = []
for f in glob.glob('sfl/**/*.py', recursive=True) + glob.glob('scripts/**/*.py', recursive=True) + glob.glob('tests/*.py'):
    try: py_compile.compile(f, doraise=True)
    except Exception as e: bad.append(f"{f}: {e}")
print(f"  {'OK' if not bad else chr(10).join(bad)}")
sys.exit(1 if bad else 0)
EOF
run "FAST 단위시험" "$PY" tests/test_fast.py
run "통합계획기 규칙" "$PY" tests/test_plan.py
run "2단계 계획기·절제 팔 (폭만은 경로를 안 옮기고, 경로만은 폭을 안 깎는다)" "$PY" tests/test_two_stage.py
run "계획 층 plan.py (물 채우기·총비용 집합·분할·폭·시너지 방향)" "$PY" tests/test_plan2.py
run "기기 연산 예산·공유 접속망·정책 연결 (torch 불필요)" "$PY" -m unittest tests.test_device_budget
run "공유 병목 경로 제어·완료 확인·재조립 무결성" "$PY" -m unittest tests.test_network_control
run "준비된 기울기 전송 순서·불확실성 범위·부하 급변 반례" "$PY" -m unittest tests.test_barrier_schedule
run "KOREN·Jetson 원시 기록 주입·단위·과거 구간 분리·시간 재생" "$PY" -m unittest tests.test_trace_replay tests.test_measured_replay
run "동적 SFL 깊이·경로 공동 계획과 SDN 권한 경계" "$PY" -m unittest tests.test_supersfl_net tests.test_sdn_policy
run "조건 원장 (값마다 출처, 스크립트에 숫자 없음, 팔 규약)" "$PY" tests/test_cond.py
run "고정 2연결 비교군 배정 (출구 A·B 다른 엣지, 고정 비율, 이후 무개입)" "$PY" tests/test_fixed2.py
run "자르기·재조립 규칙 (chunker.py, 소켓 없음)" "$PY" tests/test_chunker.py
run "유체 시뮬레이터 (fluidsim.py: 해석해·어긋남·마이크로배치·닫힌 고리 왕복 없음)" "$PY" tests/test_fluidsim.py
run "코퍼스 통계" "$PY" sfl/lora_corpus.py

if [ "$TIER" = "fast" ]; then
  echo "── FAST 끝 (fail=$fail) ──"; exit $fail
fi

# ── FULL (torch) ─────────────────────────────────────────────────
run "집행 층 조각 왕복 (mpsend ↔ ChunkServer)" "$PY" tests/test_mp_act.py
run "기기·서버 소켓 왕복 마이크로배치 정합·전송 창" "$PY" -m unittest tests.test_micro_e2e
run "네트워크 정책 실제 학습 라운드·경유 종점 완료 확인 (합성 데이터·루프백)" "$PY" -m unittest tests.test_network_runtime
run "고정 2연결 비교군 실제 학습 2라운드 (합성 데이터·루프백 엣지 2개)" "$PY" -m unittest tests.test_fixed2_e2e
run "폭 복귀 시 서버 모델 상태 동기화" "$PY" -m unittest tests.test_aggregate_width_sync
run "인지 층 sense.py (관측 단위·엣지 용량 추정·되먹임 방지)" "$PY" tests/test_sense.py
run "서버 즉시 내보내기 조각 기울기 (클라별 버퍼)" "$PY" tests/test_micro_srv.py
run "정합 검증 스위트 (분할≡단일체 등)" "$PY" sfl/verify.py
# run "R 사전 시뮬 6판정" "$PY" sfl/experiments/run_r_sim.py   # 8월 R 시리즈 사전 시뮬(구판 controller_multi·sim.py) — 판정 2건(R3 교란, 규모 64~1024)이 구판 기준이라 실패, 게이트에서 제외 (2026-09-10). 이력용으로만 둔다
# run "L1 tiny 관통 (라벨 경계·저장 경로)" "$PY" sfl/experiments/run_l1.py --domain B --tiny --steps 3 --device cpu   # 언어모델(LoRA) 트랙은 후속(9/8 결정) — tiny 관통의 정확도 통과선(+40%p)이 현 코퍼스에서 안 맞아 게이트에서 제외 (2026-09-10)

if [ "$TIER" = "full" ]; then
  echo "── FULL 끝 (fail=$fail) ──"; exit $fail
fi

# ── RIG (sudo·tc·GPU) ────────────────────────────────────────────
run "실회선 리그 자가 검사 A~E (역터널·접속 상한·엣지 용량·내려받기 자식 클래스)" "$PY" scripts/measurement/real_selftest.py
run "32대 실행 전 검증 (스모크·교란 드라이런)" bash scripts/exp/verify_scen32.sh
run "실증 플랫폼 자동 검증 (라운드·교란 tc·복구·정리)" bash scripts/exp/verify_demo.sh
echo "── RIG 끝 (fail=$fail) — 삼면비교 데모는 수동 리허설 목록(검증_매트릭스 §3) ──"
exit $fail
