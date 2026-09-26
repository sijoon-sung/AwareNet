# -*- coding: utf-8 -*-
"""유체 시뮬레이터(fluidsim.py) 시험 — 해석해와 맞는가, 계획기와 닫힌 고리로 돌 때 왕복하지 않는가.
    python tests/test_fluidsim.py
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sfl"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import fluidsim as sim, plan  # noqa: E402

M = 1e6
fails = 0
def check(name, ok, detail=""):
    global fails; fails += 0 if ok else 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

def devs(n, cpu=0.3, mb=8.39, acc=50):
    accs = acc if isinstance(acc, (list, tuple)) else [acc] * n
    cpus = cpu if isinstance(cpu, (list, tuple)) else [cpu] * n
    return [sim.Device(f"c{i}", cpus[i], mb * M, accs[i] * M) for i in range(n)]

def main():
    caps = {"1": 60 * M, "2": 60 * M}
    # ① 혼자: 배치마다 연산 + 전송(접속 상한 50M) 직렬 — 해석해
    d = devs(1)
    per = sim.simulate_round(d, {"c0": 1.0}, {"c0": ("1",)}, caps, 4)
    exp = 4 * (0.3 + 8.39 * M * 8 / (50 * M))
    check("① 혼자: 4배치 = 4×(연산 + 바이트/접속상한)", abs(per["c0"]["total"] - exp) < 1e-6, f"{per['c0']['total']:.3f} vs {exp:.3f}")
    # ② 둘이 같은 경로: 둘 다 전송 중이면 30/30 → 정적 모형과 같아야 (동시에 시작해 동기)
    d = devs(2)
    per = sim.simulate_round(d, {k: 1.0 for k in ("c0", "c1")}, {k: ("1",) for k in ("c0", "c1")}, caps, 4)
    exp = 4 * (0.3 + 8.39 * M * 8 / (30 * M))
    check("② 동질 2대 같은 경로(동기): 정적 모형 30/30 과 일치", all(abs(per[k]["total"] - exp) < 1e-6 for k in per), f"{per['c0']['total']:.3f} vs {exp:.3f}")
    # ③ 어긋난 4대: 연산이 다르면 전송이 겹치지 않는 구간이 생겨 관측 전송시간 < 정적 모형
    d = devs(4, cpu=[0.3, 0.6, 0.9, 1.2])
    sets = {k: ("1",) for k in ("c0", "c1", "c2", "c3")}
    per = sim.simulate_round(d, {k: 1.0 for k in sets}, sets, caps, 4)
    model = plan.round_times({k: 1.0 for k in sets}, sets, sim.profile_of(d), caps)
    ok = all(per[k]["xfer"] / 4 <= (model[k] - d[i].cpu) + 1e-9 for i, k in enumerate(sets))
    check("③ 어긋난 기기들: 관측 전송시간 ≤ 정적 모형 (혼잡이 낮아짐)", ok, f"관측 {[round(per[k]['xfer']/4,2) for k in sets]} 모형 {[round(model[k]-d[i].cpu,2) for i,k in enumerate(sets)]}")
    # ④ 마이크로배치: 연산 ≈ 전송이면 겹쳐서 빨라지고, 이론 하한(max 쪽) 아래로는 못 간다
    d = [sim.Device("c0", 1.342, 8.39 * M, 50 * M)]          # 연산 1.342s = 전송 8.39MB@50M 과 같게
    t1 = sim.simulate_round(d, {"c0": 1.0}, {"c0": ("1",)}, caps, 4, micro=1)["c0"]["total"]
    t4 = sim.simulate_round(d, {"c0": 1.0}, {"c0": ("1",)}, caps, 4, micro=4)["c0"]["total"]
    lower = 4 * 1.342 + 1.342 / 4                                  # 전송이 연산 뒤에 한 조각만큼 남는다
    check("④ 마이크로배치 4: 연산≈전송이면 거의 절반, 하한(연산 합 + 조각 하나 전송) 이상", t4 < 0.6 * t1 and t4 >= lower - 1e-6, f"직렬 {t1:.2f}s → m=4 {t4:.2f}s (하한 {lower:.2f})")
    d2 = devs(1)                                                   # 망 95% 지배 (h5 계열) — 이득 작아야
    s1 = sim.simulate_round(d2, {"c0": 1.0}, {"c0": ("1",)}, caps, 4, micro=1)["c0"]["total"]
    s4 = sim.simulate_round(d2, {"c0": 1.0}, {"c0": ("1",)}, caps, 4, micro=4)["c0"]["total"]
    check("④ 망 지배(연산 18%)면 마이크로배치 이득은 그 연산 몫 안쪽(≤18%)", 0 < 1 - s4 / s1 <= 0.18 + 1e-6, f"{100*(1-s4/s1):.1f}%")
    # ⑤ 닫힌 고리 — 어젯밤 h5m5: 5대 동질, 전원 경로 1 시작. 경로만 팔이 3:2 로 수렴하고 이후 왕복하지 않는다
    d5 = devs(5, acc=47)
    H = sim.run_policy(d5, caps, "path", rounds=12, batches=4)
    tail = [h["sets"] for h in H[-6:]]
    counts = sorted([list(H[-1]["sets"].values()).count(("1",)), list(H[-1]["sets"].values()).count(("2",))])
    check("⑤ 경로만: 3:2 수렴 후 마지막 6라운드 배정 불변 (왕복 없음)", all(s == tail[0] for s in tail) and counts == [2, 3], f"이동 {sim.summarize(H)['moves']}회, 최종 {[''.join(v) for v in H[-1]['sets'].values()]}")
    U = sim.run_policy(d5, caps, "uniform", rounds=12, batches=4)
    su, sp = sim.summarize(U), sim.summarize(H)
    check("⑤ 경로만: 균등보다 총비용·라운드 모두 짧다", sp["cost"] < su["cost"] and sp["makespan"] < su["makespan"], f"총비용 {su['cost']:.1f}→{sp['cost']:.1f}s 라운드 {su['makespan']:.2f}→{sp['makespan']:.2f}s")
    # ⑥ 분할 팔은 동질 집단에서 경로만보다 나쁘지 않아야 하고(≈같음), 왕복도 없어야
    Hm = sim.run_policy(d5, caps, "mp", rounds=12, batches=4)
    sm = sim.summarize(Hm)
    check("⑥ 분할 전송(동질): 경로만과 총비용 ±5% 안 (문헌: 공유 병목에서는 이득 없음)", abs(sm["cost"] / sp["cost"] - 1) < 0.05, f"{sm['cost']:.1f} vs {sp['cost']:.1f}s, 이동 {sm['moves']}회")
    # ⑦ 결합: 연산 낙오자(6.7배) + 혼잡 — 둘다 팔이 경로만·폭만보다 라운드 시간이 짧다
    dm = devs(4, cpu=[0.3 * 6.7, 0.3, 0.3, 0.3])
    res = {p: sim.summarize(sim.run_policy(dm, caps, p, rounds=12, batches=4)) for p in ("uniform", "path", "width", "both")}
    check("⑦ 결합: 둘다 라운드 ≤ 경로만, 폭만", res["both"]["makespan"] <= res["path"]["makespan"] + 1e-9 and res["both"]["makespan"] <= res["width"]["makespan"] + 1e-9,
          " ".join(f"{p} {v['makespan']:.2f}s/{v['cost']:.1f}s" for p, v in res.items()))
    check("⑦ 폭만: 낙오자(6.7배) 폭 < 1, 정상 기기 폭 = 1", res["width"]["widths"]["c0"] < 1.0 and all(res["width"]["widths"][k] == 1.0 for k in ("c1", "c2", "c3")), f"{res['width']['widths']}")
    check("⑦ B안: 경로가 풀리면 낙오자 폭은 폭만 팔 이상 (기준선을 조이지 않는다 — 여기선 경로만으로 기준선 안에 든다)", res["both"]["widths"]["c0"] >= res["width"]["widths"]["c0"], f"둘다 {res['both']['widths']['c0']} vs 폭만 {res['width']['widths']['c0']}")
    # ⑧ 심한 낙오자(15배): 경로가 풀려도 기준선을 넘는다 → 둘다 팔이 폭도 깎아 경로만보다 라운드가 짧다 (시너지)
    dh = devs(4, cpu=[0.3 * 15, 0.3, 0.3, 0.3])
    res2 = {p: sim.summarize(sim.run_policy(dh, caps, p, rounds=12, batches=4)) for p in ("path", "width", "both")}
    check("⑧ 심한 낙오자: 둘다 라운드 < 경로만 (경로가 풀려도 폭을 깎을 만큼 느리다)", res2["both"]["makespan"] < res2["path"]["makespan"] - 1e-6 and res2["both"]["widths"]["c0"] < 1.0,
          " ".join(f"{p} {v['makespan']:.2f}s w0={v['widths']['c0']}" for p, v in res2.items()))
    # ⑨ 두 가닥(50/20) 4대: 분할 팔이 이진 팔보다 총비용·라운드 모두 짧다 (대역 집성)
    dx = [sim.Device(f"c{i}", 0.3, 8.39 * M, [50 * M, 20 * M]) for i in range(4)]
    capx = {"1": 150 * M, "2": 150 * M}                          # 접속이 병목인 자리 (경로 60/60 이면 경로가 병목이라 두 가닥 이득 0)
    rx = {p: sim.summarize(sim.run_policy(dx, capx, p, rounds=12, batches=4)) for p in ("uniform", "path", "mp")}
    check("⑨ 두 가닥: 분할 < 이진 < 균등 (총비용)", rx["mp"]["cost"] < rx["path"]["cost"] - 1e-6 < rx["uniform"]["cost"], " ".join(f"{p} {v['cost']:.1f}s/{v['makespan']:.2f}s" for p, v in rx.items()))
    check("⑨ 두 가닥: 분할 팔 이동 ≤ 6회 (왕복 없음)", rx["mp"]["moves"] <= 6, f"이동 {rx['mp']['moves']}회 최종 {['+'.join(v) for v in rx['mp']['sets'].values()]}")
    # ⑩ 배치당 오버헤드: 전송마다 oh 초가 먼저 흐른다 → 라운드가 배치 수 × oh 만큼 길어진다 (연산과 겹치지 않는 직렬 경우)
    d0 = [sim.Device("c0", 0.3, 8.39 * M, 50 * M)]; d1 = [sim.Device("c0", 0.3, 8.39 * M, 50 * M, overhead=0.4)]
    m0 = sim.simulate_round(d0, {"c0": 1.0}, {"c0": ("1",)}, {"1": 100 * M}, 4)["c0"]["total"]
    m1 = sim.simulate_round(d1, {"c0": 1.0}, {"c0": ("1",)}, {"1": 100 * M}, 4)["c0"]["total"]
    check("⑩ 오버헤드 0.4s × 4배치 = +1.6s", abs((m1 - m0) - 1.6) < 1e-6, f"{m0:.2f} → {m1:.2f}")
    print(f"\n== {'전부 통과' if fails == 0 else f'실패 {fails}건'} ==")
    return 0 if fails == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
