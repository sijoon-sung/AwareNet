"""Actual client + server batch methods over sockets vs one monolithic SGD step."""
import copy
from pathlib import Path
import socket
import sys
import threading
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sfl"))
import torch
from torch import nn
from fed_client import Client, Link
from fed_server import ClientSession, RoundAccount
from proto import ACT, recv_msg


class MicroEndToEndTests(unittest.TestCase):
    def run_batch(self, n, micro, window):
        torch.set_num_threads(1)
        torch.manual_seed(11)
        front = nn.Sequential(nn.Linear(6, 5), nn.Tanh())
        back = nn.Linear(5, 3)
        rf, rb = copy.deepcopy(front), copy.deepcopy(back)
        x, y = torch.randn(n, 6), torch.randint(0, 3, (n,))
        reference_opt = torch.optim.SGD(list(rf.parameters()) + list(rb.parameters()), lr=.05, momentum=.9)
        loss = nn.functional.cross_entropy(rb(rf(x)), y)
        loss.backward(); reference_opt.step()
        left, right = socket.socketpair()
        left.settimeout(5); right.settimeout(5)
        client = Client.__new__(Client)
        client.a = SimpleNamespace(device="cpu", speed=1., id="c0")
        client.link = Link.__new__(Link); client.link.sock = left
        client._r = 0; client._nb = 0; client.mp_round = False
        client.chunk_links = None; client.micro_window = window
        client.traffic = {"activation_messages": 0, "activation_payload_bytes": 0,
                          "activation_main_channel_bytes": 0, "activation_send_s": 0., "max_inflight_microbatches": 0}
        opt = torch.optim.SGD(front.parameters(), lr=.05, momentum=.9)
        bopt = torch.optim.SGD(back.parameters(), lr=.05, momentum=.9)
        session = ClientSession.__new__(ClientSession)
        session.a = SimpleNamespace(device="cpu"); session.conn = right
        session.agg = SimpleNamespace(srv=lambda p: (back, bopt))
        errors = []
        def serve():
            try:
                count = len(x.chunk(micro)) if micro > 1 else 1
                for _ in range(count):
                    kind, meta, payload, _ = recv_msg(right)
                    assert kind == ACT
                    session._serve_batch(1., meta, payload, RoundAccount())
            except Exception as exc:
                errors.append(exc)
        thread = threading.Thread(target=serve, daemon=True); thread.start()
        try:
            actual = (client._batch_micro(front, opt, x, y, 0, micro) if micro > 1
                      else client._batch(front, opt, x, y, 0))
            thread.join(6)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            for trained, reference in ((front, rf), (back, rb)):
                for p, ref in zip(trained.parameters(), reference.parameters()):
                    torch.testing.assert_close(p, ref, atol=1e-6, rtol=1e-6)
            self.assertAlmostEqual(actual[-1], loss.item(), places=6)
            self.assertLessEqual(client.traffic["max_inflight_microbatches"], window)
            self.assertEqual(client.traffic["activation_payload_bytes"], n * (5 * 4 + 8))
            return client.traffic
        finally:
            left.close(); right.close()

    def test_equal_chunks_and_windows_match_full_batch(self):
        normal = self.run_batch(12, 1, 1)
        for window in (1, 2, 4):
            with self.subTest(window=window):
                micro = self.run_batch(12, 4, window)
                self.assertEqual(micro["activation_messages"], 4)
                self.assertEqual(micro["activation_payload_bytes"], normal["activation_payload_bytes"])
                self.assertGreater(micro["activation_main_channel_bytes"], normal["activation_main_channel_bytes"])

    def test_unequal_chunks_use_sample_weights(self):
        self.run_batch(11, 4, 2)


if __name__ == "__main__":
    unittest.main()
