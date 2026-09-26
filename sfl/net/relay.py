# -*- coding: utf-8 -*-
"""TCP 중계기 — 포트 범위로 들어온 연결을 목적지로 그대로 넘긴다. (실회선 리그의 로컬 시험용; VM 에서는 ssh -R 역터널이 이 역할)

    python sfl/net/relay.py --listen 127.0.0.1 --ports 12000-12015,12500-12515 --to 127.0.0.1:31901
"""
import argparse
import asyncio


async def pipe(r, w):
    try:
        while True:
            b = await r.read(1 << 16)
            if not b:
                break
            w.write(b)
            await w.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        try:
            w.close()
        except Exception:
            pass


async def handle(reader, writer, to):
    try:
        r2, w2 = await asyncio.open_connection(to[0], to[1])
    except OSError:
        writer.close(); return
    await asyncio.gather(pipe(reader, w2), pipe(r2, writer))


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", default="127.0.0.1")
    ap.add_argument("--ports", required=True, help="예: 12000-12015,12500-12515")
    ap.add_argument("--to", required=True, help="host:port")
    a = ap.parse_args()
    host, port = a.to.rsplit(":", 1); to = (host, int(port))
    ports = []
    for tok in a.ports.split(","):
        lo, _, hi = tok.partition("-")
        ports += list(range(int(lo), int(hi or lo) + 1))
    servers = [await asyncio.start_server(lambda r, w: handle(r, w, to), a.listen, p) for p in ports]
    print(f"relay: {a.listen} {ports[0]}..{ports[-1]} ({len(ports)}개) → {a.to}", flush=True)
    await asyncio.gather(*(s.serve_forever() for s in servers))


if __name__ == "__main__":
    asyncio.run(main())
