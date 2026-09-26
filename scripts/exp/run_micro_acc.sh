#!/usr/bin/env bash
# 즉시 내보내기 정확도 절제 — h5xa(4대 50/20, 경로 150/150) 60R × 2시드. 팔: path3(m=1) / path3m(m=4) / path3m2(m=2). 정확도는 마지막 20R 평균.
#   nohup bash scripts/exp/run_micro_acc.sh > out/micro_acc2.log 2>&1 < /dev/null &
# 내력: 1차(9/8 밤, out/micro_v1/)는 GN 팔 포함 5팔 — GN 은 자체 −15%p 라 제외. 서버 조각 누적 결함(fed_server.micro_step) 수정 뒤 2차.
#       ARMS 로 팔을 고를 수 있다. 균등 기준선은 조건·시드당 한 번(run_widthpath.sh 재사용).
set -u
cd "$(dirname "$0")/../.."
export PY=${PY:-$HOME/env/bin/python} SUDO=${SUDO:-sudo}
ARMS=${ARMS:-"path3 path3m path3m2"}
echo "### MICRO-ACC START $(date)  arms=[$ARMS]"
COND=h5xa ARMS="$ARMS" bash scripts/exp/ablate_5.sh run
echo "### MICRO-ACC rc=$? $(date)"
"$PY" - <<'PYEOF'
import json, io, glob, re, statistics as st
rows = {}
for f in sorted(glob.glob("out/wp_h5xa_s*_*_widthpath.jsonl")):
    tag = re.sub(r"^out/wp_h5xa_|_widthpath\.jsonl$", "", f); s, arm = tag.split("_", 1)
    if s == "s9": continue
    R = [json.loads(l) for l in io.open(f, encoding="utf-8") if '"round"' in l]
    if len(R) < 10: continue
    rows.setdefault(arm, []).append((st.mean(r["acc"] for r in R[-20:]), st.mean(r["makespan"] for r in R[6:])))
name = {"path3": "m=1 BN", "path3m": "m=4 BN", "path3m2": "m=2 BN", "path3m_gn": "m=4 GN", "path3_gn": "m=1 GN"}
for arm in ("path3", "path3m", "path3m2", "path3m_gn", "path3_gn"):
    if arm in rows:
        v = rows[arm]; print(f"{name[arm]:10s} n={len(v)} 정확도 {100*st.mean(a for a,_ in v):5.1f}%  라운드 {st.mean(m for _,m in v):5.2f}s  시드별 {[round(100*a,1) for a,_ in v]}")
PYEOF
echo "### MICRO-ACC DONE $(date)"
