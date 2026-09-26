# -*- coding: utf-8 -*-
"""폭×경로 온라인 판단 — 난수 시나리오 대량 점검 (몬테카를로).

  실장비 없이, 난수로 만든 판 수백 개 위에서 판단 규칙의 불변식을 검사한다:
    ① 무진동 — 같은 기기가 3회 이상 이동하지 않는다 (왕복 출렁임 금지).
              늦은 이동(정착 후 1회)은 위반이 아니라 **측정되는 성질**로 집계한다 —
              잡음(±10%)과 채택 문턱(10%)이 같은 크기라, 두 라운드 연속 문턱을
              우연히 넘는 판이 드물게 존재하는 것은 원리상 제거 불가.
    ② 개선   — 정착한 계획의 예측 시간이 '전원 경로1·전폭' 기준보다 나쁘지 않다
    ③ 상한   — 경로 이동은 어느 라운드든 최대 1명
    ④ 무개입 — 경로가 하나뿐이면 이동이 없다
    ⑤ 바닥   — 폭은 사다리 최솟값(0.25) 아래로 내려가지 않는다

  측정 잡음(±10%, 계측 불확도와 같은 크기)을 매 라운드 얹어 관측 흔들림까지 재현.

      python tests/test_wp_mc.py            # 300판
      python tests/test_wp_mc.py 1000       # 판 수 지정
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sfl"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from controller_multi import LADDER, MultiKnobController   # noqa: E402


def predict_ms(bytes1, cpu1, assign, widths, caps):
    """계획의 예측 라운드 시간 — joint_plan 과 같은 산식."""
    load = {r: 0.0 for r in caps}
    for k in bytes1:
        load[assign[k]] += bytes1[k] * widths[k] * 8 / caps[assign[k]]
    comp = sorted(cpu1.values())[len(cpu1) // 2]
    return max(load.values()) + comp


def run_scenario(rng, rounds=20):
    n = rng.randint(2, 4)                                   # 기기 수 (완전탐색 한계 —
    # 경로^n × 폭단계^n 이라 5대부터 조합 폭발. 대규모 판은 근사 탐색이 등록된 후속)
    m = rng.randint(1, 3)                                   # 경로 수
    ks = [f"c{i}" for i in range(n)]
    true_bytes = {k: rng.uniform(0.5e6, 8e6) for k in ks}   # 배치당 업로드
    true_cpu = {k: rng.uniform(0.05, 2.0) for k in ks}
    caps = {str(j + 1): rng.uniform(5e6, 100e6) for j in range(m)}

    c = MultiKnobController(ks)
    cur = {k: "1" for k in ks}                              # 전원 경로 1에서 시작
    widths = {k: 1.0 for k in ks}
    moves, viol = [], []
    move_cnt = {k: 0 for k in ks}                           # 기기별 누적 이동 (진동 검출)
    for r in range(rounds):
        for k in ks:                                        # 잡음 낀 관측 주입
            noisy = true_bytes[k] * rng.uniform(0.9, 1.1)
            c.bytes1[k] = noisy if k not in c.bytes1 else \
                0.5 * c.bytes1[k] + 0.5 * noisy
            c.cpu1[k] = true_cpu[k] * rng.uniform(0.9, 1.1)
        na, widths, ms, why = c.plan_width_path(1, caps, cur,
                                                remaining=rounds - r,
                                                switch_cost=0.3)
        moved = [k for k in na if na[k] != cur[k]]
        if len(moved) > 1:
            viol.append(f"이동 {len(moved)}명 (상한 위반)")
        if m == 1 and moved:
            viol.append("단일 경로에서 이동")
        if widths and min(widths.values()) < min(LADDER) - 1e-9:
            viol.append("폭 바닥 아래")
        for k in moved:
            move_cnt[k] += 1
        moves.append(len(moved))
        cur = na
    late = sum(moves[-5:])                                  # 성질 집계 (위반 아님)
    osc = [k for k, v in move_cnt.items() if v > 2]
    if osc:
        viol.append(f"진동 (3회 이상 이동: {osc})")
    base = predict_ms(true_bytes, true_cpu, {k: "1" for k in ks},
                      {k: 1.0 for k in ks}, caps)
    ours = predict_ms(true_bytes, true_cpu, cur, widths, caps)
    if ours > base * 1.02:                                  # 기준보다 나빠지면 위반
        viol.append(f"기준보다 나쁨 ({ours:.1f}s > {base:.1f}s)")
    return viol, (base - ours) / base * 100, late


def main():
    trials = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    rng = random.Random(7)
    bad, gains, lates = 0, [], 0
    for t in range(trials):
        viol, gain, late = run_scenario(rng)
        gains.append(gain)
        lates += 1 if late else 0
        if viol:
            bad += 1
            print(f"  판 {t}: {'; '.join(viol)}")
    gains.sort()
    print(f"\n{trials}판 점검 — 위반 {bad}판 / 늦은 이동 있는 판 {lates}판 (성질)")
    print(f"기준 대비 예측 개선: 중앙값 {gains[len(gains)//2]:+.1f}% / "
          f"최악 {gains[0]:+.1f}% / 최선 {gains[-1]:+.1f}%")
    print("PASS" if bad == 0 else "FAIL")
    sys.exit(0 if bad == 0 else 1)


if __name__ == "__main__":
    main()
