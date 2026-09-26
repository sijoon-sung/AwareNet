"""Small deterministic checks of the SuperSFL/AwareNet algorithm contract."""

import math
import unittest

from sfl.supersfl_net import (ClientProfile, DepthCost, aggregate_prefix_layers,
                              fuse_gradients, fusion_weights, plan_supernet_round)


class SuperSFLNetTests(unittest.TestCase):
    def test_memory_and_network_are_joint_constraints(self):
        clients = {
            "a": ClientProfile(1.0, (10e6,), {
                1: DepthCost(1, 1_000_000, 0.5, 0.5),
                2: DepthCost(2, 250_000, 1.0, 0.0),
                3: DepthCost(2, 100_000, 2.0, 0.0)}, ("1", "2")),
            "b": ClientProfile(0.5, (10e6,), {
                1: DepthCost(1, 1_000_000, 0.5, 0.0),
                2: DepthCost(1, 100_000, 1.0, 0.0)}, ("1", "2")),
        }
        result = plan_supernet_round(clients, {"1": 2e6, "2": 10e6},
                                     quality_weight=5)
        self.assertEqual(result["clients"]["a"]["depth"], 2)
        self.assertEqual(result["clients"]["b"]["depth"], 1)
        self.assertEqual(result["clients"]["b"]["route"], ["2"])
        self.assertTrue(math.isfinite(result["makespan_s"]))

    def test_route_switch_cost_prevents_small_moves(self):
        c = {"a": ClientProfile(1, (10e6,), {1: DepthCost(1, 100_000, 1)},
                                ("1", "2"))}
        old = {"a": {"depth": 1, "route": ["1"]}}
        keep = plan_supernet_round(c, {"1": 8e6, "2": 10e6},
                                   current=old, move_cost_s=1)
        self.assertEqual(keep["clients"]["a"]["route"], ["1"])
        move = plan_supernet_round(c, {"1": 1e6, "2": 10e6},
                                   current=old, move_cost_s=0.1)
        self.assertEqual(move["clients"]["a"]["route"], ["2"])

    def test_fusion_and_layer_coverage(self):
        wc, ws, rho = fusion_weights(1, 3, 2, 4)
        self.assertAlmostEqual(wc, 0.75)
        self.assertAlmostEqual(ws, 0.25)
        self.assertAlmostEqual(rho, 0.5)
        self.assertAlmostEqual(fuse_gradients(4, 0, 1, 3, 2, 4), 1.5)
        result = aggregate_prefix_layers({0: 10.0, 1: 20.0, 2: 30.0}, [
            {"depth": 1, "loss": 1, "layers": {0: 2.0}},
            {"depth": 2, "loss": 1, "layers": {0: 4.0, 1: 8.0}},
        ], anchor=0)
        self.assertAlmostEqual(result[0], 10 / 3)
        self.assertAlmostEqual(result[1], 8)
        self.assertAlmostEqual(result[2], 30)


if __name__ == "__main__":
    unittest.main()
