#!/usr/bin/env bash
# 망 효과 실험 (2026-09-07 오후): 두 가닥 접속 + 엣지 변경 / 분할 전송 / 즉시 내보내기. 조건·팔은 원장에서.
#
#   nohup bash scripts/exp/run_net_effect.sh > out/net_effect_0907.log 2>&1 < /dev/null &
#
# 순서 (각 조건은 게이트: 규칙 시험 + 리그 자가 검사 → 시드 × 팔). 한 조건이 실패하면 **멈춘다** (조용히 넘어가지 않는다 — 어젯밤 교훈).
#   h5x   4대 50/20, 경로 150/150            팔 path3(엣지 변경만, 출구 A) / mp(분할 전송)
#   h5xm  h5x + 즉시 내보내기(micro 4)        팔 path3 / mp
#   h5x5  5대(홀수)                            팔 path3 / mp
# 예측(predict_gain / fluidsim): h5x 경로만 −21%, 분할 추가 +23% (총비용); 즉시 내보내기 추가 −13% 안팎; h5x5 경로만 −35%, 분할 +12%.
set -u
cd "$(dirname "$0")/../.."
export PY=${PY:-$HOME/env/bin/python} SUDO=${SUDO:-sudo}
echo "### NET-EFFECT START $(date)"
for spec in "h5x:path3 mp" "h5xm:path3 mp" "h5x5:path3 mp"; do
  cond=${spec%%:*}; arms=${spec#*:}
  echo "### 조건 $cond 팔 [$arms]  $(date)"
  COND=$cond ARMS="$arms" bash scripts/exp/ablate_5.sh run
  rc=$?
  if [ $rc -ne 0 ]; then echo "### $cond 실패 rc=$rc — 멈춘다  $(date)"; exit $rc; fi
  if grep -lE "Traceback|재조립 불일치|시간 초과" out/${cond}_s*_*.log >/dev/null 2>&1; then
    echo "### $cond 로그에 오류 — 멈춘다"; grep -lE "Traceback|재조립 불일치|시간 초과" out/${cond}_s*_*.log; exit 1
  fi
  "$PY" scripts/analysis/mp_rounds.py $(ls out/wp_${cond}_s*_widthpath.jsonl | sed -E 's#out/wp_(.*)_widthpath.jsonl#\1#') 2>/dev/null | grep -E "^==|균등|계획" || true
done
echo "### NET-EFFECT DONE $(date)"
