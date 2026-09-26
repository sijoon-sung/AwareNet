# -*- coding: utf-8 -*-
"""S3 — **중앙값을 버린 근거가 옳았나.** 자기 무력화 시나리오를 직접 시험한다.

  S2 가 밝힌 것: 중앙값·기하평균이 (A)균질유지 (B)낙오자만 (C)교란반응 을
  **N=4~1024 전 구간에서** 통과한다. 현행 min 은 균질한 판에서 96% 를 깎는다.

  그런데 우리는 중앙값을 버렸다. 기록된 사유는 이렇다:
      "환경이 나빠지면 중앙값도 같이 올라가 마감선이 27->45초로 밀려
       아무도 낙오자가 되지 않았다 (자기 무력화)"
  그래서 min 으로 바꿨고, 그 결과가 대규모 붕괴다.

  ★ 그 사유를 다시 검증해야 하는 이유가 둘이다.
    1. 그 실험의 로그는 **CPU 스레드 과다구독** 아래에서 만들어졌다(오늘 확인).
       측정이 42배까지 부풀던 상태다.
    2. 산술적으로 이상하다. 조건3 은 c3 한 명(4명 중 1명)의 회선이 떨어진 것이다.
       정렬된 4개에서 한 개가 커져도 **중앙값(2·3번째)은 안 움직여야** 한다.

  그래서 자기 무력화가 진짜 나는 시나리오를 **직접 만들어** 시험한다:

    (D) 전원 악화   — 모두의 회선이 절반으로. 낙오자가 없으므로 **아무도 안 깎는 게 옳다**
                      (전원 축소가 옳은지는 별개 문제이고 E9 가 답한다)
    (E) 최속자 몰락 — 조건3 의 실제 모양. **가장 빠르던 클라**가 낙오자가 된다
    (F) 점진 악화   — 낙오자가 5% -> 50% 로 서서히 늘어난다. 어디서 규칙이 항복하나
    (G) 낙오자 과반 — 낙오자가 60% 다. 이때 '낙오자' 라는 말이 성립하나

    python sfl/experiments/run_s3.py
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from run_s2 import REFS, RefController                    # noqa: E402
from sim import World                                     # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "out")
NS = [4, 16, 64, 256, 1024]


def drive(w, ref, rounds, hook):
    """hook(round, world) 가 매 라운드 시작에 세계를 바꾼다."""
    ctl = RefController(w.ks, ref)
    pv = {k: 1.0 for k in w.ks}
    hist = []
    for r in range(rounds):
        hook(r, w)
        if r >= 1:
            pv = ctl.decide(w.batches)
        ms, obs, T = w.run(pv, {k: 0 for k in w.ks})
        ctl.observe(obs, w.batches)
        hist.append({"r": r, "ms": ms, "mean_p": sum(pv.values()) / w.n,
                     "cut": sum(1 for v in pv.values() if v < 1.0) / w.n, "pv": dict(pv)})
    return hist


def scen_all_degrade(frac_at=4, factor=2.0):
    def h(r, w):
        if r == frac_at:
            for k in w.ks:
                w.link[k] /= factor
    return h


def scen_fastest_falls(frac_at=4, factor=5.0):
    """조건3 의 실제 모양 — **가장 빠르던 클라**가 낙오자가 된다."""
    def h(r, w):
        if r == frac_at:
            k = max(w.ks, key=lambda k: w.link[k])
            w.link[k] /= factor
    return h


def scen_creep(start=2, factor=5.0):
    """낙오자가 라운드마다 늘어난다 (5% -> 50%)."""
    def h(r, w):
        if r >= start:
            n_hurt = int(w.n * 0.05 * (r - start + 1))
            for k in w.ks[:min(n_hurt, w.n // 2)]:
                if w.link[k] > 2e6:
                    w.link[k] = w.link[k] / factor if r == start else w.link[k]
            for k in w.ks[:min(n_hurt, w.n // 2)]:
                w.link[k] = min(w.link[k], 20e6 / factor)
    return h


def scen_majority_slow(factor=5.0):
    """낙오자가 60% — '낙오자' 라는 말이 성립하나."""
    def h(r, w):
        if r == 0:
            for k in w.ks[:int(w.n * 0.6)]:
                w.link[k] /= factor
    return h


SCEN = [
    ("(D) 전원 악화 (모두 회선 1/2)", scen_all_degrade(), 9,
     "낙오자가 없다 → **아무도 안 깎는 것이 옳다**. 깎으면 자기 무력화가 아니라 과잉반응"),
    ("(E) 최속자 몰락 (조건3의 실제 모양)", scen_fastest_falls(), 9,
     "그 한 명만 깎아야 한다. 못 잡으면 **이것이 중앙값을 버린 그 실패**다"),
    ("(F) 낙오자 과반 (60%)", scen_majority_slow(), 8,
     "과반이 느리면 '낙오자'가 아니라 그게 정상이다. 소수(빠른 40%)를 기준으로 삼으면 안 된다"),
]


def main():
    all_out = {}
    for title, hook, rounds, expect in SCEN:
        print("\n" + "=" * 96)
        print(f"  {title}")
        print(f"  기대: {expect}")
        print("=" * 96)
        print(f"{'기준':>12s} " + " ".join(f"{('N='+str(n)):>9s}" for n in NS)
              + "     (숫자 = 교란 후 좁힌 비율)")
        tbl = {}
        for name, ref in REFS.items():
            cells = []
            for n in NS:
                v = []
                for s in (1, 2, 3):
                    w = World(n, seed=s, dist="homogeneous")
                    h = drive(w, ref, rounds, hook)
                    v.append(h[-1]["cut"])
                cells.append(sum(v) / len(v))
            tbl[name] = cells
            print(f"{name:>12s} " + " ".join(f"{c*100:8.0f}%" for c in cells))
        all_out[title] = tbl

    io.open(os.path.join(OUT, "s3_results.json"), "w", encoding="utf-8").write(
        json.dumps(all_out, indent=1))

    print("\n" + "=" * 96)
    print("  판정")
    print("=" * 96)
    d = all_out[SCEN[0][0]]
    e = all_out[SCEN[1][0]]
    f = all_out[SCEN[2][0]]
    print("\n  (D) 전원 악화 — 아무도 안 깎아야 (낮을수록 옳다)")
    for nm in REFS:
        print(f"      {nm:>12s}  최대 {max(d[nm])*100:3.0f}%   "
              f"{'✓' if max(d[nm]) < 0.10 else '✗ 과잉반응'}")
    print("\n  (E) 최속자 몰락 — 그 한 명만 (N 이 크면 비율은 0%에 가깝게 나온다)")
    for nm in REFS:
        got = e[nm][0]        # N=4 에서 1/4 = 25% 면 정확히 한 명
        print(f"      {nm:>12s}  N=4 에서 {got*100:3.0f}%  "
              f"{'✓ 한 명 잡음' if 0.2 <= got <= 0.5 else ('✗ 못 잡음' if got < 0.2 else '✗ 과잉')}"
              f"   N=1024 에서 {e[nm][-1]*100:3.0f}%")
    print("\n  (F) 낙오자 60% — 과반이 느린 것은 '정상'이다. 전원을 깎으면 안 된다")
    for nm in REFS:
        print(f"      {nm:>12s}  최대 {max(f[nm])*100:3.0f}%   "
              f"{'✓' if max(f[nm]) < 0.70 else '✗ 사실상 전원'}")

    print("\n  ── 셋을 다 통과하는 기준 ──")
    for nm in REFS:
        ok = (max(d[nm]) < 0.10 and 0.2 <= e[nm][0] <= 0.5 and max(f[nm]) < 0.70)
        print(f"      {'✓' if ok else '✗'}  {nm}")


if __name__ == "__main__":
    main()
