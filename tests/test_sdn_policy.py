"""The SDN exporter must never command a port outside the owned bridge."""

import unittest

from sfl.sdn.policy import build_policy, validate_policy


class SDNPolicyTests(unittest.TestCase):
    def test_export_validated_flows(self):
        decision = {"clients": {"c1": {"depth": 2, "route": ["a", "b"]}}}
        policy = build_policy(decision, {"c1": ("10.2.0.1", "10.2.0.2")},
                              {"a": 3, "b": 4}, 1, "10.3.0.10", 8081, 17)
        validate_policy(policy, {3, 4}, 17, 1, "10.3.0.10", 8081)
        self.assertEqual([r["out_port"] for r in policy["rules"]], [3, 4])

    def test_cross_boundary_policy_rejected(self):
        decision = {"clients": {"c1": {"depth": 2, "route": ["a"]}}}
        p = build_policy(decision, {"c1": ("10.2.0.1",)}, {"a": 3},
                         1, "10.3.0.10", 8081, 17)
        p["rules"][0]["out_port"] = 99
        with self.assertRaises(ValueError):
            validate_policy(p, {3, 4}, 17, 1, "10.3.0.10", 8081)
        p["rules"][0]["out_port"] = 3
        p["rules"][0]["in_port"] = 8
        with self.assertRaises(ValueError):
            validate_policy(p, {3, 4}, 17, 1, "10.3.0.10", 8081)


if __name__ == "__main__":
    unittest.main()
