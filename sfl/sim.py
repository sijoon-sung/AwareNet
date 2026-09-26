# -*- coding: utf-8 -*-
"""대규모 시뮬레이터 — **클라 수백~수천 대에서 결정 규칙이 어떻게 되는가.**

  ── 왜 시뮬레이터인가 ───────────────────────────────────────────
  이 기계는 클라 4대까지가 정직한 한계다(8대는 CPU 과다구독, 고쳐도 3.4배 부풀음).
  그런데 **규칙이 규모에서 무너지는지**는 실험으로 얻을 수 있는 것이 아니다.
  결정 규칙은 시간 모형 위의 알고리즘이므로, 학습을 실제로 돌리지 않고
  시간 모형만 돌려도 **결정의 옳고 그름**은 볼 수 있다.

  ★ 시뮬레이터가 답할 수 있는 것과 없는 것을 먼저 못박는다.
      답할 수 있다: 규칙이 누구를 얼마나 좁히나 · 라운드 시간이 어떻게 되나 ·
                    N 이 커질 때 판정이 뒤집히나 · 낙오자를 놓치나
      답할 수 없다: 정확도. 학습을 안 돌리므로 **정확도는 한 줄도 말하지 않는다.**
                    폭을 깎는 대가는 실측(E8: -0.5pp / -1.2pp)에서만 온다.

  ── ★★ 자기채점 방지 — 이 파일의 설계 원칙 ─────────────────────
  시뮬레이터의 시간식이 컨트롤러의 predict() 와 같으면 컨트롤러는 **완벽한 모형**을
  갖게 되어 무조건 잘한다. 그건 오라클이 자기 연산을 하드코딩해 자기 손을 들어준
  사고와 똑같은 함정이다 (2026-08 실측으로 한 번 겪었다).
  그래서 진짜 세계에는 컨트롤러가 **모르는 것**을 반드시 넣는다:

    ① 관측 잡음      — 컨트롤러는 참값이 아니라 흔들리는 값을 본다
    ② γ 가 클라마다 다름 — 컨트롤러는 기본 1.2 를 쓴다 (실측 1.04~1.35)
    ③ 서버 직렬화     — 서버 GPU 는 전역 락 하나로 직렬화된다 (fed_server.py:42).
                        컨트롤러의 predict() 에는 이 항이 아예 없다
    ④ 라운드별 흔들림 — 회선·연산이 라운드마다 조금씩 변한다
    ⑤ 고정 비용      — 모델 배포·집계·평가처럼 폭과 무관한 시간

  ── 모수는 실측에서 가져온다 ────────────────────────────────────
    바이트 ∝ p                     (실측 정확히 0.250x at p=0.25)
    연산   ∝ p^γ, γ∈[1.04, 1.35]   (G0 실측)
    양자화 8비트 → 바이트 x0.25    (E8 실측 0.250x), 연산 불변
    회선 20~80Mbps                 (KOREN 실측 RTT 30.8ms / 업로드 55Mbps 대역)
    배치당 바이트 8.39MB           (조건4 실측 50.33MB / 6배치)
"""
import math
import random

LADDER = (0.25, 0.5, 0.75, 1.0)
QUANT_BYTES = 0.25


class World:
    """참 세계. 컨트롤러는 이 안을 직접 못 보고 **잡음 섞인 관측**만 받는다."""

    def __init__(self, n, seed=1, *, dist="lognormal",
                 link_lo=20e6, link_hi=80e6, link_sigma=0.6,
                 cpu_med=0.25, cpu_sigma=0.5,
                 bytes1=8.39e6, batches=6,
                 srv_per_batch=0.02, srv_shared=True,
                 c_shared=None, noise=0.10, drift=0.05,
                 fixed_cost=0.5):
        self.rng = random.Random(seed)
        self.n = n
        self.ks = [f"c{i}" for i in range(n)]
        self.batches = batches
        self.bytes1 = bytes1
        self.noise = noise
        self.drift = drift
        self.fixed_cost = fixed_cost
        self.srv_per_batch = srv_per_batch      # 서버가 배치당 쓰는 시간 (p=1.0)
        self.srv_shared = srv_shared            # 서버가 직렬화되나 (전역 락)

        # ── 참 능력 (컨트롤러가 모르는 값) ──────────────────────
        self.link = {}
        self.cpu = {}
        self.gamma = {}
        for i, k in enumerate(self.ks):
            if dist == "uniform_span":          # 균등하게 벌린다 (조건2 같은 모양)
                f = i / max(1, n - 1)
                self.link[k] = link_lo + (link_hi - link_lo) * f
                self.cpu[k] = cpu_med
            elif dist == "homogeneous":         # 전부 같다 (조건1)
                self.link[k] = link_hi
                self.cpu[k] = cpu_med
            elif dist == "lognormal":           # 실배치에 가까운 모양 (꼬리가 있다)
                self.link[k] = max(1e6, link_hi * math.exp(
                    self.rng.gauss(0, link_sigma)) / math.exp(link_sigma ** 2 / 2))
                self.cpu[k] = max(0.01, cpu_med * math.exp(
                    self.rng.gauss(0, cpu_sigma)))
            elif dist == "few_stragglers":      # 대다수 균질 + 소수 낙오자 (5%)
                slow = self.rng.random() < 0.05
                self.link[k] = link_lo / 4 if slow else link_hi
                self.cpu[k] = cpu_med * (4 if slow else 1)
            else:
                raise ValueError(dist)
            # ★ γ 는 클라마다 다르다. 컨트롤러는 기본 1.2 를 쓴다 (모형 오차)
            self.gamma[k] = self.rng.uniform(1.04, 1.35)

        # 공유(서버) 회선 — 기본은 합계의 40% 로 두어 진짜 공유 병목을 만든다
        self.C = c_shared if c_shared else 0.4 * sum(self.link.values())

    # ── 한 라운드를 실제로 굴린다 ───────────────────────────────
    def run(self, pv, qv=None):
        """폭·양자화 계획대로 한 라운드. 반환: (makespan, 클라별 관측)"""
        qv = qv or {k: 0 for k in self.ks}
        B = self.batches
        byt = {k: self.bytes1 * pv[k] * (QUANT_BYTES if qv.get(k) else 1.0)
               for k in self.ks}
        tot_bits = sum(byt.values()) * 8 * B

        # 서버 직렬화 — 컨트롤러의 predict() 에 **없는 항**
        srv_tot = (sum(self.srv_per_batch * (pv[k] ** 1.2) for k in self.ks) * B
                   if self.srv_shared else 0.0)

        obs, T = {}, {}
        for k in self.ks:
            d = lambda: 1.0 + self.rng.gauss(0, self.drift)       # noqa: E731
            cpu = self.cpu[k] * (pv[k] ** self.gamma[k]) * max(0.3, d())
            own = byt[k] * 8 / (self.link[k] * max(0.3, d()))
            shared = tot_bits / self.C / B                        # 배치당 공유 몫
            comm = max(own, shared)
            T[k] = B * (cpu + comm) + srv_tot + self.fixed_cost
            # 컨트롤러가 받는 관측 — **잡음이 섞인다**
            nz = lambda v: v * max(0.2, 1.0 + self.rng.gauss(0, self.noise))  # noqa: E731
            obs[k] = {"cli_fwd": nz(cpu * B) * 0.4, "cli_bwd": nz(cpu * B) * 0.6,
                      "xfer": nz(comm * B), "up_bytes": byt[k] * B,
                      "dn_bytes": byt[k] * B, "t_comm": nz(comm * B) + cpu * B,
                      "lock_wait": srv_tot * 0.5, "srv_gpu": srv_tot * 0.5}
        return max(T.values()), obs, T


# ── 정책들 ──────────────────────────────────────────────────────
def pol_uniform(ctl, w, r):
    return {k: 1.0 for k in w.ks}, {k: 0 for k in w.ks}


def pol_allmin(ctl, w, r):
    return {k: 0.25 for k in w.ks}, {k: 0 for k in w.ks}


def make_current(w, alpha=1.2):
    """현행 규칙 — 마감선 D = alpha x min(전폭 예상시간). 폭만 쓴다."""
    from controller_multi import MultiKnobController
    c = MultiKnobController(w.ks, alpha=alpha)
    c.gamma = {k: 1.2 for k in w.ks}        # ★ 컨트롤러는 참 γ 를 모른다
    c.no_quant = True
    return c


def make_multi(w, alpha=1.2):
    from controller_multi import MultiKnobController
    c = MultiKnobController(w.ks, alpha=alpha)
    c.gamma = {k: 1.2 for k in w.ks}
    c.no_quant = False
    return c


def simulate(w, policy, rounds=10, alpha=1.2, warm=1):
    """policy: 'uniform' | 'allmin' | 'ours' | 'multi'"""
    if policy in ("uniform", "allmin"):
        fn = pol_uniform if policy == "uniform" else pol_allmin
        ctl = None
    else:
        ctl = make_current(w, alpha) if policy == "ours" else make_multi(w, alpha)
        fn = None
    pv = {k: 1.0 for k in w.ks}
    qv = {k: 0 for k in w.ks}
    hist = []
    for r in range(rounds):
        if fn:
            pv, qv = fn(ctl, w, r)
        elif r >= warm:
            pv, qv = ctl.decide(w.batches)
            if getattr(ctl, "no_quant", False):
                qv = {k: 0 for k in w.ks}
                ctl.q = qv
        ms, obs, T = w.run(pv, qv)
        if ctl is not None:
            ctl.observe_round(obs, w.batches)
        hist.append({"round": r, "makespan": ms, "mean_p": sum(pv.values()) / w.n,
                     "n_cut": sum(1 for v in pv.values() if v < 1.0),
                     "n_quant": sum(1 for v in qv.values() if v),
                     "spread": max(T.values()) / min(T.values())})
    tail = hist[warm + 1:] or hist[-1:]
    return {"policy": policy, "n": w.n,
            "makespan": sum(h["makespan"] for h in tail) / len(tail),
            "mean_p": sum(h["mean_p"] for h in tail) / len(tail),
            "n_cut": tail[-1]["n_cut"], "n_quant": tail[-1]["n_quant"],
            "spread": sum(h["spread"] for h in tail) / len(tail),
            "hist": hist}
