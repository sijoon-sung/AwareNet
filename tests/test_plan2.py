# -*- coding: utf-8 -*-
"""plan.py (인지·계획·집행의 계획 층) 시험 — 물 채우기 해석해 · 총비용 열린 집합 · 분할 전송 · 폭 규칙 · 시너지 방향.
    python tests/test_plan2.py
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sfl"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import plan  # noqa: E402

M = 1e6
fails = 0
def check(name, ok, detail=""):
    global fails; fails += 0 if ok else 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

def prof4(cpu=(0.18,)*4, acc=(50,50,50,50), mb=8.39):
    ks=[f"c{i}" for i in range(len(cpu))]
    return {"cpu": dict(zip(ks,cpu)), "gamma": {k:1.2 for k in ks}, "bytes": {k: mb*M for k in ks},
            "access": {k: a*M for k,a in zip(ks,acc)}}

def main():
    print("== plan.py 시험 ==")
    caps = {"1": 60*M, "2": 60*M}
    # ① 물 채우기 해석해
    r = plan.water_fill({"c0":("1",),"c1":("1",)}, caps, None)
    check("물 채우기: 2대 균등 30/30", abs(r["c0"]["1"]-30*M)<1 and abs(r["c1"]["1"]-30*M)<1, f"{r}")
    r = plan.water_fill({"c0":("1",),"c1":("1",),"c2":("1",),"c3":("1",)}, caps, {"c2":10*M})
    check("물 채우기: 접속 10M 기기는 10, 나머지 (60-10)/3=16.7", abs(r["c2"]["1"]-10*M)<1 and abs(r["c0"]["1"]-50*M/3)<1, f"{ {k:round(v['1']/M,1) for k,v in r.items()} }")
    r = plan.water_fill({"c0":("1","2")}, caps, {"c0":50*M})
    check("물 채우기: 혼자 두 경로(120) 열어도 접속 50 이 상한", abs(sum(r["c0"].values())-50*M)<1, f"{ {k:round(v/M,1) for k,v in r['c0'].items()} }")
    r = plan.water_fill({"c0":("1","2"),"c1":("1",),"c2":("1",)}, caps, None)
    check("물 채우기: 분할 기기는 경로1 몫(20)+경로2 전부(60)=80", abs(sum(r["c0"].values())-80*M)<1 and abs(r["c1"]["1"]-20*M)<1, f"c0 {sum(r['c0'].values())/M:.0f} c1 {r['c1']['1']/M:.0f}")

    # ② 망 효과 조건(h5n): 전원 경로1, 접속 병목 c2 → 총비용 최소는 남을 옮김
    P = prof4(acc=(50,50,10,50)); cur = {k:("1",) for k in P["cpu"]}
    S, cost = plan.best_sets({k:1.0 for k in P["cpu"]}, P, caps, cur)
    check("총비용: 혼잡 기기들이 경로 2 로 나뉜다", sum(1 for k,v in S.items() if v==("2",)) >= 1, f"{S} cost {cost:.2f}")
    c_stay = plan.total_cost(plan.round_times({k:1.0 for k in P["cpu"]}, cur, P, caps))
    check("총비용: 나뉘면 전원 경로1 보다 싸다", cost < c_stay, f"{cost:.2f} < {c_stay:.2f}")

    # ③ 분할 전송: 기기 3대 홀수 → 이진은 2/1, 분할은 균형
    P3 = prof4(cpu=(0.18,)*3, acc=(50,50,50)); cur3 = {k:("1",) for k in P3["cpu"]}
    Sb, cb = plan.best_sets({k:1.0 for k in P3["cpu"]}, P3, caps, cur3, multipath=False)
    Sm, cm = plan.best_sets({k:1.0 for k in P3["cpu"]}, P3, caps, cur3, multipath=True)
    check("분할: 3대·경로 2개에서 분할 총비용 ≤ 이진", cm <= cb + 1e-9, f"분할 {cm:.2f} vs 이진 {cb:.2f}  {Sm}")
    rb = plan.effective_rate(Sb, caps, P3["access"]); rm = plan.effective_rate(Sm, caps, P3["access"])
    bal = lambda rr: max(rr.values())/min(rr.values())
    check("분할: 기기별 실효 전송률 편차(최대/최소)가 분할에서 더 작다", bal(rm) <= bal(rb) + 1e-9, f"분할 {bal(rm):.2f} vs 이진 {bal(rb):.2f}")
    Sa, ca = plan.best_sets({k:1.0 for k in P["cpu"]}, P, caps, cur, multipath=True)
    check("분할: 접속 병목 기기(c2)는 분할해도 실효율 10M 그대로", abs(plan.effective_rate(Sa, caps, P["access"])["c2"]-10*M) < 1, f"{Sa}")

    # ④ 폭 규칙
    Pc = prof4(cpu=(0.18*6.7,0.18,0.18,0.18)); Sc = {k:("1",) for k in Pc["cpu"]}
    w, D, cut, ro = plan.width_stage(Sc, Pc, {"1":400*M,"2":400*M}, (0.5,0.75,1.0), 1.2, {k:1.0 for k in Pc["cpu"]})
    check("폭: 연산 6.7배 기기만 한 칸(0.75)", w["c0"]==0.75 and all(w[k]==1.0 for k in ("c1","c2","c3")), f"{w} D={D:.2f}")
    w2, D2, cut2, ro2 = plan.width_stage(Sc, Pc, {"1":400*M,"2":400*M}, (0.5,0.75,1.0), 1.2, w, raise_ok=ro)
    check("폭: 둘째 라운드 0.5 (연산 6.7배는 바닥까지)", w2["c0"]==0.5, f"{w2}")
    w3, _, _, _ = plan.width_stage(Sc, prof4(), {"1":400*M,"2":400*M}, (0.5,0.75,1.0), 1.2, {k:1.0 for k in Pc["cpu"]})
    check("폭: 동질이면 전원 1.0", all(v==1.0 for v in w3.values()))
    obs = {"c3": 8.0}                                      # 관측이 모형보다 훨씬 느린 기기
    w4, _, _, _ = plan.width_stage({k:("1",) for k in P["cpu"]}, prof4(), caps, (0.5,0.75,1.0), 1.2, {k:1.0 for k in P["cpu"]}, observed=obs)
    check("폭: 모형은 같아도 관측이 느린 c3 를 깎는다", w4["c3"] < 1.0 and w4["c0"]==1.0, f"{w4}")

    # ⑤ 시너지 방향 — 혼합 집단(연산 낙오자 c0 + 혼잡 + 접속 병목 c2)
    Pm = prof4(cpu=(0.18*6.7,0.18,0.18,0.18), acc=(50,50,10,50))
    def run(mp, max_moves, ladder, rounds=6, mode="anchored"):
        st = {"sets": {k:("1",) for k in Pm["cpu"]}, "widths": {k:1.0 for k in Pm["cpu"]}, "raise_ok": {}}
        res=None
        for r in range(rounds):
            res = plan.plan(Pm, st, caps, ladder=ladder, alpha=1.2, max_moves=max_moves, multipath=mp, remaining=12-r, deadline_mode=mode)
            st = {"sets": res["sets"], "widths": res["widths"], "raise_ok": res["raise_ok"], "ref_sets": res["ref_sets"]}
        return res
    both = run(True, 1, (0.5,0.75,1.0)); pathonly = run(True, 1, (1.0,)); widthonly = run(False, 0, (0.5,0.75,1.0))
    check("시너지: 둘다 총비용 ≤ 경로만·폭만", both["cost"] <= pathonly["cost"]+1e-9 and both["cost"] <= widthonly["cost"]+1e-9,
          f"둘다 {both['cost']:.2f} 경로만 {pathonly['cost']:.2f} 폭만 {widthonly['cost']:.2f}")
    check("시너지: 둘다 라운드 시간 ≤ 경로만·폭만", both["makespan"] <= pathonly["makespan"]+1e-9 and both["makespan"] <= widthonly["makespan"]+1e-9,
          f"둘다 {both['makespan']:.2f} 경로만 {pathonly['makespan']:.2f} 폭만 {widthonly['makespan']:.2f}")
    check("시너지: 접속 병목 c2 는 폭으로(경로 무익), 정상 c1 은 1.0", both["widths"]["c2"] < 1.0 and both["widths"]["c1"]==1.0, f"{both['widths']}")
    check("B안(anchored): 경로가 풀려도 연산 낙오자 c0 의 폭은 폭만 팔보다 낮아지지 않는다 (기준선을 조이지 않음)", both["widths"]["c0"] >= widthonly["widths"]["c0"], f"둘다 {both['widths']['c0']} vs 폭만 {widthonly['widths']['c0']}")
    bothA = run(True, 1, (0.5,0.75,1.0), mode="relative")
    check("A안(relative) 비교: 같은 집단에서 폭 평균이 B안 이하 (라운드 우선, 정확도 대가 비교 실험용)", sum(bothA["widths"].values()) <= sum(both["widths"].values()) + 1e-9, f"A {bothA['widths']} vs B {both['widths']}")
    r3 = plan.effective_rate(both["sets"], caps, Pm["access"])["c3"]
    check("시너지: 공짜 손잡이가 있으면 정상 기기 c3 는 폭을 안 깎고 접속 상한(50M)까지 받는다", both["widths"]["c3"]==1.0 and abs(r3-50*M) < 1, f"c3 폭 {both['widths']['c3']} 경로 {both['sets']['c3']} 실효 {r3/M:.1f}M")
    print("  [INFO] 둘다 결정:", both["sets"], both["widths"], "|", both["why"])
    print(plan.explain(Pm, both, caps))

    # ⑥ 2026-09-07 새벽 실험이 잡은 결함 두 가지 — 다시는 안 나게 고정
    ks5 = [f"c{i}" for i in range(5)]
    P5 = {"cpu": {k: 0.3 for k in ks5}, "gamma": {k: 1.2 for k in ks5}, "bytes": {k: 8.39*M for k in ks5}, "access": {k: 47*M for k in ks5}}
    # ⑥-1 왕복(3:2 ↔ 2:3): 관측이 "경로 1 에 4대" 시절의 값이라 남는 기기만 무거워 보이던 문제
    cur = {"c0":("1",),"c1":("2",),"c2":("1",),"c3":("2",),"c4":("2",)}
    then = {k:("1",) for k in ks5}; then["c4"] = ("2",)                     # 관측 당시 배정: 경로 1 에 4대
    r_then = plan.effective_rate(then, caps, P5["access"])
    obs = {k: [{"net": 8.39*M*8/r_then[k]*1.1, "sets": then}] for k in ("c0","c2")}   # 그때 모형보다 10% 느렸다 (효율 1.1)
    S6, why6 = plan.path_stage({k:1.0 for k in ks5}, P5, caps, cur, max_moves=1, multipath=False, eff=plan.efficiency(P5, caps, obs, cur))
    check("⑥-1 왕복 방지: 2:3 에서 옛 관측(4대 시절)이 있어도 옮기지 않는다", S6 == cur and why6.startswith("경로 유지"), f"{why6} {S6}")
    eff6 = plan.efficiency(P5, caps, obs, cur)
    check("⑥-1 효율 계수 = 관측/그때 모형 = 1.1 (혼잡과 무관)", all(abs(eff6[k]-1.1) < 1e-6 for k in ("c0","c2")), f"{eff6}")
    t_on1 = plan.round_times({k:1.0 for k in ks5}, cur, P5, caps, eff6)["c0"]
    alt = dict(cur); alt["c0"] = ("2",)
    t_on2 = plan.round_times({k:1.0 for k in ks5}, alt, P5, caps, eff6)["c0"]
    m1 = 8.39*M*8/plan.effective_rate(cur, caps, P5["access"])["c0"]; m2 = 8.39*M*8/plan.effective_rate(alt, caps, P5["access"])["c0"]
    check("⑥-1 같은 계수를 어느 후보에나 곱한다 (남는 쪽만 무겁지 않다)", abs((t_on1-0.3)/m1 - 1.1) < 1e-6 and abs((t_on2-0.3)/m2 - 1.1) < 1e-6, f"{(t_on1-0.3)/m1:.3f} {(t_on2-0.3)/m2:.3f}")
    # ⑥-2 통째 이동 먼저: 경로 2 가 비었으면 분할(1+2)보다 통째로 옮기는 수가 싸다 — 그 수를 봐야 한다
    all1 = {k:("1",) for k in ks5}
    S7, why7 = plan.path_stage({k:1.0 for k in ks5}, P5, caps, all1, max_moves=1, multipath=True)
    movedk = [k for k in ks5 if S7[k] != all1[k]]
    c_whole = plan.total_cost(plan.round_times({k:1.0 for k in ks5}, {**all1, "c4":("2",)}, P5, caps))
    c_split = plan.total_cost(plan.round_times({k:1.0 for k in ks5}, {**all1, "c4":("1","2")}, P5, caps))
    check("⑥-2 통째 이동 먼저: 분할 허용이어도 첫 수는 한 대를 경로 2 로 통째로", len(movedk)==1 and S7[movedk[0]]==("2",), f"{why7} (통째 {c_whole:.1f}s < 분할 {c_split:.1f}s)")
    # ⑥-3 분할이 진짜 이기는 자리: 접속이 작은 기기들이 경로를 다 못 채워 남는 용량이 있을 때 큰 기기가 두 경로를 다 쓴다
    ks4 = [f"c{i}" for i in range(4)]
    P8 = {"cpu": {k: 0.3 for k in ks4}, "gamma": {k: 1.2 for k in ks4}, "bytes": {k: 8.39*M for k in ks4}, "access": dict(zip(ks4, (10*M,10*M,10*M,80*M)))}
    st = {"sets": {k:("1",) for k in ks4}, "widths": {k:1.0 for k in ks4}, "raise_ok": {}}
    for r in range(6):
        res = plan.plan(P8, st, caps, ladder=(1.0,), alpha=1.2, max_moves=1, multipath=True, remaining=12-r)
        st = {"sets": res["sets"], "widths": res["widths"], "raise_ok": res["raise_ok"], "ref_sets": res["ref_sets"]}
    best_bin = min(plan.total_cost(plan.round_times({k:1.0 for k in ks4}, {**{k:("1",) for k in ks4}, "c3":("2",)}, P8, caps)),
                   plan.total_cost(plan.round_times({k:1.0 for k in ks4}, {k:("1",) for k in ks4}, P8, caps)))
    check("⑥-3 남는 용량이 있으면 큰 기기(80M)는 두 경로를 다 열고 총비용 < 최선의 이진 배정", len(res["sets"]["c3"])==2 and res["cost"] < best_bin - 1e-9, f"{res['sets']} {res['cost']:.2f} vs 이진 {best_bin:.2f}")
    # ⑦ 두 가닥 접속 (2026-09-07 결정): 출구 A 50 + 출구 B 20
    A2 = {k: [50*M, 20*M] for k in ks4}
    check("⑦ 두 가닥 혼자 (1,2): 50+20=70", abs(plan.effective_rate({"c0":("1","2")}, caps, A2)["c0"] - 70*M) < 1)
    check("⑦ 두 가닥 (2,1) 도 후보 (출구별 순서가 다르다)", ("2","1") in plan.candidate_sets(["1","2"], True, True, two_links=True))
    c4 = plan.candidate_sets(["1","2","3","4"], True, True, two_links=True)
    check("⑦ 경로 4개·두 가닥: 후보 = 순서쌍 16 (회선 하나 후보는 제외, §9-2 09:20), 4출구 집합 없음", len(c4) == 16 and all(len(x) <= 2 for x in c4) and ("3","1") in c4, f"{len(c4)}개 최대 길이 {max(len(x) for x in c4)}")
    xr = plan.exit_rates({"c0": ("1","2"), "c1": ("1",)}, caps, {"c0": [50*M, 20*M], "c1": 50*M})
    check("⑦ 출구별 속도(조각 가중치): c0 (1,2) → [30(경로1 을 c1 과 반씩), 20], c1 은 출구 하나 [30]", abs(xr["c0"][0]-30*M) < 1 and abs(xr["c0"][1]-20*M) < 1 and xr["c1"] == [30*M], f"{ {k:[round(v/M,1) for v in vs] for k,vs in xr.items()} }")
    # 두 가닥이 버는 자리 = 경로가 아니라 **접속 회선이 병목**일 때 (KOREN 고속망 시나리오). 경로 60/60 이면 경로가 병목이라 이득 0 (문헌 §1-3)
    caps2 = {"1": 150*M, "2": 150*M}
    P9 = {"cpu": {k: 0.3 for k in ks4}, "gamma": {k: 1.2 for k in ks4}, "bytes": {k: 8.39*M for k in ks4}, "access": A2}
    st = {"sets": {k:("1",) for k in ks4}, "widths": {k:1.0 for k in ks4}, "raise_ok": {}}
    for r in range(8):
        res = plan.plan(P9, st, caps2, ladder=(1.0,), alpha=1.2, max_moves=1, multipath=True, remaining=12-r)
        st = {"sets": res["sets"], "widths": res["widths"], "raise_ok": res["raise_ok"], "ref_sets": res["ref_sets"]}
    r_mp = plan.effective_rate(res["sets"], caps2, A2)
    st1 = {"sets": {k:("1",) for k in ks4}, "widths": {k:1.0 for k in ks4}, "raise_ok": {}}
    for r in range(8):
        res1 = plan.plan(P9, st1, caps2, ladder=(1.0,), alpha=1.2, max_moves=1, multipath=False, remaining=12-r)
        st1 = {"sets": res1["sets"], "widths": res1["widths"], "raise_ok": res1["raise_ok"], "ref_sets": res1["ref_sets"]}
    check("⑦ 두 가닥 4대(경로 150/150, 접속이 병목): 분할 팔은 전원 두 출구를 열어 각 70, 이진 팔은 50 — 총비용 −28%", all(len(v)==2 for v in res["sets"].values()) and min(r_mp.values()) >= 70*M-1 and res["cost"] < res1["cost"]-1e-9,
          f"분할 {['+'.join(v) for v in res['sets'].values()]} {res['cost']:.1f}s vs 이진 {['+'.join(v) for v in res1['sets'].values()]} {res1['cost']:.1f}s")
    # ⑧ 폭 기준선 B′ (solo, 2026-09-08): 자기 회선 기준 — ρ 와 무관, 연산 병목 기기만 폭 후보 (설계기록_컨트롤러 §10)
    ks8 = [f"c{i}" for i in range(8)]
    sp = [0.15, 0.25, 1, 1, 1, 1, 1, 1]; ac = [[50, 20], [50, 20], [20, 20], [20, 20]] + [[50, 20]] * 4
    P10 = {"cpu": {k: 0.40 / sp[i] for i, k in enumerate(ks8)}, "gamma": {k: 1.2 for k in ks8}, "bytes": {k: 8.39*M for k in ks8},
           "access": {k: [x*M for x in ac[i]] for i, k in enumerate(ks8)}}
    sets1 = {k: ("1",) for k in ks8}
    D_lo = plan.deadline(sets1, P10, {str(e): 250*M for e in range(1, 5)}, 1.2, None, sets1, "solo")
    D_hi = plan.deadline(sets1, P10, {str(e): 62*M for e in range(1, 5)}, 1.2, None, sets1, "solo")
    D_b = plan.deadline(sets1, P10, {str(e): 62*M for e in range(1, 5)}, 1.2, None, sets1, "anchored")
    check("⑧-1 B′ 기준선은 엣지 용량(ρ)과 무관, B안은 혼잡할수록 커진다", abs(D_lo - D_hi) < 1e-9 and D_b > 3 * D_hi, f"solo {D_lo:.2f}={D_hi:.2f}s, anchored(ρ2) {D_b:.2f}s")
    check("⑧-2 연산 병목 판정: 낙오자 2대만 참 (접속 병목·정상은 거짓)", [plan._compute_bound(k, P10) for k in ks8] == [True, True] + [False] * 6)
    st = {"sets": sets1, "widths": {k: 1.0 for k in ks8}, "raise_ok": {}}
    caps8 = {str(e): 125*M for e in range(1, 5)}
    for r in range(10):
        res = plan.plan(P10, st, caps8, ladder=(0.5, 0.75, 1.0), alpha=1.2, max_moves=1, multipath=True, remaining=24-r, deadline_mode="solo")
        st = {"sets": res["sets"], "widths": res["widths"], "raise_ok": res["raise_ok"], "ref_sets": res["ref_sets"]}
    w = res["widths"]; S = res["sets"]
    check("⑧-3 ρ1 혼합 집단 10R: 낙오자 폭 < 1, 접속 병목은 두 출구 + 전폭, 정상 전폭",
          w["c0"] < 1 and w["c1"] < 1 and all(w[k] == 1.0 for k in ks8[2:]) and all(len(S[k]) == 2 for k in ("c2", "c3")),
          f"폭 {[w[k] for k in ks8]} 경로 {['+'.join(S[k]) for k in ks8]}")
    st_b = {"sets": sets1, "widths": {k: 1.0 for k in ks8}, "raise_ok": {}}
    for r in range(10):
        res_b = plan.plan(P10, st_b, caps8, ladder=(0.5, 0.75, 1.0), alpha=1.2, max_moves=1, multipath=True, remaining=24-r, deadline_mode="anchored")
        st_b = {"sets": res_b["sets"], "widths": res_b["widths"], "raise_ok": res_b["raise_ok"], "ref_sets": res_b["ref_sets"]}
    check("⑧-4 같은 집단에서 B안(anchored)은 폭을 하나도 안 깎는다 (B′ 를 두는 이유)", all(v == 1.0 for v in res_b["widths"].values()), f"{res_b['widths']}")
    # ⑨ 고정 목표 D (fixed, 2026-09-08 사용자 결정): 같은 D 를 맞추는 데 망을 고치면 폭을 덜 깎는다 — 3번 결합 실험의 뼈대
    D_round = 10.0                                            # 라운드 목표(초), 배치 4 → 배치당 2.5s
    st_w = {"sets": sets1, "widths": {k: 1.0 for k in ks8}, "raise_ok": {}}
    for r in range(6):                                        # 폭만(이동 0): 전원 엣지 1 혼잡 → 모두 깎아야 D 근처
        res_w = plan.plan(P10, st_w, caps8, ladder=(0.5, 0.75, 1.0), alpha=1.2, max_moves=0, multipath=False, remaining=24-r, batches=4, deadline_mode="fixed", deadline_s=D_round)
        st_w = {"sets": res_w["sets"], "widths": res_w["widths"], "raise_ok": res_w["raise_ok"], "ref_sets": res_w["ref_sets"]}
    check("⑨-1 고정 D=10s, 폭만(이동 0): 혼잡 때문에 8대 전부 폭 0.5", all(v == 0.5 for v in res_w["widths"].values()), f"{res_w['widths']}")
    st_c = {"sets": sets1, "widths": {k: 1.0 for k in ks8}, "raise_ok": {}}
    for r in range(10):                                       # 결합(폭+엣지+분할): 망 교정 뒤 연산 낙오자만 깎는다
        res_c = plan.plan(P10, st_c, caps8, ladder=(0.5, 0.75, 1.0), alpha=1.2, max_moves=1, multipath=True, remaining=24-r, batches=4, deadline_mode="fixed", deadline_s=D_round)
        st_c = {"sets": res_c["sets"], "widths": res_c["widths"], "raise_ok": res_c["raise_ok"], "ref_sets": res_c["ref_sets"]}
    wc = res_c["widths"]
    check("⑨-2 고정 D=10s, 결합: 낙오자 c0 0.5 · c1 0.75, 접속 병목·정상 6대는 전폭 (분할·엣지가 대신 풀었다)",
          wc["c0"] == 0.5 and wc["c1"] == 0.75 and all(wc[k] == 1.0 for k in ks8[2:]), f"{[wc[k] for k in ks8]}")
    check("⑨-3 폭 합: 결합이 폭만보다 크다 (정확도 대가가 작다) — D 는 같음", sum(wc.values()) > sum(res_w["widths"].values()) + 2.0,
          f"결합 {sum(wc.values()):.2f} vs 폭만 {sum(res_w['widths'].values()):.2f}")
    check("⑨-4 결합의 모형 라운드 시간 ≤ D (목표를 맞춘다)", res_c["makespan"] <= D_round + 1e-6, f"{res_c['makespan']:.2f}s")
    st_e = {"sets": sets1, "widths": {k: 1.0 for k in ks8}, "raise_ok": {}}
    for r in range(10):                                       # 초기 라운드(이동 중)에도 망 피해자 폭을 잠깐 깎지 않는다 (목표 배정 기준)
        res_e = plan.plan(P10, st_e, caps8, ladder=(0.5, 0.75, 1.0), alpha=1.2, max_moves=1, multipath=True, remaining=24-r, batches=4, deadline_mode="fixed", deadline_s=D_round)
        st_e = {"sets": res_e["sets"], "widths": res_e["widths"], "raise_ok": res_e["raise_ok"], "ref_sets": res_e["ref_sets"]}
        if r == 1:
            early = dict(res_e["widths"])
    check("⑨-5 이동이 끝나기 전(2라운드째)에도 정상·접속 병목 기기의 폭은 1.0 (왕복 없음)", all(early[k] == 1.0 for k in ks8[2:]), f"{early}")
    # ⑩ 고정 목표의 폭 판단: 가산 잔차 + 관측 보호 (3번 1차 실행 결함 2026-09-08)
    obs_half = {"c4": [{"net": 0, "raw": 0.54 + 0.5, "w": 0.5, "tot": 6.0, "sets": {k: ("2", "2") if k == "c4" else ("1", "1") for k in ks8}}]}
    rs = plan.residual(P10, caps8, obs_half)
    exp_r = 0.54 + 0.5 - 8.39*M*0.5*8/70e6                     # c4 혼자 경로 2: 속도 = 접속 합 70M
    check("⑩-1 가산 잔차: 폭 0.5 에서 잰 관측(1.04s)에서 모형(4.2MB/70M)을 뺀 잔차 (폭과 무관)", abs(rs["c4"] - exp_r) < 0.01, f"{rs} 기대 {exp_r:.2f}")
    st_h = {"sets": {k: ("2", "2") if k == "c4" else ("1", "1") for k in ks8}, "widths": {**{k: 1.0 for k in ks8}, "c4": 0.5}, "raise_ok": {"c4": 1}, "observed": obs_half}
    res_h = plan.plan(P10, st_h, caps8, ladder=(0.5, 0.75, 1.0), alpha=1.2, max_moves=1, multipath=True, remaining=10, batches=4, deadline_mode="fixed", deadline_s=10.0)
    check("⑩-2 잔차 모형에서 정상 기기 c4 는 전폭도 D 안(0.41+1.08+0.5 ≤ 2.5) → 0.5 에 고착되지 않고 복귀한다", res_h["widths"]["c4"] > 0.5, f"c4 {res_h['widths']['c4']}")
    obs_ok = {"c5": [{"net": 0, "raw": 3.0, "w": 1.0, "tot": 9.0, "sets": {k: ("1", "1") for k in ks8}}]}   # 모형은 'D 초과'라 하지만 실측 라운드 9s ≤ 10s
    st_g = {"sets": {k: ("1", "1") for k in ks8}, "widths": {k: 1.0 for k in ks8}, "raise_ok": {}, "observed": obs_ok}
    res_g = plan.plan(P10, st_g, caps8, ladder=(0.5, 0.75, 1.0), alpha=1.2, max_moves=0, multipath=False, remaining=10, batches=4, deadline_mode="fixed", deadline_s=10.0)
    check("⑩-3 관측 보호: 실측 라운드가 D 안인 기기(c5)는 모형이 초과라 해도 폭을 안 깎는다", res_g["widths"]["c5"] == 1.0, f"c5 {res_g['widths']['c5']}, 관측 없는 c6 {res_g['widths']['c6']}")
    # ⑪ 또래 기준(peer): 연산 기준으로 후보 → 망 보완 → 또래 라운드 × α 안에서 최소 축소 (2026-09-09 사용자 결정, 설계기록 §12)
    P11 = {"cpu": {**{k: 0.40 for k in ks8}, "c0": 0.40 / 0.15, "c1": 0.40 / 0.15}, "gamma": {k: 1.2 for k in ks8}, "bytes": {k: 8.39*M for k in ks8},
           "access": {**{k: [50*M, 20*M] for k in ks8}, "c2": [20*M, 20*M], "c3": [20*M, 20*M]}}       # 낙오자 c0·c1, 접속 병목 c2·c3
    cs = plan.compute_stragglers(P11, 1.2)
    check("⑪-1 연산 기준: 후보 = 연산 낙오자 c0·c1 뿐 (접속 병목 c2·c3 는 후보 아님)", cs == {"c0", "c1"}, f"{sorted(cs)}")
    def run_peer(caps_, sets0, rounds=12, dl=None):
        st_ = {"sets": sets0, "widths": {k: 1.0 for k in ks8}, "raise_ok": {}}
        hist = []
        for r in range(rounds):
            res_ = plan.plan(P11, st_, caps_, ladder=(0.5, 0.75, 1.0), alpha=1.2, max_moves=1, multipath=True, remaining=24-r, batches=4, deadline_mode="peer", deadline_s=dl)
            st_ = {"sets": res_["sets"], "widths": res_["widths"], "raise_ok": res_["raise_ok"], "ref_sets": res_["ref_sets"]}
            hist.append(dict(res_["widths"]))
        return res_, hist
    caps8b = {str(e): 125*M for e in range(1, 5)}
    res_p, hist = run_peer(caps8b, {k: ("1",) for k in ks8})
    wp = res_p["widths"]
    check("⑪-2 혼합 8대(ρ1): 낙오자 c0·c1 만 폭 < 1, 접속 병목·정상 6대는 전폭 (분할·엣지가 대신 풀었다)", wp["c0"] < 1 and wp["c1"] < 1 and all(wp[k] == 1.0 for k in ks8[2:]), f"{[wp[k] for k in ks8]}")
    flips = sum(1 for a, b in zip(hist, hist[1:]) for k in ks8 if a[k] != b[k])
    check("⑪-3 12라운드 왕복 없음 (폭 변경 ≤ 낙오자 2대 × 사다리 2칸 = 4회)", flips <= 4, f"폭 변경 {flips}회")
    # 망 보완: 같은 낙오자라도 빠른 엣지(빈 엣지)가 있으면 폭을 덜 깎는다 — 엣지 1개(모두 공유, 보완 불가) vs 엣지 4개(보완 가능)
    res_1, _ = run_peer({"1": 125*M}, {k: ("1",) for k in ks8})
    res_4, _ = run_peer(caps8b, {k: ("1",) for k in ks8})
    print(f"  [INFO] ⑪-4 또래 기준의 한계: 또래가 빨라지면 기준이 조여져 낙오자를 더 깎는다 — 엣지4 {res_4['widths']['c0']}/{res_4['widths']['c1']} vs 엣지1 {res_1['widths']['c0']}/{res_1['widths']['c1']} (→ opt 모드로 대체, ⑫)")
    res_rr, _ = run_peer(caps8b, {k: (str(i % 4 + 1),) for i, k in enumerate(ks8)})
    check("⑪-5 시작 배정(전원 엣지 1 vs 고른 시작)과 무관하게 같은 폭에 수렴", [res_rr["widths"][k] for k in ks8] == [wp[k] for k in ks8], f"고른 시작 {[res_rr['widths'][k] for k in ks8]}")
    res_cap, _ = run_peer(caps8b, {k: ("1",) for k in ks8}, dl=100.0)
    check("⑪-6 응용 상한 D 가 느슨하면(100s) 또래 기준이 그대로 작동 (고정 D 였다면 아무도 안 깎았을 것)", res_cap["widths"]["c0"] < 1, f"c0 {res_cap['widths']['c0']}")
    # ⑫ 결합 최적화(opt): min max T + λ·평균(1−w) — 기준값 없이 세 경우를 덮는다 (2026-09-09 사용자 결정, 설계기록 §12)
    def run_opt(prof_, caps_, sets0, lam, rounds=10, moves=1, mp=True):
        st_ = {"sets": sets0, "widths": {k: 1.0 for k in prof_["cpu"]}, "raise_ok": {}}
        hist = []
        for r in range(rounds):
            res_ = plan.plan(prof_, st_, caps_, ladder=(0.5, 0.75, 1.0), alpha=1.2, max_moves=moves, multipath=mp, remaining=24-r, batches=4, deadline_mode="opt", lam=lam)
            st_ = {"sets": res_["sets"], "widths": res_["widths"], "raise_ok": res_["raise_ok"], "ref_sets": res_["ref_sets"]}
            hist.append(dict(res_["widths"]))
        return res_, hist
    one_edge = {"1": 125*M}
    r_a, _ = run_opt(P11, one_edge, {k: ("1",) for k in ks8}, lam=70.0, moves=0, mp=False)
    check("⑫-1 망을 못 바꾸면(엣지 1개·이동 0) 폭만 남는다: 보통 가격(λ=70)에서 낙오자 c0·c1 만 폭 < 1", r_a["widths"]["c0"] < 1 and r_a["widths"]["c1"] < 1 and all(r_a["widths"][k] == 1.0 for k in ks8[2:]), f"{[r_a['widths'][k] for k in ks8]}")
    r_a2, _ = run_opt(P11, one_edge, {k: ("1",) for k in ks8}, lam=20.0, moves=0, mp=False)
    check("⑫-1b 망을 못 바꾸고 가격이 싸면(λ=20) 망 피해자의 폭도 내린다 — 바이트가 줄어 라운드가 주므로 (연산만·망만이 정답이 아님)", all(v < 1.0 for v in r_a2["widths"].values()) and r_a2["widths"]["c0"] <= min(r_a2["widths"][k] for k in ks8[2:]), f"{[r_a2['widths'][k] for k in ks8]}")
    P12 = {"cpu": {k: 0.40 for k in ks8}, "gamma": {k: 1.2 for k in ks8}, "bytes": {k: 8.39*M for k in ks8}, "access": {k: [50*M, 20*M] for k in ks8}}
    r_b, _ = run_opt(P12, caps8b, {k: ("1",) for k in ks8}, lam=70.0)
    check("⑫-2 연산이 정상이고 망만 막히면 폭은 안 깎고 경로만 옮긴다", all(v == 1.0 for v in r_b["widths"].values()) and len(set(r_b["sets"].values())) >= 3, f"폭 {sorted(set(r_b['widths'].values()))} 엣지 {sorted(set(''.join(v) for v in r_b['sets'].values()))}")
    r_c, hist_c = run_opt(P11, caps8b, {k: ("1",) for k in ks8}, lam=20.0)
    wc = r_c["widths"]
    check("⑫-3 둘 다 문제면 망을 옮기고(접속 병목 c2·c3 는 분할) 낙오자를 가장 깊게 내린다; 정상 4대는 전폭", wc["c0"] == 0.5 and wc["c1"] == 0.5 and all(wc[k] == 1.0 for k in ks8[4:]) and all(len(r_c["sets"][k]) == 2 for k in ("c2", "c3")) and wc["c2"] >= wc["c0"], f"{[wc[k] for k in ks8]}")
    r_m1, _ = run_opt(P11, caps8b, {k: ("1",) for k in ks8}, lam=70.0); r_m2, _ = run_opt(P11, caps8b, {k: ("1",) for k in ks8}, lam=280.0)
    check("⑫-3b 가격이 오르면 폭은 같거나 커진다 (λ 20 ≤ 70 ≤ 280 단조)", all(wc[k] <= r_m1["widths"][k] <= r_m2["widths"][k] for k in ks8), f"20:{[wc[k] for k in ks8]} 70:{[r_m1['widths'][k] for k in ks8]} 280:{[r_m2['widths'][k] for k in ks8]}")
    r_hi, _ = run_opt(P11, caps8b, {k: ("1",) for k in ks8}, lam=100000.0)
    r_lo, _ = run_opt(P11, caps8b, {k: ("1",) for k in ks8}, lam=0.0)
    check("⑫-4 가격 λ: 매우 크면 아무도 안 깎고(정확도 우선), 0 이면 이득이 있는 한 바닥까지 (라운드 우선)", all(v == 1.0 for v in r_hi["widths"].values()) and r_lo["widths"]["c0"] == 0.5 and r_lo["widths"]["c1"] == 0.5, f"λ큼 {sorted(set(r_hi['widths'].values()))} λ0 {r_lo['widths']['c0']}/{r_lo['widths']['c1']}")
    flips = sum(1 for a, b in zip(hist_c, hist_c[1:]) for k in ks8 if a[k] != b[k])
    check("⑫-5 10라운드 왕복 없음 (폭 변경 ≤ 4회)", flips <= 4, f"{flips}회")
    r_rr, _ = run_opt(P11, caps8b, {k: (str(i % 4 + 1),) for i, k in enumerate(ks8)}, lam=20.0)
    check("⑫-6 시작 배정과 무관하게 같은 폭", [r_rr["widths"][k] for k in ks8] == [wc[k] for k in ks8], f"{[r_rr['widths'][k] for k in ks8]}")
    r_1e, _ = run_opt(P11, one_edge, {k: ("1",) for k in ks8}, lam=20.0)      # 이동 가능하지만 엣지가 하나뿐 = 망 보완 불가
    r_70, _ = run_opt(P11, caps8b, {k: ("1",) for k in ks8}, lam=70.0)
    print(f"  [INFO] ⑫ λ 는 진짜 가격: 이 8대 집단(낙오자 2대 이득 4 s/라운드)에서 λ=20 → 폭 {r_c['widths']['c0']}, λ=70(가격 4.4 s) → 폭 {r_70['widths']['c0']}")
    check("⑫-7 망 보완이 가능하면(엣지 4) 낙오자의 모형 라운드가 불가능할 때(엣지 1)보다 짧다 — 폭은 같거나 덜 깎는다", r_c["makespan"] < r_1e["makespan"] and wc["c0"] >= r_1e["widths"]["c0"], f"엣지4 {r_c['makespan']:.2f}s 폭 {wc['c0']} vs 엣지1 {r_1e['makespan']:.2f}s 폭 {r_1e['widths']['c0']}")
    # ⑫-8 가격 경계의 잡음 보호: 예측 이득이 가격의 10% 안쪽이면 채택하지 않는다 (9/9 최종 1차 몰림: 4.38 vs 4.24 로 31대가 2라운드 깎였다 되돌아옴)
    P8 = {"cpu": {k: 0.4 for k in ks8}, "gamma": {k: 1.2 for k in ks8}, "bytes": {k: 8.39*M for k in ks8}, "access": {k: [50*M, 20*M] for k in ks8}}
    sets8 = {k: ("1", "1") for k in ks8}
    _, steps0, _ = plan.opt_widths(sets8, P8, {"1": 125*M}, (0.5, 0.75, 1.0), 0.0)                  # 가격 0: 첫 걸음의 이득을 읽는다
    g0, n0 = steps0[0][2], len(steps0[0][0])
    lam_edge = g0 * 8 / (0.25 * n0)                                                                   # 가격 = 이득이 되는 λ_b
    w_in, st_in, _ = plan.opt_widths(sets8, P8, {"1": 125*M}, (0.5, 0.75, 1.0), lam_edge * 0.95)    # 이득이 가격보다 5% 큼 → 불확도 안 → 안 깎음
    w_out, st_out, _ = plan.opt_widths(sets8, P8, {"1": 125*M}, (0.5, 0.75, 1.0), lam_edge * 0.85)  # 15% 큼 → 깎음
    check("⑫-8 이득이 가격의 10% 안쪽이면 폭을 안 깎고(잡음), 10% 밖이면 깎는다", not st_in and all(v == 1.0 for v in w_in.values()) and bool(st_out), f"이득 {g0:.2f} 가격 0.95배 → {len(st_in)}걸음, 0.85배 → {len(st_out)}걸음")
    # ⑬ 엣지가 막혔다는 것을 용량으로 알면(인지층 caps_effective) 계획기는 폭이 아니라 이동으로 푼다 (9/9 15:30 결함의 계획 쪽 시험)
    caps_jam = {"1": 14*M, "2": 56*M, "3": 56*M, "4": 56*M}
    P13 = {"cpu": {k: 0.8 for k in ks8}, "gamma": {k: 1.2 for k in ks8}, "bytes": {k: 8.39*M for k in ks8}, "access": {k: [5*M, 2*M] for k in ks8}}
    st13 = {"sets": {k: (("1", "1") if i < 4 else (str((i % 3) + 2), str((i % 3) + 2))) for i, k in enumerate(ks8)}, "widths": {k: 1.0 for k in ks8}, "raise_ok": {}}   # 엣지 1 에 4대(수요 28M > 14M), 엣지 2·3·4 에 나머지
    moved = 0
    for r in range(4):
        res13 = plan.plan(P13, st13, caps_jam, ladder=(0.5, 0.75, 1.0), alpha=1.2, max_moves=1, multipath=True, remaining=24-r, batches=4, deadline_mode="opt", lam=70.0)
        moved += sum(1 for k in ks8 if res13["sets"][k] != st13["sets"][k])
        st13 = {"sets": res13["sets"], "widths": res13["widths"], "raise_ok": res13["raise_ok"], "ref_sets": res13["ref_sets"]}
    on1 = sum(1 for k in ks8 if "1" in res13["sets"][k])
    check("⑬-1 엣지 1 용량이 14M 으로 관측되면 4라운드 안에 엣지 1 의 기기가 옮겨 간다 (4대 → 2대 이하)", moved >= 2 and on1 <= 2, f"이동 {moved}회, 엣지1 잔류 {on1}대, 배정 {['+'.join(res13['sets'][k]) for k in ks8]}")
    check("⑬-2 그 사이 폭은 깎지 않는다 (망 문제는 망으로)", all(v == 1.0 for v in res13["widths"].values()), f"{[res13['widths'][k] for k in ks8]}")
    # ⑬-3 분할 가중치는 정적 용량으로 — 엣지 1 이 3M 으로 관측돼도 출구 A/B 비율은 접속 상한 5:2 그대로 (막힌 엣지의 답은 이동이지 재분할이 아니다, §13-2)
    sw = plan.split_weights({"c0": ("1", "1")}, {"1": 56*M}, {"c0": [5*M, 2*M]})["c0"]
    xr_obs = plan.exit_rates({"c0": ("1", "1")}, {"1": 3*M}, {"c0": [5*M, 2*M]})["c0"]
    check("⑬-3 조각 배분 가중치는 정적 용량 기준 5:2 (관측 3M 으로 나누면 1.5:1.5 가 되어 인지 되먹임)", abs(sw[0]/sw[1] - 2.5) < 1e-6 and abs(xr_obs[0] - xr_obs[1]) < 1e-6, f"정적 {[round(v/M,2) for v in sw]} 관측 {[round(v/M,2) for v in xr_obs]}")
    # ⑭ 경로 비용 = 총합 + N·max (§9-2): 라운드를 정하는 기기를 희생하는 수를 고르지 않는다 (9/10 최종 몰림: 엣지 1(14M) 잔류 3대 65 s, c12 회선 하나 63 s 가 11라운드 라운드를 붙잡음)
    ks32 = [f"c{i}" for i in range(32)]
    P14 = {"cpu": {k: 0.8 for k in ks32}, "gamma": {k: 1.2 for k in ks32}, "bytes": {k: 8.39*M for k in ks32}, "access": {k: [5*M, 2*M] for k in ks32}}
    caps14 = {"1": 14*M, "2": 56*M, "3": 56*M, "4": 56*M}
    sets14 = {}
    for i, k in enumerate(ks32):                                   # 엣지 1 에 3대(c0·c4·c24), 엣지 2 에 9, 3·4 에 10 — 최종 몰림 R12 의 배정
        e = "1" if k in ("c0", "c4", "c24") else ("2" if i % 3 == 0 else ("3" if i % 3 == 1 else "4"))
        sets14[k] = (e, e)
    from collections import Counter as _C
    n2 = _C(v[0] for v in sets14.values())
    res14 = plan.plan(P14, {"sets": sets14, "widths": {k: 1.0 for k in ks32}, "raise_ok": {}}, caps14, ladder=(0.5, 0.75, 1.0), alpha=1.2, max_moves=3, multipath=True, remaining=12, batches=4, deadline_mode="opt", lam=70.0)
    left = [k for k in ks32 if res14["sets"][k][0] == "1"]
    single = [k for k in ks32 if len(res14["sets"][k]) == 1]
    check("⑭-1 막힌 엣지 1 의 잔류 3대(라운드를 정함)를 총합이 늘더라도 옮긴다 (총합만 쓰면 다른 10대가 조금 느려져 안 옮겼다)", len(left) < 3, f"엣지 1 잔류 {left} (시작 {sorted(n2.items())})")
    check("⑭-2 옮기면서 회선 하나만 여는 수(그 기기가 max 가 됨)는 고르지 않는다", not single, f"회선 하나 {single}")
    t14 = res14["times"]; check("⑭-3 결정 뒤 모형 라운드가 시작(엣지 1 잔류 3대)보다 짧다", max(t14.values()) < max(plan.round_times({k: 1.0 for k in ks32}, sets14, P14, caps14).values()) - 1e-6, f"{max(t14.values()):.2f}s")
    # ⑮ 망 변화 라운드에는 폭을 손대지 않는다 (§13-5): 같은 입력에서 hold_widths 면 폭은 지난 값, 이동은 그대로
    res15a = plan.plan(P14, {"sets": sets14, "widths": {k: 1.0 for k in ks32}, "raise_ok": {}}, caps14, ladder=(0.5, 0.75, 1.0), alpha=1.2, max_moves=3, multipath=True, remaining=12, batches=4, deadline_mode="opt", lam=5.0)
    res15b = plan.plan(P14, {"sets": sets14, "widths": {k: 1.0 for k in ks32}, "raise_ok": {}}, caps14, ladder=(0.5, 0.75, 1.0), alpha=1.2, max_moves=3, multipath=True, remaining=12, batches=4, deadline_mode="opt", lam=5.0, hold_widths=True)
    check("⑮-1 싼 가격(λ=5)이면 보통은 폭을 깎지만, 망 변화 라운드(hold)에는 전원 전폭 유지", any(v < 1.0 for v in res15a["widths"].values()) and all(v == 1.0 for v in res15b["widths"].values()), f"보통 {sorted(set(res15a['widths'].values()))} hold {sorted(set(res15b['widths'].values()))}")
    check("⑮-2 hold 라운드에도 이동은 한다", res15b["sets"] != sets14 and "망 변화 라운드" in res15b["why"], f"{res15b['why'][:60]}")

    # ⑯ 기기별 허용 엣지 (VM 클라 모드, 2026-09-12): c0~c3 은 엣지 3·4 만, c4~c7 은 1·2 만 — 엣지 1 이 막혀도 c4~c7 은 2 로만 가고 c0~c3 은 1·2 를 안 쓴다
    P16 = {"cpu": {k: 0.8 for k in ks8}, "gamma": {k: 1.2 for k in ks8}, "bytes": {k: 8.39*M for k in ks8}, "access": {k: [50*M, 20*M] for k in ks8},
           "allowed": {k: (["3", "4"] if i < 4 else ["1", "2"]) for i, k in enumerate(ks8)}}
    caps16 = {"1": 30*M, "2": 125*M, "3": 125*M, "4": 125*M}
    st16 = {"sets": {k: (("3", "3") if i < 4 else ("1", "1")) for i, k in enumerate(ks8)}, "widths": {k: 1.0 for k in ks8}, "raise_ok": {}}
    ok16 = True; moved16 = 0
    for r in range(4):
        res16 = plan.plan(P16, st16, caps16, ladder=(0.5, 0.75, 1.0), alpha=1.2, max_moves=3, multipath=True, remaining=20-r, batches=4, deadline_mode="opt", lam=10.0)
        moved16 += sum(1 for k in ks8 if res16["sets"][k] != st16["sets"][k])
        ok16 = ok16 and all(set(res16["sets"][k]) <= set(P16["allowed"][k]) for k in ks8)
        st16 = {"sets": res16["sets"], "widths": res16["widths"], "raise_ok": res16["raise_ok"], "ref_sets": res16["ref_sets"]}
    check("⑯ 허용 엣지 밖으로는 절대 안 옮기고(4라운드), 막힌 엣지 1 의 기기는 허용된 2 로 옮긴다", ok16 and moved16 >= 1 and any(res16["sets"][k][0] == "2" for k in ks8[4:]), f"이동 {moved16} 최종 {[''.join(res16['sets'][k]) for k in ks8]}")
    print(f"\n== {'전부 통과' if fails==0 else f'실패 {fails}건'} ==")
    return 0 if fails==0 else 1

if __name__ == "__main__":
    sys.exit(main())
