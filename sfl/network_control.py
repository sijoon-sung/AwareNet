"""Application-level routing with explicit shared bottlenecks.

Input: fixed model widths / round activation+gradient demand and authorized
routes. Output: a bounded route proposal, not an OpenFlow installation claim.
Capacities are symmetric effective rates. Predictions exclude GPU/queue time.
"""
import itertools
import json
import math
from pathlib import Path


def load_topology(path, paths):
    data = json.loads(Path(path).read_text(encoding="utf-8")) if path else {"schema": 1, "shared_links": []}
    if data.get("schema") != 1 or not isinstance(data.get("shared_links"), list):
        raise ValueError("topology needs schema=1 and shared_links")
    names = set()
    for link in data["shared_links"]:
        if (not link.get("name") or link["name"] in names or not link.get("paths")
                or not set(link["paths"]) <= set(paths)
                or not math.isfinite(link["capacity_mbps"]) or link["capacity_mbps"] <= 0):
            raise ValueError("invalid shared link name, paths or capacity")
        names.add(link["name"])
    return data


def flow_rates(sets, caps, access, shared_links=()):
    """Max-min flow rates constrained by *every* resource on each route.

    Scalar access shares one client link; a pair means independent interfaces.
    A shared link may contain multiple logical routes, e.g. one VM uplink.
    """
    capacities = {("path", p): float(v) for p, v in caps.items()}
    resources = {}
    for link in shared_links:
        capacities[("shared", link["name"])] = link["capacity_mbps"] * 1e6
    for k, routes in sets.items():
        value = access[k]
        independent = isinstance(value, (list, tuple))
        if not independent:
            capacities[("access", k)] = value
        for x, p in enumerate(routes):
            if p not in caps:
                raise ValueError(f"unknown path {p}")
            acc = ("access", k, x) if independent else ("access", k)
            if independent:
                if x >= len(value):
                    raise ValueError(f"missing interface cap: {k}/{x}")
                capacities[acc] = value[x]
            resources[k, x] = {("path", p), acc} | {
                ("shared", link["name"]) for link in shared_links if p in link["paths"]}
    if any(not math.isfinite(v) or v <= 0 for v in capacities.values()):
        raise ValueError("all link capacities must be finite and positive")
    rates = {f: 0. for f in resources}
    active = set(resources)
    residual = dict(capacities)
    while active:
        counts = {r: sum(r in resources[f] for f in active) for r in capacities}
        ratios = {r: residual[r] / n for r, n in counts.items() if n}
        increment = max(0., min(ratios.values()))
        limiting = {r for r, v in ratios.items() if v <= increment + 1e-8}
        for f in active:
            rates[f] += increment
        for r, n in counts.items():
            residual[r] = max(0., residual[r] - increment * n)
        frozen = {f for f in active if resources[f] & limiting}
        if not frozen:
            raise RuntimeError("resource allocation made no progress")
        active -= frozen
    return {k: [rates[k, x] for x in range(len(routes))] for k, routes in sets.items()}


def plan_routes(demand_bytes, current, allowed, caps, access, *, shared_links=(),
                max_moves=1, switch_cost=0., multipath=False):
    """Minimize the worst predicted round transfer completion, then its sum.

    Widths are deliberately absent from this API: the learning policy supplies
    a demand contract. Greedy moves require >5% improvement; no global optimum.
    """
    if (not demand_bytes or set(demand_bytes) != set(current) or max_moves < 0
            or not math.isfinite(switch_cost) or switch_cost < 0):
        raise ValueError("invalid route/demand keys or move constraints")
    for k, demand in demand_bytes.items():
        if not math.isfinite(demand) or demand <= 0:
            raise ValueError(f"invalid transfer demand for {k}")
        if not current[k] or not allowed.get(k) or not set(allowed[k]) <= set(caps) or not set(current[k]) <= set(allowed[k]):
            raise ValueError(f"route outside explicit allowlist: {k}")
    initial = {k: tuple(v) for k, v in current.items()}

    def evaluate(sets):
        rates = flow_rates(sets, caps, access, shared_links)
        times = {k: demand_bytes[k] * 8 / sum(rates[k])
                 + (switch_cost if sets[k] != initial[k] else 0.) for k in sets}
        return times, rates

    sets, moved = dict(initial), set()
    before, _ = evaluate(sets)
    times = before
    for _ in range(min(max_moves, len(sets))):
        best = None
        for k in sorted(sets):
            if k in moved:
                continue
            ps = sorted(allowed[k])
            candidates = [(p,) for p in ps]
            if multipath and demand_bytes[k] >= 2 * (1 << 20):
                if isinstance(access[k], (tuple, list)):
                    candidates = list(itertools.product(ps, repeat=2))
                else:
                    candidates += list(itertools.combinations(ps, 2))
            for candidate in candidates:
                if candidate == sets[k]:
                    continue
                trial = dict(sets, **{k: candidate})
                t, _ = evaluate(trial)
                mx, old = max(t.values()), max(times.values())
                improves = mx < old * .95 or (abs(mx-old) < 1e-9 and sum(times.values())-sum(t.values()) > .05*times[k])
                score = (mx, sum(t.values()))
                if improves and (best is None or score < best[0]):
                    best = (score, trial, t, k)
        if best is None:
            break
        _, sets, times, k = best
        moved.add(k)
    times, rates = evaluate(sets)
    return {"sets": sets, "weights_bps": rates, "demand_bytes": dict(demand_bytes),
            "predicted_network_s": times, "before_network_s": before,
            "moved": sorted(moved), "shared_links": list(shared_links),
            "model": "symmetric_capacity_only_excludes_compute_and_RTT",
            "route_status": "endpoint_requested"}


def endpoints_for(edges, routes, client_index):
    return [[edges[p][0], edges[p][1] + 2*client_index + x] for x, p in enumerate(routes)]


def verify_receipts(detail, endpoints, epoch):
    """Completion receipt is evidence of app execution, never a physical path proof."""
    results = {}
    for k, expected in endpoints.items():
        receipt = detail.get(k, {}).get("route_receipt") or {}
        matches = receipt.get("epoch") == epoch and receipt.get("endpoints") == expected
        results[k] = {"status": "round_completed" if matches else "unverified",
                      "active_exits": receipt.get("active_exits", [])}
    return results
