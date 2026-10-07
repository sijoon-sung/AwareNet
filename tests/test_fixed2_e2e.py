"""fixed2 종단 시험 — 클라 2대가 합성 데이터로 2라운드를 학습하며, 출구 A·B 를 서로 다른 (가짜) 엣지로 보낸다.

엣지는 로컬 중계(포트 묶음 → 서버 조각 포트)로 흉내 낸다. WAN 성능이 아니라 배정·분할 전송·로그가 맞물리는지만 본다.
    python tests/test_fixed2_e2e.py
"""
import json
from pathlib import Path
import select
import socket
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sfl"))
import torch
from torch.utils.data import DataLoader, TensorDataset
import models
import fed_client
import fed_server


def dataset():
    g = torch.Generator().manual_seed(4)
    return DataLoader(TensorDataset(torch.randn(8, 3, 32, 32, generator=g),
                                   torch.randint(0, 10, (8,), generator=g)), batch_size=4)


class LocalClient(fed_client.Client):
    def _data(self):
        return dataset()


class LocalServer(fed_server.Server):
    def _testset(self):
        return dataset()


def free_block(n):
    """연속 포트 n 개를 잡을 수 있는 시작 포트."""
    while True:
        s = socket.create_server(("127.0.0.1", 0)); base = s.getsockname()[1]; s.close()
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


class Fixed2E2E(unittest.TestCase):
    def test_two_exits_two_edges_two_rounds(self):
        torch.set_num_threads(1)
        models.set_norm("gn")
        n_cli = 2
        port = free_block(2 + 4 * n_cli)          # 제어 포트, 조각 포트(port+1), 엣지 1·2 포트 묶음을 한 블록에서
        b1, b2 = port + 2, port + 2 + 2 * n_cli
        stop = threading.Event()
        socks, used = [], []

        def bridge(conn, edge):
            try:
                up = socket.create_connection(("127.0.0.1", port + 1), timeout=5)
                socks.extend([conn, up])
                while not stop.is_set():
                    for src in select.select([conn, up], [], [], .2)[0]:
                        blob = src.recv(65536)
                        if not blob:
                            return
                        (up if src is conn else conn).sendall(blob)
            except OSError:
                pass

        listeners = []
        for edge, base in (("1", b1), ("2", b2)):
            for p in range(base, base + 2 * n_cli):
                ls = socket.create_server(("127.0.0.1", p)); ls.settimeout(.2); listeners.append(ls)

                def accept(ls=ls, edge=edge, p=p):
                    while not stop.is_set():
                        try:
                            conn, _ = ls.accept()
                            used.append((edge, p))
                            threading.Thread(target=bridge, args=(conn, edge), daemon=True).start()
                        except socket.timeout:
                            continue
                        except OSError:
                            return
                threading.Thread(target=accept, daemon=True).start()

        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "fixed2.jsonl"
            a = fed_server.parse_args(["--clients", str(n_cli), "--rounds", "2", "--batches", "1", "--norm", "gn",
                                       "--device", "cpu", "--listen", "127.0.0.1", "--port", str(port),
                                       "--policy", "fixed2", "--multipath", "--fixed-weights", "5,2",
                                       "--init-sets", "rr", "--edges", f"1=127.0.0.1:{b1},2=127.0.0.1:{b2}",
                                       "--log", str(log)])
            server = LocalServer(a)
            errors = []

            def run(fn):
                try:
                    fn()
                except Exception as exc:          # noqa: BLE001
                    errors.append(exc)
            st = threading.Thread(target=run, args=(server.run,), daemon=True); st.start()
            clients, cts = [], []
            for i in range(n_cli):
                ca = fed_client.parse_args(["--id", f"c{i}", "--index", str(i), "--clients", str(n_cli),
                                            "--server", f"127.0.0.1:{port}", "--norm", "gn", "--threads", "1"])
                c = LocalClient(ca); clients.append(c)
                t = threading.Thread(target=run, args=(c.run,), daemon=True); t.start(); cts.append(t)
            try:
                st.join(60)
                for t in cts:
                    t.join(10)
                self.assertFalse(st.is_alive(), "서버가 끝나지 않음")
                self.assertEqual(errors, [])
                rows = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if '"round"' in l]
                self.assertEqual(len(rows), 2)
                for row in rows:
                    self.assertEqual(set(row["plan"].values()), {1.0})
                    self.assertEqual(row["mp"]["c0"], [5.0, 2.0])
                # 출구 A: c0 → 엣지 1 (b1+0), c1 → 엣지 2 (b2+2) / 출구 B: c0 → 엣지 2 (b2+1), c1 → 엣지 1 (b1+3)
                expect = {("1", b1 + 0), ("2", b2 + 1), ("2", b2 + 2), ("1", b1 + 3)}
                self.assertTrue(expect <= set(used), f"쓰인 종점 {sorted(set(used))} / 기대 {sorted(expect)}")
                ex = rows[-1]["per_client_detail"]["c0"].get("exits")
                if ex:                                # 출구별 올린 바이트가 5:2 근처
                    ratio = ex[0]["up"] / max(ex[1]["up"], 1)
                    self.assertGreater(ratio, 1.5)
                    print(f"   c0 출구별 올림 {[e['up'] for e in ex]} (A/B = {ratio:.2f}, 기대 2.5)")
            finally:
                stop.set()
                for ls in listeners:
                    ls.close()
                server.barrier.abort()
                for c in clients:
                    c.link.close()
                server.st.chunks.stop = True
                server.st.chunks.srv.close()
                for s in socks:
                    s.close()


if __name__ == "__main__":
    unittest.main()
