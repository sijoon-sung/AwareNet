# -*- coding: utf-8 -*-
"""다중 노브 컨트롤러 시험 — **노브 선택이 병목 종류를 따라가는가.**

  세 상황을 합성해서 넣는다. 실측 로그가 아니라 합성인 이유는,
  '연산이 느린 낙오자' 를 우리가 아직 실측으로 안 만들어 봤기 때문이다
  (조건2·3은 전부 회선 낙오자였다). 합성으로 규칙의 **논리**를 먼저 검증하고,
  실측 검증은 그 상황을 실제로 만든 뒤에 한다.

    python tests/test_multiknob.py
"""
import os
import random
import statistics as st
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sfl"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from controller_multi import MultiKnobController      # noqa: E402

B = 6


def make(cpu1, net1, gamma=1.2):
    ks = list(cpu1)
    c = MultiKnobController(ks)
    c.cpu1, c.net1 = dict(cpu1), dict(net1)
    c.gamma = {k: gamma for k in ks}
    return c


CASES = [
    ("① 균질 — 좁힐 이유가 없다",
     {f"c{i}": 1.0 for i in range(4)}, {f"c{i}": 1.0 for i in range(4)},
     "전원 전폭 유지. 양자화도 안 켬"),

    ("② 망 낙오자 — c0 의 회선만 5배 느리다",
     {f"c{i}": 1.0 for i in range(4)},
     {"c0": 5.0, "c1": 1.0, "c2": 1.0, "c3": 1.0},
     "c0 만 좁힌다. 폭으로 안 되면 양자화까지"),

    ("③ 연산 낙오자 — c0 의 기기만 5배 느리다",
     {"c0": 5.0, "c1": 1.0, "c2": 1.0, "c3": 1.0},
     {f"c{i}": 1.0 for i in range(4)},
     "c0 을 좁히되 **양자화는 켜지 않는다** — 바이트를 줄여도 연산이 안 준다"),

    ("④ 극단 망 낙오자 — c0 회선이 20배 느리다",
     {f"c{i}": 1.0 for i in range(4)},
     {"c0": 20.0, "c1": 1.0, "c2": 1.0, "c3": 1.0},
     "폭 바닥까지 가고도 모자라 → 양자화가 켜져야 한다"),

    ("⑤ 극단 연산 낙오자 — c0 기기가 20배 느리다",
     {"c0": 20.0, "c1": 1.0, "c2": 1.0, "c3": 1.0},
     {f"c{i}": 1.0 for i in range(4)},
     "폭 바닥까지 가도 모자라지만 양자화는 무효 → **구제 불가**로 표시"),
]


def main():
    for title, cpu1, net1, expect in CASES:
        c = make(cpu1, net1)
        c.hyst = False                       # 한 라운드에 최종 상태를 보려고 끈다
        p, q = c.decide(B)
        ks = sorted(p)
        print(f"\n{'='*76}\n{title}\n  기대: {expect}\n{'='*76}")
        print(c.explain(B))
        T = c.predict(p, q, B)
        D = c.alpha * st.median(c.predict({k: 1.0 for k in ks}, {k: 0 for k in ks}, B).values())
        print(f"  마감선 D={D:.2f}s   결정 후 최대 {max(T.values()):.2f}s   "
              f"양자화 켠 클라 {[k for k in ks if q[k]]}   구제불가 {sorted(c.unrescuable)}")

    print(f"\n{'='*76}\n판정\n{'='*76}")
    ok = True

    # ① 균질이면 아무것도 안 건드린다
    c = make({f"c{i}": 1.0 for i in range(4)}, {f"c{i}": 1.0 for i in range(4)})
    c.hyst = False
    p, q = c.decide(B)
    a = all(v == 1.0 for v in p.values()) and not any(q.values())
    print(f"  ① 균질에서 유지          : {'PASS' if a else 'FAIL'}")
    ok &= a

    # ③ 연산 낙오자에게는 양자화를 켜지 않는다  ← 이 규칙의 핵심
    c = make({"c0": 20.0, "c1": 1.0, "c2": 1.0, "c3": 1.0},
             {f"c{i}": 1.0 for i in range(4)})
    c.hyst = False
    p, q = c.decide(B)
    b = q["c0"] == 0 and p["c0"] == 0.25 and "c0" in c.unrescuable
    print(f"  ③ 연산낙오자에 양자화 안켬: {'PASS' if b else 'FAIL'}  "
          f"(폭 {p['c0']}, 양자화 {q['c0']}, 구제불가 {'c0' in c.unrescuable})")
    ok &= b

    # ④ 망 낙오자에게는 폭 바닥 뒤 양자화를 켠다
    c = make({f"c{i}": 1.0 for i in range(4)},
             {"c0": 20.0, "c1": 1.0, "c2": 1.0, "c3": 1.0})
    c.hyst = False
    p, q = c.decide(B)
    d = q["c0"] == 8 and p["c0"] == 0.25
    print(f"  ④ 망낙오자에 양자화 켬    : {'PASS' if d else 'FAIL'}  "
          f"(폭 {p['c0']}, 양자화 {q['c0']})")
    ok &= d

    # 순서: 폭을 먼저 쓴다 (양자화가 먼저 켜지면 안 된다)
    c = make({f"c{i}": 1.0 for i in range(4)},
             {"c0": 2.0, "c1": 1.0, "c2": 1.0, "c3": 1.0})
    c.hyst = False
    p, q = c.decide(B)
    e = (p["c0"] < 1.0 and q["c0"] == 0) or all(v == 1.0 for v in p.values())
    print(f"  ⑤ 가벼운 낙오자엔 폭만    : {'PASS' if e else 'FAIL'}  "
          f"(폭 {p['c0']}, 양자화 {q['c0']}) — 폭이 정확도 대가가 더 싸다")
    ok &= e

    # ── 앵커 시험 (3판: 마감선 D = alpha·중앙값) ──────────────────────
    # min(2판)이 무너지던 지점과 중앙값(1판)이 무력화된다던 지점을 둘 다 짚는다.

    # ⑥ 균질 + 잡음 + 대규모 — 좁힐 게 없는 판에서 규모가 커져도 안 깎아야 한다.
    #    min 앵커는 여기서 무너졌다 (S1: N=1024 에서 97%). 잡음은 gauss(0, 8%).
    rng = random.Random(7)
    N = 256
    jit = lambda: max(0.7, min(1.3, 1.0 + rng.gauss(0.0, 0.08)))
    cpu1 = {f"c{i}": jit() for i in range(N)}
    net1 = {f"c{i}": jit() for i in range(N)}
    c = make(cpu1, net1)
    c.hyst = False
    p, q = c.decide(B)
    Tfull = c.predict({k: 1.0 for k in p}, {k: 0 for k in p}, B)
    narrowed = sum(1 for v in p.values() if v < 1.0) / N
    Dmin = c.alpha * min(Tfull.values())
    would_min = sum(1 for t in Tfull.values() if t > Dmin) / N
    f = narrowed <= 0.05 and would_min >= 0.15
    print(f"  ⑥ 균질·잡음 N={N} 유지    : {'PASS' if f else 'FAIL'}  "
          f"(중앙값 앵커 좁힘 {narrowed*100:.0f}% / min 앵커였다면 {would_min*100:.0f}% — "
          f"min 은 N 과 함께 꼬리로 밀린다, S1 참조)")
    ok &= f

    # ⑦ 최속자 몰락 (S3-E, 조건3의 실제 모양) — 몰락한 그 한 명만 잡아야 한다.
    #    "환경이 나빠지면 중앙값 마감선이 밀려 무력화"라던 옛 주장이 틀렸음을 확인.
    c = make({f"c{i}": 1.0 for i in range(4)},
             {"c0": 5.0, "c1": 1.0, "c2": 1.0, "c3": 1.0})   # c0 가 몰락한 뒤의 판
    c.hyst = False
    p, q = c.decide(B)
    g = p["c0"] < 1.0 and all(p[k] == 1.0 for k in ("c1", "c2", "c3"))
    print(f"  ⑦ 최속자 몰락 추적        : {'PASS' if g else 'FAIL'}  "
          f"(c0 폭 {p['c0']}, 나머지 {[p[k] for k in ('c1','c2','c3')]})")
    ok &= g

    # ⑧ 전원 악화 (S3-D) — 낙오자가 없으므로 아무도 안 깎는 게 옳다.
    #    (전원 축소가 이득인지는 별개 질문이고 R6/TTA 가 답한다)
    c = make({f"c{i}": 2.0 for i in range(4)}, {f"c{i}": 2.0 for i in range(4)})
    c.hyst = False
    p, q = c.decide(B)
    h = all(v == 1.0 for v in p.values()) and not any(q.values())
    print(f"  ⑧ 전원 악화에 무반응      : {'PASS' if h else 'FAIL'}  "
          f"— 상대 낙오자가 없으면 마감선도 같이 이동하는 것이 등록된 정책")
    ok &= h

    print(f"\n  ── {'전부 통과' if ok else '★ 실패 있음'} ──")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
