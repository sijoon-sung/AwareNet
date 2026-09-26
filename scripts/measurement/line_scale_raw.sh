#!/usr/bin/env bash
# 회선 규모 측정 (맨 회선) — tc 상한 없이, 기기 수만 늘려 HPC → KOREN VM → 역터널 → HPC 실회선이 몇 대에서 얼마나 나눠 주는지 잰다.
#   nohup bash scripts/measurement/line_scale_raw.sh > out/line_raw.log 2>&1 < /dev/null &
# 본실험에서는 이 회선 위에 tc 로 접속·엣지 상한을 비율(Shrink)대로 건다. 그 비율을 정하려면 맨 회선의 N별 몫이 먼저 필요하다 (사용자 지시 9/9).
# 접속 "4000/4000", 엣지 4000 = 사실상 상한 없음 (real_rig.sh 가 tc 를 걸지만 4 Gbit 천장). 패턴: 학습 왕복(batch) · 버스트.
set -u
cd "$(dirname "$0")/../.."
mv -f out/line_scale.jsonl out/line_scale_v3_tc.jsonl 2>/dev/null
ACC="4000/4000" bash scripts/measurement/line_scale.sh "${1:-8 16 32 48 64 96}" "1" "${2:-tcp:batch tcp:burst}"
