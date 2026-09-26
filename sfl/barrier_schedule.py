"""Research prototype: schedule a closed window of ready gradients.

The longest-tail-first candidate is a CLASSICAL scheduling rule, not a new
algorithm claim. The gate checks its effect on max(completion + local tail)
against chunk round-robin for every tail inside declared intervals.

Scope: one controlled, constant-rate egress, all window jobs ready, independent
local tails, no new network dependency inside a tail. No live SFL/SDN hookup.
"""
from dataclasses import dataclass
from collections import deque
import math
import statistics


@dataclass(frozen=True)
class GradientJob:
    cid: str
    size_bytes: int
    tail_estimate_s: float
    tail_low_s: float
    tail_high_s: float

    def __post_init__(self):
        vals = (self.tail_low_s, self.tail_estimate_s, self.tail_high_s)
        if (not self.cid or not isinstance(self.size_bytes, int) or self.size_bytes <= 0
                or not all(math.isfinite(x) for x in vals)
                or not 0 <= vals[0] <= vals[1] <= vals[2]):
            raise ValueError("job needs positive bytes and 0 <= low <= estimate <= high")


def chunk_schedule(jobs, policy, quantum_bytes=65536):
    """Return (client, offset, length) with each byte sent exactly once."""
    jobs = list(jobs)
    if (not jobs or len({j.cid for j in jobs}) != len(jobs)
            or not isinstance(quantum_bytes, int) or quantum_bytes <= 0):
        raise ValueError("need nonempty unique jobs and a positive integer quantum")
    if policy == "tail":
        jobs = sorted(jobs, key=lambda j: -j.tail_estimate_s)
    elif policy == "sjf":
        jobs = sorted(jobs, key=lambda j: j.size_bytes)
    elif policy not in ("fifo", "rr"):
        raise ValueError("unknown policy")
    result = []
    if policy != "rr":
        for j in jobs:
            for off in range(0, j.size_bytes, quantum_bytes):
                result.append((j.cid, off, min(quantum_bytes, j.size_bytes-off)))
    else:
        offsets = {j.cid: 0 for j in jobs}
        while any(offsets[j.cid] < j.size_bytes for j in jobs):
            for j in jobs:
                off = offsets[j.cid]
                if off < j.size_bytes:
                    size = min(quantum_bytes, j.size_bytes-off)
                    result.append((j.cid, off, size))
                    offsets[j.cid] += size
    return result


def completions(schedule, capacity_bps):
    if not math.isfinite(capacity_bps) or capacity_bps <= 0:
        raise ValueError("positive finite capacity required")
    t, done = 0., {}
    for cid, _, size in schedule:
        t += size * 8 / capacity_bps
        done[cid] = t
    return done


def barrier_time(completion_s, tails_s):
    if not completion_s or set(completion_s) != set(tails_s):
        raise ValueError("completion and tail keys must match")
    return max(completion_s[k] + tails_s[k] for k in completion_s)


def worst_case_regret(candidate_s, baseline_s, intervals):
    """Exact max_q[max_i(C_i+q_i) - max_i(B_i+q_i)] on a tail box.

    For fixed i, the maximizing assignment uses q_i=high_i and all other
    q_j=low_j. Taking max over i commutes with max over q. This is a conditional
    certificate for the stated window model, NOT an end-to-end WAN guarantee.
    """
    if not candidate_s or set(candidate_s) != set(baseline_s) or set(candidate_s) != set(intervals):
        raise ValueError("matching nonempty keys required")
    for k, (lo, hi) in intervals.items():
        if not all(math.isfinite(v) and v >= 0 for v in (lo, hi, candidate_s[k], baseline_s[k])) or lo > hi:
            raise ValueError("invalid completion or interval")
    return max(candidate_s[k] + intervals[k][1]
               - max(baseline_s[j] + (intervals[j][1] if k == j else intervals[j][0]) for j in baseline_s)
               for k in candidate_s)


def plan_window(jobs, capacity_bps, *, quantum_bytes=65536,
                required_gain_s=.001, completion_error_s=0.):
    """Keep RR unless tail-first improves even at the worst point in the box.

    completion_error_s bounds absolute error of EACH completion prediction in
    both arms; 2*error is charged in the comparison. Tail intervals must come
    from past observations and their coverage must be measured separately.
    """
    if any(not math.isfinite(v) or v < 0 for v in (required_gain_s, completion_error_s)):
        raise ValueError("gain and completion error must be nonnegative")
    jobs = list(jobs)
    baseline = chunk_schedule(jobs, "rr", quantum_bytes)
    candidate = chunk_schedule(jobs, "tail", quantum_bytes)
    b, c = completions(baseline, capacity_bps), completions(candidate, capacity_bps)
    intervals = {j.cid: (j.tail_low_s, j.tail_high_s) for j in jobs}
    regret = worst_case_regret(c, b, intervals) + 2*completion_error_s
    use = regret < -required_gain_s
    return {"schedule": candidate if use else baseline, "used_tail": use,
            "reason": "window_gain_certified" if use else "insufficient_evidence_keep_rr",
            "worst_case_regret_bound_s": regret,
            "baseline_completion_s": b, "candidate_completion_s": c,
            "scope": "closed_ready_window_single_egress_independent_local_tails"}


class TailHistory:
    """Past-only heuristic intervals with a joint-coverage circuit breaker.

    These are NOT statistical confidence intervals. A first unanticipated
    drift may cause a bad decision before it can be observed. Use a separate
    instance after a model/width/batch/context change; never mix contexts.
    """
    def __init__(self, window=12, warmup=8, cooldown=3):
        if not 1 <= warmup <= window or cooldown < 0:
            raise ValueError("invalid history options")
        self.window, self.warmup, self.cooldown = window, warmup, cooldown
        self.history = {}
        self.coverage = deque(maxlen=8)
        self.blocked = 0
        self.pending = None

    def predict(self, sizes):
        if self.pending is not None:
            raise RuntimeError("observe the previous window before predicting again")
        if self.history and set(sizes) != set(self.history):
            raise ValueError("client/context changed; create a new TailHistory")
        ready = bool(sizes) and all(len(self.history.get(k, ())) >= self.warmup for k in sizes)
        jobs = []
        for k, size in sizes.items():
            hist = self.history.get(k, ())
            if ready:
                lo, hi, estimate = max(0., min(hist)*.8-.002), max(hist)*1.2+.002, statistics.median(hist)
            else:
                lo, hi, estimate = 0., 1e9, statistics.median(hist) if hist else 0.
            jobs.append(GradientJob(k, size, estimate, lo, hi))
        trusted = ready and self.blocked == 0 and (not self.coverage or statistics.mean(self.coverage) >= .875)
        self.pending = {"jobs": jobs, "ready": ready}
        return jobs, trusted

    def observe(self, actual):
        if self.pending is None or set(actual) != {j.cid for j in self.pending["jobs"]}:
            raise ValueError("observation needs a matching prediction")
        if any(not math.isfinite(q) or q < 0 for q in actual.values()):
            raise ValueError("tails must be finite and nonnegative")
        covered = all(j.tail_low_s <= actual[j.cid] <= j.tail_high_s for j in self.pending["jobs"])
        if self.pending["ready"]:
            self.coverage.append(covered)
        self.blocked = max(0, self.blocked-1)
        if not covered:
            self.blocked = self.cooldown
        for k, q in actual.items():
            self.history.setdefault(k, deque(maxlen=self.window)).append(q)
        self.pending = None
        return covered
