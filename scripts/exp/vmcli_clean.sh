#!/usr/bin/env bash
# VM 클라 실험 전체 정리 (HPC 에서 실행): bash scripts/exp/vmcli_clean.sh
# pkill 패턴이 호출 명령줄(ssh "…")에 나오면 자기 세션을 죽인다 → 파일로 둔다. VM 쪽은 [.] 로 자기 제외.
cd ~/awarenet
pkill -f "scripts/exp/run_real.sh" 2>/dev/null
pkill -f "scripts/exp/run_vmcli.sh" 2>/dev/null
pkill -f "sfl/fed_server.py" 2>/dev/null
pkill -f "ssh .*fed_client.py" 2>/dev/null
sleep 1
bash sfl/net/real_rig.sh down >/dev/null 2>&1
for h in 116.89.187.190 116.89.187.189; do
  ssh -o BatchMode=yes -o ConnectTimeout=10 -p 26022 ubuntu@$h 'pkill -f "sfl/fed_client[.]py"; sleep 0.5; echo "$(hostname) clients left: $(pgrep -fc "sfl/fed_client[.]py" || echo 0)"'
done
echo "HPC run_real/fed_server left: $(pgrep -fc "run_real.sh|fed_server.py" || echo 0)   ssh -R left: $(ps -ef | grep -c "[s]sh .*-R ")"
