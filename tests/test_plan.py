# -*- coding: utf-8 -*-
"""통합 계획기(plan_round) 규칙 시험 — torch 불필요, FAST 티어.

시험 이름 = 증명하는 주장 (검증_매트릭스 원칙):
  1. 이득 없으면 깊이 1 — 연산≫망(또는 반대)이면 파이프라인을 켜지 않는다
  2. 겹칠 게 있으면 깊이 2 — 연산≈망이면 예상 시간이 실제로 준다
  3. 동기 시차는 겹칠 때만 — 종료가 벌어져 있으면 offset 0, 몰리면 직렬 슬롯
  4. 용량 미관측이면 무개입 — cap 없이는 offset 을 만들지 않는다
  5. 폭 결정은 기존 decide() 와 동일 — 계획기가 폭 규칙을 바꾸지 않는다
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sfl"))
from controller_multi import MultiKnobController                     # noqa: E402

B = 10


def mk(cpu, net, cap=None):
    ks = sorted(cpu)
    c = MultiKnobController(ks)
    c.cpu1.update(cpu)
    c.net1.update(net)
    c.gamma.update({k: 1.2 for k in ks})
    if cap:
        c.cap.update(cap)
    return c


def test_no_gain_no_pipe():
    c = mk({"c0": 1.0}, {"c0": 0.001})          # 연산 지배 — 겹쳐도 안 준다
    plan, pred = c.plan_round(B)
    assert plan["c0"]["depth"] == 1 and pred["gain_pipe"] == 0.0


def test_overlap_gain_pipe():
    c = mk({"c0": 0.5}, {"c0": 0.5})            # 반반 — 겹치면 ~절반
    plan, pred = c.plan_round(B)
    t1 = B * 1.0
    assert plan["c0"]["depth"] == 2
    assert pred["makespan"] < t1 * 0.6          # (c+n)+(B-1)max = 1+4.5=5.5 < 6
    assert pred["gain_pipe"] > 0


def test_stagger_only_on_collision():
    # 두 클라 종료 동시 → 둘째는 첫째 동기가 끝날 때까지 미룬다
    c = mk({"c0": 0.5, "c1": 0.5}, {"c0": 0.001, "c1": 0.001},
           cap={"c0": 1e6, "c1": 1e6})
    plan, pred = c.plan_round(B, sync_bytes=2e6)         # 동기 2초짜리
    offs = sorted(p["sync_offset_s"] for p in plan.values())
    assert offs[0] == 0.0 and abs(offs[1] - 2.0) < 0.05
    # 종료가 동기 길이보다 벌어져 있으면 → 둘 다 0
    c2 = mk({"c0": 0.1, "c1": 1.0}, {"c0": 0.001, "c1": 0.001},
            cap={"c0": 1e6, "c1": 1e6})
    plan2, _ = c2.plan_round(B, sync_bytes=1e5)          # 동기 0.1초 ≪ 종료 격차
    assert all(p["sync_offset_s"] == 0.0 for p in plan2.values())


def test_no_cap_no_stagger():
    c = mk({"c0": 0.5, "c1": 0.5}, {"c0": 0.001, "c1": 0.001})   # cap 미관측
    plan, _ = c.plan_round(B, sync_bytes=2e6)
    assert all(p["sync_offset_s"] == 0.0 for p in plan.values())


def test_effective_quant_precedence():
    # R5-Q 결함 재발 방지 — 서버 지시(>0)가 우선, 서버 0 은 '지시 없음'
    from controller_multi import effective_quant
    assert effective_quant(0, 8) == 8       # 서버 무지시 + CLI 강제 → CLI 가 산다
    assert effective_quant(8, 0) == 8       # 컨트롤러가 켬
    assert effective_quant(0, 0) == 0
    assert effective_quant(8, 4) == 8       # 서버 지시가 CLI 를 이긴다


def test_width_rule_unchanged():
    cpu = {f"c{i}": 0.1 for i in range(4)}
    net = {f"c{i}": 0.1 for i in range(4)}
    cpu["c3"], net["c3"] = 0.4, 0.4                       # 낙오자 하나
    a = mk(dict(cpu), dict(net))
    b = mk(dict(cpu), dict(net))
    pv, _ = a.decide(B)
    plan, _ = b.plan_round(B)
    assert {k: plan[k]["p"] for k in plan} == pv


def _mk_wp(bytes1, cpu=None):
    ks = sorted(bytes1)
    c = MultiKnobController(ks)
    c.bytes1.update(bytes1)
    c.cpu1.update(cpu or {k: 0.05 for k in ks})
    return c


def test_wp_homogeneous_no_move():
    # 균질 — 어느 배정이든 비슷 → 현 배정 유지
    c = _mk_wp({f"c{i}": 2e6 for i in range(4)})
    cur = {"c0": "A", "c1": "A", "c2": "B", "c3": "B"}
    a, w, ms, why = c.plan_width_path(6, {"A": 50e6, "B": 50e6}, cur)
    assert a == cur and "유지" in why


def test_wp_clear_gain_moves_capped():
    # 전원이 느린 경로에 몰림 — 이동이 명백히 이득이면 즉시, 단 한 라운드 1명만
    c = _mk_wp({f"c{i}": 2e6 for i in range(4)})
    cur = {f"c{i}": "B" for i in range(4)}                 # 전원 느린 경로
    a, w, ms, why = c.plan_width_path(6, {"A": 100e6, "B": 20e6}, cur)
    moved = [k for k in a if a[k] != cur[k]]
    assert len(moved) == 1 and "1명" in why


def test_wp_hysteresis_small_gain():
    # 경로 차이가 미미 — 이득 < 계측 불확도 → 안 움직임
    c = _mk_wp({f"c{i}": 2e6 for i in range(4)})
    cur = {"c0": "A", "c1": "A", "c2": "B", "c3": "B"}
    a, w, ms, why = c.plan_width_path(6, {"A": 52e6, "B": 50e6}, cur)
    assert a == cur and "유지" in why


def test_wp_free_exile_shape():
    # M2' 형태 재현 — 초기 배정: 느린 경로에 보낸 클라는 폭을 줄여
    #   빠른 경로보다 먼저 끝나게 (아무도 기다리지 않음)
    c = _mk_wp({f"c{i}": 2e6 for i in range(4)})
    a, w, ms, why = c.plan_width_path(6, {"A": 100e6, "B": 20e6})
    slow = [k for k in a if a[k] == "B"]
    assert slow, "느린 경로도 활용해야 한다 (전원 몰림은 빠른 경로 과부하)"
    assert all(w[k] < 1.0 for k in slow), "느린 경로 배정자는 폭을 줄인다"


def test_wp_switch_cost_horizon():
    # 경제성 모델 — 같은 판이라도 남은 라운드가 적고 전환 비용이 크면 안 움직인다
    caps = {"A": 100e6, "B": 20e6}
    c1 = _mk_wp({f"c{i}": 2e6 for i in range(4)})
    cur = {f"c{i}": "B" for i in range(4)}
    a1, _, _, why1 = c1.plan_width_path(6, caps, cur, remaining=1, switch_cost=10.0)
    assert a1 == cur and "유지" in why1                     # 막바지 — 비용 회수 불가
    c2 = _mk_wp({f"c{i}": 2e6 for i in range(4)})
    a2, _, _, why2 = c2.plan_width_path(6, caps, cur, remaining=50, switch_cost=10.0)
    assert a2 != cur and "이동" in why2                     # 초반 — 상각되어 이동


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print(f"  PASS {name}")
            except AssertionError as e:
                fails += 1
                print(f"  FAIL {name}: {e}")
    sys.exit(1 if fails else 0)
