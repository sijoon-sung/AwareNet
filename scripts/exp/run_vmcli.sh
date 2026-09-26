#!/usr/bin/env bash
# VM 클라 판 (2026-09-12): 기기 8대가 KOREN VM 두 대에 살고 서버는 HPC. 정상 / 몰림(R8 엣지 1 용량 1/4, R20 복구) 두 장면, 균등 vs 계획.
#   nohup bash scripts/exp/run_vmcli.sh > out/vmcli.log 2>&1 < /dev/null &
# 전제: 두 VM 의 ~/awarenet 코드가 HPC 와 같고(.venv torch cpu, data/cifar10), HPC → VM ssh 키. 결과 out/wp_vmcli_<장면>_s1_bothmp_{uniform,widthpath}.jsonl
set -u
cd "$(dirname "$0")/../.."
export PY=${PY:-$HOME/env/bin/python} VMCLI=${VMCLI:-1} SAME_GROUPS=1 REUSE_UNIFORM=0 UNIFORM_MP=0   # VMCLI=0 PFX=hpccli 면 같은 조건·같은 엣지 그룹을 HPC 안 기기로 (비교판)
PFX=${PFX:-vmcli}
SCEN=${SCEN:-"normal traffic"}
echo "### VMCLI START $(date)  [$SCEN] VMCLI=$VMCLI PFX=$PFX"
for sc in $SCEN; do
  tag="${PFX}_${sc}_s1_bothmp"
  for p in $(pgrep -f "sfl/fed_(server|client)[.]py"); do kill $p 2>/dev/null; done; sleep 1
  for host in 116.89.187.190 116.89.187.189; do ssh -o BatchMode=yes -o ConnectTimeout=10 -p 26022 ubuntu@$host "pkill -f 'sfl/fed_client[.]py' 2>/dev/null; true"; done
  echo "## $sc  $(date +%H:%M:%S)"
  WPID=""
  if [ "$sc" = "traffic" ]; then
    rm -f out/wp_${tag}_uniform.jsonl out/wp_${tag}_widthpath.jsonl
    ( bash scripts/exp/scenario_perturb.sh out/wp_${tag}_uniform.jsonl 0 31 125 8 20; bash scripts/exp/scenario_perturb.sh out/wp_${tag}_widthpath.jsonl 0 31 125 8 20 ) > out/${tag}_perturb.log 2>&1 &
    WPID=$!
  fi
  COND=v8mix ARM=bothmp SEED=1 TAG="${tag}_" timeout 5400 bash scripts/exp/run_real.sh > "out/$tag.log" 2>&1; rc=$?
  bash sfl/net/real_rig.sh down > /dev/null 2>&1
  [ -n "$WPID" ] && { wait $WPID 2>/dev/null; sed 's/^/   /' out/${tag}_perturb.log; }
  if [ $rc -ne 0 ] || grep -qE "Traceback|OSError" "out/$tag.log"; then echo "### $sc 실패 rc=$rc — 멈춘다"; exit 1; fi
  grep -E "균등   |계획   " "out/$tag.log" | sed 's/^/   /'
done
echo "### VMCLI DONE $(date)"
