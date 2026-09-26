# -*- coding: utf-8 -*-
"""링크 실측 프로브 — 어느 호스트에서든 돌려서 다른 호스트까지의 TCP 왕복·도달성을 주기적으로 남긴다.

    python scripts/measurement/link_probe.py --src hpc \
        --targets vm1=116.89.187.190:22,vm1=116.89.187.190:12001,vm2=116.89.187.189:22 \
        --interval 30 --out out/probe/link_probe.jsonl

한 줄 = 한 측정: {"ts", "src", "dst", "ip", "port", "state", "rtt_ms", "n_ok"}
  state: open(듣는 프로그램 있음) / refused(도달했지만 안 들음 = 방화벽 열림) / timeout(차단) / error
  rtt_ms: TCP 연결 왕복 중앙값 (open·refused 모두 도달까지의 시간이라 유효). ICMP 가 막힌 KOREN 에서도 된다.
선택: --iperf vm1=116.89.187.190:12005 를 주면 iperf3 클라이언트로 처리량(Mbps)도 같은 파일에 남긴다
  ({"kind":"iperf", ...}). 상대 쪽에 iperf3 -s -p 12005 가 떠 있어야 한다.
표준 라이브러리만 쓴다. 그라파나 쪽(net_exporter.py)이 이 파일의 마지막 줄들을 읽어 간다.
"""
import argparse
import io
import json
import os
import shutil
import socket
import statistics
import subprocess
import time


def probe_once(ip, port, tries=5, timeout=3.0):
    rtts, states = [], []
    for _ in range(tries):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        t0 = time.perf_counter()
        try:
            s.connect((ip, port))
            states.append("open")
            rtts.append((time.perf_counter() - t0) * 1000)
        except ConnectionRefusedError:
            states.append("refused")
            rtts.append((time.perf_counter() - t0) * 1000)
        except socket.timeout:
            states.append("timeout")
        except OSError:
            states.append("error")
        finally:
            s.close()
        time.sleep(0.2)
    state = max(set(states), key=states.count)
    rtt = round(statistics.median(rtts), 2) if rtts else None
    return state, rtt, len(rtts)


def iperf_once(ip, port, secs=5):
    if not shutil.which("iperf3"):
        return None
    try:
        r = subprocess.run(["iperf3", "-c", ip, "-p", str(port), "-t", str(secs), "-J"],
                           capture_output=True, text=True, timeout=secs + 15)
        d = json.loads(r.stdout)
        bps = d["end"]["sum_sent"]["bits_per_second"]
        return round(bps / 1e6, 2)
    except Exception:
        return None


def parse_targets(spec):
    out = []
    for item in [x for x in spec.split(",") if x.strip()]:
        name, addr = item.split("=", 1)
        ip, port = addr.rsplit(":", 1)
        out.append((name.strip(), ip.strip(), int(port)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="이 호스트 이름표 (hpc / pc / vm1 / vm2)")
    ap.add_argument("--targets", required=True, help="이름=IP:포트 를 쉼표로")
    ap.add_argument("--iperf", default="", help="이름=IP:포트 (iperf3 서버) 를 쉼표로, 선택")
    ap.add_argument("--interval", type=float, default=30)
    ap.add_argument("--out", default="out/probe/link_probe.jsonl")
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    targets = parse_targets(a.targets)
    iperfs = parse_targets(a.iperf) if a.iperf else []
    while True:
        t_cycle = time.time()
        rows = []
        for name, ip, port in targets:
            state, rtt, n = probe_once(ip, port)
            rows.append({"ts": round(time.time(), 1), "kind": "tcp", "src": a.src, "dst": name,
                         "ip": ip, "port": port, "state": state, "rtt_ms": rtt, "n_ok": n})
        for name, ip, port in iperfs:
            mbps = iperf_once(ip, port)
            rows.append({"ts": round(time.time(), 1), "kind": "iperf", "src": a.src, "dst": name,
                         "ip": ip, "port": port, "mbps": mbps})
        with io.open(a.out, "a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(time.strftime("%H:%M:%S"), " ".join(
            f"{r['dst']}:{r['port']}={r.get('state', r.get('mbps'))}"
            + (f"({r['rtt_ms']}ms)" if r.get("rtt_ms") is not None else "") for r in rows), flush=True)
        if a.once:
            break
        time.sleep(max(0.0, a.interval - (time.time() - t_cycle)))


if __name__ == "__main__":
    main()
