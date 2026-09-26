import itertools
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sfl"))
from barrier_schedule import GradientJob, TailHistory, barrier_time, chunk_schedule, completions, plan_window, worst_case_regret


class BarrierScheduleTests(unittest.TestCase):
    def test_regret_formula_matches_all_box_vertices(self):
        r = random.Random(73)
        for _ in range(100):
            keys = list("abcd")
            c, b = ({k: r.random()*3 for k in keys} for _ in range(2))
            intervals = {k: (r.random(), 1+r.random()) for k in keys}
            brute = max(barrier_time(c, dict(zip(keys, v))) - barrier_time(b, dict(zip(keys, v)))
                        for v in itertools.product(*(intervals[k] for k in keys)))
            self.assertAlmostEqual(worst_case_regret(c, b, intervals), brute)

    def test_classical_tail_rule_matches_exhaustive_ready_job_optimum(self):
        r = random.Random(51)
        for _ in range(20):
            jobs = [GradientJob(str(i), r.randint(1, 6)*65536, q, q, q)
                    for i, q in enumerate(r.random() for _ in range(5))]
            tails = {j.cid: j.tail_estimate_s for j in jobs}
            opt = min(barrier_time(completions(chunk_schedule(p, "fifo"), 1e6), tails)
                      for p in itertools.permutations(jobs))
            got = barrier_time(completions(chunk_schedule(jobs, "tail"), 1e6), tails)
            self.assertAlmostEqual(got, opt)

    def test_byte_coverage_and_common_bottleneck(self):
        jobs = [GradientJob("a", 100005, .01, 0, .02), GradientJob("b", 240007, 2, 1.9, 2.1)]
        result = plan_window(jobs, 1e6)
        self.assertTrue(result["used_tail"])
        for p in ("rr", "tail", "fifo", "sjf"):
            seq = chunk_schedule(jobs, p)
            for j in jobs:
                offset = 0
                for cid, off, size in seq:
                    if cid == j.cid:
                        self.assertEqual(off, offset); offset += size
                self.assertEqual(offset, j.size_bytes)

    def test_uncertainty_homogeneity_and_prediction_error_stop_intervention(self):
        self.assertFalse(plan_window([GradientJob(str(i), 100000, 1, 1, 1) for i in range(3)], 1e6)["used_tail"])
        jobs = [GradientJob("a", 100000, 0., 0., 3.), GradientJob("b", 100000, 2., 0., 3.)]
        self.assertFalse(plan_window(jobs, 1e6)["used_tail"])
        jobs = [GradientJob("a", 100000, 0., 0., 0.), GradientJob("b", 100000, 2., 2., 2.)]
        self.assertFalse(plan_window(jobs, 1e6, completion_error_s=3)["used_tail"])

    def test_inverted_prediction_can_break_an_invalid_certificate(self):
        jobs = [GradientJob("a", 100000, 0., 0., 0.), GradientJob("b", 100000, 2., 2., 2.)]
        result = plan_window(jobs, 1e6)
        self.assertTrue(result["used_tail"])
        actual = {"a": 2., "b": 0.}  # Deliberately outside declared intervals.
        self.assertGreater(barrier_time(completions(result["schedule"], 1e6), actual),
                           barrier_time(result["baseline_completion_s"], actual))

    def test_malformed_inputs(self):
        with self.assertRaises(ValueError):
            GradientJob("a", 1, 2, 3, 4)
        j = GradientJob("a", 1, 0, 0, 0)
        for jobs, cap in [([], 1.), ([j, j], 1.), ([j], 0.)]:
            with self.assertRaises(ValueError):
                plan_window(jobs, cap)

    def test_equal_size_sjf_preserves_fifo_ties(self):
        jobs = [GradientJob(k, 100000, 1, 1, 1) for k in ("c7", "c1", "c3")]
        self.assertEqual(chunk_schedule(jobs, "sjf"), chunk_schedule(jobs, "fifo"))

    def test_history_uses_past_only_and_stops_after_observed_drift(self):
        hist = TailHistory()
        sizes = {"a": 100000, "b": 100000}
        for _ in range(8):
            _, trusted = hist.predict(sizes)
            self.assertFalse(trusted)
            hist.observe({"a": .1, "b": 1.})
        _, trusted = hist.predict(sizes)
        self.assertTrue(trusted)
        self.assertFalse(hist.observe({"a": 1., "b": .1}))
        _, trusted = hist.predict(sizes)
        self.assertFalse(trusted)
        with self.assertRaises(RuntimeError):
            hist.predict(sizes)
        hist.observe({"a": 1., "b": .1})


if __name__ == "__main__":
    unittest.main()
