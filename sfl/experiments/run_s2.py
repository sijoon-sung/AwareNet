# -*- coding: utf-8 -*-
"""S2 — **낙오자 인식 조건을 규모에서 고른다.**

  S1 이 밝힌 것: 현행 마감선 D = alpha x **min**(전폭 예상시간) 은 규모에서 무너진다.
      균질한 판(전원 동일 회선·동일 기기)인데 N=4 에서 33%, **N=1024 에서 97%** 를 깎는다.
      고칠 것이 없는 판에서 학습 능력만 버리는 것이다.

  ── 왜 그런가 (통계 문제다) ─────────────────────────────────────
  N개 표본의 최솟값은 N 이 커질수록 왼쪽 꼬리로 계속 밀려난다.
  잡음 표준편차 sigma 일 때 대략  min ~ mu - sigma*sqrt(2 ln N)  이다.
      N=4    -> 1.7 sigma
      N=1024 -> 3.7 sigma
  마감선이 그걸 따라 내려가니 거의 전원이 마감선 위로 올라간다.
  **min 은 N 에 대해 수렴하지 않는 통계량**인데 그것을 기준으로 삼았다.

  ── 그런데 중앙값도 안 된다 (그래서 min 으로 바꿨었다) ──────────
  1판은 D = alpha x 중앙값이었는데 N=4 교란 실험에서 죽었다:
  환경이 나빠지자 중앙값도 같이 올라 마감선이 27->45초로 밀려 아무도 안 걸렸다.
  ★ 그런데 **그 실패도 N=4 이라서**였다. 4명 중 1명이 나빠지면 중앙값이 크게 움직인다.
    N 이 크면 낙오자 몇이 중앙값을 거의 못 움직인다.
  즉 **min 은 큰 N 에서 죽고 중앙값은 작은 N 에서 죽는다.**

  ── 그래서 무엇을 기준으로 삼아야 하나 ──────────────────────────
  요구조건 셋을 동시에 만족해야 한다:
    (A) 균질하면 **아무도 안 깎는다** — 모든 N 에서
    (B) 낙오자가 있으면 **낙오자만 깎는다** — 모든 N 에서
    (C) 환경이 나빠지면 **반응한다** (자기 무력화 없음)
  후보를 시뮬레이터에 넣고 N=4~1024 에서 셋을 다 보게 한다.

    python sfl/experiments/run_s2.py
"""
import io
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from sim import LADDER, World                      # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "out")
NS = [4, 8, 16, 32, 64, 128, 256, 512, 1024]


# ── 기준 통계량 후보 ────────────────────────────────────────────
def q(vals, f):
    v = sorted(vals)
    if len(v) == 1:
        return v[0]
    i = f * (len(v) - 1)
    lo, hi = int(math.floor(i)), int(math.ceil(i))
    return v[lo] + (v[hi] - v[lo]) * (i - lo)


REFS = {
    "min (현행)":   lambda v: min(v),
    "10분위":       lambda v: q(v, 0.10),
    "25분위":       lambda v: q(v, 0.25),
    "중앙값":       lambda v: q(v, 0.50),
    # 순위통계가 아닌 것 — N 과 무관하게 정의된다
    "기하평균":     lambda v: math.exp(sum(math.log(max(x, 1e-9)) for x in v) / len(v)),
}


class RefController:
    """현행 규칙과 같되 **기준 통계량만 갈아 끼운다.** 다른 것은 전부 동일하다."""

    def __init__(self, ks, ref, alpha=1.2, p_min=0.25, ewma=0.5):
        self.ks, self.ref, self.alpha, self.p_min, self.a = ks, ref, alpha, p_min, ewma
        self.cpu1, self.net1 = {}, {}
        self.p = {k: 1.0 for k in ks}

    def observe(self, obs, B):
        for k, d in obs.items():
            p = self.p[k]
            cpu = (d["cli_fwd"] + d["cli_bwd"]) / B / (p ** 1.2)
            net = d["xfer"] / B / p
            self.cpu1[k] = cpu if k not in self.cpu1 else \
                (1 - self.a) * self.cpu1[k] + self.a * cpu
            self.net1[k] = net if k not in self.net1 else \
                (1 - self.a) * self.net1[k] + self.a * net

    def predict(self, pv, B):
        return {k: B * (self.cpu1.get(k, 0) * pv[k] ** 1.2 + self.net1.get(k, 0) * pv[k])
                for k in self.ks}

    def decide(self, B):
        if not self.cpu1:
            return dict(self.p)
        full = {k: 1.0 for k in self.ks}
        D = self.alpha * self.ref(list(self.predict(full, B).values()))
        pv, stuck = dict(full), set()
        while True:
            T = self.predict(pv, B)
            over = {k: t for k, t in T.items() if t > D and k not in stuck}
            if not over:
                break
            k = max(over, key=over.get)
            i = LADDER.index(pv[k])
            if i == 0 or LADDER[i - 1] < self.p_min:
                stuck.add(k)
                continue
            pv[k] = LADDER[i - 1]
        for k in self.ks:                                  # 히스테리시스 한 칸
            i0, i1 = LADDER.index(self.p[k]), LADDER.index(pv[k])
            if abs(i1 - i0) > 1:
                pv[k] = LADDER[i0 + (1 if i1 > i0 else -1)]
        self.p = pv
        return dict(pv)


def run(w, ref, rounds=8, perturb_at=None):
    """perturb_at 이 주어지면 그 라운드에 클라 5% 의 회선을 1/5 로 떨어뜨린다."""
    ctl = RefController(w.ks, ref)
    pv = {k: 1.0 for k in w.ks}
    hist = []
    hurt = w.ks[:max(1, w.n // 20)]
    for r in range(rounds):
        if perturb_at is not None and r == perturb_at:
            for k in hurt:
                w.link[k] /= 5.0
        if r >= 1:
            pv = ctl.decide(w.batches)
        ms, obs, T = w.run(pv, {k: 0 for k in w.ks})
        ctl.observe(obs, w.batches)
        hist.append({"ms": ms, "mean_p": sum(pv.values()) / w.n,
                     "cut": sum(1 for v in pv.values() if v < 1.0) / w.n,
                     "hurt_p": sum(pv[k] for k in hurt) / len(hurt)})
    return hist


def main():
    print("=" * 92)
    print("  (A) 균질한 판 — 아무도 안 깎아야 한다.  좁힌 비율(%) 이 낮을수록 옳다")
    print("=" * 92)
    print(f"{'기준':>12s} " + " ".join(f"{('N='+str(n)):>7s}" for n in NS))
    tblA = {}
    for name, ref in REFS.items():
        cells = []
        for n in NS:
            v = []
            for s in (1, 2, 3):
                h = run(World(n, seed=s, dist="homogeneous"), ref)
                v.append(h[-1]["cut"])
            cells.append(sum(v) / len(v))
        tblA[name] = cells
        print(f"{name:>12s} " + " ".join(f"{c*100:6.0f}%" for c in cells))

    print("\n" + "=" * 92)
    print("  (B) 낙오자 5% 인 판 — **낙오자만** 깎아야 한다.  좁힌 비율이 5% 근처면 옳다")
    print("=" * 92)
    print(f"{'기준':>12s} " + " ".join(f"{('N='+str(n)):>7s}" for n in NS))
    tblB = {}
    for name, ref in REFS.items():
        cells = []
        for n in NS:
            v = []
            for s in (1, 2, 3):
                h = run(World(n, seed=s, dist="few_stragglers"), ref)
                v.append(h[-1]["cut"])
            cells.append(sum(v) / len(v))
        tblB[name] = cells
        print(f"{name:>12s} " + " ".join(f"{c*100:6.0f}%" for c in cells))

    print("\n" + "=" * 92)
    print("  (C) 교란 대응 — R4 에 5% 의 회선이 1/5 로 급락. **그들의 폭이 내려가야** 한다")
    print("      숫자 = 교란당한 클라의 평균 폭 (1.00 이면 반응 실패)")
    print("=" * 92)
    print(f"{'기준':>12s} " + " ".join(f"{('N='+str(n)):>7s}" for n in NS))
    tblC = {}
    for name, ref in REFS.items():
        cells = []
        for n in NS:
            v = []
            for s in (1, 2, 3):
                h = run(World(n, seed=s, dist="homogeneous"), ref, rounds=9, perturb_at=4)
                v.append(h[-1]["hurt_p"])
            cells.append(sum(v) / len(v))
        tblC[name] = cells
        print(f"{name:>12s} " + " ".join(f"{c:7.2f}" for c in cells))

    io.open(os.path.join(OUT, "s2_results.json"), "w", encoding="utf-8").write(
        json.dumps({"A_homogeneous_cut": tblA, "B_straggler_cut": tblB,
                    "C_perturb_hurt_p": tblC, "NS": NS}, indent=1))

    print("\n" + "=" * 92)
    print("  종합 판정 — 셋을 **모든 N 에서** 동시에 만족하는 기준이 있는가")
    print("=" * 92)
    for name in REFS:
        a_ok = max(tblA[name]) < 0.10                       # 균질에서 10% 미만만 깎음
        b_ok = all(0.02 <= c <= 0.30 for c in tblB[name])   # 낙오자만 (5% 근처)
        c_ok = max(tblC[name]) < 0.95                       # 교란에 반응
        mark = "✓" if (a_ok and b_ok and c_ok) else "✗"
        print(f"  {mark} {name:>12s}  (A)균질유지 {'O' if a_ok else 'X'} "
              f"(최대 {max(tblA[name])*100:3.0f}%)   "
              f"(B)낙오자만 {'O' if b_ok else 'X'} "
              f"({min(tblB[name])*100:.0f}~{max(tblB[name])*100:.0f}%)   "
              f"(C)교란반응 {'O' if c_ok else 'X'} "
              f"(폭 {max(tblC[name]):.2f})")


if __name__ == "__main__":
    main()
