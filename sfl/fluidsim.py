# -*- coding: utf-8 -*-
"""유체 이벤트 시뮬레이터 — HPC 에 올리기 전에 내 PC 에서 라운드를 돌려 본다. (2026-09-07)

  (sim.py 는 폭만 있던 시절의 대규모 시뮬레이터다. 이 파일은 경로·분할·마이크로배치까지 있는 새 판.
   sim.py 의 설계 원칙 "컨트롤러가 모르는 것을 세계에 넣어 자기채점을 막는다"는 여기서도 지킨다:
   기기들이 서로 어긋나 혼잡이 시간에 따라 변하는 것을 계획기의 정적 모형은 모른다 → 관측과 모형이 갈라진다.)

  무엇을 흉내 내나
    기기 k 는 배치마다 [연산 C_k w^γ] → [전송 B_k w 비트] 를 반복한다. 전송 중인 기기들은 열린 경로에서
    TCP 공정 분배(물 채우기, plan.water_fill)로 **순간** 전송률을 나눈다. 기기들이 서로 어긋나면 혼잡이 낮아져
    관측 전송시간이 정적 모형보다 짧아진다 — 실제 리그에서 본 그 현상이 여기서 재현된다.
    (즉시 내보내기) 마이크로배치 m: 배치를 m 조각으로 잘라 연산(i+1) 과 전송(i) 을 겹친다.

  무엇을 안 흉내 내나
    패킷·큐·RTT(유체 근사), 정확도(정확도는 HPC 실측: rw_long). 서버 연산은 상수로 준다.

  쓰임
    simulate_round(devs, widths, sets, caps, batches, micro=1) → {k: {"total","compute","xfer"}}
    run_policy(devs, caps, policy, rounds, ...)               → 라운드별 기록 (계획기 plan.py 를 닫힌 고리로 호출)
"""
import statistics

import plan

EPS = 1e-9


class Device:
    def __init__(self, k, cpu, bytes_, access=None, gamma=1.2, wobble=None, overhead=0.0):
        """wobble=(exit, period_s, frac, seed): 그 출구의 접속 속도가 period 마다 [1-frac, 1+frac]×기준 으로 흔들린다 (무선 페이딩 흉내).
        계획기는 기준값(프로브)만 알고, 흔들림은 관측(효율 계수)으로만 본다 — 자기채점 방지."""
        self.k, self.cpu, self.bytes, self.access, self.gamma = k, cpu, bytes_, access, gamma
        self.wobble = wobble
        self.overhead = overhead           # 배치당 고정 전송 오버헤드(초): 바이트가 흐르기 전 협상·회신 시간 (실측 0.3~0.5s, 2026-09-08)

    def access_at(self, t):
        """시각 t 의 접속 상한 (출구별). wobble 이 없으면 고정."""
        if not self.wobble or not isinstance(self.access, (list, tuple)):
            return self.access
        import random
        e, period, frac, seed = self.wobble
        slot = int(t // period)
        r = random.Random(seed * 1000003 + slot).uniform(1 - frac, 1 + frac)
        a = list(self.access); a[e] = a[e] * r
        return a


def _rates(active_sets, caps, access):
    """전송 중인 기기들만으로 물 채우기 → {k: bit/s}."""
    if not active_sets:
        return {}
    return plan.effective_rate(active_sets, caps, access)


def simulate_round(devs, widths, sets, caps, batches, micro=1, server_s=0.0):
    """한 라운드. 반환 {k: {"total": 라운드 시간, "compute": 연산 합, "xfer": 전송 합(대기 포함)}}.

    기기마다 연산줄·전송줄 두 개. 직렬(micro=1): 조각 i 의 전송이 끝나야(기울기가 와야) 조각 i+1 연산.
    마이크로배치(micro>1): 전송줄은 연산이 끝난 조각을 집고, 연산줄은 한 배치치(m 조각) 이상 앞서지 않는다."""
    access = {d.k: d.access for d in devs if d.access}
    oh = {d.k: getattr(d, "overhead", 0.0) for d in devs}
    wob = [d for d in devs if d.wobble]
    st = {}
    for d in devs:
        w = widths[d.k]
        c = d.cpu * (w ** d.gamma) / micro
        x = d.bytes * w * 8 / micro
        st[d.k] = {"cq": [c] * (batches * micro), "xq": [x] * (batches * micro), "ready": 0,
                   "c_rem": None, "x_rem": None, "h_rem": 0.0, "done_c": 0, "done_x": 0,
                   "t_compute": 0.0, "t_xfer": 0.0, "t_end": 0.0}
    t = 0.0
    while True:
        for k, s in st.items():
            if s["c_rem"] is None and s["cq"]:
                if micro == 1 and s["done_x"] < s["done_c"]:
                    pass
                elif micro > 1 and s["ready"] - s["done_x"] >= micro:
                    pass
                else:
                    s["c_rem"] = s["cq"].pop(0)
            if s["x_rem"] is None and s["xq"] and s["ready"] > s["done_x"]:
                s["x_rem"] = s["xq"].pop(0); s["h_rem"] = oh.get(k, 0.0)
        active = {k: tuple(sets[k]) for k, s in st.items() if s["x_rem"] is not None and s["h_rem"] <= 0}
        if wob:                                                    # 무선 흔들림: 지금 시각의 접속 상한으로
            access = dict(access); access.update({d.k: d.access_at(t) for d in wob})
        rates = _rates(active, caps, access)
        dt = float("inf")
        if wob:                                                    # 다음 흔들림 경계까지만 진행 (속도가 바뀌는 시각을 넘지 않게)
            per = min(d.wobble[1] for d in wob)
            dt = min(dt, max(1e-6, (int(t // per) + 1) * per - t))
        for k, s in st.items():
            if s["c_rem"] is not None:
                dt = min(dt, s["c_rem"])
            if s["x_rem"] is not None and s["h_rem"] > 0:
                dt = min(dt, s["h_rem"])
            elif s["x_rem"] is not None and rates.get(k, 0) > 0:
                dt = min(dt, s["x_rem"] / rates[k])
        if dt == float("inf"):
            break
        t += dt
        for k, s in st.items():
            if s["c_rem"] is not None:
                s["c_rem"] -= dt; s["t_compute"] += dt
                if s["c_rem"] <= EPS:
                    s["c_rem"] = None; s["ready"] += 1; s["done_c"] += 1
            if s["x_rem"] is not None and s["h_rem"] > 0:
                s["h_rem"] -= dt; s["t_xfer"] += dt
                if s["h_rem"] <= EPS:
                    s["h_rem"] = 0.0
            elif s["x_rem"] is not None:
                r = rates.get(k, 0.0)
                s["x_rem"] -= r * dt; s["t_xfer"] += dt
                if s["x_rem"] <= EPS * max(1.0, r):
                    s["x_rem"] = None; s["done_x"] += 1; s["t_end"] = t + server_s
        if all(not s["cq"] and not s["xq"] and s["c_rem"] is None and s["x_rem"] is None for s in st.values()):
            break
    return {k: {"total": s["t_end"], "compute": s["t_compute"], "xfer": s["t_xfer"]} for k, s in st.items()}


def profile_of(devs):
    return {"cpu": {d.k: d.cpu for d in devs}, "gamma": {d.k: d.gamma for d in devs},
            "bytes": {d.k: d.bytes for d in devs}, "access": {d.k: d.access for d in devs if d.access} or None}


POLICIES = ("uniform", "rr", "path", "mp", "width", "both", "bothmp")   # rr = 고르게 나눈 고정 배정(라운드로빈), 규모 실험의 공정한 기준선


def run_policy(devs, caps, policy, rounds, batches=4, ladder=(0.5, 0.75, 1.0), alpha=1.2, micro=1,
               window=3, deadline_mode="anchored", max_moves=1, deadline_s=None, lam=None):
    """계획기를 닫힌 고리로. policy ∈ POLICIES. 반환 [{"round","sets","widths","makespan","cost","why","per"}]."""
    assert policy in POLICIES, policy
    ks = [d.k for d in devs]
    prof = profile_of(devs)
    paths = sorted(caps)
    sets = {k: ((paths[i % len(paths)],) if policy == "rr" else ("1",)) for i, k in enumerate(ks)}
    widths = {k: 1.0 for k in ks}
    obs = {k: [] for k in ks}
    state = {"sets": sets, "widths": widths, "observed": {}, "raise_ok": {}, "ref_sets": None}
    lad = ladder if policy in ("width", "both", "bothmp") else (1.0,)
    mm = 0 if policy in ("uniform", "rr", "width") else max_moves
    mp = policy in ("mp", "bothmp")
    hist = []
    for r in range(rounds):
        why = "균등" if policy == "uniform" else "고정 분산"
        if policy not in ("uniform", "rr"):
            res = plan.plan(prof, state, caps, ladder=lad, alpha=alpha, max_moves=mm, multipath=mp,
                            remaining=rounds - r, batches=batches, p_min=min(lad), deadline_mode=deadline_mode, deadline_s=deadline_s, lam=lam)
            sets, widths, why = res["sets"], res["widths"], res["why"]
            state.update({"sets": sets, "widths": widths, "raise_ok": res["raise_ok"], "ref_sets": res["ref_sets"]})
        per = simulate_round(devs, widths, sets, caps, batches, micro=micro)
        for k in ks:                                   # 인지: 관측 전송시간(배치당, 전폭 환산) + 배정 스냅샷 — sense.Sensor 와 같은 꼴
            obs[k].append({"net": per[k]["xfer"] / batches / max(widths[k], 1e-6), "raw": per[k]["xfer"] / batches, "w": widths[k],
                           "tot": per[k]["total"], "sets": dict(sets)})
            del obs[k][:-window]
        state["observed"] = {k: list(v) for k, v in obs.items()}
        hist.append({"round": r, "sets": dict(sets), "widths": dict(widths),
                     "makespan": max(v["total"] for v in per.values()),
                     "cost": sum(v["total"] for v in per.values()), "why": why, "per": per})
    return hist


def summarize(hist, skip=2):
    """앞 skip 라운드(수렴 전)를 뺀 평균과 마지막 배정, 이동 횟수."""
    H = hist[skip:] or hist
    return {"makespan": statistics.mean(h["makespan"] for h in H), "cost": statistics.mean(h["cost"] for h in H),
            "widths": H[-1]["widths"], "sets": H[-1]["sets"],
            "moves": sum(1 for a, b in zip(hist, hist[1:]) if a["sets"] != b["sets"])}
