#!/usr/bin/env bash
# 두 갈래 실험을 순서대로 — ① 연산 효과(h5c, 폭만) ② 네트워크 효과(h5n, 경로만) ③ 폭별 정확도 대가(rw_long, 밤샘)
#   nohup bash scripts/exp/run_tracks.sh > out/tracks.log 2>&1 < /dev/null &
# 각 단계는 자기 게이트(규칙 시험 + 리그 자가 검사)를 통과해야 돈다.
set -u
cd "$(dirname "$0")/../.."
echo "### 두 갈래 실험 시작  $(date)"
COND=h5c ARMS="width" bash scripts/exp/ablate_5.sh run || echo "ERR h5c"
COND=h5n ARMS="path"  bash scripts/exp/ablate_5.sh run || echo "ERR h5n"
bash scripts/exp/rw_long.sh run || echo "ERR rw_long"
echo "TRACKS_DONE  $(date)"
