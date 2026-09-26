#!/usr/bin/env bash
# 회선 규모 측정 스윕 (Shrink) — HPC 에서 실행. 학습 없음, 전송 패턴만.
#   bash scripts/measurement/line_scale.sh "16 32 48 64" "0.5" "tcp:batch tcp:burst tcp:paced udp:burst"   # N 목록, shrink 목록, 방식 목록 → out/line_scale.jsonl
# 접속 상한 = 50/20 × s (tc, real_rig.sh), 엣지 용량은 4000M (안 걺: 회선만 본다). 각 (s, N) 마다 리그를 새로 올린다.
set -u
cd "$(dirname "$0")/../.."
PY=${PY:-$HOME/env/bin/python}
NS=${1:-"8 16 32"}; SS=${2:-"1"}; MODES=${3:-"tcp:batch"}; ACC=${ACC:-"50/20"}; SINK=${SINK:-31950}
export BASE=${BASE:-12100} SRV_PORT=$((SINK - 1)) DEV=${DEV:-ens160}
pkill -f "line_scale[.]py sink" 2>/dev/null; sleep 0.5
"$PY" scripts/measurement/line_scale.py sink --port $SINK > out/line_sink.log 2>&1 &
SINKPID=$!; sleep 1
echo "### LINE-SCALE START $(date)  N=[$NS] s=[$SS] modes=[$MODES] acc=$ACC"
for s in $SS; do
  aA=$(echo "$ACC" | cut -d/ -f1); aB=$(echo "$ACC" | cut -d/ -f2)
  sA=$("$PY" -c "print(max(1, round($aA*$s)))"); sB=$("$PY" -c "print(max(1, round($aB*$s)))")
  for N in $NS; do
    acc_list=$(for i in $(seq 1 $N); do printf "%s/%s " $sA $sB; done)
    echo "## s=$s N=$N 접속 $sA/$sB  $(date +%H:%M:%S)"
    bash sfl/net/real_rig.sh up $N "$acc_list" "4000 4000 4000 4000" > out/line_rig_${s}_${N}.log 2>&1 || { echo "리그 실패 (out/line_rig_${s}_${N}.log)"; bash sfl/net/real_rig.sh down > /dev/null 2>&1; continue; }
    EDGES=$(bash sfl/net/real_rig.sh edges)
    for mode in $MODES; do
      proto=${mode%%:*}; pat=${mode##*:}
      echo "   [$proto $pat]"
      timeout 900 "$PY" scripts/measurement/line_scale.py load --n $N --edges "$EDGES" --acc "$ACC" --shrink $s --proto $proto --pattern $pat --out out/line_scale.jsonl | sed 's/^/   /'
      sleep 3
    done
    bash sfl/net/real_rig.sh down > /dev/null 2>&1
  done
done
kill $SINKPID 2>/dev/null
echo "### LINE-SCALE DONE $(date)"
"$PY" - <<'PYEOF'
import json, io
rows = [json.loads(l) for l in io.open("out/line_scale.jsonl", encoding="utf-8")]
print(f"{'방식':12s} {'s':>5s} {'N':>4s} {'상한(M)':>8s} {'기기당 실효(M)':>13s} {'N=최소 대비':>10s} {'합계(M)':>9s} {'배치 p90(s)':>11s} {'UDP도달':>7s}")
base = {}
for r in rows:
    key = (r.get("proto", "tcp"), r.get("pattern", "batch"), r["shrink"]); base.setdefault(key, r["per_client_mbps_median"])
    agg = r["n"] * r["per_client_mbps_median"]                       # 합계 = N × 기기당 실효 (wall 은 첫 연결 정체가 섞여 못 쓴다)
    ud = f"{100*r['udp_delivered']:5.0f}%" if "udp_delivered" in r else "     -"
    print(f"{key[0]+':'+key[1]:12s} {r['shrink']:5.2f} {r['n']:4d} {r['cap_mbps']:8.1f} {r['per_client_mbps_median']:13.1f} {r['per_client_mbps_median']/max(1e-9, base[key]):10.2f} {agg:9.0f} {r['batch_s_p90']:11.2f} {ud:>7s}")
print("읽는 법: 'N=최소 대비'(같은 s 의 가장 작은 N 에서 잰 기기당 속도 대비)가 0.9 아래로 내려가는 첫 N 이 그 s 에서의 회선 병목 규모. 그때의 합계가 실회선(터널 포함) 용량.")
PYEOF
