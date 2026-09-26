from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sfl"))
from barrier_schedule import GradientJob, chunk_schedule, completions
from trace_replay import replay


class TraceReplayTests(unittest.TestCase):
    def test_closed_queue_matches_independent_static_calculation(self):
        jobs = [GradientJob(k, b, q, q, q) for k, b, q in [("a", 120003, .1), ("b", 240008, 2.), ("c", 180001, .3)]]
        for policy in ("rr", "fifo", "sjf", "tail"):
            got = replay(jobs, dict.fromkeys("abc", 0.), {j.cid: j.tail_estimate_s for j in jobs}, 1e6, policy, record_chunks=True)
            expected = completions(chunk_schedule(jobs, policy), 1e6)
            for k in expected:
                self.assertAlmostEqual(got["completion_s"][k], expected[k])
            for j in jobs:
                offset = 0
                for c in got["chunks"]:
                    if c["cid"] == j.cid:
                        self.assertEqual(c["offset"], offset); offset += c["bytes"]
                self.assertEqual(offset, j.size_bytes)

    def test_no_invented_gain_without_overlap_and_no_waiting(self):
        jobs = [GradientJob("a", 100000, 0., 0., 0.), GradientJob("b", 100000, 1., 1., 1.)]
        for policy in ("rr", "fifo", "sjf", "tail", "guarded"):
            got = replay(jobs, {"a": 0., "b": 5.}, {"a": 0., "b": 1.}, 1e6, policy)
            self.assertAlmostEqual(got["completion_s"]["a"], .8)
            self.assertAlmostEqual(got["barrier_s"], 6.8)
            self.assertFalse(got["used_tail"])

    def test_score_uses_actual_capacity_not_planner_capacity(self):
        job = GradientJob("a", 100000, 0., 0., 0.)
        got = replay([job], {"a": 0}, {"a": 0}, 1e6, "guarded", predicted_capacity_bps=1e9)
        self.assertAlmostEqual(got["barrier_s"], .8)

    def test_invalid_release_rejected(self):
        job = GradientJob("a", 1, 0, 0, 0)
        with self.assertRaises(ValueError):
            replay([job], {"a": -1}, {"a": 0}, 1e6, "rr")


if __name__ == "__main__":
    unittest.main()
