# -*- coding: utf-8 -*-
"""네트워크 실측 시스템의 Prometheus 익스포터 — PC 에서 돌리고 그라파나(monitoring/)가 읽는다.

    python scripts/measurement/net_exporter.py                       # http://localhost:9108/metrics
    python scripts/measurement/net_exporter.py --interval 30 --remotes hpc=koren-hpc,vm1=koren-vm,vm2=koren-vm2

한 주기마다:
  1) 이 호스트에서 직접 TCP 왕복 프로브 (--local-targets, 기본: VM1·VM2 의 22·12001·26022)
  2) 원격 호스트(ssh 별칭)의 out/probe/link_probe.jsonl 꼬리를 ssh 로 읽어 최신 측정을 게이지로 노출
     (원격 프로브는 link_probe.py 로 각 호스트에서 따로 돌린다. ssh 가 안 되는 호스트는 조용히 건너뛴다)
  3) HPC 의 실험 진행: GPU 사용률·메모리, 최근 10분 안에 갱신된 out/*.jsonl 의 마지막 라운드(라운드·makespan·정확도·폭)
지표 이름은 전부 awarenet_ 로 시작한다. 표준 라이브러리만 쓴다.
"""
import argparse
import io
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from link_probe import parse_targets, probe_once  # noqa: E402

STATE_CODE = {"open": 2, "refused": 1, "timeout": 0, "error": -1}
LOCK = threading.Lock()
METRICS = {"lines": [], "updated": 0.0}


def ssh(host, cmd, timeout=25):
    """host 가 "" 또는 "local" 이면 같은 호스트에서 그냥 실행한다 (HPC·VM 안에서 돌릴 때)."""
    argv = (["bash", "-lc", cmd] if host in ("", "local")
            else ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6", host, cmd])
    try:
        r = subprocess.run(argv,
                           capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None


def esc(v):
    return str(v).replace("\\", "\\\\").replace('"', '\\"')


def line(name, labels, value):
    if value is None:
        return None
    lab = ",".join(f'{k}="{esc(v)}"' for k, v in labels.items())
    return f"{name}{{{lab}}} {value}"


def collect_local(src, targets):
    out = []
    for name, ip, port in targets:
        state, rtt, n = probe_once(ip, port, tries=2, timeout=2.0)
        lab = {"src": src, "dst": name, "ip": ip, "port": port}
        out.append(line("awarenet_tcp_state", lab, STATE_CODE.get(state, -1)))
        out.append(line("awarenet_tcp_rtt_ms", lab, rtt))
    return out


def collect_remote_probe(src, host, path):
    txt = ssh(host, f"tail -n 60 {path} 2>/dev/null")
    if not txt:
        return [line("awarenet_remote_reachable", {"host": src}, 0)]
    latest = {}
    for l in txt.splitlines():
        try:
            r = json.loads(l)
        except Exception:
            continue
        latest[(r.get("kind", "tcp"), r["dst"], r["port"])] = r
    out = [line("awarenet_remote_reachable", {"host": src}, 1)]
    newest = 0
    for (kind, dst, port), r in latest.items():
        lab = {"src": src, "dst": dst, "ip": r.get("ip", ""), "port": port}
        newest = max(newest, r.get("ts", 0))
        if kind == "tcp":
            out.append(line("awarenet_tcp_state", lab, STATE_CODE.get(r.get("state"), -1)))
            out.append(line("awarenet_tcp_rtt_ms", lab, r.get("rtt_ms")))
        elif kind == "iperf":
            out.append(line("awarenet_iperf_mbps", lab, r.get("mbps")))
    if newest:
        out.append(line("awarenet_probe_age_seconds", {"src": src}, round(time.time() - newest, 1)))
    return out


HPC_CMD = r'''cd ~/awarenet 2>/dev/null || exit 0
nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits 2>/dev/null | head -1 | sed "s/^/GPU /"
# 홈이 NFS 라 파일 mtime 이 이 장비 시계보다 1시간쯤 뒤처진다. 그래서 "지금"도 같은 파일 시스템에서 얻어
# 상대 나이로 비교한다 (mmin 을 쓰면 방금 쓴 파일도 오래된 것으로 걸러진다).
touch out/.nowmark 2>/dev/null
NOW=$(date -r out/.nowmark +%s 2>/dev/null || date +%s)
for f in $(ls -t out/*.jsonl 2>/dev/null | head -8); do
  T=$(date -r "$f" +%s 2>/dev/null || echo 0)
  AGE=$((NOW - T))
  [ "$AGE" -lt 900 ] || continue                               # 최근 15분 안에 갱신된 것만
  echo "FILE $f $AGE"; tail -n 1 "$f"
done
pgrep -af "run_widthpath|run_l1|run_l2|run_l3|run_rw|fed_server" 2>/dev/null | grep -v pgrep | wc -l | sed "s/^/PROCS /"
grep -h "^== " out/batch_net.log 2>/dev/null | tail -1 | sed "s/^== /STAGE /;s/ ==$//"
'''


def collect_hpc(host):
    txt = ssh(host, HPC_CMD)
    if txt is None:
        return []
    out = []
    lines = txt.splitlines()
    i = 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("GPU "):
            parts = [p.strip() for p in l[4:].split(",")]
            if len(parts) >= 3:
                out.append(line("awarenet_gpu_util_percent", {"host": "hpc"}, parts[0]))
                out.append(line("awarenet_gpu_mem_used_mib", {"host": "hpc"}, parts[1]))
                out.append(line("awarenet_gpu_mem_total_mib", {"host": "hpc"}, parts[2]))
        elif l.startswith("STAGE "):
            out.append(line("awarenet_batch_stage", {"host": "hpc", "stage": l[6:].strip()}, 1))
        elif l.startswith("PROCS "):
            out.append(line("awarenet_exp_processes", {"host": "hpc"}, l[6:].strip()))
        elif l.startswith("FILE ") and i + 1 < len(lines):
            parts = l[5:].strip().rsplit(" ", 1)
            age = parts[1] if len(parts) == 2 and parts[1].isdigit() else None
            run = os.path.basename(parts[0]).replace(".jsonl", "")
            try:
                r = json.loads(lines[i + 1])
            except Exception:
                r = {}
            i += 1
            if "round" in r:
                lab = {"host": "hpc", "run": run, "policy": r.get("policy", "")}
                out.append(line("awarenet_run_age_seconds", lab, age))
                out.append(line("awarenet_run_round", lab, r["round"]))
                out.append(line("awarenet_run_makespan_seconds", lab, r.get("makespan")))
                if r.get("acc") is not None:
                    out.append(line("awarenet_run_accuracy", lab, r["acc"]))
                for c, w in (r.get("plan") or {}).items():
                    out.append(line("awarenet_run_width", dict(lab, client=c), w))
                for c, d in (r.get("per_client_detail") or {}).items():
                    out.append(line("awarenet_run_client_comm_seconds", dict(lab, client=c), d.get("t_comm")))
                    out.append(line("awarenet_run_client_up_bytes", dict(lab, client=c), d.get("up_bytes")))
            elif "upload_wall" in r:   # run_l3_net
                lab = {"host": "hpc", "run": run, "policy": r.get("policy", "")}
                out.append(line("awarenet_run_round", lab, r.get("round")))
                out.append(line("awarenet_run_makespan_seconds", lab, r.get("upload_wall")))
        i += 1
    return out


def loop(a):
    local_targets = parse_targets(a.local_targets) if a.local_targets else []
    remotes = [x.split("=", 1) for x in a.remotes.split(",") if x.strip()]
    while True:
        t0 = time.time()
        lines = ["# HELP awarenet_tcp_state 2=open 1=refused(도달, 방화벽 열림) 0=timeout(차단) -1=error",
                 "# TYPE awarenet_tcp_state gauge", "# TYPE awarenet_tcp_rtt_ms gauge",
                 "# TYPE awarenet_iperf_mbps gauge", "# TYPE awarenet_run_round gauge"]
        try:
            lines += collect_local(a.src, local_targets)
        except Exception as e:
            print("local probe error", e, file=sys.stderr)
        if a.local_runs:                      # 같은 호스트의 실험 진행을 직접 읽는다 (ssh 없이)
            try:
                lines += collect_hpc("")
            except Exception as e:
                print("local runs error", e, file=sys.stderr)
        for src, host in remotes:
            try:
                lines += collect_remote_probe(src, host, a.remote_path)
                if src == "hpc":
                    lines += collect_hpc(host)
            except Exception as e:
                print("remote", src, "error", e, file=sys.stderr)
        lines.append(line("awarenet_exporter_cycle_seconds", {}, round(time.time() - t0, 2)))
        with LOCK:
            METRICS["lines"] = [l for l in lines if l]
            METRICS["updated"] = time.time()
        print(time.strftime("%H:%M:%S"), f"{len(METRICS['lines'])} 지표, {time.time()-t0:.1f}s", flush=True)
        time.sleep(max(1.0, a.interval - (time.time() - t0)))


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/metrics"):
            with LOCK:
                body = "\n".join(METRICS["lines"]) + "\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))
        else:
            self.send_response(200); self.end_headers()
            self.wfile.write(b"awarenet net exporter: /metrics\n")

    def log_message(self, *args):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9108)
    ap.add_argument("--interval", type=float, default=30)
    ap.add_argument("--local-targets", default="vm1=116.89.187.190:22,vm1=116.89.187.190:12001,vm1=116.89.187.190:26022,"
                                                 "vm2=116.89.187.189:22,vm2=116.89.187.189:12001,vm2=116.89.187.189:26022")
    ap.add_argument("--src", default="pc", help="이 호스트 이름표 — 직접 재는 프로브에 붙는다")
    ap.add_argument("--remotes", default="hpc=koren-hpc,vm1=koren-vm,vm2=koren-vm2",
                    help="이름=ssh별칭 을 쉼표로. 빈 값이면 원격 수집을 하지 않는다")
    ap.add_argument("--local-runs", action="store_true",
                    help="같은 호스트의 out/*.jsonl·GPU 를 ssh 없이 읽는다 (HPC·VM 안에서 돌릴 때)")
    ap.add_argument("--remote-path", default="~/awarenet/out/probe/link_probe.jsonl")
    a = ap.parse_args()
    threading.Thread(target=loop, args=(a,), daemon=True).start()
    print(f"exporter http://localhost:{a.port}/metrics", flush=True)
    HTTPServer(("0.0.0.0", a.port), H).serve_forever()


if __name__ == "__main__":
    main()
