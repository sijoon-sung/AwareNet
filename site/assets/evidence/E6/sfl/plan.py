# -*- coding: utf-8 -*-
"""계획 — 순수 함수. 프로파일(인지)과 상태를 받아 폭 w_k 와 열린 경로 집합 S_k 를 낸다.
소켓·tc 를 모른다. 설계: docs/04_설계기록/정식화_결합_시스템.md.

  water_fill(open_sets, bytes, caps, access)   경로별 균등 몫 + 접속 상한 → 기기별 실효 전송률 (고정점)
  efficiency(prof, caps, observed)              관측 ÷ 모형 = 기기별 효율 계수 (혼잡과 무관한 보정)
  round_times(...)                              t_k = C_k w^γ + eff_k · B_k w / Σ rate
  plan(profile, state, caps, ladder, alpha, ...)  (P) 총비용 최소 열린 집합 → (W) 기준선 폭 → (P) 재평가

관측을 어떻게 쓰나 (2026-09-07 새벽 실험이 가르쳐 준 것)
  이전 판은 "그 자리에 남는 기기"의 예상 시간을 max(모형, 관측) 으로 바닥을 깔았다. 그런데 관측은 그때의
  혼잡(경로에 4대)에서 잰 값이라, 사람이 줄어든 지금(2대)의 모형보다 훨씬 크다. 남는 기기만 무거워 보이고
  옮기는 기기는 순수 모형이라 가벼워 보여 → 매 라운드 한 대씩 3:2 ↔ 2:3 을 왔다 갔다 했다 (h5m5 시드 1).
  지금은 관측을 **그때의 배정으로 계산한 모형과 비교해 효율 계수 eff_k = 관측/모형** 으로 만들고, 어느 후보를
  평가하든 같은 계수를 곱한다. 혼잡이 바뀌어도 계수는 그대로라 후보 비교가 공정하다.
"""
import itertools
import statistics

MEAS_UNCERT = 0.10       # 계측 불확도 — 이보다 작은 예측 이득은 채택하지 않는다 (K8s HPA tolerance 와 같은 값, 실측 CV 8~13%)
WATER_ITERS = 30


# ── 물 채우기 ───────────────────────────────────────────────
def n_exits(access, k):
    """기기 k 의 출구(접속 회선) 수. access[k] 가 목록이면 두 가닥, 숫자/없음이면 한 가닥(출구 2개가 한 회선을 나눔)."""
    a = (access or {}).get(k)
    return len(a) if isinstance(a, (list, tuple)) else 2


def water_fill(open_sets, caps, access=None, iters=WATER_ITERS):
    """기기별 경로별 실효 전송률 rate[k][r] (bit/s).

    열린 집합 S_k 는 **출구별 경로** 튜플이다: S_k[e] = 출구 e 가 붙은 경로. ("1",) 출구 A 만 경로 1 /
    ("1","2") A→1, B→2 / ("2","1") A→2, B→1 / ("1","1") 두 출구 다 경로 1 (흐름 2개 = 몫 2개).
    접속 회선 모형 두 가지 (2026-09-07 사용자 결정: 두 가닥으로 간다):
      access[k] = [a_A, a_B]  두 가닥 — 출구마다 자기 상한 (유선+무선, 또는 그냥 경로 2개)
      access[k] = a           한 가닥 — 두 출구가 상한 a 를 **합쳐서** 쓴다 (구 모형, 시험·비교용)
    규칙: 경로 r 의 용량 c_r 을 r 에 붙은 흐름들이 균등하게 나눈다. 상한에 닿은 흐름이 남긴 용량은 나머지가 다시 나눈다. 고정점 반복.
    """
    access = access or {}
    flows = []                                                   # (k, e, r)
    for k, S in open_sets.items():
        for e, r in enumerate(S):
            if r is not None:
                flows.append((k, e, r))
    users = {r: [(k, e) for (k, e, rr) in flows if rr == r] for r in caps}
    frate = {(k, e): 0.0 for (k, e, r) in flows}
    def cap_of(k, e):
        a = access.get(k)
        if isinstance(a, (list, tuple)):
            return a[e] if e < len(a) else 0.0
        return float("inf")                                      # 한 가닥은 기기 합으로 제한
    def joint(k):
        a = access.get(k)
        return None if isinstance(a, (list, tuple)) or a is None else a
    for _ in range(iters):
        changed = False
        for r, fl in users.items():
            if not fl:
                continue
            left, active = caps[r], list(fl)
            head = {}
            for (k, e) in fl:
                h = cap_of(k, e)
                j = joint(k)
                if j is not None:                                # 한 가닥: 다른 흐름이 이미 쓰는 몫을 뺀 여유
                    h = min(h, j - sum(v for (kk, ee), v in frate.items() if kk == k and (kk, ee) != (k, e)))
                head[(k, e)] = max(0.0, h)
            new = {f: 0.0 for f in fl}
            while active and left > 1e-9:
                eq = left / len(active)
                capped = [f for f in active if head[f] <= eq]
                if not capped:
                    for f in active:
                        new[f] = eq
                    break
                for f in capped:
                    new[f] = head[f]; left -= new[f]; active.remove(f)
            for f in fl:
                if abs(new[f] - frate[f]) > 1e-6 * max(1.0, caps[r]):
                    changed = True
                frate[f] = new[f]
        if not changed:
            break
    rate = {k: {} for k in open_sets}
    for (k, e, r) in flows:
        rate[k][r] = rate[k].get(r, 0.0) + frate[(k, e)]
    water_fill.last_flows = frate                                 # 출구별 (exit_rates 가 읽는다)
    return rate


def exit_rates(open_sets, caps, access=None):
    """기기별 **출구별** 예상 전송률 {k: [bit/s, ...]} (출구 순서 = S_k 순서). 분할 전송의 조각 배분 가중치가 된다.
    조각 단위 실측(보낸 시간)은 페이로드가 소켓 버퍼보다 작으면 못 믿으므로(2026-09-07), 비율은 여기서 온다."""
    water_fill(open_sets, caps, access)
    fr = water_fill.last_flows
    return {k: [fr.get((k, e), 0.0) for e in range(len(S))] for k, S in open_sets.items()}


def split_weights(open_sets, static_caps, access=None):
    """조각 배분 가중치 = 정적 용량에서의 출구별 예상 속도. 관측 용량(caps_effective)은 **이동 판단에만** 쓰고 분할에는 쓰지 않는다 —
    막힌 엣지 위에서 분할을 바꾸면 인지층이 그 결과를 포화와 구분할 수 없다 (설계기록 §13-2, test_plan2 ⑬-3)."""
    return exit_rates(open_sets, static_caps, access)


def effective_rate(open_sets, caps, access=None):
    r = water_fill(open_sets, caps, access)
    return {k: sum(v.values()) for k, v in r.items()}


# ── 시간 모형 ──────────────────────────────────────────────
EFF_CLIP = (0.5, 4.0)
RESID_MAX = 10.0         # 가산 잔차 상한(초/배치) — 넘으면 계측 사고    # 효율 계수 허용 범위 — 밖이면 계측 사고로 보고 자른다


def efficiency(prof, caps, observed, current_sets=None):
    """관측 → 기기별 효율 계수 {k: eff}.  eff = 관측 전송시간 / 그때 배정으로 계산한 모형 전송시간 (전폭 기준).

    observed 의 두 꼴을 받는다:
      새 꼴  {k: [{"net": 배치당 초(전폭), "sets": {모든 기기: 열린 집합}}, ...]}  ← sense.Sensor.observed()
      옛 꼴  {k: 배치당 초}  — 지금 배정(current_sets)에서 잰 것으로 본다 (시험·호환용)
    항목이 여럿이면 중앙값. 관측이 없는 기기는 1.0."""
    eff = {}
    if not observed:
        return eff
    for k, v in observed.items():
        entries = v if isinstance(v, (list, tuple)) else [{"net": v, "sets": current_sets}]
        vals = []
        for e in entries:
            sets = e.get("sets") or current_sets
            if not sets or k not in sets or not prof["bytes"].get(k):
                continue
            rate = effective_rate(sets, caps, prof.get("access")).get(k, 0.0)
            if rate <= 0:
                continue
            model = prof["bytes"][k] * 8 / rate
            vals.append(min(max(e["net"] / model, EFF_CLIP[0]), EFF_CLIP[1]))
        if vals:
            eff[k] = statistics.median(vals)
    return eff


def residual(prof, caps, observed):
    """관측 → 기기별 가산 잔차 {k: 초/배치}: 그 폭·그 배정의 모형 전송시간과 실측의 차이 중앙값 (≥0).
    효율 계수(곱)는 폭을 줄이면 배치당 고정 오버헤드(왕복·회신·조각 협상)가 '바이트당 비효율'로 보여 폭이 바닥에 고착된다
    (3번 1차 실행 2026-09-08: 정상 기기 8대 전부 0.5). 가산 잔차는 폭과 무관하다. 고정 목표(fixed) 폭 판단에만 쓴다."""
    out = {}
    for k, v in (observed or {}).items():
        vals = []
        for e in (v if isinstance(v, (list, tuple)) else []):
            if "raw" not in e or not e.get("sets") or k not in e["sets"] or not prof["bytes"].get(k):
                continue
            rate = effective_rate(e["sets"], caps, prof.get("access")).get(k, 0.0)
            if rate <= 0:
                continue
            vals.append(min(max(e["raw"] - prof["bytes"][k] * e.get("w", 1.0) * 8 / rate, -RESID_MAX / 5), RESID_MAX))   # 음수 허용: 내리기가 모형보다 빠른 리그
        if vals:
            out[k] = statistics.median(vals)
    return out


def observed_round(observed):
    """관측 → 기기별 최근 라운드 총시간 중앙값 {k: 초} (관측 보호용)."""
    out = {}
    for k, v in (observed or {}).items():
        t = [e["tot"] for e in (v if isinstance(v, (list, tuple)) else []) if e.get("tot")]
        if t:
            out[k] = statistics.median(t)
    return out


def round_times(widths, open_sets, prof, caps, eff=None, current_sets=None, switch_cost=0.0, batches=1):
    """기기별 배치당 예상 시간 {k: t}. prof: {"cpu": {k}, "gamma": {k}, "bytes": {k}, "access": {k}}.
    eff: efficiency() 의 효율 계수 — 후보가 무엇이든 같은 계수를 곱한다 (공정 비교).
    switch_cost: 집합이 바뀐 기기에 라운드당 추가 (초/배치로 환산 = δ/batches)."""
    rate = effective_rate(open_sets, caps, prof.get("access"))
    eff = eff or {}
    t = {}
    for k in widths:
        w = widths[k]
        g = prof.get("gamma", {}).get(k, 1.2)
        comp = prof["cpu"].get(k, 0.0) * (w ** g)
        b = prof["bytes"].get(k, 0.0) * w
        net = b * 8 / rate[k] * eff.get(k, 1.0) if rate.get(k, 0) > 0 else float("inf")
        if current_sets and tuple(open_sets[k]) != tuple(current_sets[k]) and switch_cost:
            net += switch_cost / max(1, batches)
        t[k] = comp + net
    return t


def total_cost(t):
    """경로 단계의 비용 = **라운드(가장 느린 기기) + 기기 평균**. 2026-09-06 §9-1 의 "총합"은 망 손잡이 실험(라운드가 안 변하는 조건)에서 기기→서버 총 비용을 보려던 것이고,
    결합 최적화(§12)의 목적은 라운드(max)다. 총합만 쓰면 한 기기를 희생해 여럿을 조금씩 살리는 수를 고른다 — 9/10 최종 몰림 장면: c12 를 회선 하나(4)로 보내 63 s 로 만들고
    엣지 1 에 3대를 남겨 라운드가 R12~22 내내 65 s(정상 47) 였다. 비용 = 총합 + N·max — 총합의 "공짜 손잡이"(test ⑤) 는 그대로, 라운드를 정하는 기기의 1초는 N 초 값이라 희생되지 않는다(§9-2)."""
    v = list(t.values())
    return sum(v) + len(v) * max(v)          # = N·(평균 + 라운드): 공짜 손잡이(한 기기만 빨라짐)는 총합으로 그대로 잡히고, 라운드를 정하는 기기의 1초는 N초 값


# ── (P) 열린 경로 집합 ─────────────────────────────────────
def candidate_sets(paths, multipath, min_chunks_ok=True, two_links=False):
    """기기 하나가 고를 수 있는 열린 집합(출구별 경로 튜플).
    한 가닥: {(1,), (2,)} + multipath 면 (1,2) (두 출구가 한 회선을 나눠 두 경로로).
    두 가닥: 출구 A 만 {(p,)} + multipath 면 (A,B) 의 모든 순서쌍 — 경로 2개면 4개, 4개면 16개. (2026-09-08: 경로 4개에서 "전부 열기" 4출구 집합을 내던 버그 수정)"""
    single = [(r,) for r in paths]
    if multipath and min_chunks_ok and len(paths) >= 2 and two_links:
        single = []                     # 두 가닥 기기는 회선 하나만 여는 배정을 후보에서 뺀다 (2026-09-10 §9-2): 자기 시간만 길어지고(5M 로 63 s) 남들 몫을 덜 뺏는 것뿐이라
                                        # 총합에는 유리해 보여도 라운드(max)를 붙잡는다 — 최종 몰림 장면 c12. 두 번째 가닥은 그 기기 고유의 용량이라 비워 둘 이유가 없다.
    if not (multipath and min_chunks_ok and len(paths) >= 2):
        return single
    if two_links:
        return single + [(p, q) for p in paths for q in paths]   # 출구는 2개 — 경로가 몇 개든 (A→p, B→q) 순서쌍 (경로 4개면 16개)
    return single + [tuple(paths)] if len(paths) == 2 else single + [(p, q) for i, p in enumerate(paths) for q in paths[i + 1:]]


def best_sets(widths, prof, caps, current_sets, multipath=False, eff=None, limit=20000):
    """총 비용을 최소화하는 열린 집합 배정. 후보 수가 limit 이하면 완전 열거, 아니면 탐욕(큰 기기부터)."""
    ks = sorted(widths)
    paths = sorted(caps)
    acc = prof.get("access") or {}
    allowed = prof.get("allowed") or {}                          # 기기별 허용 경로 (VM 클라 모드: 다른 VM 의 엣지만, 2026-09-12). 없으면 전부
    cands = {k: candidate_sets([p for p in paths if p in allowed.get(k, paths)], multipath, prof["bytes"].get(k, 0) * widths[k] >= 2 * (1 << 20),
                               isinstance(acc.get(k), (list, tuple))) for k in ks}
    n_combo = 1
    for k in ks:
        n_combo *= len(cands[k])
    if n_combo <= limit:
        best = None
        for combo in itertools.product(*[cands[k] for k in ks]):
            S = dict(zip(ks, combo))
            c = total_cost(round_times(widths, S, prof, caps, eff, current_sets))
            if best is None or c < best[0] - 1e-9:
                best = (c, S)
        return best[1], best[0]
    # 탐욕: 큰 기기부터, 그 기기 하나의 후보 중 총 비용 최소
    S = {k: tuple(current_sets[k]) for k in ks}
    for k in sorted(ks, key=lambda k: -prof["bytes"].get(k, 0) * widths[k]):
        bestc = None
        for cand in cands[k]:
            trial = dict(S); trial[k] = cand
            c = total_cost(round_times(widths, trial, prof, caps, eff, current_sets))
            if bestc is None or c < bestc[0] - 1e-9:
                bestc = (c, cand)
        S[k] = bestc[1]
    return S, total_cost(round_times(widths, S, prof, caps, eff, current_sets))


def path_stage(widths, prof, caps, current_sets, max_moves=1, multipath=False, eff=None,
               remaining=None, switch_cost=0.0, batches=1):
    """(P) 이동은 총비용 이득이 문턱을 넘을 때만, 라운드당 max_moves 대.
    문턱 = 계측 불확도(10%) × **옮기는 기기들 자신의 현재 시간** + δ/남은 배치.
    (총비용 전체의 10% 로 두면 기기 수가 늘수록 문턱이 커져 공짜 손잡이를 놓치고 폭을 깎게 된다 — test_plan2 ⑤)

    한 라운드에 한 대만 옮길 수 있으면 **모든 (기기, 후보 집합) 한 수**를 다 놓아 보고 총비용이 가장 낮은 수를 고른다.
    이전 판은 전역 최적해에 나온 목적지만 한 수 후보로 삼아서, 최적해가 분할을 품고 있으면 "통째로 옮기기"(더 싼 수)를
    아예 보지 못했다 (h5m5 mp 시드 1: 경로 2가 비었는데 c2 를 1+2 로 분할부터 함 — 총비용 99s, 통째 이동은 81s)."""
    cur = {k: tuple(current_sets[k]) for k in widths}
    t_stay = round_times(widths, cur, prof, caps, eff, cur)
    C_stay = total_cost(t_stay)
    if max_moves <= 0:
        return cur, "경로 고정"
    horizon = max(1, remaining or 1) * max(1, batches)
    dsw = switch_cost / horizon if switch_cost else 0.0

    def thresh(ks):
        return MEAS_UNCERT * sum(t_stay[k] for k in ks) + dsw * len(ks)

    cand, C_cand = best_sets(widths, prof, caps, cur, multipath, eff)
    moved = [k for k in widths if tuple(cand[k]) != tuple(cur[k])]
    if not moved:
        return cur, "경로 유지"
    if len(moved) <= max_moves:
        if C_stay - C_cand <= thresh(moved):
            return cur, "경로 유지"
        return cand, f"경로 변경 {len(moved)}대"
    # 이동 상한을 넘으면: 한 수(기기 하나 × 후보 집합 하나)를 전부 놓아 보고 최선의 한 수. max_moves>1 이면 탐욕 반복.
    paths = sorted(caps)
    allowed = prof.get("allowed") or {}
    S, why = dict(cur), []
    for _ in range(max_moves):
        best = None
        for k in widths:
            for c_set in candidate_sets([p for p in paths if p in allowed.get(k, paths)], multipath, prof["bytes"].get(k, 0) * widths[k] >= 2 * (1 << 20),
                                        isinstance((prof.get("access") or {}).get(k), (list, tuple))):
                if tuple(c_set) == tuple(S[k]):
                    continue
                trial = dict(S); trial[k] = c_set
                c = total_cost(round_times(widths, trial, prof, caps, eff, cur))
                if best is None or c < best[0] - 1e-9:
                    best = (c, trial, k)
        C_now = total_cost(round_times(widths, S, prof, caps, eff, cur))
        if best is None or C_now - best[0] <= thresh([best[2]]):
            break
        S, k = best[1], best[2]
        why.append(f"{k}→{'+'.join(S[k])}")
    if not why:
        return cur, "경로 유지 (한 수 이동은 문턱 미달)"
    return S, f"경로 변경 {len(why)}대({', '.join(why)})"


# ── (W) 폭 ─────────────────────────────────────────────────
def deadline(open_sets, prof, caps, alpha, eff=None, ref_sets=None, mode="anchored", deadline_s=None):
    """기준선 D.
    anchored (B안, 기본, 2026-09-07 사용자 결정): 기준선은 **시작 상태(ref_sets: 전원 기본 경로)** 의 전폭 시간 중앙값에서 잡는다.
        우리가 경로를 옮겨 남들이 빨라진 것으로는 기준선을 조이지 않는다 → 경로가 풀리면 폭은 커지기만 한다(정확도 우선).
        망이 나빠지면(관측이 느려지면) 기준선은 늦춰진다 — 관측은 ref 경로에 그대로 있는 기기에만 적용.
    relative (A안, 비교용): 지금 배정의 전폭 시간 중앙값. 남들이 빨라지면 연산 낙오자를 더 깎는다(라운드 우선).
    fixed (고정 목표, 3번 결합 실험, 2026-09-08 사용자 결정): D = deadline_s 초 — 응용이 정한 라운드 목표(FedCS 식 마감). 팔마다 같은 D 를
        맞추기 위해 폭을 얼마나 깎는지를 비교한다("망을 고치면 폭을 덜 깎아도 된다"). 폭 판단은 경로 교정이 끝난 목표 배정(goal_sets) 기준 —
        이동이 1대/라운드라 아직 못 옮긴 기기의 폭을 잠깐 깎았다 되돌리는 왕복을 막는다.
    opt (결합 최적화, 2026-09-09 사용자 결정): min max_k T_k(w,s) + λ·(1/N)Σ(1−w_k). 경로 단계(총비용 최소)로 s 를 정하고, 목표 배정에서
        opt_widths() 가 가장 느린 기기부터 가격 λ 를 넘는 이득이 있을 때만 폭을 내린다. λ(초/평균폭 1) 는 --lam. deadline_s 는 선택 제약.
    peer (또래 기준, 2026-09-09 사용자 결정 — "연산·네트워크 기준을 따로 세우고, 네트워크로 보완할 수 있으면 연산을 덜 줄인다"):
        ① 연산 기준: compute_stragglers() 로 후보만 고른다. ② 네트워크 보완: 후보에게 목표 배정(경로·분할 교정 뒤)의 망 시간을 준다.
        ③ 후보의 폭: 또래(후보 아닌 기기) 라운드 중앙값 × α 를 넘지 않는 가장 큰 폭 — 망이 보완한 만큼 덜 깎는다. deadline_s 가 있으면 상한으로만.
        고정 목표 하나로 하면 D 가 느슨할 땐 아무도 안 깎고 빡빡하면 전원을 깎아 조건을 계속 미세조정해야 했다(9/9 32대 실행).
    solo (B′안, 2026-09-08 제안): 기준선은 **기기 자기 회선만으로 낼 수 있는 시간**(연산 + 바이트/접속 합, 공유 혼잡 없음)의 중앙값.
        시작 상태의 혼잡 정도(ρ)와 무관하고, 계획기 자신의 이동으로도 안 움직인다(A안의 추격 없음). B안은 ρ≥1 에서 시작 혼잡이
        기준선을 부풀려 폭이 영영 안 켜지는 문제가 있어(combo_sim 2026-09-08) 그 대안. 접속 정보가 없으면 anchored 로 돌아간다."""
    ks = sorted(open_sets)
    full = {k: 1.0 for k in ks}
    if mode == "fixed":
        return float(deadline_s) if deadline_s else float("inf")
    acc = prof.get("access") or {}
    if mode == "solo" and all(k in acc for k in ks):
        def _a(k):
            v = acc[k]
            return sum(v) if isinstance(v, (list, tuple)) else float(v)
        t = {k: prof["cpu"].get(k, 0.0) + (prof["bytes"].get(k, 0.0) * 8 / _a(k) if _a(k) > 0 else 0.0) for k in ks}
        return alpha * statistics.median(t.values())
    if mode == "relative" or not ref_sets:
        t = round_times(full, open_sets, prof, caps, eff, open_sets)
    else:
        ref = {k: tuple(ref_sets[k]) for k in ks}
        t = round_times(full, ref, prof, caps, eff, open_sets)          # 효율 계수는 배정과 무관하게 적용
    return alpha * statistics.median(t.values())


def width_stage(open_sets, prof, caps, ladder, alpha, prev_widths, observed=None, p_min=0.5, raise_ok=None,
                ref_sets=None, deadline_mode="anchored", eff=None, deadline_s=None, goal_sets=None, resid=None, obs_round=None, batches=1, lam=None):
    """(W) 각 기기: t_k(w) ≤ D 인 가장 큰 폭. D 는 deadline() (기본 B안 anchored). 라운드당 한 칸, 복귀는 2라운드 연속.
    반환 (widths, D, 축소 목록, raise_ok 갱신)."""
    lad = tuple(sorted(ladder))
    ks = sorted(open_sets)
    if eff is None:
        eff = efficiency(prof, caps, observed, open_sets)          # 직접 호출(시험)용 — plan() 은 eff 를 준다
    eval_sets = goal_sets or open_sets                        # 고정 목표·또래: 경로 교정이 끝난 배정 기준으로 폭을 잰다
    fixed = deadline_mode in ("fixed", "peer", "opt")
    cand = None
    if deadline_mode == "opt":
        lam_b = float(lam if lam is not None else 60.0) / max(1, batches)          # λ 는 라운드 초 단위로 받는다 → 배치당
        w_opt, steps, tmax = opt_widths(eval_sets, prof, caps, lad, lam_b, p_min, resid, deadline_s)
        D = tmax                                                                    # 보고용: 결정 뒤의 모형 라운드(배치당)
        w = dict(w_opt)
    elif deadline_mode == "peer":
        cand = compute_stragglers(prof, alpha)
        D = peer_reference(eval_sets, prof, caps, alpha, cand, resid)
        if deadline_s:                                        # 응용 상한이 있으면 둘 중 작은 쪽 (배치당)
            D = min(D, float(deadline_s))
    else:
        D = deadline(open_sets, prof, caps, alpha, eff, ref_sets, deadline_mode, deadline_s)
    if deadline_mode != "opt":
        w = {}
    for k in (ks if deadline_mode != "opt" else []):
        i = len(lad) - 1
        if deadline_mode == "solo" and not _compute_bound(k, prof):   # B′: 연산 병목 기기만 폭 후보 — 망 피해자는 경로·분할로 푼다
            w[k] = lad[i]; continue
        if cand is not None and k not in cand:                 # 또래 규칙: 연산 낙오자가 아니면 폭을 건드리지 않는다
            w[k] = lad[i]; continue
        while i > 0 and lad[i - 1] >= p_min:
            t = _t_one(k, lad[i], eval_sets, prof, caps, eff, resid if fixed else None)
            if t <= D:
                break
            i -= 1
        w[k] = lad[i]
    if fixed and obs_round:                         # 관측 보호: 지금 폭으로 실제 라운드가 D 안이면 더 깎지 않는다 (모형이 틀려도)
        for k in ks:
            pw = prev_widths.get(k, 1.0)
            if w[k] < pw and obs_round.get(k) is not None and obs_round[k] <= D * max(1, batches):
                w[k] = pw
    raise_ok = dict(raise_ok or {})
    for k in ks:                                    # 히스테리시스: 한 칸 + 복귀 재확인
        pw = prev_widths.get(k, 1.0)
        if w[k] > pw:
            raise_ok[k] = raise_ok.get(k, 0) + 1
            if raise_ok[k] < 2:
                w[k] = pw
            else:
                j = lad.index(pw) if pw in lad else 0
                w[k] = lad[min(j + 1, len(lad) - 1)]
        elif w[k] < pw:
            raise_ok[k] = 0
            j = lad.index(pw) if pw in lad else len(lad) - 1
            w[k] = lad[max(j - 1, 0)] if lad[max(j - 1, 0)] >= p_min else pw
        else:
            raise_ok[k] = 0
    cut = [k for k in ks if w[k] < 1.0]
    return w, D, cut, raise_ok


def _compute_bound(k, prof):
    """B′ 판정: 기기 k 가 **자기 회선만으로도** 연산이 전송보다 긴가 (연산 ≥ 바이트/접속 합). 혼잡·효율 계수와 무관한 정적 판정이라
    라운드마다 뒤집히지 않는다 (관측 기반 판정은 효율 계수가 흔들릴 때 폭이 왕복했다 — combo_sim 2026-09-08). 접속 정보가 없으면 참."""
    acc = (prof.get("access") or {}).get(k)
    if acc is None:
        return True
    a = sum(acc) if isinstance(acc, (list, tuple)) else float(acc)
    return a <= 0 or prof["cpu"].get(k, 0.0) >= prof["bytes"].get(k, 0.0) * 8 / a


def opt_widths(eval_sets, prof, caps, ladder, lam_b, p_min=0.5, resid=None, deadline_b=None):
    """결합 최적화의 폭 단계 (경로 고정): min  max_k T_k(w) + λ_b·(1/N)·Σ(1−w_k).  T_k 는 목표 배정(eval_sets)에서 배치당 시간.
    탐욕: 전원 전폭에서 시작해, 가장 느린 기기의 폭을 한 칸 내렸을 때 max 가 λ_b/N 보다 많이 줄면 채택, 아니면 멈춘다.
    deadline_b(응용 상한, 배치당)가 있으면 그 아래로 갈 때까지는 가격과 무관하게 계속 내린다(바닥 p_min 까지).
    망을 못 바꾸는 기기는 eval_sets 가 그대로라 폭만 남고, 연산이 병목이 아니면 max 가 안 줄어 안 깎인다 — 기준값(α·D) 없이 세 경우를 덮는다."""
    lad = tuple(sorted(x for x in ladder if x >= p_min))
    ks = sorted(eval_sets); n = max(1, len(ks))
    w = {k: lad[-1] for k in ks}
    t = {k: _t_one(k, w[k], eval_sets, prof, caps, None, resid if resid is not None else {}) for k in ks}
    steps = []
    def lower(k):
        return _t_one(k, lad[lad.index(w[k]) - 1], eval_sets, prof, caps, None, resid if resid is not None else {})
    for _ in range(len(ks) * len(lad)):
        tmax = max(t.values())
        kmax = max(ks, key=lambda k: t[k])
        if lad.index(w[kmax]) == 0:
            break                                                                  # 가장 느린 기기가 바닥이면 더 내려도 max 가 안 준다
        floor_t = lower(kmax)                                                      # 최대 기기를 한 칸 내리면 닿는 시간
        group = [k for k in ks if lad.index(w[k]) > 0 and (k == kmax or t[k] > floor_t + 1e-9)]   # 그보다 느린 기기들도 같이 내려야 max 가 실제로 준다 (근접 동률 포함)
        t_new = {k: lower(k) for k in group}
        tmax_new = max([t_new[k] for k in group] + [t[k] for k in ks if k not in group])
        gain = tmax - tmax_new
        dw = sum(w[k] - lad[lad.index(w[k]) - 1] for k in group)                  # 이번 걸음에 잃는 폭의 합 (한 칸 = 0.25 씩)
        must = deadline_b is not None and tmax > deadline_b
        # 예측 이득은 계측 불확도(MEAS_UNCERT)만큼 깎아서 가격과 견준다 — 경로 이동 문턱과 같은 규칙. 9/9 최종 1차 몰림 장면: 목표 배정이 엣지 3개에 32대를
        # 얹어 전원 근접 동률이 되자 이득 4.38 vs 가격 4.24 로 31대 폭이 2라운드 깎였다 되돌아옴(잡음 경계). 10% 여유면 채택 안 됨 (test_plan2 ⑫-8).
        if gain * (1.0 - MEAS_UNCERT) > lam_b * dw / n or must:
            for k in group:
                w[k] = lad[lad.index(w[k]) - 1]; t[k] = t_new[k]
            steps.append((tuple(group), w[group[0]], round(gain, 3)))
        else:
            break
    return w, steps, max(t.values())


def compute_stragglers(prof, alpha=1.2):
    """연산 기준 (또래 규칙 1단): 자기 연산 시간이 또래 중앙값의 α 배를 넘는 기기만 폭 후보. 회선이 약해 느린 기기는 후보가 아니다 — 폭은 연산 손잡이.
    근거: Spark 투기 실행(중앙값 배수로 낙오자 판정), Aergia(연산 능력으로 낙오자 판정), HeteroFL·FjORD(폭은 연산 능력 등급에)."""
    cpu = prof.get("cpu") or {}
    if not cpu:
        return set()
    med = statistics.median(cpu.values())
    return {k for k, c in cpu.items() if c > alpha * med}


def peer_reference(eval_sets, prof, caps, alpha, cand, resid=None):
    """또래 기준선 (규칙 3단): 후보가 아닌 기기들의 전폭 라운드(목표 배정에서, 배치당) 중앙값 × α. 후보가 전부면 전원 중앙값.
    목표 배정(경로 교정이 끝난 상태) 기준이라 시작 혼잡(ρ)에 끌려가지 않고, 또래가 빨라지면 같이 조여진다(전원이 느려지면 같이 풀림)."""
    ks = sorted(eval_sets)
    peers = [k for k in ks if k not in cand] or ks
    t = [_t_one(k, 1.0, eval_sets, prof, caps, None, resid if resid is not None else {}) for k in peers]
    return alpha * statistics.median(t)


def _t_one(k, wk, open_sets, prof, caps, eff, resid=None):
    """기기 k 만 폭 wk 로 바꿨을 때의 시간 (남은 기기는 전폭) — 물 채우기는 폭과 무관하므로 전체를 다시 안 푼다.
    resid 가 주어지면(고정 목표) 곱 효율 대신 가산 잔차: 전송 = 바이트·w/속도 + 잔차 (폭과 무관한 오버헤드)."""
    rate = effective_rate(open_sets, caps, prof.get("access"))[k]
    g = prof.get("gamma", {}).get(k, 1.2)
    comp = prof["cpu"].get(k, 0.0) * (wk ** g)
    if rate <= 0:
        return float("inf")
    if resid is not None:
        return comp + prof["bytes"].get(k, 0.0) * wk * 8 / rate + resid.get(k, 0.0)
    return comp + prof["bytes"].get(k, 0.0) * wk * 8 / rate * (eff or {}).get(k, 1.0)


# ── 전체 ───────────────────────────────────────────────────
def plan(prof, state, caps, ladder=(0.5, 0.75, 1.0), alpha=1.2, max_moves=1, multipath=False,
         remaining=None, switch_cost=0.0, batches=1, p_min=0.5, deadline_mode="anchored", deadline_s=None, lam=None, hold_widths=False):
    """한 라운드의 결정. state: {"sets": {k: tuple}, "widths": {k}, "observed": {k}, "raise_ok": {k}, "ref_sets": {k}}.
    ref_sets 가 없으면 이번 sets 를 시작 상태로 기억한다(호출자가 state 에 보존). 반환 dict(sets, widths, D, times, cost, why, ref_sets)."""
    cur_sets = {k: tuple(v) for k, v in state["sets"].items()}
    ref_sets = {k: tuple(v) for k, v in (state.get("ref_sets") or cur_sets).items()}
    prev_w = dict(state.get("widths", {}))
    eff = efficiency(prof, caps, state.get("observed"), cur_sets)      # 관측 → 효율 계수 (한 번만)
    # (P) 지금 폭으로 총 비용 최소 집합
    w0 = {k: prev_w.get(k, 1.0) for k in cur_sets}
    S, why_p = path_stage(w0, prof, caps, cur_sets, max_moves, multipath, eff, remaining, switch_cost, batches)
    goal = None
    if deadline_s:
        deadline_s = float(deadline_s) / max(1, batches)                 # 목표는 라운드 단위(초), 폭 판단(_t_one)은 배치 단위
    if deadline_mode in ("fixed", "peer", "opt") and 0 < max_moves < len(cur_sets):   # 이동 상한 없이 푼 목표 배정 — 폭 판단용 (망 보완을 먼저 반영)
        goal, _ = path_stage(w0, prof, caps, S, len(cur_sets), multipath, eff, remaining, switch_cost, batches)
    # (W) 기준선 폭 — B안: 기준선은 시작 상태에서, 경로 이동으로 조이지 않는다 / fixed: 목표 배정 기준
    resid = residual(prof, caps, state.get("observed")) if deadline_mode in ("fixed", "peer", "opt") else None
    obs_r = observed_round(state.get("observed")) if deadline_mode in ("fixed", "peer", "opt") else None
    w, D, cut, raise_ok = width_stage(S, prof, caps, ladder, alpha, prev_w, None, p_min, state.get("raise_ok"),
                                      ref_sets, deadline_mode, eff=eff, deadline_s=deadline_s, goal_sets=goal,
                                      resid=resid, obs_round=obs_r, batches=batches, lam=lam)
    if hold_widths:                                       # 망 변화 라운드(엣지 용량 관측이 바뀐 라운드): 폭은 손대지 않는다 — "둘 다면 망 먼저" (§13-5, 2026-09-10).
        w = {k: prev_w.get(k, 1.0) for k in cur_sets}     # 교란 첫 라운드의 관측(147 s 등)으로 만든 목표 배정은 아직 이동이 반영되기 전이라 전원을 망 병목으로 보고
        raise_ok = dict(state.get("raise_ok") or {})      # 한 칸 깎았다 되돌렸다 (9/10 몰림 R9~10). 이동이 자리 잡은 다음 라운드부터 가격을 따진다. HPA 안정화 창과 같은 뜻.
        cut = [k for k in cur_sets if w[k] < 1.0]
    # (P) 재평가 — 폭이 바뀌었으면 바이트가 달라졌으니 한 번 더 (이동 상한은 이미 썼으므로 추가 이동 없음)
    times = round_times(w, S, prof, caps, eff, cur_sets, switch_cost, batches)
    why = why_p + (f" · 폭 축소 {len(cut)}대{cut} (기준선 {D:.2f}s)" if cut else f" · 폭 전원 전폭 (기준선 {D:.2f}s)") + (" · 망 변화 라운드: 폭 유지" if hold_widths else "")
    return {"sets": S, "widths": w, "D": D, "times": times, "cost": total_cost(times), "eff": eff,
            "makespan": max(times.values()), "raise_ok": raise_ok, "why": why, "ref_sets": ref_sets}


def explain(prof, result, caps):
    """기기마다 왜 이 손잡이인지 한 줄."""
    rate = effective_rate(result["sets"], caps, prof.get("access"))
    lines = []
    for k in sorted(result["sets"]):
        S = "+".join(result["sets"][k])
        lines.append(f"  {k}: 경로 {S:4s} 폭 {result['widths'][k]:.2f}  예상 {result['times'][k]:.2f}s/배치  "
                     f"(연산 {prof['cpu'].get(k,0):.2f}s, 실효 {rate[k]/1e6:.1f} Mbps)")
    return "\n".join(lines)
