# -*- coding: utf-8 -*-
"""2단계 계획기(plan_two_stage)와 절제 팔(경로만·폭만) 시험 — **팔이 자기 손잡이만 쓰는가.**

  왜 있나: 절제 2판(2026-09-05~06)에서 '폭만' 팔이 경로를 옮긴 채로 돌아 결과가 무효가 됐다.
  `max_moves<=0` 분기가 실험 도중에 추가됐는데 그것을 지키는 시험이 없었다
  (docs/02_실험/실험_절제_조건표_복원.md §4). 이 시험이 통과하지 않으면 절제 실험을 걸지 않는다.

    python tests/test_two_stage.py
"""
import os
import statistics as st
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sfl"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from controller_multi import MultiKnobController      # noqa: E402

B = 4
MB = 1e6
CAPS = {"1": 100e6, "2": 50e6}          # 절제 2판 4대 100/50 조건
LADDER = (0.5, 0.75, 1.0)               # 절제 사다리


def make(cpu1, bytes1, gamma=1.2):
    """관측이 끝난 컨트롤러를 합성한다. bytes1 = 배치당 왕복 바이트."""
    ks = list(cpu1)
    c = MultiKnobController(ks)
    c.cpu1 = dict(cpu1)
    c.bytes1 = dict(bytes1)
    c.net1 = {k: bytes1[k] * 8 / CAPS["1"] for k in ks}
    c.gamma = {k: gamma for k in ks}
    return c


def homo(n=4, cpu=0.18, mb=8.39):
    """동질 4대 — 절제 2판 실측 근사 (연산 0.71초/4배치, 배치당 8.39MB 왕복)."""
    return ({f"c{i}": cpu for i in range(n)}, {f"c{i}": mb * MB for i in range(n)})


def all_on_1(c):
    return {k: "1" for k in c.ks}


fails = 0


def check(name, cond, detail=""):
    global fails
    fails += 0 if cond else 1
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def main():
    print("== 2단계 계획기 · 절제 팔 시험 ==")

    # ① 폭만 팔: max_moves=0 이면 이동이 이득이어도 배정이 절대 안 바뀐다
    c = make(*homo())
    cur = all_on_1(c)
    na, nw, T, why = c.plan_two_stage(B, CAPS, current_assign=cur, max_moves=0, ladder=LADDER, remaining=12)
    check("폭만(max_moves=0): 배정 불변", na == cur, f"{[na[k] for k in c.ks]} / {why}")
    check("폭만(max_moves=0): 사유에 '경로 고정'", "경로 고정" in why, why)
    # 같은 상태에서 이동을 허용하면 실제로 옮긴다 — 위 시험이 공허하지 않음을 확인
    c2 = make(*homo())
    na2, _, _, why2 = c2.plan_two_stage(B, CAPS, current_assign=all_on_1(c2), max_moves=1, ladder=LADDER, remaining=12)
    check("(대조) max_moves=1 이면 1대 이동", sum(v == "2" for v in na2.values()) == 1, f"{[na2[k] for k in c2.ks]} / {why2}")

    # ② 경로만 팔: ladder=(1.0,) 이면 연산 낙오자가 있어도 폭이 절대 안 바뀐다
    cpu, byt = homo()
    cpu["c0"] = cpu["c0"] * 5                       # c0 연산 5배
    c = make(cpu, byt)
    na, nw, T, why = c.plan_two_stage(B, CAPS, current_assign=all_on_1(c), max_moves=1, ladder=(1.0,), remaining=12)
    check("경로만(ladder=1.0): 폭 전원 1.0", all(v == 1.0 for v in nw.values()), f"{[nw[k] for k in c.ks]} / {why}")

    # ③ 동질 연산·낙오자 없음 → 2단은 폭을 깎지 않고, 이동은 max_moves 이하
    c = make(*homo())
    na, nw, T, why = c.plan_two_stage(B, CAPS, current_assign=all_on_1(c), max_moves=1, ladder=LADDER, remaining=12)
    check("동질: 폭 전원 1.0", all(v == 1.0 for v in nw.values()), f"{[nw[k] for k in c.ks]}")
    check("동질: 이동 ≤ max_moves", sum(v == "2" for v in na.values()) <= 1, f"{[na[k] for k in c.ks]}")

    # ④ 연산 낙오자 1대(5배) → 연산 기준선(경로 무관)으로 그 기기만. 히스테리시스로 0.75 → 0.5
    cpu, byt = homo()
    cpu["c0"] = cpu["c0"] * 5
    c = make(cpu, byt)
    cur = all_on_1(c)
    na, nw, T, why = c.plan_two_stage(B, CAPS, current_assign=cur, max_moves=0, ladder=LADDER, remaining=12)
    others_full = all(nw[k] == 1.0 for k in c.ks if k != "c0")
    check("낙오자 5배: c0 만 첫 라운드 0.75, 사유에 '연산 낙오자'", nw["c0"] == 0.75 and others_full and "연산 낙오자 1대" in why,
          f"{[nw[k] for k in c.ks]} / {why}")
    na, nw, T, why = c.plan_two_stage(B, CAPS, current_assign=cur, max_moves=0, ladder=LADDER, remaining=11)
    check("낙오자 5배: 한 칸(0.75)으로 총시간이 기준선 안 → 둘째 라운드도 0.75", nw["c0"] == 0.75 and others_full, f"{[nw[k] for k in c.ks]}")
    # 연산 기준선 규칙 자체: D_c = α × 중앙값(전폭 연산시간) 를 넘는 기기만 대상
    w0, cut, Dc = c._compute_widths(LADDER)
    check("연산만 기준 진단: 초과 기기 = [c0] (이름표용)", cut == ["c0"], f"D_c={Dc:.3f}s, 초과 {cut}")

    # ⑤ 연산 낙오자 12배 → 계획은 0.5 를 원하지만 히스테리시스로 첫 라운드 0.75, 둘째 라운드 0.5
    cpu, byt = homo()
    cpu["c0"] = cpu["c0"] * 12
    c = make(cpu, byt)
    cur = all_on_1(c)
    na, nw, T, why = c.plan_two_stage(B, CAPS, current_assign=cur, max_moves=0, ladder=LADDER, remaining=12)
    check("낙오자 12배: 첫 라운드 0.75 (라운드당 한 칸)", nw["c0"] == 0.75 and all(nw[k] == 1.0 for k in c.ks if k != "c0"),
          f"{[nw[k] for k in c.ks]} / {why}")
    na, nw, T, why = c.plan_two_stage(B, CAPS, current_assign=cur, max_moves=0, ladder=LADDER, remaining=11)
    check("낙오자 12배: 둘째 라운드 0.5", nw["c0"] == 0.5 and all(nw[k] == 1.0 for k in c.ks if k != "c0"),
          f"{[nw[k] for k in c.ks]} / {why}")

    # ⑥ (기록) 구판 plan_width_path 는 max_moves=0 을 '폭만'으로 해석하지 않는다 — 1판 폭만 팔이 무효였던 이유
    c = make(*homo())
    na, nw, ms, why = c.plan_width_path(B, CAPS, current_assign=all_on_1(c), max_moves=0, ladder=LADDER, remaining=12)
    moved = sum(v == "2" for v in na.values())
    print(f"  [INFO] 구판 joint 에 max_moves=0: 이동 {moved}대 ({why}) — 구판으로는 '폭만' 절제를 만들 수 없다")

    # ⑦ 혼합 집단 — 연산 낙오자(c0 속도 0.25) + 공유 구간 혼잡(전원 경로1). 두 손잡이의 본뜻:
    #    연산 병목은 폭으로, 혼잡은 경로로. 남들이 경로를 옮겨도 c0 의 폭이 되돌아오면 안 된다.
    #    (구판 two-stage-v1 은 R1 에서 c0 폭이 1.0 으로 복귀해 둘다 3.94s > 폭만 3.48s 였다 — 2026-09-06 시뮬)
    def mixed():
        cpu = {"c0": 0.65 / 0.25, "c1": 0.65, "c2": 0.65, "c3": 0.65}      # 스레드 1 수준 전속 0.65초/배치
        return cpu, {k: 8.39 * MB for k in cpu}

    def run(planner_name, max_moves, ladder, rounds=6):
        cpu, byt = mixed()
        c = make(cpu, byt)
        cur = all_on_1(c)
        planner = getattr(c, planner_name)
        hist = []
        for r in range(rounds):
            na, nw, T, why = planner(B, CAPS, current_assign=cur, max_moves=max_moves, ladder=ladder, remaining=12 - r)
            cur = na
            hist.append((dict(na), dict(nw), why))
        t, Tmax = c.round_time(cur, nw, CAPS)
        return hist, t, Tmax

    hist, t_both, T_both = run("plan_two_stage", 1, LADDER)
    w_c0 = [h[1]["c0"] for h in hist]
    check("혼합: c0 폭이 내려가고 1.0 으로 복귀하지 않는다", w_c0[0] < 1.0 and all(w < 1.0 for w in w_c0) and w_c0[-1] <= w_c0[0], f"{w_c0}")
    check("혼합: 정상 기기(c1~c3)는 폭 1.0", all(h[1][k] == 1.0 for h in hist for k in ("c1", "c2", "c3")),
          f"{[[h[1][k] for k in ('c1','c2','c3')] for h in hist]}")
    check("혼합: 공유 혼잡은 경로 이동으로 푼다 (경로2 에 1대 이상)", any(v == "2" for v in hist[-1][0].values()), f"{hist[-1][0]}")
    _, _, T_width = run("plan_two_stage", 0, LADDER)
    _, _, T_path = run("plan_two_stage", 1, (1.0,))
    check("혼합: 둘다 ≤ 폭만 그리고 둘다 ≤ 경로만 (예측 T)", T_both <= T_width + 1e-9 and T_both <= T_path + 1e-9,
          f"둘다 {T_both:.2f}s  폭만 {T_width:.2f}s  경로만 {T_path:.2f}s")
    hist1, _, T_v1 = run("plan_two_stage_v1", 1, LADDER)
    print(f"  [INFO] 구판 two-stage-v1 혼합 집단: c0 폭 {[h[1]['c0'] for h in hist1]} → 예측 T {T_v1:.2f}s (복귀 결함 기록)")

    # ⑧ 접속 회선 병목 — c3 의 접속 회선 20M (나머지 100M). 경로를 옮겨도 c3 는 안 빨라진다 → 잔여 단계가 폭으로.
    cpu, byt = homo()
    c = make(cpu, byt)
    c.access_cap = {"c0": 100e6, "c1": 100e6, "c2": 100e6, "c3": 20e6}
    cur = all_on_1(c)
    na, nw, T, why = c.plan_two_stage(B, CAPS, current_assign=cur, max_moves=1, ladder=LADDER, remaining=12)
    check("접속 회선 병목: 연산 낙오자 아님(0단 무개입)", "연산 낙오자 없음" in why, why)
    check("접속 회선 병목: c3 만 잔여 폭 축소", nw["c3"] < 1.0 and all(nw[k] == 1.0 for k in ("c0", "c1", "c2")), f"{[nw[k] for k in c.ks]} / {why}")
    t_before, _ = c.round_time(cur, {k: 1.0 for k in c.ks}, CAPS)
    t_moved, _ = c.round_time(dict(cur, c3="2"), {k: 1.0 for k in c.ks}, CAPS)
    check("접속 회선 병목: c3 를 경로2 로 옮겨도 c3 시간은 그대로 (모형에 접속 회선 항)", abs(t_before["c3"] - t_moved["c3"]) < 1e-9,
          f"경로1 {t_before['c3']:.2f}s vs 경로2 {t_moved['c3']:.2f}s")

    # ⑨ 절제 팔 규약이 새 계획기에서도 유지되는가 (혼합 집단)
    hist_p, _, _ = run("plan_two_stage", 1, (1.0,))
    check("경로만(ladder 1.0): 혼합 집단에서도 폭 전원 1.0", all(v == 1.0 for h in hist_p for v in h[1].values()))
    hist_w, _, _ = run("plan_two_stage", 0, LADDER)
    check("폭만(max_moves 0): 혼합 집단에서도 배정 불변", all(h[0] == all_on_1(c) for h in hist_w))

    # ⑩ 연산은 고정 — 관측이 흔들려도 cpu1 은 첫 값(사전 진단)에서 안 움직인다
    cpu, byt = homo()
    c = make(cpu, byt)
    c0_before = c.cpu1["c0"]
    for r in range(4):
        detail = {k: {"cli_fwd": 0.5 * (1 + 0.5 * r), "cli_bwd": 0.5, "xfer": 1.0, "up_bytes": 8.39e6 * 2, "dn_bytes": 8.39e6 * 2} for k in c.ks}
        c.observe_round(detail, B)
    check("연산 고정: 4라운드 흔들린 관측 뒤에도 cpu1 불변", abs(c.cpu1["c0"] - c0_before) < 1e-12, f"{c0_before:.3f} → {c.cpu1['c0']:.3f} (관측 {c.cpu_obs['c0']:.3f})")
    c2 = MultiKnobController(list(cpu), fix_compute=False); c2.cpu1 = dict(cpu); c2.bytes1 = dict(byt); c2.net1 = dict(c.net1); c2.gamma = dict(c.gamma)
    for r in range(4):
        detail = {k: {"cli_fwd": 0.5 * (1 + 0.5 * r), "cli_bwd": 0.5, "xfer": 1.0, "up_bytes": 8.39e6 * 2, "dn_bytes": 8.39e6 * 2} for k in c2.ks}
        c2.observe_round(detail, B)
    check("(대조) fix_compute=False 면 EWMA 로 움직인다", abs(c2.cpu1["c0"] - c0_before) > 1e-6)

    # ⑪ 망은 최근 window 라운드 최선값 — 한 번 느렸다고 추정이 끌려가지 않고, window 를 넘기면 잊는다
    c = make(*homo())
    xs = [1.0, 3.0, 1.0, 1.0, 1.0]
    for x in xs:
        c.observe_round({k: {"cli_fwd": 0.1, "cli_bwd": 0.1, "xfer": x, "up_bytes": 8e6, "dn_bytes": 8e6} for k in c.ks}, B)
    net_after = c.net1["c0"]
    c.observe_round({k: {"cli_fwd": 0.1, "cli_bwd": 0.1, "xfer": 3.0, "up_bytes": 8e6, "dn_bytes": 8e6} for k in c.ks}, B)
    check("망 최선값: 한 라운드 느려져도 추정은 최선값 유지", abs(c.net1["c0"] - net_after) < 1e-12, f"{net_after:.3f} vs {c.net1['c0']:.3f}")
    for _ in range(3):
        c.observe_round({k: {"cli_fwd": 0.1, "cli_bwd": 0.1, "xfer": 3.0, "up_bytes": 8e6, "dn_bytes": 8e6} for k in c.ks}, B)
    check("망 최선값: window(3) 를 넘겨 계속 느리면 따라간다", c.net1["c0"] > net_after * 2.5, f"{net_after:.3f} → {c.net1['c0']:.3f}")

    # ⑫ 폭은 망 상황으로 다시 계산 — 망 병목 기기(c3, 관측 전송 8배)는 망이 빨라지면 폭을 덜 줄인다. 연산은 고정.
    def width_c3(net_scale):
        c = make(*homo())
        c.net1 = {k: v * net_scale for k, v in c.net1.items()}
        c.net1["c3"] *= 8.0                                     # 모형의 혼잡 추정(2.7s)보다 확실히 느린 관측
        caps = {"1": CAPS["1"] / net_scale, "2": CAPS["2"] / net_scale}
        cur = all_on_1(c); w = None
        for r in range(3):
            na, nw, T, why = c.plan_two_stage(B, caps, current_assign=cur, max_moves=0, ladder=LADDER, remaining=12 - r); cur = na; w = nw
        return w["c3"], w["c0"]
    (w3_slow, w0_slow), (w3_fast, w0_fast) = width_c3(1.0), width_c3(0.05)
    check("망 병목 기기: 망이 느리면 깎고(c3<1.0)", w3_slow < 1.0, f"느린 망 c3 {w3_slow}")
    check("망 병목 기기: 망이 20배 빨라지면 같은 기기를 덜 깎는다 (c3 폭 ≥ 느릴 때)", w3_fast >= w3_slow, f"빠른 망 c3 {w3_fast} vs 느린 망 {w3_slow}")
    check("정상 기기는 어느 망에서도 1.0", w0_slow == 1.0 and w0_fast == 1.0, f"{w0_slow} {w0_fast}")

    # ⑬ 관측으로 낙오자 포착 — 모형은 전원 같다고 보는데 c3 의 관측 전송시간만 3배면 c3 를 깎는다 (5판 1차 관찰 A 의 재발 방지)
    c = make(*homo())
    c.net1["c3"] = 8.0                                           # 모형(경로 부하 2.7s)보다 훨씬 느린 관측 — 5판 1차 c2 의 11s 처럼
    na, nw, T, why = c.plan_two_stage(B, CAPS, current_assign=all_on_1(c), max_moves=0, ladder=LADDER, remaining=12)
    check("관측 기반: 모형은 동질이어도 관측이 느린 c3 를 깎는다", nw["c3"] < 1.0 and all(nw[k] == 1.0 for k in ("c0", "c1", "c2")), f"{[nw[k] for k in c.ks]} / {why}")

    # ⑭ 복귀 재확인 — 폭을 올리는 결정은 2라운드 연속 "올려도 된다"일 때만
    cpu, byt = homo(); cpu["c0"] *= 12
    c = make(cpu, byt); cur = all_on_1(c)
    for r in range(3):
        na, nw, _, _ = c.plan_two_stage(B, CAPS, current_assign=cur, max_moves=0, ladder=LADDER, remaining=12 - r); cur = na
    check("(준비) c0 가 0.5 까지 내려감", nw["c0"] == 0.5, str(nw["c0"]))
    c.cpu1["c0"] = 0.18                                            # 기기가 갑자기 빨라졌다고 치자 (시험용)
    hist = []
    for r in range(3):
        na, nw, _, _ = c.plan_two_stage(B, CAPS, current_assign=cur, max_moves=0, ladder=LADDER, remaining=9 - r); cur = na; hist.append(nw["c0"])
    check("복귀 재확인: 첫 라운드는 유지, 둘째 라운드부터 한 칸씩 복귀", hist[0] == 0.5 and hist[1] == 0.75 and hist[2] == 1.0, f"{hist}")

    print(f"\n== {'전부 통과' if fails == 0 else f'실패 {fails}건'} ==")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
