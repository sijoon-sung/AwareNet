"""로컬 중계(sfl/net/local_relay.py) 시험 — 상한이 맞게 걸리는지, 실행 중 용량 변경, fixed2 학습 2라운드 관통.

    python tests/test_local_relay.py
"""
import asyncio
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sfl"))
sys.path.insert(0, str(ROOT / "sfl" / "net"))
import local_relay  # noqa: E402


def free_block(n):
    """연속 포트 n 개가 비어 있는 시작 포트 (20000~50000 사이에서 고른다)."""
    import random
    while True:
        base = random.randint(20000, 50000 - n)
        held = []
        try:
            for p in range(base, base + n):
                held.append(socket.create_server(("127.0.0.1", p)))
            return base
        except OSError:
            continue
        finally:
            for h in held:
                h.close()


class Sink:
    """받은 바이트를 세는 상류 서버 (서버 조각 포트 대역)."""
    def __init__(self, port):
        self.srv = socket.create_server(("127.0.0.1", port)); self.srv.settimeout(.2)
        self.got = 0; self.stop = False
        threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        while not self.stop:
            try:
                c, _ = self.srv.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            threading.Thread(target=self.eat, args=(c,), daemon=True).start()

    def eat(self, c):
        while True:
            b = c.recv(65536)
            if not b:
                return
            self.got += len(b)


def start_relay(argv):
    a = local_relay.parse_args(argv)
    r = local_relay.Relay(a)
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=lambda: (asyncio.set_event_loop(loop), loop.run_until_complete(r.main())), daemon=True)
    t.start()
    time.sleep(0.8)
    return r, loop


def send(port, nbytes, out):
    s = socket.create_connection(("127.0.0.1", port))
    t0 = time.monotonic(); blob = b"x" * 65536; left = nbytes
    while left > 0:
        k = min(left, len(blob)); s.sendall(blob[:k]); left -= k
    s.shutdown(socket.SHUT_WR)
    try:
        s.recv(1)
    except OSError:
        pass
    out.append(time.monotonic() - t0)
    s.close()


class RelayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        n = 2
        cls.up = free_block(1)
        cls.base = free_block(4 * 500 + 2 * n)
        while cls.base <= cls.up < cls.base + 4 * 500 + 2 * n:
            cls.base = free_block(4 * 500 + 2 * n)
        cls.sink = Sink(cls.up)
        cls.ctl = os.path.join(tempfile.mkdtemp(), "caps.json")
        # 접속: 클라 0 = 8/4 Mbps, 클라 1 = 100/100. 엣지: 1 = 100, 2 = 8, 3·4 = 100
        cls.relay, cls.loop = start_relay(["--clients", str(n), "--acc", "8/4 100/100", "--caps", "100 8 100 100",
                                           "--upstream", f"127.0.0.1:{cls.up}", "--base", str(cls.base),
                                           "--delay-ms", "0", "--control", cls.ctl])

    def wait_sink(self, target, timeout=10):
        t0 = time.monotonic()
        while self.sink.got < target and time.monotonic() - t0 < timeout:
            time.sleep(0.02)
        return time.monotonic() - t0

    def test_access_cap(self):
        """클라 0 출구 A (8 Mbps) 로 1 MB → 약 1.0초."""
        g0 = self.sink.got; t = []
        threading.Thread(target=send, args=(self.base + 0, 1_000_000, t), daemon=True).start()
        t0 = time.monotonic(); self.wait_sink(g0 + 1_000_000)
        dt = time.monotonic() - t0
        self.assertAlmostEqual(dt, 1.0, delta=0.25, msg=f"8 Mbps 로 1MB = 1.0s 기대, 실제 {dt:.2f}s")

    def test_shared_edge(self):
        """엣지 2 (8 Mbps) 를 클라 1 의 두 출구(접속 100)가 나눠 쓴다: 합 1 MB → 약 1.0초."""
        g0 = self.sink.got; t = []
        for x in (0, 1):
            threading.Thread(target=send, args=(self.base + 500 + 2 * 1 + x, 500_000, t), daemon=True).start()
        t0 = time.monotonic(); self.wait_sink(g0 + 1_000_000)
        dt = time.monotonic() - t0
        self.assertAlmostEqual(dt, 1.0, delta=0.25, msg=f"공유 엣지 8 Mbps 로 합 1MB = 1.0s 기대, 실제 {dt:.2f}s")

    def test_zz_control_change(self):
        """엣지 3 용량을 100 → 4 Mbps 로 바꾸면 클라 1 출구 A 의 0.5 MB 가 약 1.0초."""
        d = json.load(open(self.ctl, encoding="utf-8")); d["caps"][2] = 4
        json.dump(d, open(self.ctl, "w", encoding="utf-8")); time.sleep(1.2)
        g0 = self.sink.got; t = []
        threading.Thread(target=send, args=(self.base + 1000 + 2 * 1, 500_000, t), daemon=True).start()
        t0 = time.monotonic(); self.wait_sink(g0 + 500_000)
        dt = time.monotonic() - t0
        self.assertAlmostEqual(dt, 1.0, delta=0.25, msg=f"4 Mbps 로 0.5MB = 1.0s 기대, 실제 {dt:.2f}s")


class Fixed2ThroughRelay(unittest.TestCase):
    """fixed2 학습 2라운드를 로컬 중계(상한 넉넉) 경유로 — 서버·클라·중계가 실제로 맞물리는지."""
    def test_two_rounds(self):
        import torch
        from torch.utils.data import DataLoader, TensorDataset
        import models
        import fed_client
        import fed_server

        def dataset():
            g = torch.Generator().manual_seed(4)
            return DataLoader(TensorDataset(torch.randn(8, 3, 32, 32, generator=g),
                                           torch.randint(0, 10, (8,), generator=g)), batch_size=4)

        class C(fed_client.Client):
            def _data(self):
                return dataset()

        class S(fed_server.Server):
            def _testset(self):
                return dataset()

        torch.set_num_threads(1); models.set_norm("gn")
        n = 2
        port = free_block(2)
        base = free_block(4 * 500 + 2 * n)
        while base <= port + 1 and port < base + 4 * 500 + 2 * n:
            base = free_block(4 * 500 + 2 * n)
        relay, loop = start_relay(["--clients", str(n), "--acc", "200/80", "--caps", "400 400 400 400",
                                   "--upstream", f"127.0.0.1:{port + 1}", "--base", str(base), "--delay-ms", "1"])
        edges = ",".join(f"{e + 1}=127.0.0.1:{base + 500 * e}" for e in range(4))
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "f2.jsonl"
            a = fed_server.parse_args(["--clients", str(n), "--rounds", "2", "--batches", "1", "--norm", "gn",
                                       "--device", "cpu", "--listen", "127.0.0.1", "--port", str(port),
                                       "--policy", "fixed2", "--multipath", "--fixed-weights", "5,2",
                                       "--init-sets", "rr", "--edges", edges, "--log", str(log)])
            server = S(a); errors = []

            def run(fn):
                try:
                    fn()
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)
            st = threading.Thread(target=run, args=(server.run,), daemon=True); st.start()
            cl = []
            for i in range(n):
                c = C(fed_client.parse_args(["--id", f"c{i}", "--index", str(i), "--clients", str(n),
                                             "--server", f"127.0.0.1:{port}", "--norm", "gn", "--threads", "1"]))
                cl.append(c); threading.Thread(target=run, args=(c.run,), daemon=True).start()
            st.join(90)
            try:
                self.assertFalse(st.is_alive(), "서버가 끝나지 않음")
                self.assertEqual(errors, [])
                rows = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if '"round"' in l]
                self.assertEqual(len(rows), 2)
                used = {k for k in relay.stats if relay.stats[k] > 0}
                self.assertTrue({(0, "up"), (2, "up"), (1, "up"), (3, "up")} <= used, f"쓰인 엣지 {sorted(used)}")
            finally:
                server.barrier.abort()
                for c in cl:
                    c.link.close()
                server.st.chunks.stop = True
                server.st.chunks.srv.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
