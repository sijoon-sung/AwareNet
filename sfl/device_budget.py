"""Experimental compute-budget policy for serial, fixed-cut SFL.

Width controls client compute time; routing controls delivery at that width.
All times are predictions, not enforced CPU quotas or accuracy guarantees.
This module has no torch, socket, or privileged network dependencies.
"""
import math
import statistics

try:
    from . import plan as network
except ImportError:  # fed_server.py's existing direct-script entry point
    import plan as network


def positive(value):
    return isinstance(value, (int, float)) and math.isfinite(value) and value > 0


def access_profile(access, mode):
    """Two endpoint probes do not establish two independent access links."""
    if mode not in ("shared", "independent"):
        raise ValueError("access mode must be shared or independent")
    result = {}
    for k, value in (access or {}).items():
        vals = list(value) if isinstance(value, (tuple, list)) else [value]
        if not vals or not all(positive(v) for v in vals):
            raise ValueError(f"invalid access capacity for {k}")
        if mode == "independent":
            if len(vals) != 2:
                raise ValueError(f"{k}: independent mode needs two measured/configured link caps")
            result[k] = vals
        else:
            # A proxy bound from solo probes, NOT proof of available aggregate bandwidth.
            result[k] = max(vals)
    return result


def transport_observations(detail):
    """Serial-only residual: remove measured server compute and lock wait.

    Serialization, OS scheduling and control overhead remain. This is not a
    wire-only timer. Never use this subtraction for overlapped execution.
    """
    return {k: dict(d, xfer=max(1e-6, d.get("xfer", 0.0)
                              - d.get("srv_gpu", 0.0) - d.get("lock_wait", 0.0)))
            for k, d in detail.items()}


def measured_outcome(detail, decision, makespan):
    """Observed results are separate from the pre-round predictions."""
    if not decision:
        return None
    clients = {}
    for k, predicted in decision["clients"].items():
        d = detail.get(k, {})
        if "cli_fwd" not in d or "cli_bwd" not in d:
            clients[k] = {"status": "missing_measurement"}
            continue
        compute = d["cli_fwd"] + d["cli_bwd"]
        clients[k] = {"compute_s": compute,
                      "compute_budget_miss": compute > predicted["budget_s"],
                      "compute_prediction_error_s": compute - predicted["predicted_compute_s"],
                      "server_compute_and_wait_s": d.get("srv_gpu", 0.) + d.get("lock_wait", 0.)}
    deadline = decision["deadline_s"]
    return {"clients": clients, "makespan_s": makespan,
            "deadline_miss": None if deadline is None else makespan > deadline}


class ComputeTracker:
    """Refresh full-width compute estimates without using round or wait time."""
    def __init__(self):
        self.history = {}

    def update(self, profile, widths, detail, batches):
        if batches < 1:
            raise ValueError("batches must be positive")
        prof = dict(profile, cpu=dict(profile.get("cpu", {})))
        sources = {}
        for k, width in widths.items():
            d = detail.get(k, {})
            parts = [d.get("cli_fwd"), d.get("cli_bwd")]
            valid = all(isinstance(v, (int, float)) and math.isfinite(v) and v >= 0
                        for v in parts)
            if valid and sum(parts) > 0:
                gamma = prof.get("gamma", {}).get(k, 1.2)
                if not positive(width) or not positive(gamma):
                    raise ValueError(f"invalid width/gamma for {k}")
                full = sum(parts) / batches / width ** gamma
                hist = self.history.setdefault(k, [])
                hist.append(full)
                del hist[:-3]
                # React immediately to overload; require sustained recovery.
                prof["cpu"][k] = max(full, statistics.median(hist))
                sources[k] = "round_compute_scaled"
            elif self.history.get(k):
                prof["cpu"][k] = max(self.history[k][-1], statistics.median(self.history[k]))
                sources[k] = "stale_compute"
            else:
                sources[k] = "preflight"
        return prof, sources


def choose_widths(prof, previous, budgets, ladder, batches, raise_ok=None, recovery_allowed=None):
    """Largest feasible ladder width; overload immediate, recovery one step/2 rounds."""
    lad = sorted(set(ladder))
    if not lad or any(not positive(w) or w > 1 for w in lad):
        raise ValueError("width ladder must lie in (0, 1]")
    widths, counters, decisions = {}, {}, {}
    for k, old in previous.items():
        cpu, gamma, budget = prof["cpu"].get(k), prof.get("gamma", {}).get(k, 1.2), budgets.get(k)
        if not all(positive(v) for v in (cpu, gamma, budget, old)) or batches < 1:
            raise ValueError(f"missing/invalid compute profile or budget for {k}")
        cost = lambda w: batches * cpu * w ** gamma
        feasible = [w for w in lad if cost(w) <= budget]
        target = max(feasible) if feasible else min(lad)
        count = 0
        if target < old:
            chosen, reason = target, "compute_budget_exceeded"
        elif target > old and recovery_allowed is not None and k not in recovery_allowed:
            chosen, reason = old, "recovery_waiting_for_measurement"
        elif target > old:
            count = (raise_ok or {}).get(k, 0) + 1
            chosen = min(w for w in lad if w > old) if count >= 2 else old
            reason = "compute_recovery" if count >= 2 else "recovery_pending"
            if count >= 2:
                count = 0
        else:
            chosen, reason = target, "compute_within_budget"
        if not feasible:
            reason = "compute_budget_infeasible_at_min_width"
        widths[k], counters[k] = chosen, count
        decisions[k] = {"reason": reason, "budget_s": budget, "full_compute_s": cost(1),
                        "predicted_compute_s": cost(chosen), "previous_width": old,
                        "width": chosen, "largest_feasible_width": max(feasible) if feasible else None,
                        "predicted_budget_miss": cost(chosen) > budget}
    return widths, counters, decisions


def predict(widths, sets, prof, caps, batches, initial, switch_cost, overhead=None):
    times = network.round_times(widths, sets, prof, caps, current_sets=initial,
                                switch_cost=switch_cost, batches=batches)
    return {k: t * batches + (overhead or {}).get(k, 0.0) for k, t in times.items()}


def route_at_fixed_width(widths, sets, prof, caps, batches, max_moves, switch_cost,
                         multipath=False, overhead=None):
    """Bounded greedy search: reduce max round time, then sum on tied maxima.

    No global-optimum claim. Every trial respects an explicit client allowlist.
    A client may move at most once in this decision. Five percent hysteresis
    suppresses small model-only improvements; switch time is also charged.
    """
    current = {k: tuple(v) for k, v in sets.items()}
    if not caps or any(not positive(v) for v in caps.values()):
        raise ValueError("route capacities must be finite and positive")
    allowed = prof.get("allowed", {})
    for k in widths:
        if not allowed.get(k) or not set(allowed[k]) <= set(caps):
            raise ValueError(f"{k}: an explicit registered edge allowlist is required")
        if not current.get(k) or not set(current[k]) <= set(allowed[k]):
            raise ValueError(f"{k}: current route is outside its allowlist")
        if not positive(prof.get("bytes", {}).get(k)):
            raise ValueError(f"{k}: missing activation/gradient byte profile")
    evaluate = lambda s: predict(widths, s, prof, caps, batches, current, switch_cost, overhead)
    result, moved = dict(current), set()
    times = evaluate(result)
    for _ in range(min(max_moves, len(widths))):
        old_max, old_sum = max(times.values()), sum(times.values())
        best = None
        for k in sorted(widths):
            if k in moved:
                continue
            candidates = network.candidate_sets(sorted(allowed[k]), multipath,
                prof["bytes"][k] * widths[k] >= 2 * (1 << 20),
                isinstance((prof.get("access") or {}).get(k), (tuple, list)))
            for cand in candidates:
                if cand == result[k]:
                    continue
                trial = dict(result, **{k: cand})
                trial_times = evaluate(trial)
                mx, total = max(trial_times.values()), sum(trial_times.values())
                improves = (mx < old_max * .95 or
                            (abs(mx - old_max) < 1e-9 and old_sum - total > .05 * times[k]))
                if improves and (best is None or (mx, total) < best[0]):
                    best = ((mx, total), trial, trial_times, k)
        if best is None:
            break
        _, result, times, k = best
        moved.add(k)
    return result, times


def plan_round(prof, previous, sets, budgets, ladder, batches, *, raise_ok=None,
               max_moves=1, switch_cost=0.0, multipath=False, access_mode="shared",
               deadline_s=None, overhead=None, recovery_allowed=None):
    if max_moves < 0 or not math.isfinite(switch_cost) or switch_cost < 0:
        raise ValueError("move limit and switch cost must be nonnegative")
    if deadline_s is not None and not positive(deadline_s):
        raise ValueError("deadline must be positive")
    if set(previous) != set(sets) or not previous:
        raise ValueError("widths and routes must cover the same nonempty client set")
    prof = dict(prof, access=access_profile(prof.get("access"), access_mode))
    widths, counters, decisions = choose_widths(prof, previous, budgets, ladder, batches, raise_ok, recovery_allowed)
    routes, times = route_at_fixed_width(widths, sets, prof, prof["caps"], batches,
                                        max_moves, switch_cost, multipath, overhead)
    return {"widths": widths, "sets": routes, "raise_ok": counters, "clients": decisions,
            "predicted_round_s": times, "predicted_makespan_s": max(times.values()),
            "deadline_s": deadline_s,
            "predicted_deadline_miss": {k: deadline_s is not None and t > deadline_s for k, t in times.items()},
            "access_mode": access_mode, "access_proxy_bps": prof["access"],
            "route_model": "shared_capacity_plus_last_server_time", "measured_performance": False}


def validate_options(a):
    """Fail before opening sockets when this experimental mode cannot be evaluated."""
    network_mode = a.policy == "network"
    if a.planner != "device-budget" and not network_mode:
        return
    if a.policy not in ("widthpath", "network") or not a.preflight or not a.edges or not a.paths:
        raise ValueError("network/device-budget requires --preflight --edges --paths")
    if a.path_exec:
        raise ValueError("device-budget uses registered endpoints; --path-exec is not used in this mode")
    if a.pipeline != "off" or (a.micro != 1 and not network_mode) or a.stagger != "off":
        raise ValueError("use pipeline off / stagger off; device-budget also needs micro 1")
    if (not network_mode and not positive(a.compute_budget_s)) or a.batches < 1 or a.clients < 1:
        raise ValueError("device-budget requires a positive --compute-budget-s, batches and clients")
    if network_mode and a.micro > 1 and a.norm != "gn":
        raise ValueError("network microbatch comparison requires --norm gn on server and clients")
    if network_mode and a.oracle_plan:
        import json
        widths = json.loads(a.oracle_plan)
        if set(widths) != {f"c{i}" for i in range(a.clients)} or any(not positive(w) or w > 1 for w in widths.values()):
            raise ValueError("network --oracle-plan must supply a valid fixed width for every client")
    if a.max_moves < 0 or not math.isfinite(a.switch_cost) or a.switch_cost < 0:
        raise ValueError("invalid move limit or switch cost")
    if a.deadline_s is not None and not positive(a.deadline_s):
        raise ValueError("--deadline-s must be positive")
    if a.access_mode == "independent" and not a.multipath:
        raise ValueError("independent access requires --multipath and two independent interfaces")
    caps = [float(v) for v in a.paths.split(",")]
    edges = [tok.split("=")[0] for tok in a.edges.split(",")]
    if not all(positive(v) for v in caps) or set(edges) != {str(i+1) for i in range(len(caps))} or len(set(edges)) != len(edges):
        raise ValueError("--edges must register each --paths ID exactly once (1..M)")
    allowed = {}
    for grp in a.edge_groups.split(";"):
        if not grp.strip():
            continue
        ps, span = grp.split(":")
        lo, hi = (span.split("-") + [span])[:2]
        lo, hi = int(lo), int(hi)
        if lo < 0 or hi < lo or hi >= a.clients or not set(ps.split(",")) <= set(edges):
            raise ValueError("invalid --edge-groups range or unregistered edge")
        for i in range(lo, hi+1):
            if i in allowed:
                raise ValueError("overlapping client ranges in --edge-groups")
            allowed[i] = ps
    if len(allowed) != a.clients:
        raise ValueError("--edge-groups must explicitly cover every client")
    if a.ladder and any(not positive(float(w)) or float(w) > 1 for w in a.ladder.split(",")):
        raise ValueError("--ladder must lie in (0,1]")
    if not a.solo:
        configured = {kv.split("=")[0] for kv in a.access_caps.split(",") if "=" in kv}
        if configured != {f"c{i}" for i in range(a.clients)}:
            raise ValueError("provide --solo or --access-caps for every client")
