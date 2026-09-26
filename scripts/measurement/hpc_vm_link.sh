#!/usr/bin/env bash
# HPC ↔ KOREN VM 링크 실측 — 로컬(git-bash)에서 실행. 결과는 out/measure/hpc_vm_*.txt
#
#   bash scripts/measurement/hpc_vm_link.sh reach     # 도달·RTT (VM 로그인 불필요) — HPC → VM 22/12001/26022, ICMP, 경로
#   bash scripts/measurement/hpc_vm_link.sh iperf     # 처리량 HPC → VM (VM 에 iperf3 서버를 띄워야 하므로 VM SSH 가 되는 곳에서)
#
# 사실 관계 (2026-09-02): HPC 출구 116.89.174.50 → VM 116.89.187.190/.189 의 TCP 22·10000~15000 은 열림(연결 거부 = 도달),
# 26022 와 ICMP 는 차단. VM → HPC 방향은 HPC 가 사설 IP 라 불가. 따라서 처리량은 HPC 가 클라이언트(iperf3 -c), VM 이 서버.
set -e
cd "$(dirname "$0")/../.."
H=koren-hpc; V1=koren-vm; IP1=116.89.187.190; IP2=116.89.187.189; PORT=12005
mkdir -p out/measure
TS=$(date +%Y%m%d_%H%M)
MODE="${1:-reach}"

ssh -o ConnectTimeout=8 -o BatchMode=yes $H 'echo ok' >/dev/null || { echo "HPC 접속 불가 — 런처를 켜세요"; exit 1; }

case "$MODE" in
  reach)
    ssh $H "python3 - <<'EOF'
import socket, time, statistics
for host in ('$IP1','$IP2'):
    for port in (22, $PORT, 26022):
        ts=[]; res=None
        for i in range(10):
            s=socket.socket(); s.settimeout(4); t=time.perf_counter()
            try: s.connect((host,port)); res='OPEN'
            except ConnectionRefusedError: res='REFUSED(도달)'
            except socket.timeout: res='TIMEOUT(차단)'
            except Exception as e: res=type(e).__name__
            ts.append((time.perf_counter()-t)*1000); s.close()
        print(f'HPC -> {host}:{port:5d} {res:14s} rtt median {statistics.median(ts):6.1f} ms  p90 {sorted(ts)[8]:6.1f} ms')
EOF
ping -c 5 -W 2 $IP1 | tail -1; tracepath -n -m 12 $IP1 | head -14" | tee "out/measure/hpc_vm_reach_$TS.txt" ;;
  iperf)
    echo "── VM1 에 iperf3 서버(:$PORT) 기동 (VM SSH 필요)"
    ssh $V1 "pkill -f 'iperf3 -s -p $PORT' 2>/dev/null; nohup iperf3 -s -p $PORT > /tmp/iperf_$PORT.log 2>&1 < /dev/null & echo started" || { echo "VM1 SSH 불가 — 연구실 회선에서 실행하거나 sshd Port 22 추가"; exit 1; }
    sleep 2
    echo "── HPC → VM1 처리량 (10초 × 1스트림, 4스트림)"
    ssh $H "iperf3 -c $IP1 -p $PORT -t 10 -J | python3 -c \"import json,sys; d=json.load(sys.stdin); print('1스트림 송신', round(d['end']['sum_sent']['bits_per_second']/1e6,1), 'Mbps  수신', round(d['end']['sum_received']['bits_per_second']/1e6,1), 'Mbps')\"; iperf3 -c $IP1 -p $PORT -t 10 -P 4 -J | python3 -c \"import json,sys; d=json.load(sys.stdin); print('4스트림 송신', round(d['end']['sum_sent']['bits_per_second']/1e6,1), 'Mbps  수신', round(d['end']['sum_received']['bits_per_second']/1e6,1), 'Mbps')\"" | tee "out/measure/hpc_vm_iperf_$TS.txt"
    ssh $V1 "pkill -f 'iperf3 -s -p $PORT' || true" ;;
  *) echo "usage: hpc_vm_link.sh reach|iperf"; exit 2 ;;
esac
