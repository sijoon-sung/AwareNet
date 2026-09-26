# α · EWMA 감도 — 2단계 계획기를 합성 이질 조건(5판 후보)에서 돌려 결정이 얼마나 달라지는지 본다.
# 정확도는 말하지 않는다(시뮬). 예측 라운드 시간·폭 축소 대수·이동 횟수만.
import os, sys, random, statistics as st
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "sfl"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from controller_multi import MultiKnobController

MB = 1e6
LAD = (0.5, 0.75, 1.0)

def scenario(rng, n=4, caps=(100e6, 50e6)):
    """5판 후보: 연산 속도 U(0.1,1.0)(Aergia), 배치당 왕복 8.39MB, 경로 100/50."""
    speed = {f"c{i}": rng.uniform(0.1, 1.0) for i in range(n)}
    cpu_true = {k: 0.18 / s for k, s in speed.items()}             # 전속 0.18초/배치(2판 실측 근사)
    byt = {k: 8.39 * MB for k in speed}
    return cpu_true, byt, {str(i + 1): c for i, c in enumerate(caps)}

def true_time(assign, widths, cpu_true, byt, caps, gamma):
    load = {r: 0.0 for r in caps}
    for k in byt:
        load[assign[k]] += byt[k] * widths[k] * 8 / caps[assign[k]]
    return max(cpu_true[k] * widths[k] ** gamma[k] + load[assign[k]] for k in byt)

def run(alpha, ewma, seeds=300, rounds=12, noise=0.10):
    gains, cuts, moves, minw = [], [], [], []
    for s in range(seeds):
        rng = random.Random(s)
        cpu_true, byt, caps = scenario(rng)
        gamma = {k: rng.uniform(1.04, 1.35) for k in byt}
        c = MultiKnobController(list(byt), alpha=alpha, ewma=ewma)
        c.gamma = {k: 1.2 for k in byt}                              # 컨트롤러는 참 γ 를 모른다
        cur = {k: "1" for k in byt}; w = {k: 1.0 for k in byt}
        base = true_time(cur, {k: 1.0 for k in byt}, cpu_true, byt, caps, gamma)
        n_move = 0; tot = 0.0; ncut = 0
        for r in range(rounds):
            # 관측(잡음 ±noise) — 실제로 쓴 폭·배정 기준으로 컨트롤러에 넣는다
            for k in byt:
                p = w[k]
                cpu_obs = cpu_true[k] * p ** gamma[k] * rng.uniform(1 - noise, 1 + noise)
                c._ewma(c.cpu1, k, cpu_obs / p ** 1.2)
                c._ewma(c.bytes1, k, byt[k])
            na, nw, _, why = c.plan_two_stage(4, caps, current_assign=cur, max_moves=1, ladder=LAD, remaining=rounds - r)
            n_move += sum(na[k] != cur[k] for k in byt)
            cur, w = na, nw
            tot += true_time(cur, w, cpu_true, byt, caps, gamma)
            ncut += sum(v < 1.0 for v in w.values())
        gains.append(1 - (tot / rounds) / base)
        cuts.append(ncut / rounds); moves.append(n_move); minw.append(min(w.values()))
    return st.mean(gains) * 100, st.mean(cuts), st.mean(moves), st.mean(minw)

print(f"{'α':>5} {'ewma':>5} | 참 makespan 이득  폭축소 대수/R  이동 횟수/12R  마지막 최소폭")
for a in (1.1, 1.2, 1.3, 1.5):
    for e in (0.3, 0.5, 0.7):
        g, cu, mv, mw = run(a, e)
        print(f"{a:5.1f} {e:5.1f} | {g:+13.1f}%  {cu:12.2f}  {mv:12.2f}  {mw:12.2f}")
print("\n(동질 대조) 속도 전원 1.0:")
def run_homo(alpha):
    gains, cuts = [], []
    for s in range(100):
        rng = random.Random(s)
        byt = {f"c{i}": 8.39 * MB for i in range(4)}; cpu_true = {k: 0.18 for k in byt}
        caps = {"1": 100e6, "2": 50e6}; gamma = {k: 1.2 for k in byt}
        c = MultiKnobController(list(byt), alpha=alpha); cur = {k: "1" for k in byt}; w = {k: 1.0 for k in byt}
        base = true_time(cur, w, cpu_true, byt, caps, gamma); tot = 0; ncut = 0
        for r in range(12):
            for k in byt:
                c._ewma(c.cpu1, k, cpu_true[k] * rng.uniform(0.9, 1.1)); c._ewma(c.bytes1, k, byt[k])
            cur, w, _, _ = c.plan_two_stage(4, caps, current_assign=cur, max_moves=1, ladder=LAD, remaining=12 - r)
            tot += true_time(cur, w, cpu_true, byt, caps, gamma); ncut += sum(v < 1 for v in w.values())
        gains.append(1 - tot / 12 / base); cuts.append(ncut / 12)
    return st.mean(gains) * 100, st.mean(cuts)
for a in (1.1, 1.2, 1.5):
    g, cu = run_homo(a); print(f"  α={a}: 이득 {g:+.1f}%  폭축소 {cu:.2f}대/R  (0이어야 정상 — 동질에서 무개입)")
