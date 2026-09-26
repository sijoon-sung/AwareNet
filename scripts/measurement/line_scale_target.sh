#!/usr/bin/env bash
# 회선 규모 측정 3차 — 목표 규모(32~64대, 50대 안)에서 tc 상한이 지켜지는 축소 비율 s 찾기. line_scale.sh 를 감싼다.
#   nohup bash scripts/measurement/line_scale_target.sh > out/line_scale3.log 2>&1 < /dev/null &
# 1·2차 결과: 실회선 합계 ≈ 0.9~1.0 Gbps. 50×70×s ≤ ~800 이면 s ≈ 0.25~0.3. 여기서는 s=0.3, 0.25 × N=32,40,48,56,64 를 TCP 왕복·버스트로 잰다.
set -u
cd "$(dirname "$0")/../.."
mv -f out/line_scale.jsonl out/line_scale_v2.jsonl 2>/dev/null
bash scripts/measurement/line_scale.sh "32 40 48 56 64" "0.3 0.25" "tcp:batch tcp:burst"
