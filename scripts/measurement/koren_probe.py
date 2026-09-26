# -*- coding: utf-8 -*-
"""정밀 프로브 클라이언트 — 사전 등록 비교(C1~C5)를 한 번에 잰다.

  정밀 수칙 (docs/02_실험/실측_프로토콜_KOREN.md):
    · 여러 표적을 **A/B 교차**(같은 분 안에 번갈아) — 시간대 편향 제거
    · fresh(새 연결 = 핸드셰이크+slow start 포함, 실사용값)와
      steady(재사용 연결 = 정상상태)를 **둘 다, 라벨 갈라** 잰다
    · perf_counter_ns · TCP_NODELAY · 웜업 1회 버림 · p5/50/95/99 + 지터(IQR)
    · 리눅스면 ss -ti 로 재전송 카운트 전후차 기록 (손실 대리)

  예 (판교 vs 상용 경유를 동시 비교):
    python3 koren_probe.py --targets koren=10.x.x.x:9099,inet=x.x.x.x:9099 \
        --label pc_home --rtt-n 200 --sizes 1,4,8.39 --reps 3 --burst-k 13
  산출: out/measure/probe_<label>_<UTC>.json → koren_compare.py 로 비교표
"""
import argparse
import datetime
import io
import json
import os
import platform
import socket
import statistics as st
import subprocess
import sys
import threading
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "out", "measure")
CHUNK = 65536
NS = 1e9


def now():
    return time.perf_counter_ns()


def conn(hp, timeout=15):
    h, p = hp.rsplit(":", 1)
    c = socket.create_connection((h, int(p)), timeout=timeout)
    c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    return c


def req(c, op, n, payload=False):
    c.sendall(op.encode() + n.to_bytes(8, "big"))
    if op == "E":
        c.sendall(b"\x2a" * n)
        left = n
        while left:
            b = c.recv(min(CHUNK, left))
            if not b:
                raise ConnectionError
            left -= len(b)
    elif op == "U":
        buf = b"\x55" * CHUNK
        left = n
        while left:
            m = min(CHUNK, left)
            c.sendall(buf[:m])
            left -= m
        ack = b""
        while len(ack) < 8:
            b = c.recv(8 - len(ack))
            if not b:
                raise ConnectionError
            ack += b
    elif op == "D":
        left = n
        while left:
            b = c.recv(min(CHUNK, left))
            if not b:
                raise ConnectionError
            left -= len(b)


def pct(v):
    if not v:
        return {}
    s = sorted(v)
    q = lambda p: s[min(len(s) - 1, int(p / 100 * len(s)))]
    return {"n": len(s), "p5": q(5), "p50": q(50), "p95": q(95), "p99": q(99),
            "min": s[0], "max": s[-1], "iqr": q(75) - q(25),
            "mean": st.mean(s)}


def retrans_snapshot(host):
    """리눅스 ss -ti 재전송 총계 (best effort — 없으면 None)."""
    try:
        o = subprocess.run(["ss", "-ti", "dst", host], capture_output=True,
                           text=True, timeout=5).stdout
        tot = 0
        for tok in o.split():
            if tok.startswith("retrans:"):
                tot += int(tok.split("/")[-1])
        return tot
    except Exception:
        return None


def measure_rtt(hp, n_fresh, n_steady):
    fresh, steady = [], []
    for _ in range(n_fresh):
        t0 = now()
        c = conn(hp)
        req(c, "E", 1)
        fresh.append((now() - t0) / NS * 1000)
        c.close()
        time.sleep(0.05)
    c = conn(hp)
    req(c, "E", 1)                                       # 웜업 버림
    for _ in range(n_steady):
        t0 = now()
        req(c, "E", 1)
        steady.append((now() - t0) / NS * 1000)
        time.sleep(0.05)
    c.close()
    return {"fresh_connect_ms": pct(fresh), "steady_echo_ms": pct(steady)}


def measure_goodput(hp, size_mb, direction, fresh):
    n = int(size_mb * 1e6)
    if fresh:
        t0 = now()
        c = conn(hp)
        req(c, "U" if direction == "up" else "D", n)
        dt = (now() - t0) / NS
        c.close()
    else:
        c = conn(hp)
        req(c, "E", 1)                                   # 웜업(핸드셰이크·slow start 일부 소화)
        req(c, "U" if direction == "up" else "D", n)     # 1회 예열 전송
        t0 = now()
        req(c, "U" if direction == "up" else "D", n)
        dt = (now() - t0) / NS
        c.close()
    return n * 8 / dt / 1e6                              # Mbps


def measure_burst(hp, k, size_mb, idle_s=5.0, recover_s=5.0):
    """K 병렬 업로드 + 그동안 100ms 간격 에코 RTT — 3구간(평시/버스트/회복)."""
    n = int(size_mb * 1e6)
    phases = {"idle": [], "burst": [], "recover": []}
    phase = {"cur": "idle"}
    stop = threading.Event()

    def sampler():
        c = conn(hp)
        req(c, "E", 1)
        while not stop.is_set():
            t0 = now()
            try:
                req(c, "E", 1)
            except Exception:
                break
            phases[phase["cur"]].append((now() - t0) / NS * 1000)
            time.sleep(0.1)
        c.close()

    smp = threading.Thread(target=sampler, daemon=True)
    smp.start()
    time.sleep(idle_s)
    barrier = threading.Barrier(k + 1)
    done = [None] * k

    def flow(i):
        c = conn(hp)
        barrier.wait()
        t0 = now()
        req(c, "U", n)
        done[i] = (now() - t0) / NS
        c.close()

    ths = [threading.Thread(target=flow, args=(i,)) for i in range(k)]
    for t in ths:
        t.start()
    phase["cur"] = "burst"
    t_burst0 = time.perf_counter()
    barrier.wait()
    for t in ths:
        t.join()
    burst_wall = time.perf_counter() - t_burst0
    phase["cur"] = "recover"
    time.sleep(recover_s)
    stop.set()
    smp.join(timeout=2)
    return {"k": k, "size_mb": size_mb,
            "flow_done_s": pct([d for d in done if d]),
            "spread_ratio": (max(done) / min(done)) if all(done) else None,
            "agg_goodput_mbps": k * n * 8 / burst_wall / 1e6,
            "rtt_ms": {ph: pct(v) for ph, v in phases.items()}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", required=True,
                    help="label=host:port[,label2=...] — 여러 개면 A/B 교차")
    ap.add_argument("--label", default="run", help="관측 지점 라벨 (pc_home 등)")
    ap.add_argument("--rtt-n", type=int, default=100)
    ap.add_argument("--sizes", default="1,4,8.39", help="굿풋 스윕 MB")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--burst-k", type=int, default=0, help="0=버스트 생략")
    ap.add_argument("--burst-size", type=float, default=8.68)
    ap.add_argument("--connect-only", action="store_true",
                    help="프로브 서버 없이 TCP connect RTT 만 (26022 등 기존 포트로)")
    a = ap.parse_args()
    targets = dict(t.split("=", 1) for t in a.targets.split(","))
    sizes = [float(x) for x in a.sizes.split(",")]
    os.makedirs(OUT, exist_ok=True)
    res = {"meta": {"label": a.label, "utc": datetime.datetime.utcnow().isoformat(),
                    "host": platform.node(), "os": platform.platform(),
                    "targets": targets, "argv": vars(a)},
           "targets": {k: {"goodput": {"up": {}, "down": {}}} for k in targets}}

    if a.connect_only:
        print("── connect-RTT 전용 (서버 불필요 — SYN 왕복) ──")
        for lb, hp in targets.items():
            v = []
            for _ in range(a.rtt_n):
                t0 = now()
                c = conn(hp)
                v.append((now() - t0) / NS * 1000)
                c.close()
                time.sleep(0.05)
            res["targets"][lb]["rtt"] = {"fresh_connect_ms": pct(v),
                                         "steady_echo_ms": {}}
            print(f"  {lb:8s} connect p50 {pct(v)['p50']:.1f}ms p95 {pct(v)['p95']:.1f}ms")
        path = os.path.join(OUT, f"probe_{a.label}_"
                            f"{datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json")
        io.open(path, "w", encoding="utf-8").write(json.dumps(res, indent=1))
        print(f"저장: {path}")
        return

    print("── RTT (표적 교차) ──")
    for lb, hp in targets.items():
        r0 = retrans_snapshot(hp.rsplit(":", 1)[0])
        res["targets"][lb]["rtt"] = measure_rtt(hp, a.rtt_n // 4, a.rtt_n)
        res["targets"][lb]["retrans_delta"] = (
            None if r0 is None else (retrans_snapshot(hp.rsplit(":", 1)[0]) or 0) - r0)
        s = res["targets"][lb]["rtt"]["steady_echo_ms"]
        print(f"  {lb:8s} steady p50 {s['p50']:.1f}ms p95 {s['p95']:.1f}ms "
              f"(fresh p50 {res['targets'][lb]['rtt']['fresh_connect_ms']['p50']:.1f}ms)")

    print("── 굿풋 스윕 (크기 × fresh/steady, 표적 교차) ──")
    for rep in range(a.reps):
        for sz in sizes:
            for lb, hp in targets.items():                # A/B 교차의 핵심 — 안쪽 루프
                for mode in ("fresh", "steady"):
                    for d in ("up", "down"):
                        g = measure_goodput(hp, sz, d, mode == "fresh")
                        res["targets"][lb]["goodput"][d].setdefault(
                            f"{sz}MB_{mode}", []).append(g)
        print(f"  rep {rep+1}/{a.reps} 완료")
    for lb in targets:
        for d in ("up", "down"):
            res["targets"][lb]["goodput"][d] = {
                k: pct(v) for k, v in res["targets"][lb]["goodput"][d].items()}

    if a.burst_k:
        print(f"── 버스트 (K={a.burst_k} × {a.burst_size}MB, 표적별) ──")
        for lb, hp in targets.items():
            res["targets"][lb]["burst"] = measure_burst(hp, a.burst_k, a.burst_size)
            b = res["targets"][lb]["burst"]
            deg = (b["rtt_ms"]["burst"].get("p95", 0) /
                   max(b["rtt_ms"]["idle"].get("p50", 1e-9), 1e-9))
            print(f"  {lb:8s} 완료 p50 {b['flow_done_s']['p50']:.2f}s · "
                  f"편차 {b['spread_ratio']:.2f}배 · 버스트 중 RTT p95 = 평시 p50 × {deg:.1f}")

    path = os.path.join(OUT, f"probe_{a.label}_"
                        f"{datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json")
    io.open(path, "w", encoding="utf-8").write(json.dumps(res, indent=1))
    print(f"저장: {path}")


if __name__ == "__main__":
    main()
