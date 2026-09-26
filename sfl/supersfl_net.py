"""SuperSFL-inspired split-depth training with AwareNet path planning.

This module is independent of the fixed-cut wire protocol in fed_client/server.
Depth profiles must come from measurements of the chosen supernetwork; activation
size is not assumed to be monotone in depth. Rates use AwareNet's water-fill model.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Mapping

from sfl.plan import effective_rate


@dataclass(frozen=True)
class DepthCost:
    compute_s: float
    activation_bytes: int  # forward and backward bytes per round
    memory_gb: float
    quality_penalty: float = 0.0  # calibrated validation penalty, not accuracy


@dataclass(frozen=True)
class ClientProfile:
    memory_gb: float
    access_bps: tuple[float, ...]
    depths: Mapping[int, DepthCost]
    allowed_paths: tuple[str, ...]


def supersfl_initial_depth(memory_gb: float, latency_ms: float,
                           min_latency_ms: float, max_latency_ms: float,
                           total_layers: int) -> int:
    """SuperSFL Eq. 1 initial depth; measured feasibility is checked separately."""
    if total_layers < 2 or memory_gb <= 0:
        raise ValueError("total_layers >= 2 and memory_gb > 0 are required")
    rank = (max_latency_ms - latency_ms) / (max_latency_ms - min_latency_ms + 1e-8)
    return max(1, min(total_layers - 1, math.floor(0.5 * memory_gb + 4 * rank)))


def _routes(client: ClientProfile, caps: Mapping[str, float]):
    paths = tuple(p for p in client.allowed_paths if p in caps and caps[p] > 0)
    if not paths:
        raise ValueError("client has no usable path")
    # A route tuple assigns each live exit to a path, as in sfl.plan.
    n_exits = min(len(client.access_bps), 2)
    return tuple(itertools.product(paths, repeat=n_exits))


def _score(depths, routes, clients, caps, quality_weight, switch_cost_s):
    access = {cid: p.access_bps for cid, p in clients.items()}
    rates = effective_rate(routes, caps, access)
    times = {}
    for cid, p in clients.items():
        cost = p.depths[depths[cid]]
        rate = rates.get(cid, 0.0)
        times[cid] = (cost.compute_s + 8 * cost.activation_bytes / rate
                      if rate > 0 else math.inf)
    penalty = sum(clients[cid].depths[d].quality_penalty for cid, d in depths.items()) / len(clients)
    return max(times.values()) + quality_weight * penalty + switch_cost_s, times


def plan_supernet_round(clients: Mapping[str, ClientProfile], caps: Mapping[str, float],
                        quality_weight: float = 0.0, current: Mapping | None = None,
                        move_cost_s: float = 0.0, max_passes: int = 8):
    """Coordinate search over feasible split depths and AwareNet routes.

    Objective: predicted round makespan + quality_weight * mean calibrated
    depth penalty + path-switch cost. This is a heuristic, not a global optimum.
    Returns a decision and diagnostics suitable for logging and replay.
    """
    if not clients or not caps or quality_weight < 0 or move_cost_s < 0:
        raise ValueError("nonempty clients/caps and nonnegative costs are required")
    current = current or {}
    options = {}
    for cid, p in clients.items():
        feasible = tuple(sorted(d for d, c in p.depths.items()
                                if d >= 1 and c.memory_gb <= p.memory_gb
                                and c.compute_s >= 0 and c.activation_bytes >= 0
                                and c.quality_penalty >= 0))
        if not feasible or not p.access_bps or any(a <= 0 for a in p.access_bps):
            raise ValueError(f"no feasible depth or access for {cid}")
        options[cid] = (feasible, _routes(p, caps))

    depths = {}
    routes = {}
    for cid, (ds, rs) in options.items():
        old = current.get(cid, {})
        depths[cid] = old.get("depth") if old.get("depth") in ds else ds[-1]
        old_route = tuple(old.get("route", ()))
        routes[cid] = old_route if old_route in rs else rs[0]

    def evaluate():
        switches = sum(tuple(current[cid].get("route", ())) != routes[cid]
                       for cid in clients if cid in current)
        return _score(depths, routes, clients, caps, quality_weight,
                      switches * move_cost_s)

    score, times = evaluate()
    for _ in range(max_passes):
        changed = False
        for cid in sorted(clients):
            previous_score = score
            best = (score, depths[cid], routes[cid], times)
            for d in options[cid][0]:
                for route in options[cid][1]:
                    depths[cid], routes[cid] = d, route
                    trial, trial_times = evaluate()
                    if trial < best[0] - 1e-9:
                        best = (trial, d, route, trial_times)
            score, depths[cid], routes[cid], times = best
            changed |= score < previous_score - 1e-9
        # A full sweep with no objective improvement is a fixed point.
        new_score, times = evaluate()
        if abs(new_score - score) > 1e-8:
            raise AssertionError("planner score drift")
        if not changed:
            break
    return {"clients": {cid: {"depth": depths[cid], "route": list(routes[cid]),
                               "predicted_s": times[cid]} for cid in clients},
            "objective": score, "makespan_s": max(times.values()),
            "quality_penalty": sum(clients[cid].depths[d].quality_penalty
                                   for cid, d in depths.items()) / len(clients)}


def fusion_weights(client_loss: float, server_loss: float, depth: int,
                   total_layers: int):
    """SuperSFL Eq. 2-4: local/server direction weights and coverage scale."""
    if min(client_loss, server_loss) < 0 or not 1 <= depth < total_layers:
        raise ValueError("losses must be nonnegative; 1 <= depth < total_layers")
    a, b = 1 / (client_loss + 1e-8), 1 / (server_loss + 1e-8)
    return a / (a + b), b / (a + b), depth / total_layers


def fuse_gradients(local, server, client_loss: float, server_loss: float,
                   depth: int, total_layers: int):
    """Works with scalars, NumPy arrays, or Torch tensors of identical shape."""
    wc, ws, rho = fusion_weights(client_loss, server_loss, depth, total_layers)
    return rho * (wc * local + ws * server)


def aggregate_prefix_layers(server_layers: Mapping[int, object], updates: list[dict],
                            anchor: float = 0.01):
    """SuperSFL Eq. 5-7, only over clients covering each layer.

    Each update: {depth: int, loss: float, layers: {layer_index: tensor}}.
    Values may be scalars or same-shaped tensors. Missing layers stay at server.
    """
    if anchor < 0 or not updates or any(u["depth"] < 1 or u["loss"] < 0 for u in updates):
        raise ValueError("updates required; depth positive, loss/anchor nonnegative")
    raw = [u["depth"] / (u["loss"] + 1e-8) for u in updates]
    total = sum(raw)
    weights = [w / total for w in raw]
    result = {}
    for layer, server_value in server_layers.items():
        selected = [(w, u["layers"][layer]) for w, u in zip(weights, updates)
                    if layer < u["depth"] and layer in u["layers"]]
        if not selected:
            result[layer] = server_value
            continue
        denom = anchor + sum(w for w, _ in selected)
        result[layer] = (anchor * server_value + sum((w * v for w, v in selected),
                                                      start=0)) / denom
    return result
