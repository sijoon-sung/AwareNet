"""Causal invariants of the experimental compute-budget policy (no torch)."""
import argparse
import ast
import contextlib
import copy
import io
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sfl"))
from device_budget import (ComputeTracker, access_profile, plan_round,
                           measured_outcome, transport_observations, validate_options)
from plan import effective_rate
from policies import RoundContext, WidthPath, POLICY_NAMES


def profile():
    return {"cpu": {"c0": 1., "c1": 4.}, "gamma": {"c0": 1., "c1": 1.},
            "bytes": {"c0": 4_000_000., "c1": 4_000_000.},
            "access": {"c0": [40e6, 20e6], "c1": [40e6, 20e6]},
            "allowed": {"c0": ["1", "2"], "c1": ["1", "2"]},
            "caps": {"1": 10e6, "2": 100e6}}


def options(**changes):
    values = dict(planner="device-budget", policy="widthpath", preflight=True,
        edges="1=localhost:12000,2=localhost:13000", paths="10,100",
        edge_groups="1,2:0-1", clients=2, pipeline="off", micro=1, stagger="off",
        compute_budget_s=4., batches=4, max_moves=1, switch_cost=0.,
        deadline_s=None, access_mode="shared", multipath=False, ladder="0.25,0.5,0.75,1",
        solo=True, access_caps="", path_exec="", rounds=24)
    values.update(changes)
    return SimpleNamespace(**values)


class BudgetTests(unittest.TestCase):
    def run_plan(self, prof=None, widths=None, sets=None, **kwargs):
        args = dict(max_moves=1, switch_cost=0., access_mode="shared")
        args.update(kwargs)
        return plan_round(prof or profile(), widths or {"c0": 1., "c1": 1.},
                          sets or {"c0": ("1",), "c1": ("1",)},
                          {"c0": 4., "c1": 4.}, [.25, .5, .75, 1.], 4, **args)

    def test_only_compute_overloaded_client_shrinks(self):
        res = self.run_plan()
        self.assertEqual(res["widths"], {"c0": 1., "c1": .25})
        self.assertFalse(any(d["predicted_budget_miss"] for d in res["clients"].values()))

    def test_network_collapse_and_deadline_never_change_widths(self):
        normal = self.run_plan()
        congested = profile()
        congested["caps"] = {"1": 100., "2": 100.}
        slow = self.run_plan(congested, deadline_s=.01)
        self.assertEqual(normal["widths"], slow["widths"])
        self.assertTrue(all(slow["predicted_deadline_miss"].values()))

    def test_infeasible_budget_is_reported(self):
        prof = profile()
        prof["cpu"]["c1"] = 100.
        res = self.run_plan(prof)
        self.assertTrue(res["clients"]["c1"]["predicted_budget_miss"])
        self.assertIsNone(res["clients"]["c1"]["largest_feasible_width"])

    def test_recovery_requires_two_rounds_and_one_ladder_step(self):
        widths = {"c0": .25, "c1": .25}
        one = self.run_plan(widths=widths)
        self.assertEqual(one["widths"]["c0"], .25)
        two = self.run_plan(widths=widths, raise_ok=one["raise_ok"])
        self.assertEqual(two["widths"]["c0"], .5)

    def test_wait_is_not_a_compute_observation(self):
        tracker = ComputeTracker()
        detail = {"c0": {"cli_fwd": 2., "cli_bwd": 2., "cli_wait": 1000., "t_round": 1004.}}
        prof, src = tracker.update(profile(), {"c0": 1.}, detail, 4)
        self.assertEqual(prof["cpu"]["c0"], 1.)
        self.assertEqual(src["c0"], "round_compute_scaled")
        detail["c0"]["cli_fwd"] = 18.
        prof, _ = tracker.update(prof, {"c0": 1.}, detail, 4)
        self.assertEqual(prof["cpu"]["c0"], 5.)

    def test_stale_measurement_cannot_trigger_recovery(self):
        res = self.run_plan(widths={"c0": .25, "c1": .25},
                            raise_ok={"c0": 2}, recovery_allowed=set())
        self.assertEqual(res["widths"]["c0"], .25)
        self.assertEqual(res["clients"]["c0"]["reason"], "recovery_waiting_for_measurement")

    def test_width_normalization_and_invalid_measurement_fallback(self):
        tracker = ComputeTracker()
        prof, _ = tracker.update(profile(), {"c0": .5},
            {"c0": {"cli_fwd": 1., "cli_bwd": 1.}}, 4)
        self.assertEqual(prof["cpu"]["c0"], 1.)
        prof, src = tracker.update(prof, {"c0": .5},
            {"c0": {"cli_fwd": float("nan"), "cli_bwd": 0.}}, 4)
        self.assertEqual(prof["cpu"]["c0"], 1.)
        self.assertEqual(src["c0"], "stale_compute")

    def test_shared_interface_does_not_sum_probe_caps(self):
        acc = access_profile({"c0": [40e6, 20e6]}, "shared")
        rates = effective_rate({"c0": ("1", "2")}, {"1": 100e6, "2": 100e6}, acc)
        self.assertEqual(acc["c0"], 40e6)
        self.assertLessEqual(rates["c0"], 40e6)
        independent = access_profile({"c0": [40e6, 20e6]}, "independent")
        rates = effective_rate({"c0": ("1", "2")}, {"1": 100e6, "2": 100e6}, independent)
        self.assertEqual(rates["c0"], 60e6)

    def test_independent_mode_rejects_a_single_cap(self):
        with self.assertRaises(ValueError):
            access_profile({"c0": 40e6}, "independent")

    def test_routing_is_bounded_and_can_improve_at_fixed_width(self):
        stay = self.run_plan(max_moves=0)
        move = self.run_plan(max_moves=1)
        self.assertEqual(stay["widths"], move["widths"])
        self.assertEqual(sum(move["sets"][k] != stay["sets"][k] for k in stay["sets"]), 1)
        self.assertLess(move["predicted_makespan_s"], stay["predicted_makespan_s"])

    def test_switch_cost_can_prevent_a_move(self):
        res = self.run_plan(switch_cost=1000.)
        self.assertEqual(res["sets"], {"c0": ("1",), "c1": ("1",)})

    def test_allowlist_blocks_faster_unregistered_destination(self):
        prof = profile()
        prof["allowed"] = {"c0": ["1"], "c1": ["1"]}
        self.assertEqual(self.run_plan(prof)["sets"], {"c0": ("1",), "c1": ("1",)})
        prof["allowed"].pop("c1")
        with self.assertRaises(ValueError):
            self.run_plan(prof)

    def test_server_queue_is_removed_only_from_sensor_residual(self):
        original = {"c0": {"xfer": 12., "srv_gpu": 3., "lock_wait": 7.}}
        self.assertEqual(transport_observations(original)["c0"]["xfer"], 2.)
        self.assertEqual(original["c0"]["xfer"], 12.)

    def test_plan_does_not_mutate_input(self):
        prof = profile()
        before = copy.deepcopy(prof)
        self.run_plan(prof, multipath=True)
        self.assertEqual(before, prof)

    def test_predicted_feasibility_does_not_hide_observed_violation(self):
        decision = self.run_plan(deadline_s=20.)
        self.assertFalse(decision["clients"]["c0"]["predicted_budget_miss"])
        result = measured_outcome({"c0": {"cli_fwd": 5., "cli_bwd": 1.}}, decision, 25.)
        self.assertTrue(result["clients"]["c0"]["compute_budget_miss"])
        self.assertEqual(result["clients"]["c1"]["status"], "missing_measurement")
        self.assertTrue(result["deadline_miss"])

    def test_bad_numeric_inputs_fail_explicitly(self):
        for value in (0., -1., float("nan"), float("inf")):
            with self.subTest(value=value):
                prof = profile()
                prof["cpu"]["c0"] = value
                with self.assertRaises(ValueError):
                    self.run_plan(prof)


class IntegrationTests(unittest.TestCase):
    def test_real_policy_updates_width_endpoint_weights_and_audit(self):
        prof = profile()
        sensor = SimpleNamespace(profile=lambda: copy.deepcopy(prof),
                                 caps_effective=lambda caps: caps, access={})
        args = options()
        ctx = RoundContext(a=args, r=0, mctl=None, ids=["c0", "c1"],
            rnd={"psets": {"c0": ("1",), "c1": ("1",)}},
            plan={"c0": 1., "c1": 1.}, measured=True, sensor=sensor,
            allowed=prof["allowed"], edges={"1": ("localhost", 12000), "2": ("localhost", 13000)})
        policy = WidthPath(args)
        with contextlib.redirect_stdout(io.StringIO()):
            policy.apply(ctx)
        self.assertEqual(ctx.plan, {"c0": 1., "c1": .25})
        self.assertEqual(ctx.rnd["budget_decision"]["route_status"], "endpoint_requested")
        self.assertEqual(sensor.access["c0"], 40e6)
        for i, k in enumerate(ctx.ids):
            for x, p in enumerate(ctx.rnd["psets"][k]):
                self.assertEqual(ctx.dp[k][x][1], ctx.edges[p][1] + 2*i + x)
            self.assertEqual(len(ctx.mpplan[k]), len(ctx.dp[k]))
        # An actual subsequent round's compute overload must override the preflight.
        ctx.r = 1
        ctx.last_detail = {"c0": {"cli_fwd": 8., "cli_bwd": 8.}}
        with contextlib.redirect_stdout(io.StringIO()):
            policy.apply(ctx)
        self.assertEqual(ctx.plan["c0"], .25)

    def test_invalid_mode_combinations_fail_before_runtime(self):
        for changes in ({"preflight": False}, {"micro": 2}, {"pipeline": "on"},
                        {"compute_budget_s": 0}, {"edge_groups": "1:0"},
                        {"edge_groups": "3:0-1"}, {"edge_groups": "1:0-1;2:1"},
                        {"edges": "1=x:1"}, {"solo": False},
                        {"access_mode": "independent"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_options(options(**changes))
        validate_options(options())
        validate_options(options(planner="plan", compute_budget_s=None))

    def test_actual_server_argument_parser_without_loading_torch(self):
        # Execute the real standalone parser AST, not a copied argument definition.
        tree = ast.parse((ROOT / "sfl/fed_server.py").read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "parse_args")
        ns = {"argparse": argparse, "POLICY_NAMES": POLICY_NAMES,
              "torch": SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "fed_server.parse_args", "exec"), ns)
        argv = ["--planner", "device-budget", "--policy", "widthpath", "--preflight", "--solo",
                "--compute-budget-s", "4", "--clients", "2", "--paths", "10,100",
                "--edges", "1=localhost:12000,2=localhost:13000", "--edge-groups", "1,2:0-1"]
        args = ns["parse_args"](argv)
        self.assertEqual(args.access_mode, "shared")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            ns["parse_args"](argv + ["--micro", "2"])


if __name__ == "__main__":
    unittest.main()
