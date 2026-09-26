# -*- coding: utf-8 -*-
"""분할 전송 채널만 따로 잰다 — 리그 위에서 FL 프로토콜 없이. (2026-09-07)

    sudo env DELAY_MS=10 PATH_DELAYS="5 5" sh sfl/net/hairpin_lo.sh setup "150 150" "50/20 50/20 50/20 50/20"
    sudo sh sfl/net/hairpin_lo.sh assign "1 1 2+2 1"
    python scripts/measurement/mp_bench.py --dev 3 --port 31905 --mb 1 --n 16 --weights 46.6,17.5

기기 3(127.0.0.3 / 127.0.1.3)이 (a) 주 링크 한 가닥으로 n×mb MB 를 올릴 때, (b) 두 출구 조각 채널로 올릴 때,
(c) 두 출구로 내려받을 때, (d) 올리기·내려받기를 번갈아(즉시 내보내기 흐름) 할 때 걸리는 시간을 잰다.
이상값 = 바이트 / (aA + aB). 채널의 효율 = 이상값 / 측정."""
import argparse, os, socket, sys, threading, time
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "sfl"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from mpsend import ChunkLinks, ChunkServer  # noqa: E402
from proto import CHUNK, recv_msg, send_msg  # noqa: E402

SRV = "127.0.0.100"


def single_link(src, port, blob, n):
    """주 링크 한 가닥: 상시 연결 하나로 n 번 보내고 회신 받기 (fed 의 ACT 와 같은 꼴)."""
    stop = {"v": False}
    def sink():
        s = socket.create_server((SRV, port)); s.settimeout(1)
        try:
            c, _ = s.accept()
        except socket.timeout:
            return
        while not stop["v"]:
            try:
                k, m, p, _ = recv_msg(c)
            except OSError:
                break
            send_msg(c, CHUNK, {"ack": 1})
    th = threading.Thread(target=sink, daemon=True); th.start(); time.sleep(0.3)
    c = socket.create_connection((SRV, port), source_address=(src, 0)); c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    t0 = time.perf_counter()
    for i in range(n):
        send_msg(c, CHUNK, {"i": i}, blob)
        recv_msg(c)
    dt = time.perf_counter() - t0
    stop["v"] = True; c.close()
    return dt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev", type=int, default=3)
    ap.add_argument("--port", type=int, default=31905)
    ap.add_argument("--mb", type=float, default=1.0)
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--weights", default="46.6,17.5")
    ap.add_argument("--acc", default="50,20", help="출구 A,B 상한 Mbps (이상값 계산용)")
    a = ap.parse_args()
    exits = [f"127.0.0.{a.dev}", f"127.0.1.{a.dev}"]
    W = [float(x) for x in a.weights.split(",")]
    aA, aB = [float(x) for x in a.acc.split(",")]
    blob = os.urandom(int(a.mb * (1 << 20)))
    total_mb = a.mb * a.n
    print(f"기기 {a.dev}: 출구 {exits}, {a.n}×{a.mb}MB = {total_mb:.0f}MB, 가중치 {W}")
    print(f"  이상값: 한 가닥 {total_mb*8/aA:5.2f}s (@{aA:.0f}M)   두 가닥 {total_mb*8/(aA+aB):5.2f}s (@{aA+aB:.0f}M)")

    t = single_link(exits[0], a.port + 3, blob, a.n)
    print(f"  (a) 주 링크 한 가닥 올리기 {a.n}건 순차(회신 대기): {t:5.2f}s  → {total_mb*8/t:5.1f} Mbps")

    cs = ChunkServer(SRV, a.port); cs.start()
    L = ChunkLinks(SRV, a.port, exits)
    # 워밍업 1건
    th = threading.Thread(target=lambda: cs.wait("w0", 30)); th.start(); L.send(blob, "w0", cid="d", weights=W); th.join(30); L.flush()
    # (b) 올리기 n건 (비동기 회신, 서버는 도착만 기다림)
    waits = [threading.Thread(target=lambda i=i: cs.wait(f"u{i}", 60)) for i in range(a.n)]
    for w in waits: w.start()
    t0 = time.perf_counter()
    for i in range(a.n):
        L.send(blob, f"u{i}", cid="d", weights=W)
    L.flush()
    for w in waits: w.join(60)
    tb = time.perf_counter() - t0
    st = L.exit_stats()
    print(f"  (b) 두 출구 올리기 {a.n}건: {tb:5.2f}s → {total_mb*8/tb:5.1f} Mbps   출구 몫 A {100*st[0]['up']/(st[0]['up']+st[1]['up']):.0f}%   효율(이상/측정) {total_mb*8/(aA+aB)/tb*100:.0f}%")
    # (c) 내려받기 n건
    waits = [threading.Thread(target=lambda i=i: L.wait(f"d{i}", 60)) for i in range(a.n)]
    for w in waits: w.start()
    t0 = time.perf_counter()
    for i in range(a.n):
        cs.send_back("d", blob, f"d{i}", weights=W)
    cs.peers["d"].flush()
    for w in waits: w.join(60)
    tc = time.perf_counter() - t0
    print(f"  (c) 두 출구 내려받기 {a.n}건: {tc:5.2f}s → {total_mb*8/tc:5.1f} Mbps   효율 {total_mb*8/(aA+aB)/tc*100:.0f}%")
    # (d) 번갈아 (즉시 내보내기 흐름): 올리기 i → 서버가 받으면 내려보내기 i, 클라는 4개 앞서감
    def server_side():
        for i in range(a.n):
            cs.wait(f"x{i}", 60)
            cs.send_back("d", blob, f"y{i}", weights=W)
        cs.peers["d"].flush()
    ths = threading.Thread(target=server_side); ths.start()
    t0 = time.perf_counter()
    got = []
    for i in range(a.n):
        L.send(blob, f"x{i}", cid="d", weights=W)
        if i >= 3:
            got.append(L.wait(f"y{i-3}", 60))
    for i in range(a.n - 3, a.n):
        got.append(L.wait(f"y{i}", 60))
    L.flush(); ths.join(60)
    td = time.perf_counter() - t0
    print(f"  (d) 번갈아 올리기+내려받기 {a.n}건씩 (깊이 4): {td:5.2f}s → {2*total_mb*8/td:5.1f} Mbps   이상 {2*total_mb*8/(aA+aB):5.2f}s  효율 {2*total_mb*8/(aA+aB)/td*100:.0f}%")
    L.close(); cs.stop = True


if __name__ == "__main__":
    main()
