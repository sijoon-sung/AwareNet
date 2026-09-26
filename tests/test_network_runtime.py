"""Two real learning rounds with synthetic data and a loopback relay.

This tests route execution/receipt/log integration, NOT WAN performance.
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


class RuntimeTests(unittest.TestCase):
    def test_registered_route_is_executed_and_receipted_for_two_rounds(self):
        torch.set_num_threads(1)
        models.set_norm("gn")
        for micro in (1, 4):
            with self.subTest(micro=micro), tempfile.TemporaryDirectory() as tmp:
                relay = socket.create_server(("127.0.0.1", 0))
                relay_port = relay.getsockname()[1]
                relay.settimeout(.2)
                # Reserve a usable control/data port pair before constructing Server.
                while True:
                    reserve = socket.create_server(("127.0.0.1", 0))
                    port = reserve.getsockname()[1]
                    try:
                        data_reserve = socket.create_server(("127.0.0.1", port+1))
                        data_reserve.close(); reserve.close(); break
                    except OSError:
                        reserve.close()
                stop = threading.Event()
                sockets = []
                def bridge(conn):
                    try:
                        upstream = socket.create_connection(("127.0.0.1", port+1), timeout=5)
                        sockets.extend([conn, upstream])
                        while not stop.is_set():
                            for src in select.select([conn, upstream], [], [], .2)[0]:
                                blob = src.recv(65536)
                                if not blob:
                                    return
                                (upstream if src is conn else conn).sendall(blob)
                    except OSError:
                        pass
                def accept_relay():
                    while not stop.is_set():
                        try:
                            conn, _ = relay.accept()
                            threading.Thread(target=bridge, args=(conn,), daemon=True).start()
                        except socket.timeout:
                            continue
                        except OSError:
                            return
                threading.Thread(target=accept_relay, daemon=True).start()
                log = Path(tmp) / "synthetic_loopback.jsonl"
                a = fed_server.parse_args(["--clients", "1", "--rounds", "2", "--batches", "1", "--norm", "gn",
                    "--device", "cpu", "--listen", "127.0.0.1", "--port", str(port), "--policy", "network",
                    "--preflight", "--paths", "1,100", "--access-caps", "c0=100", "--edge-groups", "1,2:0",
                    "--edges", f"1=127.0.0.1:{port+1},2=127.0.0.1:{relay_port}",
                    "--micro", str(micro), "--micro-window", "2", "--log", str(log)])
                server = LocalServer(a)
                errors = []
                def run(fn):
                    try:
                        fn()
                    except Exception as exc:
                        errors.append(exc)
                st = threading.Thread(target=run, args=(server.run,), daemon=True); st.start()
                ca = fed_client.parse_args(["--id", "c0", "--index", "0", "--clients", "1",
                                           "--server", f"127.0.0.1:{port}", "--norm", "gn", "--threads", "1"])
                client = LocalClient(ca)
                ct = threading.Thread(target=run, args=(client.run,), daemon=True); ct.start()
                try:
                    st.join(20); ct.join(5)
                    self.assertFalse(st.is_alive(), "server did not finish")
                    self.assertFalse(ct.is_alive(), "client did not finish")
                    self.assertEqual(errors, [])
                    rows = [json.loads(line) for line in log.read_text().splitlines()]
                    rows = [r for r in rows if "round" in r]
                    self.assertEqual(len(rows), 2)
                    for row in rows:
                        self.assertEqual(row["paths"]["c0"], "2")
                        self.assertEqual(row["route_receipts"]["c0"]["status"], "round_completed")
                        self.assertEqual(row["plan"]["c0"], 1.)
                        self.assertEqual(row["per_client_detail"]["c0"]["traffic"]["activation_messages"], micro)
                        durations = row["per_client_detail"]["c0"]["traffic"]["exchange_completion_s"]
                        self.assertEqual(len(durations), micro)
                        self.assertTrue(all(t > 0 for t in durations))
                        detail = row["per_client_detail"]["c0"]
                        self.assertEqual(len(detail["traffic"]["batch_compute"]), 1)
                        self.assertGreater(detail["traffic"]["batch_compute"][0]["backward_s"], 0)
                        events = detail["gradient_events"]
                        self.assertEqual(len(events), micro)
                        self.assertTrue(all(e["batch_index"] == 0 for e in events))
                        self.assertTrue(all(e["submit_done_server_monotonic_s"] >= e["ready_server_monotonic_s"] for e in events))
                        self.assertTrue(all(e["completion_scope"] == "async_queue_submission" for e in events))
                finally:
                    stop.set(); relay.close()
                    server.barrier.abort()
                    client.link.close()
                    server.st.chunks.stop = True
                    server.st.chunks.srv.close()
                    for sock in sockets:
                        sock.close()


if __name__ == "__main__":
    unittest.main()
