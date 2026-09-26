import copy
from pathlib import Path
import statistics
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/analysis"))
from measured_replay import load_inputs, network_windows, scenario


class MeasuredReplayTests(unittest.TestCase):
    def test_rate_counts_payload_over_a_common_wall_interval(self):
        d = {"meta": {"n": 2, "proto": "tcp", "pattern": "burst", "rounds": 1,
                      "batches": 4, "up_mb": 4.2, "dn_mb": 4.2, "aggregate_mbps": 999999},
             "per": {"a": {"spans": [[1., 5.]]}, "b": {"spans": [[1., 9.]]}}}
        w = network_windows(d)[0]
        self.assertEqual(w["duration_s"], 8.)
        self.assertEqual(w["effective_service_bps"], 67.2e6)

    def test_evaluation_samples_never_change_the_calibrated_estimate(self):
        data = load_inputs()
        first = scenario(data, 10, .5, "compute_ready", 1., 1)
        changed = copy.deepcopy(data)
        changed["jetson"]["power_modes"]["MAXN_SUPER"]["step_times_ms"][10] *= 4
        second = scenario(changed, 10, .5, "compute_ready", 1., 1)
        self.assertEqual({j.cid: j.tail_estimate_s for j in first["jobs"]},
                         {j.cid: j.tail_estimate_s for j in second["jobs"]})
        self.assertNotEqual(first["tails_s"]["c0"], second["tails_s"]["c0"])

    def test_millisecond_units_mapping_and_raw_payload_are_preserved(self):
        data = load_inputs()
        s = scenario(data, 10, .5, "compute_ready", 1., 1)
        self.assertAlmostEqual(s["full_step_s"]["c0"], .553330)
        for k in s["tails_s"]:
            self.assertAlmostEqual(s["tails_s"][k]+s["release_s"][k], s["full_step_s"][k])
        self.assertEqual(sum(j.size_bytes for j in s["jobs"]), 33600000)
        raw = data["jetson"]["power_modes"]["15W"]["step_times_ms"]
        self.assertEqual(round(statistics.median(raw), 1), 903.7)
        with self.assertRaises(ValueError):
            scenario(data, 0, .5, "compute_ready", 1., 1)


if __name__ == "__main__":
    unittest.main()
