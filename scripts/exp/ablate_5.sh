#!/usr/bin/env bash
# 절제 5판 드라이버 — 조건은 전부 원장(scripts/exp/conditions.json 의 h5)에서. 이 파일에는 숫자가 없다.
#
#   bash scripts/exp/ablate_5.sh check     # ① 규칙 시험(test_two_stage) ② 리그 자가 검사(rig_selftest) — 둘 다 통과해야 실험
#   bash scripts/exp/ablate_5.sh smoke     # 둘다 팔 1시드 2라운드 + 사전등록 §3-1 점검치
#   nohup bash scripts/exp/ablate_5.sh > out/ablate5.log 2>&1 < /dev/null &      # 본 실행: 팔 × 시드 (원장)
#   결과: out/wp_h5_s<시드>_<팔>_{uniform,widthpath}.jsonl (+ .args.json), out/h5_s<시드>_<팔>.log
#   판정: python scripts/analysis/ablate5_judge.py ; 표: python scripts/analysis/ablate_table.py h5_
set -u
cd "$(dirname "$0")/../.."
export PY=${PY:-$HOME/env/bin/python} SUDO=${SUDO:-sudo} PYTHONPATH=sfl
COND=${COND:-h5}
ARMS=${ARMS:-"path width both bothv1"}     # 돌릴 팔 — 연산 효과만이면 ARMS=width, 망 효과만이면 ARMS=path
MODE=${1:-run}

gate() {
  echo "== 게이트 ① 규칙 시험 =="
  "$PY" tests/test_two_stage.py > /dev/null && echo "   test_two_stage 통과" || { echo "   test_two_stage FAIL — 실험을 걸지 않는다"; return 1; }
  "$PY" tests/test_cond.py > /dev/null && echo "   test_cond 통과" || { echo "   test_cond FAIL"; return 1; }
  "$PY" tests/test_plan2.py > /dev/null && echo "   test_plan2 통과 (3층 계획기)" || { echo "   test_plan2 FAIL"; return 1; }
  "$PY" tests/test_mp_act.py > /dev/null && echo "   test_mp_act 통과 (조각 왕복)" || { echo "   test_mp_act FAIL"; return 1; }
  echo "== 게이트 ② 리그 자가 검사 (COND=$COND) =="
  $SUDO -E "$PY" scripts/measurement/rig_selftest.py --cond "$COND" --json "out/rig_selftest_${COND}.json" || { echo "   리그 자가 검사 FAIL — 실험을 걸지 않는다"; return 1; }
}

one() {  # 팔 시드 [라운드]
  local arm=$1 s=$2
  local tag="${COND}_s${s}_${arm}"
  echo "## $COND $arm 시드 $s  $(date +%H:%M:%S)"
  COND=$COND ARM=$arm SEED=$s ROUNDS_OVERRIDE=${3:-} TAG="${tag}_" bash scripts/exp/run_widthpath.sh > "out/${tag}.log" 2>&1 \
    && echo "[done] $tag" || echo "ERR $tag"
  grep -E "\[widthpath" "out/${tag}.log" | tail -1 | sed 's/^/   /'
  tail -2 "out/${tag}.log" | sed 's/^/   /'
}

checks() {  # 사전등록 §3-1 점검 — 균등 팔 jsonl 에서
  "$PY" - "$1" <<'PYEOF'
import json, io, sys, statistics as st
tag=sys.argv[1]
U=[json.loads(l) for l in io.open(f"out/wp_{tag}_uniform.jsonl",encoding="utf-8") if '"round"' in l][1:]
ks=sorted(U[0]["per_client_detail"])
for k in ks:
    cpu=st.median(r["per_client_detail"][k]["cli_fwd"]+r["per_client_detail"][k]["cli_bwd"] for r in U)
    xf=st.median(r["per_client_detail"][k]["xfer"] for r in U)
    print(f"  {k}: 연산 {cpu:5.2f}s  전송 {xf:5.2f}s  연산 몫 {100*cpu/(cpu+xf):3.0f}%  망 몫 {100*xf/(cpu+xf):3.0f}%")
PYEOF
}

case "$MODE" in
  check) gate ;;
  smoke) gate || exit 1; one $(echo $ARMS | cut -d" " -f1) 9 2; echo "== §3-1 점검 (균등 팔) =="; checks "${COND}_s9_$(echo $ARMS | cut -d" " -f1)" ;;
  run)
    gate || exit 1
    eval "$("$PY" scripts/exp/cond.py --env "$COND")"      # SEEDS
    echo "### 절제 5판 ($COND)  $(date)"; "$PY" scripts/exp/cond.py --table "$COND"
    for s in $SEEDS; do for arm in $ARMS; do one $arm $s; done; done
    echo "ABLATE5_DONE $COND  $(date)" ;;
  *) echo "usage: ablate_5.sh [check|smoke|run]"; exit 2 ;;
esac
