# -*- coding: utf-8 -*-
"""R 시리즈 사전 시뮬 — **재실측이 통과할 것인가를 실측 전에 시뮬로 확인한다.**

  재실측(scripts/exp/rerun_R.sh)은 몇 시간짜리 밤 배치다. 돌리기 전에,
  확정된 3판 규칙(D = α·중앙값, controller_multi — 이 파일이 아니라 **본체를 임포트**)을
  자기채점 방지 시뮬레이터(sim.World: 관측잡음·γ 오차·서버 직렬화·라운드 흔들림·고정비용)
  위에서 R2~R4 와 같은 모양으로 굴려 사전 등록 판정을 미리 적용해 본다.

  ★ 이 시뮬이 답할 수 있는 것: 결정(누구를 얼마나 좁히나)과 시간의 방향.
    답할 수 없는 것: 정확도(R5)와 실측 계측 건전성(R1) — 그건 실측만 안다.

  조건 재현 시나리오는 리그 물리를 따른다: c_shared=200e6 (run_g2 SHARED=200 —
  "서버 회선이 합계 이상이라 자기 회선이 주 병목"). World 기본(합계의 40%)은
  공유 병목 연구용이라 낙오자 자체가 안 생긴다 — 1차 실행에서 확인.

  ★ 2차 실행이 가르친 것 (N=16 FAIL 의 물리): SHARED 를 200M 고정한 채 N 을 늘리면
    전폭 총수요가 서버 회선을 넘어 **전원이 공유 회선에 묶인다** → 상대 낙오자가
    사라지고 규칙은 옳게 무개입한다 (그 국면의 정답은 전원 축소 — R6/E9 질문).
    리그 설계 의도("자기 회선이 주 병목")를 규모에서 유지하려면 서버 회선도
    클라당 ~50M 비례로 커야 한다 → run_g2 에 SFL_SHARED 손잡이 추가, R4 N=16 은
    SFL_SHARED=800 으로 등록.

  대응표 (판정은 docs/02_실험/실험_재설계_R시리즈.md §1 을 그대로 옮김):
    R2a 조건1  homogeneous N=4        → 전원 폭 1.0 유지 (좁힘 0)
    R2b 조건2  uniform_span 20~80 N=4 → 느린 쪽만 좁힘 + uniform 대비 makespan 단축
    R3  조건3  R2b 판에서 c3 80→16Mbps 교란 → 2라운드 내 반응, 교란 클라 좁힘, 회복
    R4  조건4  uniform_span N=8·16    → R2b 결론의 방향 유지
    (덤) 규모  homogeneous N=64~1024  → 균질 유지가 규모에서도 서는가 (min 은 여기서 죽었다)

    python sfl/experiments/run_r_sim.py
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from sim import World, simulate                     # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "out")
SEEDS = (1, 2, 3)


def avg(xs):
    return sum(xs) / len(xs)


def r2a():
    """조건1: 균질 — 아무것도 안 해야 한다."""
    cuts, ms_ratio = [], []
    for s in SEEDS:
        w = World(4, seed=s, dist="homogeneous", c_shared=200e6)
        u = simulate(w, "uniform", rounds=10)
        w = World(4, seed=s, dist="homogeneous", c_shared=200e6)
        o = simulate(w, "multi", rounds=10)
        cuts.append(max(h["n_cut"] for h in o["hist"]))
        ms_ratio.append(o["makespan"] / u["makespan"])
    ok = max(cuts) == 0
    return ok, {"최대 좁힘 수": max(cuts), "makespan 비(ours/uniform)": round(avg(ms_ratio), 3)}, \
        "전 라운드 전원 폭 1.0 유지"


def r2b(n=4, tag="조건2"):
    """조건2/4: 고정 이질 20~80Mbps — 느린 쪽만 좁히고 시간을 벌어야 한다."""
    gains, wrong = [], 0
    for s in SEEDS:
        w = World(n, seed=s, dist="uniform_span", c_shared=50e6 * n)
        u = simulate(w, "uniform", rounds=10)
        w = World(n, seed=s, dist="uniform_span", c_shared=50e6 * n)
        o = simulate(w, "multi", rounds=10)
        gains.append(1 - o["makespan"] / u["makespan"])
        # 좁힌 클라가 회선 하위 절반에 속하나 (uniform_span 은 c0 이 최저, c{n-1} 이 최고)
        last_p = {k: 1.0 for k in w.ks}
        ctl_hist = o["hist"][-1]
        # simulate 는 폭 벡터를 히스토리에 안 남기므로 좁힘 수와 방향만 본다:
        # 검증은 '최고회선 절반이 전폭 유지'로 대신한다 → 시뮬 한 번 더 돌려 마지막 폭을 직접 본다
    # 마지막 폭을 직접 얻는 재실행 (seed 1)
    from sim import make_multi
    w = World(n, seed=1, dist="uniform_span", c_shared=50e6 * n)
    ctl = make_multi(w)
    pv = {k: 1.0 for k in w.ks}
    qv = {k: 0 for k in w.ks}
    for r in range(10):
        if r >= 1:
            pv, qv = ctl.decide(w.batches)
        ms, obs, T = w.run(pv, qv)
        ctl.observe_round(obs, w.batches)
    slow_half = set(list(w.ks)[: n // 2])
    narrowed = {k for k, v in pv.items() if v < 1.0}
    ok = avg(gains) > 0.10 and narrowed and narrowed.issubset(slow_half)
    return ok, {"uniform 대비 단축": f"{avg(gains)*100:+.1f}%",
                "좁힌 클라": sorted(narrowed), "허용 범위(하위 절반)": sorted(slow_half)}, \
        f"{tag}: 단축 >10% + 좁힘이 회선 하위 절반에만"


def r3():
    """조건3: c3(최고 회선 80M)이 라운드 4에 16M 로 몰락 — 따라가야 한다."""
    from sim import make_multi
    reacts, recovers = [], []
    for s in SEEDS:
        w = World(4, seed=s, dist="uniform_span", c_shared=200e6)  # 20/40/60/80, 리그 SHARED=200M
        ctl = make_multi(w)
        pv = {k: 1.0 for k in w.ks}
        qv = {k: 0 for k in w.ks}
        ms_hist, p3_hist = [], []
        for r in range(14):
            if r == 4:
                w.link["c3"] = 16e6                        # ★ 몰락 (실측 조건3과 동일)
            if r >= 1:
                pv, qv = ctl.decide(w.batches)
            ms, obs, T = w.run(pv, qv)
            ctl.observe_round(obs, w.batches)
            ms_hist.append(ms)
            p3_hist.append(pv["c3"])
        react = next((r - 4 for r in range(4, 14) if p3_hist[r] < 1.0), None)
        reacts.append(react if react is not None else 99)
        # 회복: 교란 직후 최악 makespan 대비, 이후 최저가 교란 전 수준의 1.3배 이내로
        pre = avg(ms_hist[1:4])
        post_worst = max(ms_hist[4:7])
        post_best = min(ms_hist[7:])
        recovers.append(post_best <= max(pre * 1.3, post_worst * 0.75))
    ok = max(reacts) <= 2 and all(recovers)
    return ok, {"반응 라운드(교란 후)": reacts, "회복": recovers}, \
        "반응 ≤2라운드 + makespan 회복 — ★ 중앙값 '자기 무력화' 반증의 시뮬 예고편"


def scale_bonus():
    """(덤) 균질 대규모 — min 이 죽던 자리. 3판은 서야 한다."""
    rows = {}
    for n in (64, 256, 1024):
        cuts = []
        for s in SEEDS:
            w = World(n, seed=s, dist="homogeneous")
            o = simulate(w, "multi", rounds=6)
            cuts.append(max(h["n_cut"] for h in o["hist"]) / n)
        rows[n] = round(max(cuts) * 100, 1)
    ok = all(v <= 5.0 for v in rows.values())
    return ok, {"최대 좁힘 비율 %": rows}, "균질 N=64~1024 에서 좁힘 ≤5% (구 규칙: N=1024 에서 97%)"


def main():
    res = {}
    print("=" * 78)
    print("  R 시리즈 사전 시뮬 — 3판 규칙(α·중앙값), 자기채점 방지 World, 시드 3")
    print("=" * 78)
    for name, fn in [("R2a 조건1 균질", r2a),
                     ("R2b 조건2 이질 N=4", lambda: r2b(4, "조건2")),
                     ("R3  조건3 교란", r3),
                     ("R4  조건4 N=8", lambda: r2b(8, "조건4 N=8")),
                     ("R4  조건4 N=16", lambda: r2b(16, "조건4 N=16")),
                     ("규모 균질 64~1024", scale_bonus)]:
        ok, detail, crit = fn()
        res[name] = {"pass": ok, "detail": detail, "crit": crit}
        print(f"\n  [{name}]  {'PASS' if ok else 'FAIL'}")
        print(f"    기준: {crit}")
        for k, v in detail.items():
            print(f"    {k}: {v}")
    io.open(os.path.join(OUT, "r_sim_results.json"), "w", encoding="utf-8").write(
        json.dumps(res, ensure_ascii=False, indent=1, default=str))
    allok = all(v["pass"] for v in res.values())
    print("\n" + "=" * 78)
    print(f"  종합: {'전부 PASS — 재실측이 같은 방향이면 사다리가 선다' if allok else '★ FAIL 있음 — 재실측 전에 원인을 본다'}")
    print("  (정확도(R5)·계측 건전성(R1)은 시뮬이 답하지 않는다 — 실측의 몫)")
    print("=" * 78)
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
