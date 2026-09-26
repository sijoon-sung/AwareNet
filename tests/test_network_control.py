import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sfl"))
from network_control import flow_rates, plan_routes, verify_receipts
from chunker import Reassembler
from policies import NetworkOnly, RoundContext


class RoutingTests(unittest.TestCase):
    def test_two_logical_paths_share_one_physical_limit(self):
        rates = flow_rates({"c0": ("1",), "c1": ("2",)}, {"1": 100e6, "2": 100e6},
            {"c0": 100e6, "c1": 100e6}, [{"name": "uplink", "paths": ["1", "2"], "capacity_mbps": 20}])
        self.assertEqual(rates, {"c0": [10e6], "c1": [10e6]})

    def test_client_shared_access_is_also_a_joint_limit(self):
        rates = flow_rates({"c0": ("1", "2")}, {"1": 100e6, "2": 100e6}, {"c0": 30e6})
        self.assertEqual(sum(rates["c0"]), 30e6)
        rates = flow_rates({"c0": ("1", "2")}, {"1": 100e6, "2": 100e6}, {"c0": [30e6, 20e6]})
        self.assertEqual(sum(rates["c0"]), 50e6)

    def test_a_capped_flow_releases_capacity_to_other_flows(self):
        rates = flow_rates({"c0": ("1",), "c1": ("1",)}, {"1": 100e6}, {"c0": 10e6, "c1": 100e6})
        self.assertEqual(rates, {"c0": [10e6], "c1": [90e6]})

    def test_same_shared_bottleneck_has_no_invented_routing_gain(self):
        args = ({"c0": 10e6}, {"c0": ("1",)}, {"c0": ["1", "2"]},
                {"1": 100e6, "2": 100e6}, {"c0": 200e6})
        result = plan_routes(*args, multipath=True, shared_links=[{"name": "wan", "paths": ["1", "2"], "capacity_mbps": 10}])
        self.assertEqual(result["moved"], [])
        self.assertAlmostEqual(result["predicted_network_s"]["c0"], 8.)

    def test_independent_alternative_can_reduce_completion_at_same_payload(self):
        demand = {"c0": 10e6, "c1": 10e6}
        result = plan_routes(demand, {"c0": ("1",), "c1": ("1",)},
            {"c0": ["1", "2"], "c1": ["1", "2"]}, {"1": 10e6, "2": 100e6},
            {"c0": 100e6, "c1": 100e6}, max_moves=1)
        self.assertEqual(len(result["moved"]), 1)
        self.assertEqual(result["demand_bytes"], demand)
        self.assertLess(max(result["predicted_network_s"].values()), max(result["before_network_s"].values()))

    def test_route_authorization_and_switch_cost(self):
        args = ({"c0": 10e6}, {"c0": ("1",)}, {"c0": ["1", "2"]},
                {"1": 10e6, "2": 100e6}, {"c0": 100e6})
        self.assertEqual(plan_routes(*args, switch_cost=100)["moved"], [])
        bad = list(args); bad[2] = {"c0": ["2"]}
        with self.assertRaises(ValueError):
            plan_routes(*bad)

    def test_receipt_must_match_both_epoch_and_endpoint(self):
        endpoints = {"c0": [["host", 12000]]}
        detail = {"c0": {"route_receipt": {"epoch": 4, "endpoints": endpoints["c0"], "active_exits": [0]}}}
        self.assertEqual(verify_receipts(detail, endpoints, 4)["c0"]["status"], "round_completed")
        self.assertEqual(verify_receipts(detail, endpoints, 5)["c0"]["status"], "unverified")
        self.assertEqual(verify_receipts({}, endpoints, 4)["c0"]["status"], "unverified")

    def test_network_policy_preserves_external_width_and_requires_receipt(self):
        args = SimpleNamespace(paths="10,100", ladder="", access_caps="", network_topology="", oracle_plan="",
            access_mode="shared", batches=4, max_moves=1, switch_cost=0., multipath=False, micro=1)
        prof = {"bytes": {"c0": 4e6}, "access": {"c0": 100e6}}
        ctx = RoundContext(a=args, r=0, ids=["c0"], mctl=None, measured=True,
            rnd={"psets": {"c0": ("1",)}}, plan={"c0": .75}, allowed={"c0": ["1", "2"]},
            edges={"1": ("host", 12000), "2": ("host", 13000)},
            sensor=SimpleNamespace(profile=lambda: copy.deepcopy(prof), caps_effective=lambda caps: caps))
        policy = NetworkOnly(args)
        policy.apply(ctx)
        self.assertEqual(ctx.plan, {"c0": .75})
        self.assertEqual(ctx.dp, {"c0": [["host", 13000]]})
        ctx.r = 1
        with self.assertRaises(RuntimeError):
            policy.apply(ctx)


class ReassemblyTests(unittest.TestCase):
    def test_overlap_cannot_fake_completion(self):
        r = Reassembler()
        r.feed(dict(tid="t", total=4, seq=0, off=0, ln=2), b"ab")
        with self.assertRaises(ValueError):
            r.feed(dict(tid="t", total=4, seq=1, off=0, ln=2), b"cd")
        self.assertFalse(r.is_complete("t"))
        with self.assertRaises(ValueError):
            r.pop("t")

    def test_total_negative_offset_and_conflicting_duplicate_rejected(self):
        r = Reassembler()
        m = dict(tid="t", total=4, seq=0, off=0, ln=2)
        r.feed(m, b"ab"); r.feed(m, b"ab")
        for change, payload in [({"total": 5}, b"ab"), ({"off": -1}, b"ab"), ({}, b"zz")]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                r.feed(dict(m, **change), payload)
        r.feed(dict(m, seq=1, off=2), b"cd")
        self.assertEqual(r.pop("t"), b"abcd")


if __name__ == "__main__":
    unittest.main()
