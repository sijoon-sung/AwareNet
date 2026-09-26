"""Trace-conditioned single-egress model. No field-measurement claims.

All release and tail inputs are explicit. A guarded intervention is considered
only after every outstanding job has been released; it never waits to build a
queue. Actual capacity scores the execution; predicted capacity plans it.
"""
from collections import deque
import math

from barrier_schedule import GradientJob, plan_window


def replay(jobs, release_s, tails_s, capacity_bps, policy, *, predicted_capacity_bps=None,
           quantum_bytes=65536, completion_error_s=.01, record_chunks=False):
    jobs = list(jobs)
    keys = {j.cid for j in jobs}
    if (not jobs or len(keys) != len(jobs) or keys != set(release_s) or keys != set(tails_s)
            or policy not in ("rr", "fifo", "sjf", "tail", "guarded")
            or not isinstance(quantum_bytes, int) or quantum_bytes <= 0):
        raise ValueError("invalid job set, policy or quantum")
    predicted_capacity_bps = capacity_bps if predicted_capacity_bps is None else predicted_capacity_bps
    if any(not math.isfinite(x) or x <= 0 for x in (capacity_bps, predicted_capacity_bps)):
        raise ValueError("capacities must be finite and positive")
    if any(not math.isfinite(x) or x < 0 for x in [*release_s.values(), *tails_s.values(), completion_error_s]):
        raise ValueError("invalid time")
    order = {j.cid: i for i, j in enumerate(jobs)}
    by_id = {j.cid: j for j in jobs}
    waiting = deque(sorted(jobs, key=lambda j: (release_s[j.cid], order[j.cid])))
    ready, final_plan = deque(), None
    remaining = {j.cid: j.size_bytes for j in jobs}
    offsets = dict.fromkeys(keys, 0)
    now, completed, chunks, used_tail, decision = 0., {}, [], False, None
    persistent = None

    def arrivals():
        while waiting and release_s[waiting[0].cid] <= now+1e-12:
            ready.append(waiting.popleft().cid)

    while len(completed) < len(jobs):
        arrivals()
        if not ready and not final_plan:
            now = release_s[waiting[0].cid]
            arrivals()
        if policy == "guarded" and not waiting and final_plan is None:
            window = [GradientJob(k, remaining[k], by_id[k].tail_estimate_s,
                                  by_id[k].tail_low_s, by_id[k].tail_high_s) for k in ready]
            decision = plan_window(window, predicted_capacity_bps, quantum_bytes=quantum_bytes,
                                   completion_error_s=completion_error_s)
            final_plan = deque(decision["schedule"])
            used_tail = decision["used_tail"]
        if final_plan:
            k, _, length = final_plan.popleft()
        else:
            if persistent is not None:
                k = persistent
            elif policy == "tail":
                k = max(ready, key=lambda c: by_id[c].tail_estimate_s)
            elif policy == "sjf":
                k = min(ready, key=lambda c: remaining[c])
            else:
                k = ready[0]
            ready.remove(k)
            length = min(quantum_bytes, remaining[k])
            persistent = k if policy in ("fifo", "sjf") else None
        now += length*8/capacity_bps
        if record_chunks:
            chunks.append({"cid": k, "offset": offsets[k], "bytes": length, "send_at_s": now})
        offsets[k] += length
        remaining[k] -= length
        if remaining[k] == 0:
            completed[k] = now
            persistent = None
        if final_plan is None:
            arrivals()
            if remaining[k]:
                ready.append(k)
    return {"completion_s": completed,
            "finish_s": {k: completed[k]+tails_s[k] for k in keys},
            "barrier_s": max(completed[k]+tails_s[k] for k in keys),
            "used_tail": used_tail, "total_payload_bytes": sum(j.size_bytes for j in jobs),
            "prediction_regret_bound_s": decision["worst_case_regret_bound_s"] if decision else None,
            "chunks": chunks}
