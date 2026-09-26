# -*- coding: utf-8 -*-
"""경로 배정 — **정확도 대가가 0인 노브.** 그래서 폭·양자화보다 먼저 쓴다.

  ── 왜 이것만 공짜인가 ──────────────────────────────────────────
  폭과 양자화는 *보내는 것을 줄여서* 시간을 산다 → 학습을 대가로 낸다 (−0.5pp / −1.2pp).
  경로는 *같은 것을 더 좋은 선으로 보낸다* → **대가가 없다.**
  그래서 순서가 정해진다: 경로 → 폭 → 양자화. 공짜인 것부터.

  ── 배분층은 죽었는데 경로는 왜 사나 ────────────────────────────
      한 회선 안: makespan ≥ 총바이트 / C
                  ★ TCP 가 가만 둬도 이 하한에 닿는다 → 개입할 틈이 없다 (사망 원인)
      경로 여럿: makespan ≥ 총바이트 / ΣC_r
                  ★ TCP 는 가만 두면 못 닿는다 — 흐름 하나는 경로 하나만 쓴다
                  → 기본 동작과 하한 사이에 **틈**이 생긴다. 그 틈이 우리 자리다

  경로 배정은 재분배가 아니라 **매칭**이다. 숫자로 보면 (경로 100M·20M, 클라 2명 각 50MB):
      둘 다 100M 에      → 50MB×2/100M         = 8초
      하나씩 나눠 태우면 → max(4초, 20초)       = 20초
  같은 자원인데 배정에 따라 2.5배. 한 회선 안에서는 이런 일이 없었다.

  ── 문제의 형태 ─────────────────────────────────────────────────
  경로 r 에 클라 집합 S_r 이 붙으면 그 경로가 끝나는 시각은 Σbytes(S_r)/C_r 이다.
  즉 **최대 경로 부하를 최소화하는 부하분산**(uniform machines makespan)이다.
  NP-난해지만 클라 ≤8·경로 ≤4 규모면 큰 것부터 넣는 탐욕(LPT)으로 충분하고,
  그 규모에서는 완전탐색으로 최적을 확인할 수도 있다.
"""
import itertools

SEARCH_LIMIT = 2_000_000       # 완전탐색 허용 조합 수 상한 — 넘으면 탐욕으로 물러난다


def path_load(assign, bytes_of, caps):
    """배정에 따른 경로별 완료 시각 {경로: 초}."""
    tot = {r: 0.0 for r in caps}
    for k, r in assign.items():
        tot[r] += bytes_of[k]
    return {r: (tot[r] * 8 / caps[r] if caps[r] > 0 else float("inf")) for r in caps}


def makespan(assign, bytes_of, caps):
    return max(path_load(assign, bytes_of, caps).values())


def assign_greedy(bytes_of, caps):
    """큰 클라부터 '넣었을 때 가장 빨리 끝나는 경로'에 넣는다 (LPT).

    균질한 경로에서는 자연히 고르게 흩어진다 — 즉 **경로가 다 같으면 아무 일도 안 한다.**
    이건 폭 노브에서 배운 원칙과 같다: 균질할 때 가만있는 것이 이질할 때 움직이는 것만큼 중요하다.
    """
    load = {r: 0.0 for r in caps}
    out = {}
    for k in sorted(bytes_of, key=lambda k: -bytes_of[k]):
        r = min(caps, key=lambda r: (load[r] + bytes_of[k]) * 8 / caps[r]
                if caps[r] > 0 else float("inf"))
        out[k] = r
        load[r] += bytes_of[k]
    return out


def assign_optimal(bytes_of, caps, limit=4 ** 8):
    """완전탐색 최적 배정. 탐색공간이 크면 None 을 돌려 탐욕으로 넘긴다.

    ★ 이건 '오라클' 이 아니라 **탐욕이 얼마나 손해인지 재는 잣대**다.
      결과 채점에 쓰면 자기채점이 되므로 알고리즘 품질 확인에만 쓴다.
    """
    ks, rs = sorted(bytes_of), sorted(caps)
    if len(rs) ** len(ks) > limit:
        return None
    best, best_ms = None, float("inf")
    for combo in itertools.product(rs, repeat=len(ks)):
        a = dict(zip(ks, combo))
        m = makespan(a, bytes_of, caps)
        if m < best_ms:
            best, best_ms = a, m
    return best


def gain(bytes_of, caps, baseline=None):
    """배정으로 얻는 이득. baseline 이 없으면 '전원 같은 경로'(TCP 기본 동작에 가장 가까움).

    반환: (탐욕 makespan, 기준 makespan, 개선율)
    """
    ks = sorted(bytes_of)
    if baseline is None:
        r0 = max(caps, key=lambda r: caps[r])       # 기본은 제일 좋은 경로 하나로 몰림
        baseline = {k: r0 for k in ks}
    g = assign_greedy(bytes_of, caps)
    mg, mb = makespan(g, bytes_of, caps), makespan(baseline, bytes_of, caps)
    return mg, mb, (1 - mg / mb) if mb > 0 else 0.0


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    MB = 1e6

    print("=== ① 문서의 예시를 재현하는가 (경로 100M·20M, 클라 2명 각 50MB) ===")
    b = {"c0": 50 * MB, "c1": 50 * MB}
    caps = {"fast": 100e6, "slow": 20e6}
    both = {"c0": "fast", "c1": "fast"}
    split = {"c0": "fast", "c1": "slow"}
    print(f"  둘 다 빠른 경로 : {makespan(both, b, caps):5.1f}초")
    print(f"  하나씩 나눠 태움: {makespan(split, b, caps):5.1f}초")
    print(f"  탐욕이 고른 것  : {assign_greedy(b, caps)} → {makespan(assign_greedy(b, caps), b, caps):.1f}초")

    print("\n=== ② 경로가 균질하면 아무 일도 안 하는가 (M4 판정) ===")
    b4 = {f"c{i}": 50 * MB for i in range(4)}
    same = {"p0": 50e6, "p1": 50e6}
    g = assign_greedy(b4, same)
    load = path_load(g, b4, same)
    print(f"  배정 {g}")
    print(f"  경로별 완료 {({r: round(v, 2) for r, v in load.items()})}  "
          f"→ {'고르게 흩어짐 ✓' if max(load.values()) - min(load.values()) < 1e-9 else '치우침 ✗'}")
    _, _, gn = gain(b4, same)
    print(f"  '전원 한 경로' 대비 개선 {gn*100:.0f}%  (균질이어도 몰아넣지 않는 것이 이득의 정체)")

    print("\n=== ③ 이질 경로에서 이득이 얼마나 나오나 ===")
    for name, caps2 in (("2경로 100/20M", {"p0": 100e6, "p1": 20e6}),
                        ("2경로 100/50M", {"p0": 100e6, "p1": 50e6}),
                        ("3경로 100/50/20M", {"p0": 100e6, "p1": 50e6, "p2": 20e6})):
        mg, mb, gn = gain(b4, caps2)
        opt = assign_optimal(b4, caps2)
        mo = makespan(opt, b4, caps2) if opt else float("nan")
        print(f"  {name:18s} 기본 {mb:6.2f}초 → 탐욕 {mg:6.2f}초 ({gn*100:4.0f}% 개선)   "
              f"최적 {mo:6.2f}초 (탐욕 손해 {(mg/mo-1)*100:4.1f}%)")

    print("\n=== ④ 클라 바이트가 다를 때 (폭이 이미 섞인 상황) ===")
    bm = {"c0": 50 * MB, "c1": 25 * MB, "c2": 12.5 * MB, "c3": 50 * MB}
    caps3 = {"p0": 100e6, "p1": 30e6}
    mg, mb, gn = gain(bm, caps3)
    opt = assign_optimal(bm, caps3)
    print(f"  바이트 {[int(v/MB) for v in bm.values()]}MB  기본 {mb:.2f}초 → 탐욕 {mg:.2f}초 "
          f"({gn*100:.0f}% 개선), 최적 {makespan(opt, bm, caps3):.2f}초")
    print(f"  탐욕 배정 {assign_greedy(bm, caps3)}")


def joint_plan(bytes1, caps, ladder=(0.25, 0.5, 0.75, 1.0), comp=0.0):
    """폭 × 경로 **공동** 완전탐색 — M2 가 실측으로 가르친 교훈의 구현.

    따로 정하면 서로의 입력을 무효화한다 (M2 FAIL, 2026-08-27):
        경로 배정의 입력(바이트)은 폭이 정하고, 폭 결정의 입력(회선)은 경로가 정한다.
    그래서 (배정, 폭벡터)를 한 문제로 푼다. 목적함수는 등록된 비(比) 목적
    (controller.py 2판과 동일): makespan / 평균폭 — 시간 이득과 학습 손실을 직접 저울질.
    N=4·경로 2 면 2^4×4^4 = 4,096 — 완전탐색으로 최적 보장.

    반환: (assign, widths, 예측 makespan, 예측 ratio)
    """
    ks = sorted(bytes1)
    if len(caps) ** len(ks) * len(ladder) ** len(ks) > SEARCH_LIMIT:
        # 완전탐색이 터지는 규모(예: 16대 = 2^16·3^16 ≈ 2.8조) — 탐욕 배정 + 전폭으로 물러난다.
        # 2026-09-06 절제 2판 16대 판이 여기서 두 시간 넘게 멈춘 사고의 방지책이다.
        assign = assign_greedy({k: bytes1[k] for k in ks}, caps)
        widths = {k: ladder[-1] for k in ks}
        ms = makespan(assign, {k: bytes1[k] * widths[k] for k in ks}, caps) + comp
        return assign, widths, ms, ms / (sum(widths.values()) / len(widths))
    best = None
    for combo_r in itertools.product(sorted(caps), repeat=len(ks)):
        for combo_p in itertools.product(ladder, repeat=len(ks)):
            load = {r: 0.0 for r in caps}
            for k, r, p in zip(ks, combo_r, combo_p):
                load[r] += bytes1[k] * p * 8 / caps[r]
            ms = max(load.values()) + comp
            avgw = sum(combo_p) / len(combo_p)
            key = (ms / avgw, ms, -avgw)
            if best is None or key < best[0]:
                best = (key, dict(zip(ks, combo_r)), dict(zip(ks, combo_p)), ms)
    _, assign, widths, ms = best
    return assign, widths, ms, ms / (sum(widths.values()) / len(widths))


def best_widths(bytes1, assign, caps, ladder=(0.25, 0.5, 0.75, 1.0), comp=0.0):
    """경로 배정을 **고정**하고 폭만 최적화 — "이대로 있을 때의 최선".

    joint_plan 과 같은 목적함수(makespan/평균폭). 온라인 판단의 히스테리시스가
    "현 배정 유지 시 최선"과 "완전탐색 최적"을 비교할 때 쓴다.

    반환: (widths, 예측 makespan)
    """
    ks = sorted(bytes1)
    if len(ladder) ** len(ks) > SEARCH_LIMIT:
        widths = {k: ladder[-1] for k in ks}                     # 큰 규모에서는 전폭 유지
        return widths, makespan(assign, {k: bytes1[k] for k in ks}, caps) + comp
    best = None
    for combo_p in itertools.product(ladder, repeat=len(ks)):
        load = {r: 0.0 for r in caps}
        for k, p in zip(ks, combo_p):
            load[assign[k]] += bytes1[k] * p * 8 / caps[assign[k]]
        ms = max(load.values()) + comp
        avgw = sum(combo_p) / len(combo_p)
        key = (ms / avgw, ms, -avgw)
        if best is None or key < best[0]:
            best = (key, dict(zip(ks, combo_p)), ms)
    return best[1], best[2]
