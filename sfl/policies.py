# -*- coding: utf-8 -*-
"""라운드 정책 — 서버가 라운드 시작마다 "이번 라운드 기기별 폭·경로를 어떻게 둘지"를 정한다.

정책은 컨트롤러(controller_multi.MultiKnobController)를 **어떻게 부를지**만 다르다.
관측·예측·계획은 전부 컨트롤러 안에 있고, 여기에는 호출 순서와 집행(경로 명령 실행)만 있다.

    uniform    아무것도 안 한다 — 전원 전폭·전원 빠른 경로 (기준선)
    oracle     --oracle-plan 으로 준 폭을 고정 (정확도 실험용)
    random     매 라운드 무작위 폭 (기준선)
    ours/multi 폭만 — 마감선 기준 사다리 (controller.decide)
    static     ours 를 첫 실측 뒤 한 번만 결정하고 얼린다 (정적 프로파일링 기준선)
    joint      폭·양자화·파이프라인 깊이·시차 통합 계획 (예비 — 파이프라인은 정확도 대가 발견으로 기본 끔)
    widthpath  폭 × 경로 공동 결정 — 두 손잡이 체제의 본체
    fixed2     고정 2연결 비교군 — 전폭·출구 A·B 를 서로 다른 엣지에 고정·고정 비율 분할 (판단 없음)
"""
import json
import random
import subprocess
from dataclasses import dataclass, field

from controller_multi import LADDER


@dataclass
class RoundContext:
    """정책이 라운드마다 받는 것. plan/qplan/dplan/splan 은 **제자리에서** 고친다 (세션 스레드가 같은 dict 를 본다)."""
    a: object                     # argparse 결과
    r: int                        # 라운드 번호
    mctl: object                  # MultiKnobController
    ids: list                     # 클라이언트 id 순서
    rnd: dict                     # 라운드 공유 상태 (passign, static_frozen 등)
    plan: dict                    # cid → 폭
    qplan: dict = field(default_factory=dict)   # cid → 양자화 비트
    dplan: dict = field(default_factory=dict)   # cid → 파이프라인 깊이
    splan: dict = field(default_factory=dict)   # cid → 시작 지연(초)
    last_detail: dict = field(default_factory=dict)   # 직전 라운드 계측
    measured: bool = False        # 실측이 한 번이라도 있었나 (r>0 또는 사전 진단)
    allowed: dict = field(default_factory=dict)   # 기기별 허용 엣지 (--edge-groups); 비어 있으면 전부
    sensor: object = None         # 인지 층 (sense.Sensor) — planner=plan 이 쓴다
    mpplan: dict = field(default_factory=dict)   # cid → 분할 전송 여부 (제자리 갱신)
    edges: dict = None            # 실회선 리그: 경로 → (host, base_port). 있으면 집행 = 종점 갱신
    dp: dict = field(default_factory=dict)       # cid → 출구별 데이터 종점 (제자리 갱신)


class Policy:
    name = "base"

    def __init__(self, a):
        self.a = a

    def apply(self, c: RoundContext):
        """이번 라운드의 plan 을 갱신한다. 기본은 무개입."""


class Uniform(Policy):
    name = "uniform"


class Oracle(Policy):
    name = "oracle"

    def __init__(self, a):
        super().__init__(a)
        self.fixed = json.loads(a.oracle_plan) if a.oracle_plan else {}

    def apply(self, c):
        if self.fixed:
            c.plan.update(self.fixed)


class Random(Policy):
    name = "random"

    def apply(self, c):
        if c.r > 0:
            c.plan.update({k: random.choice(LADDER) for k in c.ids})


class WidthOnly(Policy):
    """폭만 — 마감선(중앙값×alpha)을 넘는 기기만 한 칸씩 (controller.decide)."""
    name = "ours"

    def apply(self, c):
        if not c.measured:
            return
        pv, qv = c.mctl.decide(c.a.batches)
        c.plan.update(pv)
        c.qplan.update(qv)
        print(c.mctl.explain(c.a.batches), flush=True)


class Static(Policy):
    """정적 프로파일링 기준선 — 첫 실측 뒤 **한 번만** 결정하고 얼린다.

    규칙은 ours 와 같고 차이는 하나: 다시 재지도 바꾸지도 않는다. 첫 결정은 히스테리시스 없이
    수렴할 때까지 한다. 라운드당 한 칸 제한을 두면 첫 결정이 한 칸만 내려가고 얼어 허수아비가 된다
    (시드1 실측: static [0.75,1,1,1] 동결 vs ours [0.25,1,1,1] — 2026-09-02)."""
    name = "static"

    def apply(self, c):
        if not c.measured or c.rnd.get("static_frozen"):
            return
        saved = c.mctl.hyst
        c.mctl.hyst = False
        try:
            pv, qv = c.mctl.decide(c.a.batches)
        finally:
            c.mctl.hyst = saved
        c.plan.update(pv)
        c.qplan.update(qv)
        c.rnd["static_frozen"] = True
        print(f"   [static] 첫 실측 후 배정 고정(수렴 결정, 히스테리시스 없음) — 이후 무개입: "
              f"{[c.plan[k] for k in c.ids]}", flush=True)
        print(c.mctl.explain(c.a.batches), flush=True)


class Joint(Policy):
    """통합 계획 — 폭·양자화·파이프라인 깊이·시작 지연을 같은 측정에서 유도 (예비)."""
    name = "joint"

    def apply(self, c):
        if not c.measured:
            return
        per_b = [d.get("up_bytes", 0) / max(c.a.batches, 1) for d in c.last_detail.values()]
        sync_b = sum(per_b) / len(per_b) if per_b else 0
        jplan, jpred = c.mctl.plan_round(c.a.batches, sync_bytes=sync_b)
        for k, v in jplan.items():
            c.plan[k] = v["p"]
            c.qplan[k] = v["q"]
            c.dplan[k] = v["depth"]
            c.splan[k] = v["sync_offset_s"]
        print(c.mctl.explain(c.a.batches), flush=True)
        print(f"   [joint] depth {[c.dplan[k] for k in c.ids]} "
              f"delay {[round(c.splan[k], 2) for k in c.ids]} "
              f"예상 makespan {jpred['makespan']:.2f}s", flush=True)


class WidthPath(Policy):
    """폭 × 경로 공동 결정 — 두 손잡이 체제의 본체.

    경로 집행(--path-exec)이 실패하면 컨트롤러의 배정도 되돌린다. 믿음과 커널 상태가 어긋나면
    이후 모든 용량 추정이 오염되기 때문이다."""
    name = "widthpath"

    def __init__(self, a):
        super().__init__(a)
        self.caps = {str(i + 1): float(m) * 1e6                     # Mbps → bit/s
                     for i, m in enumerate(a.paths.split(","))} if a.paths else {}
        self.ladder = tuple(float(x) for x in a.ladder.split(",")) if a.ladder else None
        acc = getattr(a, "access_caps", "")
        def _acc(v):                                                       # "35" 한 가닥 / "50/20" 두 가닥(출구 A/B) Mbps → bit/s
            return [float(x) * 1e6 for x in v.split("/")] if "/" in v else float(v) * 1e6
        self.access = {kv.split("=")[0]: _acc(kv.split("=")[1]) for kv in acc.split(",") if "=" in kv} if acc else {}

    def apply(self, c):
        if not c.measured or not self.caps:
            return
        planner_name = getattr(c.a, "planner", "two-stage")
        if planner_name == "device-budget":
            return self._apply_device_budget(c)
        if planner_name == "plan":
            return self._apply_plan(c)
        passign = c.rnd.setdefault("passign", {k: "1" for k in c.ids})
        planner = {"two-stage": c.mctl.plan_two_stage,          # 병목 유형 우선 (기본, 2026-09-06 개정)
                   "two-stage-v1": c.mctl.plan_two_stage_v1,    # 구판 — 경로 먼저 (비교용)
                   "joint": c.mctl.plan_width_path}.get(planner_name, c.mctl.plan_two_stage)
        if self.access and not c.mctl.access_cap:               # 리그 검증용 오라클 — 보고서에 '오라클'이라 적는다
            c.mctl.access_cap = dict(self.access)
        na, nw, _, why = planner(
            c.a.batches, self.caps, current_assign=passign,
            max_moves=c.a.max_moves, ladder=self.ladder,
            remaining=c.a.rounds - c.r, switch_cost=c.a.switch_cost)
        if na != passign and self.a.path_exec:
            order = " ".join(na[k] for k in c.ids)
            rc = subprocess.run(self.a.path_exec.format(assign=order), shell=True, check=False).returncode
            if rc != 0:
                print(f"   [widthpath] 경로 집행 실패 rc={rc} — 배정 유지", flush=True)
                na = passign
        c.rnd["passign"] = na
        c.plan.update(nw)
        c.mctl.diagnose(c.a.batches)
        print(c.mctl.explain(c.a.batches), flush=True)
        print(f"   [widthpath/{planner_name}] 배정 {[na[k] for k in c.ids]} 폭 {[nw[k] for k in c.ids]} — {why}", flush=True)


    def _apply_device_budget(self, c):
        """Experimental serial SFL: compute budget -> fixed-width endpoint routing."""
        import device_budget as budget
        import plan as planmod

        if not hasattr(self, "_compute_tracker"):
            self._compute_tracker = budget.ComputeTracker()
        prof, sources = self._compute_tracker.update(
            c.sensor.profile(), c.plan, c.last_detail, c.a.batches)
        prof["access"] = dict(self.access, **(prof.get("access") or {}))
        if set(prof["access"]) != set(c.ids):
            raise ValueError("device-budget needs an access profile for every client")
        prof["access"] = budget.access_profile(prof["access"], c.a.access_mode)
        prof["allowed"] = c.allowed
        prof["caps"] = c.sensor.caps_effective(self.caps)
        old_sets = c.rnd["psets"]  # Registered endpoints initialized by Server.
        server_time = {k: max(0.0, c.last_detail.get(k, {}).get("srv_gpu", 0.0)
                             + c.last_detail.get(k, {}).get("lock_wait", 0.0)) for k in c.ids}
        res = budget.plan_round(prof, dict(c.plan), old_sets,
            {k: c.a.compute_budget_s for k in c.ids}, self.ladder or LADDER, c.a.batches,
            raise_ok=c.rnd.get("budget_raise_ok"), max_moves=c.a.max_moves,
            switch_cost=c.a.switch_cost, multipath=c.a.multipath,
            access_mode=c.a.access_mode, deadline_s=c.a.deadline_s, overhead=server_time,
            recovery_allowed={k for k, src in sources.items() if src != "stale_compute"})
        # Endpoint selection uses ordinary client sockets. No client-side tc/root.
        # A request is not an OpenFlow acknowledgement or authenticated identity.
        for i, k in enumerate(c.ids):
            c.dp[k] = [[c.edges[p][0], c.edges[p][1] + 2*i + x]
                       for x, p in enumerate(res["sets"][k])]
        c.plan.update(res["widths"])
        c.rnd["psets"] = res["sets"]
        c.rnd["budget_raise_ok"] = res["raise_ok"]
        # Keep the existing static-weight transport to avoid its feedback loop.
        rates = planmod.split_weights(res["sets"], self.caps, prof["access"])
        for k in c.ids:
            c.mpplan[k] = [max(1e-6, v / 1e6) for v in rates[k]]
        c.sensor.access = dict(prof["access"])
        res.update(compute_sources=sources, server_time_s=server_time,
                   effective_caps_bps=prof["caps"], route_status="endpoint_requested",
                   observation_model="serial_residual_excluding_server_compute_and_lock")
        c.rnd["budget_decision"] = res
        print(f"   [device-budget] widths {[c.plan[k] for k in c.ids]} "
              f"compute misses {sum(v['predicted_budget_miss'] for v in res['clients'].values())} "
              f"predicted round {res['predicted_makespan_s']:.2f}s", flush=True)

    def _apply_plan(self, c):
        """인지·계획·집행 3층 (2026-09-07). 인지 = c.sensor, 계획 = plan.plan (순수), 집행 = tc assign + 분할 전송 지시."""
        import plan as planmod
        prof = c.sensor.profile()
        if not prof["cpu"] or not prof["bytes"]:
            return
        if getattr(c, "allowed", None):
            prof["allowed"] = dict(c.allowed)                     # 기기별 허용 엣지 → 계획기 후보 제한
        if not prof.get("access") and self.access:                # 측정이 없을 때만 오라클 (프로파일에 오라클로 표시)
            prof["access"] = dict(self.access)
            for k in self.access:
                c.sensor.src[("access", k)] = "오라클"
        psets = c.rnd.setdefault("psets", {k: ("1",) for k in c.ids})
        state = {"sets": psets, "widths": dict(c.plan), "observed": c.sensor.observed(),
                 "raise_ok": c.rnd.get("raise_ok", {}), "ref_sets": c.rnd.get("ref_sets")}
        lad = self.ladder or LADDER
        caps = c.sensor.caps_effective(self.caps)                  # 관측으로 갱신된 경로 용량 (막힌 엣지는 작아진다 → 이동 이득이 보인다)
        if any(abs(caps[e] - self.caps[e]) > 1e3 for e in caps):
            print(f"   [sense] 경로 용량(관측) {{{', '.join(f'{e}:{caps[e]/1e6:.0f}M' for e in sorted(caps, key=int))}}} (정적 {{{', '.join(f'{e}:{self.caps[e]/1e6:.0f}M' for e in sorted(self.caps, key=int))}}})", flush=True)
        last = getattr(self, "_last_caps", None)
        net_changed = last is not None and any(abs(caps[e] - last.get(e, caps[e])) > 0.05 * self.caps[e] for e in caps)   # 어느 엣지든 용량 관측이 5% 넘게 바뀐 라운드
        self._last_caps = dict(caps)
        res = planmod.plan(prof, state, caps, ladder=lad, alpha=c.a.alpha, max_moves=c.a.max_moves,
                           multipath=bool(getattr(c.a, "multipath", False)), remaining=c.a.rounds - c.r,
                           switch_cost=c.a.switch_cost, batches=c.a.batches, p_min=min(lad),
                           deadline_mode=getattr(c.a, "deadline", "anchored"), deadline_s=getattr(c.a, "deadline_s", None), lam=getattr(c.a, "lam", None),
                           hold_widths=net_changed)
        new = res["sets"]
        edges = getattr(c, "edges", None)
        if edges:                                                  # 실회선 리그: 집행 = 출구별 종점 갱신 (클라가 다음 라운드에 재접속)
            from network_control import endpoints_for
            for i, k in enumerate(c.ids):
                c.dp[k] = endpoints_for(edges, new[k], i)
        elif new != psets and self.a.path_exec:
            order = " ".join("+".join(new[k]) for k in c.ids)     # "1 1+2 2 1" — hairpin_lo.sh assign 규약
            rc = subprocess.run(self.a.path_exec.format(assign=order), shell=True, check=False).returncode
            if rc != 0:
                print(f"   [plan] 경로 집행 실패 rc={rc} — 배정 유지", flush=True)
                new = psets
        c.rnd["psets"] = new
        c.rnd["raise_ok"] = res["raise_ok"]
        c.rnd["ref_sets"] = res["ref_sets"]
        c.plan.update(res["widths"])
        xr = planmod.split_weights(new, self.caps, prof.get("access"))           # 출구별 예상 속도 → 조각 배분 가중치 (규칙 3′). **정적 용량**으로 나눈다 (9/9 21:40, §13-2):
                                                                              # 관측 용량(막힌 엣지 14M)으로 나누면 느린 출구 B 에 바이트가 몰려, 그 뒤의 관측(접속 기대와 같은 처리량)이
                                                                              # 포화인지 분할 탓인지 구분이 안 돼 추정이 풀렸다 되돌아오기를 반복했다(최종 2차 몰림 R13 되돌아감). 막힌 엣지의 답은 재분할이 아니라 이동.
        for k in c.ids:
            c.mpplan[k] = [round(v / 1e6, 2) for v in xr[k]] if (len(new[k]) >= 2 or edges) else False   # 엣지 모드: 출구 1개도 채널
        print(planmod.explain(prof, res, caps), flush=True)
        print(f"   [widthpath/plan] 경로 {['+'.join(new[k]) for k in c.ids]} 폭 {[res['widths'][k] for k in c.ids]} — {res['why']}", flush=True)


class NetworkOnly(WidthPath):
    """Fixed learning demand -> shared-link route planning -> endpoint execution."""
    name = "network"

    def __init__(self, a):
        super().__init__(a)
        from network_control import load_topology
        self.topology = load_topology(a.network_topology, self.caps)
        self.fixed = json.loads(a.oracle_plan) if a.oracle_plan else {}

    def apply(self, c):
        from device_budget import access_profile
        from network_control import plan_routes, endpoints_for
        if self.fixed:
            c.plan.update(self.fixed)
        if not c.measured:
            return
        if c.r > 0 and not c.rnd.get("network_route_verified", False):
            raise RuntimeError("previous route has no matching completion receipt; check client version/route log")
        prof = c.sensor.profile()
        access = access_profile(dict(self.access, **(prof.get("access") or {})), c.a.access_mode)
        demand = {k: prof["bytes"][k] * c.plan[k] * c.a.batches for k in c.ids}
        result = plan_routes(demand, c.rnd["psets"], c.allowed,
            c.sensor.caps_effective(self.caps), access,
            shared_links=self.topology["shared_links"], max_moves=c.a.max_moves,
            switch_cost=c.a.switch_cost, multipath=c.a.multipath)
        for i, k in enumerate(c.ids):
            c.dp[k] = endpoints_for(c.edges, result["sets"][k], i)
            c.mpplan[k] = [v / 1e6 for v in result["weights_bps"][k]]
        c.rnd["psets"] = result["sets"]
        c.sensor.access = access
        result.update(epoch=c.r, widths=dict(c.plan),
                      capacity_observation="serial_residual" if c.a.micro == 1 else "frozen_during_overlap")
        c.rnd["network_decision"] = result
        print(f"   [network] moved {result['moved']}; fixed widths {list(c.plan.values())}", flush=True)


class FixedTwo(Policy):
    """고정 2연결 비교군 (2026-10-07) — 연결 수 효과와 스케줄러 판단 효과를 나누기 위한 기준.

    균등(uniform)과 같이 전원 전폭·폭 조절 없음·경로 이동 없음이다. 다른 점은 하나:
    출구 A·B 두 연결을 모두 쓴다. 출구 A 는 균등과 같은 엣지(--init-sets rr), 출구 B 는 다른 VM 의
    엣지(엣지 수의 절반만큼 떨어진 엣지)에 **처음 한 번** 배정하고 바꾸지 않는다. 엣지마다 출구 A 8대 + 출구 B 8대로
    부하가 고르게 실린다. 조각은 --fixed-weights 비율(기본 '1,1', 실행 스크립트는 접속 상한 5/2 → '5,2')로 고정 분할한다.
    비교: 균등(1연결) → fixed2 = 연결 수를 늘린 효과, fixed2 → widthpath = 폭·경로 판단의 효과."""
    name = "fixed2"

    def __init__(self, a):
        super().__init__(a)
        w = [float(x) for x in str(getattr(a, "fixed_weights", "1,1") or "1,1").split(",")]
        if len(w) != 2 or min(w) <= 0:
            raise ValueError(f"--fixed-weights 는 양수 두 개여야 한다: {w}")
        self.weights = w

    def apply(self, c):
        if c.rnd.get("fixed2_done"):
            return
        if not c.edges:
            raise RuntimeError("fixed2 는 실회선 리그(--edges)에서만 쓴다")
        if not getattr(c.a, "multipath", False):
            raise RuntimeError("fixed2 는 --multipath 가 필요하다 (출구 B 조각 수신기)")
        from network_control import endpoints_for
        paths = sorted(c.edges, key=int)
        sets = {}
        for i, k in enumerate(c.ids):
            pk = c.allowed.get(k, paths) if c.allowed else paths
            pa = pk[i % len(pk)] if getattr(c.a, "init_sets", "1") == "rr" else pk[0]
            ia = pk.index(pa)
            pb = pk[(ia + max(1, len(pk) // 2)) % len(pk)] if len(pk) > 1 else pa
            sets[k] = (pa, pb)
            c.dp[k] = endpoints_for(c.edges, sets[k], i)
            c.mpplan[k] = list(self.weights)
            c.plan[k] = 1.0
        c.rnd["psets"] = sets
        c.rnd["fixed2_done"] = True
        load = {}
        for pa, pb in sets.values():
            load[pa] = load.get(pa, [0, 0]); load[pa][0] += 1
            load[pb] = load.get(pb, [0, 0]); load[pb][1] += 1
        print(f"   [fixed2] 출구 A·B 고정 배정 {['+'.join(sets[k]) for k in c.ids]} "
              f"분할 비율 {self.weights[0]:g}:{self.weights[1]:g} — 엣지별 (출구A, 출구B) 기기 수 "
              f"{{{', '.join(f'{e}:{tuple(load[e])}' for e in sorted(load, key=int))}}}. 이후 무개입", flush=True)


_REGISTRY = {"uniform": Uniform, "oracle": Oracle, "random": Random,
             "ours": WidthOnly, "multi": WidthOnly, "static": Static,
             "joint": Joint, "widthpath": WidthPath, "network": NetworkOnly,
             "fixed2": FixedTwo}
POLICY_NAMES = tuple(_REGISTRY)


def make_policy(a):
    return _REGISTRY[a.policy](a)
