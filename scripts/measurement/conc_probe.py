# -*- coding: utf-8 -*-
"""동시성에 따른 연결 응답 측정 — 붙는 클라이언트가 늘어날 때 경로·방화벽이 어떻게 반응하나.

    python scripts/measurement/conc_probe.py --target 116.89.187.190:12001 \
        --levels 1,4,16,32 --secs 6 --repeat 3 --tag vm1

동시 연결 수를 올려 가며 (1) 연결 왕복 중앙값·p95 (2) 초당 성립하는 연결 수 (3) 실패율을 잰다.
듣는 프로그램이 없어도(연결 거부) 왕복은 유효하므로 처리량 측정 전에도 쓸 수 있다.
연합학습에서 여러 대가 같은 순간에 붙는 상황의 경로 반응을 보는 용도다.
결과: out/probe/conc_<태그>.json. 표준 라이브러리만 쓴다.
"""
import argparse
import io
import json
import os
import socket
import statistics
import threading
import time


def worker(ip, port, deadline, timeout, out, lock):
    while time.time() < deadline:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        t0 = time.perf_counter()
        try:
            s.connect((ip, port))
            st, rtt = "open", (time.perf_counter() - t0) * 1000
        except ConnectionRefusedError:
            st, rtt = "refused", (time.perf_counter() - t0) * 1000
        except socket.timeout:
            st, rtt = "timeout", None
        except OSError:
            st, rtt = "error", None
        finally:
            s.close()
        with lock:
            out.append((st, rtt))


def level(ip, port, n, secs, timeout):
    out, lock = [], threading.Lock()
    dl = time.time() + secs
    th = [threading.Thread(target=worker, args=(ip, port, dl, timeout, out, lock)) for _ in range(n)]
    t0 = time.perf_counter()
    for t in th:
        t.start()
    for t in th:
        t.join()
    wall = time.perf_counter() - t0
    rtts = [r for st, r in out if r is not None]
    fail = sum(1 for st, r in out if r is None)
    rtts_sorted = sorted(rtts)
    p95 = rtts_sorted[min(len(rtts_sorted) - 1, int(0.95 * (len(rtts_sorted) - 1)))] if rtts else None
    return {"concurrency": n, "attempts": len(out), "wall_s": round(wall, 2),
            "rate_per_s": round(len(out) / max(wall, 1e-9), 1),
            "fail_pct": round(100 * fail / max(1, len(out)), 2),
            "median_ms": round(statistics.median(rtts), 3) if rtts else None,
            "p95_ms": round(p95, 3) if p95 else None,
            "max_ms": round(max(rtts), 3) if rtts else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, help="IP:포트")
    ap.add_argument("--levels", default="1,4,16,32")
    ap.add_argument("--secs", type=float, default=6)
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=3.0)
    ap.add_argument("--tag", default="conc")
    a = ap.parse_args()
    ip, port = a.target.rsplit(":", 1)
    port = int(port)
    rows = []
    print(f"{a.target} · 동시 {a.levels} · 각 {a.secs}초 · {a.repeat}회 반복", flush=True)
    for rep in range(1, a.repeat + 1):
        for n in [int(x) for x in a.levels.split(",") if x]:
            r = level(ip, port, n, a.secs, a.timeout)
            r["repeat"] = rep
            rows.append(r)
            print(f"  {rep}회 동시 {n:>3}: 중앙 {r['median_ms']}ms  p95 {r['p95_ms']}ms  "
                  f"초당 {r['rate_per_s']}건  실패 {r['fail_pct']}%", flush=True)
            time.sleep(2)
    summary = {}
    for n in sorted(set(r["concurrency"] for r in rows)):
        v = [r for r in rows if r["concurrency"] == n]
        summary[f"동시 {n}"] = {
            "중앙 ms": round(statistics.median([x["median_ms"] for x in v if x["median_ms"]]), 3),
            "p95 ms": round(statistics.median([x["p95_ms"] for x in v if x["p95_ms"]]), 3),
            "초당 건수": round(statistics.median([x["rate_per_s"] for x in v]), 1),
            "실패율 %": round(statistics.median([x["fail_pct"] for x in v]), 2)}
    os.makedirs(os.path.join("out", "probe"), exist_ok=True)
    p = os.path.join("out", "probe", f"conc_{a.tag}.json")
    io.open(p, "w", encoding="utf-8").write(json.dumps({"target": a.target, "rows": rows, "summary": summary},
                                                       ensure_ascii=False, indent=1))
    print("\n요약:", json.dumps(summary, ensure_ascii=False), "\n→", p, flush=True)


if __name__ == "__main__":
    main()
