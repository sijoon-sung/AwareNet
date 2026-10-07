# -*- coding: utf-8 -*-
"""로컬 중계(엣지) — KOREN VM 엣지를 한 장비 안에서 흉내 낸다 (2026-10-07, GPU 단독 장비용).

실회선 리그(real_rig.sh)는 엣지 = KOREN VM 의 역터널, 접속 상한 = HPC egress tc, 엣지 용량 = VM tc 였다.
여기서는 같은 포트 규약 P(e, i, x) = BASE + 500·e + 2i + x 로 로컬 포트를 열고, 받은 바이트를 서버 조각 포트로
넘기면서 두 가지 상한을 응용 계층에서 건다 (sudo·tc 불필요).
  - 접속 상한: 클라 i 출구 x 마다 aA/aB Mbps (올리기·내리기 각각, 엣지와 무관 — real_rig 의 HPC egress 와 같음)
  - 엣지 용량: 엣지 e 마다 c_e Mbps (올리기·내리기 각각, 그 엣지를 지나는 모든 연결이 나눠 씀)
  지연: --delay-ms (편도, 기본 2 ms — KOREN 실측 왕복 약 4 ms)
엣지 용량은 실행 중에 바꿀 수 있다: --control 파일(JSON {"caps": [56,56,56,56]})을 0.5초마다 다시 읽는다.

    python sfl/net/local_relay.py --clients 32 --acc "5/2 5/2 ..." --caps "56 56 56 56" --upstream 127.0.0.1:31901
"""
import argparse
import asyncio
import json
import os
import sys
import time

CHUNK = 16384


class Bucket:
    """토큰 버킷을 시각으로 표현: 다음에 비는 시각. reserve 가 끝나는 시각을 돌려준다.
    BURST 초만큼 밀린 시간은 되찾을 수 있다(버킷 깊이) — 잠들기가 늦게 깨어나도(Windows 타이머 약 16 ms) 평균 속도가 깎이지 않게."""
    __slots__ = ("bps", "t")
    BURST = 0.05

    def __init__(self, mbps):
        self.bps = mbps * 1e6
        self.t = 0.0

    def reserve(self, nbytes, now):
        start = max(now - self.BURST, self.t)
        self.t = start + nbytes * 8 / self.bps
        return self.t


class Relay:
    def __init__(self, a):
        self.a = a
        acc = a.acc.split()
        if len(acc) == 1:
            acc = acc * a.clients
        self.acc = [tuple(float(v) for v in s.split("/")) for s in acc]
        caps = [float(v) for v in a.caps.split()]
        self.edge_up = [Bucket(c) for c in caps]
        self.edge_dn = [Bucket(c) for c in caps]
        self.acc_up, self.acc_dn = {}, {}
        for i, (aa, ab) in enumerate(self.acc):
            for x, m in enumerate((aa, ab)):
                self.acc_up[(i, x)] = Bucket(m)
                self.acc_dn[(i, x)] = Bucket(m)
        self.up_host, self.up_port = a.upstream.rsplit(":", 1)
        self.delay = a.delay_ms / 1000.0
        self.ctl_mtime = None
        self.stats = {}

    def key(self, port):
        off = port - self.a.base
        e, rest = divmod(off, 500)
        i, x = divmod(rest, 2)
        return e, i, x

    async def pump(self, reader, writer, edge_b, acc_b, tag):
        try:
            while True:
                data = await reader.read(CHUNK)
                if not data:
                    break
                now = time.monotonic()
                done = max(edge_b.reserve(len(data), now), acc_b.reserve(len(data), now)) + self.delay
                wait = done - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)
                writer.write(data)
                await writer.drain()
                self.stats[tag] = self.stats.get(tag, 0) + len(data)
        except (ConnectionError, OSError):
            pass
        finally:
            try:
                writer.close()
            except Exception:  # noqa: BLE001
                pass

    async def handle(self, reader, writer):
        port = writer.get_extra_info("sockname")[1]
        e, i, x = self.key(port)
        try:
            ur, uw = await asyncio.open_connection(self.up_host, int(self.up_port))
        except OSError as ex:
            print(f"[relay] 서버 조각 포트 연결 실패 {self.a.upstream}: {ex}", flush=True)
            writer.close()
            return
        for s in (writer, uw):
            sock = s.get_extra_info("socket")
            if sock is not None:
                import socket
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        await asyncio.gather(
            self.pump(reader, uw, self.edge_up[e], self.acc_up[(i, x)], (e, "up")),
            self.pump(ur, writer, self.edge_dn[e], self.acc_dn[(i, x)], (e, "dn")))

    async def control(self):
        path = self.a.control
        while True:
            try:
                m = os.path.getmtime(path)
                if m != self.ctl_mtime:
                    self.ctl_mtime = m
                    with open(path, encoding="utf-8") as f:
                        caps = json.load(f)["caps"]
                    for e, c in enumerate(caps):
                        if abs(self.edge_up[e].bps - c * 1e6) > 1:
                            print(f"[relay] 엣지 {e + 1} 용량 → {c:g} Mbps  {time.strftime('%H:%M:%S')}", flush=True)
                        self.edge_up[e].bps = self.edge_dn[e].bps = c * 1e6
            except (OSError, ValueError, KeyError):
                pass
            await asyncio.sleep(0.5)

    async def main(self):
        n_edges = len(self.edge_up)
        servers = []
        for e in range(n_edges):
            for i in range(self.a.clients):
                for x in (0, 1):
                    p = self.a.base + 500 * e + 2 * i + x
                    servers.append(await asyncio.start_server(self.handle, self.a.listen, p))
        print(f"[relay] 엣지 {n_edges}개 × 클라 {self.a.clients} × 출구 2 = 포트 {len(servers)}개 대기 "
              f"(기준 {self.a.base}) → {self.a.upstream}  접속 {self.acc[0][0]:g}/{self.acc[0][1]:g} Mbps  "
              f"엣지 {[b.bps / 1e6 for b in self.edge_up]} Mbps  편도 지연 {self.a.delay_ms:g} ms", flush=True)
        if self.a.control:
            with open(self.a.control, "w", encoding="utf-8") as f:
                json.dump({"caps": [b.bps / 1e6 for b in self.edge_up]}, f)
            asyncio.ensure_future(self.control())
        await asyncio.gather(*(s.serve_forever() for s in servers))


def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--clients", type=int, required=True)
    ap.add_argument("--acc", required=True, help="클라별 접속 상한 'aA/aB ...' (하나만 주면 전원 같음)")
    ap.add_argument("--caps", required=True, help="엣지별 용량 Mbps 'c1 c2 c3 c4'")
    ap.add_argument("--upstream", required=True, help="서버 조각 포트 host:port (서버 --port + 1)")
    ap.add_argument("--base", type=int, default=12100)
    ap.add_argument("--listen", default="127.0.0.1")
    ap.add_argument("--delay-ms", type=float, default=2.0)
    ap.add_argument("--control", default="", help="엣지 용량 제어 파일(JSON)")
    return ap.parse_args(argv)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        asyncio.run(Relay(parse_args()).main())
    except KeyboardInterrupt:
        pass
