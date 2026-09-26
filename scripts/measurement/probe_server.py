# -*- coding: utf-8 -*-
"""정밀 측정용 프로브 서버 — KOREN VM/POP 에 하나 띄워 둔다.

  SSH 터널이 아니라 **맨 TCP** 라 암호화·다중화 오버헤드가 없다.
  프로토콜(길이 접두): [op 1B][n 8B big-endian]
      E  에코   — 클라가 n바이트 보내면 그대로 n바이트 반환 (RTT·지터용, n=1)
      U  업로드 — 클라가 n바이트 보내면 8B ack (상행 굿풋)
      D  다운로드 — 서버가 n바이트 전송 (하행 굿풋)

      python3 scripts/measurement/probe_server.py --port 9099
"""
import argparse
import socket
import threading

CHUNK = 65536


def recv_n(c, n):
    left = n
    while left:
        b = c.recv(min(CHUNK, left))
        if not b:
            raise ConnectionError("closed")
        left -= len(b)


def send_n(c, n):
    buf = b"\x55" * CHUNK
    left = n
    while left:
        m = min(CHUNK, left)
        c.sendall(buf[:m])
        left -= m


def serve(c):
    c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    try:
        while True:
            h = b""
            while len(h) < 9:
                b = c.recv(9 - len(h))
                if not b:
                    return
                h += b
            op, n = chr(h[0]), int.from_bytes(h[1:9], "big")
            if op == "E":
                buf = bytearray()
                while len(buf) < n:
                    b = c.recv(min(CHUNK, n - len(buf)))
                    if not b:
                        return
                    buf += b
                c.sendall(bytes(buf))
            elif op == "U":
                recv_n(c, n)
                c.sendall(b"\x00" * 8)
            elif op == "D":
                send_n(c, n)
            else:
                return
    except (ConnectionError, OSError):
        pass
    finally:
        c.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9099)
    a = ap.parse_args()
    s = socket.create_server(("0.0.0.0", a.port))
    print(f"probe_server on :{a.port}")
    while True:
        c, addr = s.accept()
        threading.Thread(target=serve, args=(c,), daemon=True).start()


if __name__ == "__main__":
    main()
