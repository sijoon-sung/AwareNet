#!/usr/bin/env bash
# 절제 '폭만' 팔 재실행 — 2판 오염분을 현재 코드로 다시 잰다 (docs/02_실험/실험_절제_조건표_복원.md §4-1, §7-1).
#
#   오염분: 4대 100/50 시드 1·2·3, 8대 200/40 시드 1 — `max_moves<=0` 분기(2026-09-06 01:13) 이전에 돌아
#           '폭만'인데 경로를 옮겼다. 유효분(8대 200/40 s2·s3, 8대 200/100, 16대)은 다시 돌리지 않는다.
#   드라이버를 저장소에 두는 이유: 2판 드라이버가 이전 PC 에만 있다가 유실됐다.
#
#   HPC 에서:
#     bash scripts/exp/ablate_rerun_width.sh smoke     # 2라운드 — 로그에 '경로 고정' 이 찍히는지만 본다
#     nohup bash scripts/exp/ablate_rerun_width.sh > out/ablate_rw.log 2>&1 < /dev/null &
#   결과: out/wp_<조건>r_s<시드>_width_{uniform,widthpath}.jsonl (+ .args.json), 요약은 각 out/<조건>r_s<시드>_width.log 끝.
#
#   스레드: 16코어 ÷ 대수 (4대 4, 8대 2). 2판 8대의 연산 1.27초/라운드가 재현되는지로 2판 설정을 역추정한다.
set -u
cd "$(dirname "$0")/../.."
export PY=${PY:-$HOME/env/bin/python} SUDO=${SUDO:-sudo} PYTHONPATH=sfl
LAD=${LAD:-"0.5,0.75,1.0"}
MODE=${1:-run}

# 실험 전 게이트 — 폭만 팔이 경로를 안 옮기는지 단위 시험이 먼저 통과해야 한다
"$PY" tests/test_two_stage.py > /dev/null || { echo "test_two_stage FAIL — 실험을 걸지 않는다"; exit 1; }

one() {  # cond caps_setup caps_arg clients threads seed [rounds]
  local cond=$1 cs=$2 ca=$3 n=$4 th=$5 s=$6 r=${7:-12}
  local tag="${cond}r_s${s}_width"
  echo "## $cond 시드 $s 폭만 (threads $th, rounds $r)  $(date +%H:%M:%S)"
  CAPS_SETUP="$cs" CAPS_ARG="$ca" CLIENTS=$n THREADS=$th SEED=$s ROUNDS=$r \
    TAG="${tag}_" EXTRA="--max-moves 0 --ladder $LAD" \
    bash scripts/exp/run_widthpath.sh > "out/${tag}.log" 2>&1 \
    && echo "[done] $tag" || echo "ERR $tag"
  grep -cE "경로 고정" "out/${tag}.log" | sed 's/^/   경로 고정 문구 수: /'
  grep -E "경로 이동" "out/${tag}.log" | head -1 | sed 's/^/   !! 이동 발생: /'
  tail -2 "out/${tag}.log" | sed 's/^/   /'
}

if [ "$MODE" = "smoke" ]; then
  one c4_10050 "100 50" "100,50" 4 4 9 2
  exit 0
fi

echo "### 절제 폭만 팔 재실행 — 현재 코드 (controller max_moves<=0 분기 포함)  $(date)"
for s in 1 2 3; do one c4_10050 "100 50" "100,50" 4 4 $s; done
one c8_20040 "200 40" "200,40" 8 2 1
echo "ABLATE_RW_DONE  $(date)"
