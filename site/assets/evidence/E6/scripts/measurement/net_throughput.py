# -*- coding: utf-8 -*-
"""처리량·연결 응답 측정 — iperf3 가 없어도 되는 순수 파이썬판. 양방향·다중 흐름을 잰다.

받는 쪽 (KOREN VM 처럼 열린 포트가 있는 쪽):
    python scripts/measurement/net_throughput.py serve --port 12005

보내는 쪽 (HPC 처럼 밖으로만 나갈 수 있는 쪽):
    python scripts/measurement/net_throughput.py client --server 116.89.187.190:12005 \
        --secs 10 --streams 1,4,8 --repeat 3 --tag hpc2vm1

무엇을 재나
  - 상향(보내는 쪽 → 받는 쪽) 처리량: 흐름 수를 1·4·8 로 올려 가며 잰다. 한 흐름으로는 지연·창 크기 때문에
    회선 용량이 다 안 나오므로, 여러 흐름의 합이 회선 용량에 가깝다.
  - 하향(받는 쪽 → 보내는 쪽) 처리량: 같은 연결을 뒤집어 서버가 보낸다.
  - 연결 왕복(handshake RTT)과 첫 바이트 도착 시간.
결과: out/probe/thr_<태그>.json (회차별 값과 요약) + 화면 표. 표준 라이브러리만 쓴다.
"""
import argparse
import io
import json
import os
import socket
import statistics
import threading
import time

CC = [""]                # 소켓마다 혼잡 제어 알고리즘을 지정할 때 (--cc bbr)
CHUNK = 1 << 20          # 1 MiB
CHUNKSZ = [1 << 20]      # 왕복 모드에서 한 번에 주고받는 크기 (--chunk 로 설정)
HDR = 64                 # 제어 줄 길이 (고정)


_CACHE = {}


def _fill(n):
    """같은 크기를 반복해서 만들지 않도록 캐시한다 (큰 덩어리에서 측정이 왜곡되는 것을 막는다)."""
    if n not in _CACHE:
        _CACHE[n] = (b"AwareNet-throughput-" * ((n // 20) + 1))[:n]
    return _CACHE[n]


BLOB = _fill(CHUNK)


def _recvall(sock, n):
    """큰 덩어리에서 buf += b 는 매번 전체를 복사해 측정을 왜곡한다. 조각을 모아 마지막에 한 번만 잇는다."""
    parts, got = [], 0
    while got < n:
        b = sock.recv(min(1 << 20, n - got))
        if not b:
            return None
        parts.append(b)
        got += len(b)
    return b"".join(parts)


def serve(port, bind="0.0.0.0"):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((bind, port))
    s.listen(64)
    print(f"받는 쪽 준비 {bind}:{port} — 종료는 Ctrl+C", flush=True)
    while True:
        c, addr = s.accept()
        threading.Thread(target=_serve_one, args=(c, addr), daemon=True).start()


def _serve_one(c, addr):
    try:
        c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        hdr = c.recv(HDR)
        if not hdr:
            return
        mode, secs = hdr.decode("ascii", "replace").strip().split()[:2]
        secs = float(secs)
        if mode == "rr":                      # 왕복 — 받은 만큼 그대로 돌려준다 (분할학습의 배치 왕복 모양)
            while True:
                hdr2 = _recvall(c, 16)
                if not hdr2:
                    break
                n = int(hdr2.decode("ascii").strip())
                if n <= 0:
                    break
                _recvall(c, n)
                c.sendall(BLOB[:n] if n <= CHUNK else _fill(n))
            c.close()
            return
        if mode == "up":                      # 클라이언트가 보내고 서버는 받는다
            n, t0 = 0, time.perf_counter()
            while True:
                b = c.recv(CHUNK)
                if not b:
                    break
                n += len(b)
            dt = time.perf_counter() - t0
            c.close()
            print(f"  {addr[0]} 상향 {n/1e6:.1f} MB / {dt:.2f}s = {n*8/1e6/max(dt,1e-9):.1f} Mbps", flush=True)
        else:                                  # 서버가 보내고 클라이언트가 받는다
            t0 = time.perf_counter()
            while time.perf_counter() - t0 < secs:
                c.sendall(BLOB)
            c.close()
    except Exception as e:
        print("  연결 오류", addr, e, flush=True)


def _one_stream(ip, port, mode, secs, res, idx):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        if CC[0]:                        # 시스템 기본을 건드리지 않고 이 소켓만 바꾼다
            try:
                s.setsockopt(socket.IPPROTO_TCP, 13, CC[0].encode())   # 13 = TCP_CONGESTION
            except OSError as e:
                print(f"  혼잡 제어 {CC[0]} 설정 실패: {e}", flush=True)
        s.settimeout(secs + 20)
        t_c = time.perf_counter()
        s.connect((ip, port))
        rtt = (time.perf_counter() - t_c) * 1000
        s.sendall(f"{mode} {secs}".ljust(HDR).encode("ascii"))
        n, t0, first = 0, time.perf_counter(), None
        if mode == "rr":
            payload = BLOB[:CHUNKSZ[0]] if CHUNKSZ[0] <= CHUNK else _fill(CHUNKSZ[0])
            hdr2 = str(CHUNKSZ[0]).rjust(16).encode("ascii")
            laps = []
            while time.perf_counter() - t0 < secs:
                tl = time.perf_counter()
                s.sendall(hdr2)
                s.sendall(payload)
                if _recvall(s, CHUNKSZ[0]) is None:
                    break
                laps.append((time.perf_counter() - tl) * 1000)
                n += CHUNKSZ[0] * 2
            try:
                s.sendall(str(0).rjust(16).encode("ascii"))
            except OSError:
                pass
            dt = time.perf_counter() - t0
            s.close()
            laps.sort()
            res[idx] = {"bytes": n, "secs": round(dt, 3),
                        "mbps": round(n * 8 / 1e6 / max(dt, 1e-9), 2),
                        "handshake_ms": round(rtt, 3),
                        "lap_median_ms": round(laps[len(laps) // 2], 2) if laps else None,
                        "lap_p95_ms": round(laps[int(0.95 * (len(laps) - 1))], 2) if laps else None,
                        "laps": len(laps)}
            return
        if mode == "up":
            while time.perf_counter() - t0 < secs:
                s.sendall(BLOB)
                n += CHUNK
            s.shutdown(socket.SHUT_WR)
        else:
            while True:
                b = s.recv(CHUNK)
                if not b:
                    break
                if first is None:
                    first = (time.perf_counter() - t0) * 1000
                n += len(b)
                if time.perf_counter() - t0 > secs + 2:
                    break
        dt = time.perf_counter() - t0
        s.close()
        res[idx] = {"bytes": n, "secs": round(dt, 3), "mbps": round(n * 8 / 1e6 / max(dt, 1e-9), 2),
                    "handshake_ms": round(rtt, 3), "first_byte_ms": None if first is None else round(first, 3)}
    except Exception as e:
        res[idx] = {"error": f"{type(e).__name__}: {e}"}


def run_case(ip, port, mode, secs, streams):
    res = [None] * streams
    th = [threading.Thread(target=_one_stream, args=(ip, port, mode, secs, res, i)) for i in range(streams)]
    t0 = time.perf_counter()
    for t in th:
        t.start()
    for t in th:
        t.join()
    wall = time.perf_counter() - t0
    ok = [r for r in res if r and "mbps" in r]
    return {"mode": mode, "streams": streams, "wall_s": round(wall, 3),
            "total_mbps": round(sum(r["mbps"] for r in ok), 2) if ok else None,
            "per_stream": res,
            "handshake_ms": round(statistics.median(r["handshake_ms"] for r in ok), 3) if ok else None,
            "errors": [r["error"] for r in res if r and "error" in r]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("role", choices=["serve", "client"])
    ap.add_argument("--port", type=int, default=12005)
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--server", default="", help="client 일 때 IP:포트")
    ap.add_argument("--secs", type=float, default=10)
    ap.add_argument("--streams", default="1,4,8")
    ap.add_argument("--modes", default="up,down", help="up=보내기, down=받기, rr=왕복(배치 모양)")
    ap.add_argument("--chunks", default="", help="rr 모드에서 잴 덩어리 크기들, MB 단위 쉼표 구분 (예: 0.25,1,4,8)")
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--cc", default="", help="이 소켓들에만 쓸 혼잡 제어 (예: bbr). 시스템 기본은 그대로 둔다")
    ap.add_argument("--tag", default="thr")
    a = ap.parse_args()

    CC[0] = a.cc
    if a.role == "serve":
        serve(a.port, a.bind)
        return

    ip, port = a.server.rsplit(":", 1)
    port = int(port)
    rows = []
    chunks = [float(x) for x in a.chunks.split(",") if x.strip()] or [1.0]
    print(f"{a.repeat}회 반복 · 흐름 {a.streams} · {a.secs}초 · {ip}:{port}", flush=True)
    for rep in range(1, a.repeat + 1):
        for mode in [m for m in a.modes.split(",") if m]:
            for ch in (chunks if mode == "rr" else [None]):
                if ch:
                    CHUNKSZ[0] = int(ch * 1e6)
                for st in [int(x) for x in a.streams.split(",") if x]:
                    r = run_case(ip, port, mode, a.secs, st)
                    r["repeat"] = rep
                    if ch:
                        r["chunk_mb"] = ch
                    rows.append(r)
                    lap = [x.get("lap_median_ms") for x in r["per_stream"] if x and x.get("lap_median_ms")]
                    print(f"  {rep}회 {mode:>4}{(' 덩어리 ' + str(ch) + 'MB') if ch else ''} 흐름 {st:>2}: "
                          f"합계 {r['total_mbps']} Mbps"
                          f"{('  왕복 중앙 ' + str(round(sum(lap)/len(lap), 1)) + 'ms') if lap else ''}"
                          f" {('오류 ' + str(r['errors'][:1])) if r['errors'] else ''}", flush=True)
    summary = {}
    for mode in set(r["mode"] for r in rows):
        for st in sorted(set(r["streams"] for r in rows)):
            v = [r["total_mbps"] for r in rows if r["mode"] == mode and r["streams"] == st and r["total_mbps"]]
            if v:
                summary[f"{mode}_{st}흐름"] = {"중앙 Mbps": round(statistics.median(v), 2),
                                               "최소": min(v), "최대": max(v), "n": len(v)}
    os.makedirs(os.path.join("out", "probe"), exist_ok=True)
    p = os.path.join("out", "probe", f"thr_{a.tag}.json")
    io.open(p, "w", encoding="utf-8").write(json.dumps({"target": a.server, "rows": rows, "summary": summary},
                                                       ensure_ascii=False, indent=1))
    print("\n요약:", json.dumps(summary, ensure_ascii=False), "\n→", p, flush=True)


if __name__ == "__main__":
    main()
