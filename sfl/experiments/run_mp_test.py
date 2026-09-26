# -*- coding: utf-8 -*-
"""분할 전송 검증 도구 — 설계서 §8 의 조건들을 돌린다.

  스모크 (아무 데서나):   python sfl/experiments/run_mp_test.py --size 8 --sources 127.0.0.1,127.0.0.1
  출구 2개 (tc 리눅스):   python sfl/experiments/run_mp_test.py --size 35 --sources 127.0.2.1,127.0.2.2
  출구 1개 대조:          python sfl/experiments/run_mp_test.py --size 35 --sources 127.0.2.1
  절단 내결함성:          python sfl/experiments/run_mp_test.py --size 8 --sources 127.0.0.1,127.0.0.1 --cut-delay 0.2
"""
import argparse
import os
import socket
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from mpsend import Reassembler, send_multipath          # noqa: E402
from proto import CHUNK, recv_msg, send_msg             # noqa: E402


def sink(host, port, stop, reasm):
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(8)
    srv.settimeout(0.5)

    def handle(conn):
        while True:
            try:
                kind, meta, payload, _ = recv_msg(conn)
            except (OSError, ConnectionError):
                break
            if kind != CHUNK:
                break
            r = reasm.feed(meta, payload)
            if r is not None:                       # fin — 다른 연결의 조각이 아직
                ok, got = r                          # 배달 중일 수 있어 잠시 기다린다
                t0 = time.time()
                while not ok and time.time() - t0 < 30:
                    time.sleep(0.01)
                    ok, got = reasm.feed(meta, b"")
                send_msg(conn, CHUNK, {"got": got if ok else -1})
                break
        conn.close()

    while not stop.is_set():
        try:
            conn, _ = srv.accept()
        except socket.timeout:
            continue
        threading.Thread(target=handle, args=(conn,), daemon=True).start()
    srv.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=float, default=8, help="전송 크기 MB")
    ap.add_argument("--sources", default="127.0.0.1,127.0.0.1")
    ap.add_argument("--host", default="127.0.0.100")
    ap.add_argument("--port", type=int, default=31920)
    ap.add_argument("--cut-delay", type=float, default=0.0,
                    help=">0 이면 그 시점(초)에 연결 하나를 강제로 끊어 재전송을 시험")
    a = ap.parse_args()

    try:                                            # 윈도우 스모크: 127.0.0.100 불가 시 폴백
        socket.socket().bind((a.host, 0))
        host = a.host
    except OSError:
        host = "127.0.0.1"

    stop = threading.Event()
    reasm = Reassembler()
    threading.Thread(target=sink, args=(host, a.port, stop, reasm),
                     daemon=True).start()
    time.sleep(0.3)

    blob = os.urandom(int(a.size * 1e6))
    sources = a.sources.split(",")

    holder = {}
    if a.cut_delay > 0:                             # 절단 시험 — 연결 목록을 훔쳐 하나 끊는다
        import mpsend as _m
        orig = _m.socket.create_connection
        made = []

        def spy(*args, **kw):
            s = orig(*args, **kw)
            made.append(s)
            return s
        _m.socket.create_connection = spy

        def cutter():
            time.sleep(a.cut_delay)
            if len(made) > 1:
                made[1].close()
                print("  [절단] 연결 2 를 강제로 닫음", flush=True)
        threading.Thread(target=cutter, daemon=True).start()

    r = send_multipath(host, a.port, blob, sources, tid="t1")
    print(f"전송 {a.size:.0f}MB  출구 {len(sources)}개(성립 {r['conns']})  "
          f"벽시계 {r['wall']:.2f}s")
    for src, st in r["per"].items():
        print(f"  {src:12s} {st['bytes']/1e6:6.1f}MB  송신점유 {st['busy_s']:.2f}s")
    data = reasm.pop("t1")
    print("재조립 일치:", data == blob)
    stop.set()
    sys.exit(0 if data == blob else 1)


if __name__ == "__main__":
    main()
