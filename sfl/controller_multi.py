# -*- coding: utf-8 -*-
"""컨트롤러 — 실측만 보고 기기별 역할을 정한다.

구조는 세 걸음이다 (모두 이 파일 안, 위에서 아래 순서):

    관측  observe_round()   라운드 계측을 EWMA 로 흡수 (전폭 기준으로 정규화)
    예측  predict()         "이 폭·양자화면 몇 초 걸리나"
    결정  decide()          폭·양자화 — 기준선(중앙값×1.2)을 넘는 기기만 한 단계씩
          plan_width_path() 폭×경로 공동 결정 — 완전탐색 + 이동의 경제성 모델
          plan_round()      파이프라인 깊이·동기 시차까지 포함한 통합 계획 (예비)

설계 원칙: 튜닝 상수 0 — 쓰는 값은 기준선 배율(중앙값×1.2)과 계측 불확도(10%)뿐이며,
전자는 "전형적 참가자의 1.2배까지 기다린다"는 정책, 후자는 계측 정밀도의 한계다.
각 규칙이 왜 이렇게 정해졌는지(마감선 세 판, 문턱 상수를 안 쓰는 이유, R5-Q 결함,
안정화 규칙의 발견 경위)는 docs/04_설계기록/설계기록_컨트롤러.md 에 있다.
"""
import itertools
import math
import statistics

from paths import best_widths, joint_plan

LADDER = (0.25, 0.5, 0.75, 1.0)     # 폭 사다리 (최소 25% — 배제 없는 학습)
QUANT_BYTES = 0.25                  # 8비트 양자화의 바이트 배율 (E8 실측)
MEAS_UNCERT = 0.10                  # 계측 불확도 — 이보다 작은 예측 이득은 채택하지 않는다


def _ratio(ms, widths):
    """계획기와 같은 목적값 — makespan / 평균 폭. 시간 이득과 학습 손실을 함께 본다."""
    if not widths:
        return ms
    return ms / max(1e-6, sum(widths.values()) / len(widths))


def effective_quant(server_q, cli_q):
    """유효 양자화 비트 — 서버 지시(>0)가 우선, 0 은 '지시 없음'이라 CLI 값을 쓴다.

    서버가 항상 quant=0 을 동봉해 실험용 --quant 가 무시되던 R5-Q 결함의 수정이다
    (경위: 설계기록_컨트롤러.md §5)."""
    return int(server_q) or int(cli_q)


class MultiKnobController:
    """기기별 폭 p·양자화 q·접속 경로를 실측에서 정한다.

    결정 순서 (대가가 없는 것부터):
        경로 이동 (정확도 손실 0)  →  폭 축소 (가장 싼 대가)  →  양자화 (예비)
    """

    def __init__(self, clients, p_min=0.25, alpha=1.2, ewma=0.5, hysteresis=True,
                 fix_compute=True, window=3):
        self.ks = list(clients)
        self.p_min = p_min          # 폭 바닥 — 아무도 배제하지 않음
        self.alpha = alpha          # 기준선 배율 (중앙값 × alpha)
        self.a = ewma               # EWMA 가중치 — 2026-09-06 개정 후에는 연산·망 어디에도 안 쓴다(구판 호환용으로만 남김)
        self.hyst = hysteresis      # 라운드당 폭 한 칸 제한
        # ── 2026-09-06 개정 (설계기록_컨트롤러.md §9): "연산은 고정, 망은 최근 최선값, 폭은 매 라운드 다시"
        self.fix_compute = fix_compute   # 기기 연산 속도는 한 번 재면 고정 — 성능이 변할 가능성은 매우 낮다. 사전 진단이 있으면 그 값, 없으면 첫 관측
        self.window = window        # 망 추정은 EWMA 대신 최근 window 라운드 중 최선값 (BBR 의 windowed max/min 방식) — 상수 하나 줄임
        self.win = {}               # (저장소이름, 기기) → 최근 관측 목록
        self.raise_ok = {}          # 기기 → 폭을 올려도 된다고 판정된 연속 라운드 수 (복귀 재확인: 2라운드)
        self.path_objective = "sum" # 경로 단계 목적: "sum" = 기기→서버 총 비용 (사용자 지시 2026-09-06) / "max" = 구판(v1)
        # 관측 (전부 전폭·무양자화 기준으로 정규화해 저장)
        self.cpu1 = {}              # 기기 → 배치당 연산 초
        self.net1 = {}              # 기기 → 배치당 망 초
        self.cap = {}               # 기기 → 업로드 용량 추정 (B/s)
        self.bytes1 = {}            # 기기 → 배치당 왕복 바이트 (올리고 내리는 것 모두)
        #  경로는 양방향을 같은 클래스로 성형하므로 내려오는 바이트도 같은 회선을 쓴다.
        #  상향만 세면 느린 경로의 비용을 절반으로 보아 이동을 낙관하게 된다 (2026-09-04 수정)
        self.gamma = {}             # 기기 → 연산의 폭 지수 (실측 적합, 기본 1.2)
        # 결정 상태
        self.p = {k: 1.0 for k in self.ks}
        self.q = {k: 0 for k in self.ks}
        self.depth = {k: 1 for k in self.ks}
        # 설명용
        self.diag = {}
        self.unrescuable = set()
        self.path_cap = {}          # 경로별 실효 용량 추정 (bit/s) — 관측에서 채운다. caps 와 같은 단위
        self.access_cap = {}        # 기기별 접속 회선 용량 (bit/s). 비어 있으면 모형에 접속 회선 항이 없다.
        #  hairpin 리그(접속 회선 + 공유 경로)에서 "경로를 옮겨도 안 풀리는 병목"을 모형이 알게 하는 자리.
        #  관측 처리량(self.cap)으로 채우면 안 된다 — 혼잡 중 관측치는 공유 구간 몫이라 이동 이득을 지워 버린다.
        #  채우는 길: --access-caps(리그 검증용 오라클) 또는 사전 진단의 단독 측정(후속).

    # ── 관측 ────────────────────────────────────────────────
    def _ewma(self, store, k, value):
        store[k] = value if k not in store else (1 - self.a) * store[k] + self.a * value

    def _best(self, name, store, k, value, best=min):
        """최근 window 개 관측 중 최선값(시간은 min, 용량은 max)을 store[k] 에 둔다 — EWMA 대신."""
        buf = self.win.setdefault((name, k), [])
        buf.append(value)
        del buf[:-self.window]
        store[k] = best(buf)

    def observe_round(self, detail, batches, assign=None):
        """fed_server 의 per_client_detail 을 흡수한다.

        2026-09-06 개정: 연산(cpu1)은 고정(사전 진단 또는 첫 관측), 망(net1·cap·path_cap)은 최근 window 라운드 최선값.
        계측 정의와 한계(내리는 구간은 바이트 비로 보정, 스레드 과다구독 교훈)는 설계기록_컨트롤러.md §2."""
        for k, d in detail.items():
            if k not in self.ks or not batches:
                continue
            p, q = self.p.get(k, 1.0), self.q.get(k, 0)
            g = self.gamma.get(k, 1.2)
            cpu = (d.get("cli_fwd", 0.0) + d.get("cli_bwd", 0.0)) / batches
            up, dn = d.get("up_bytes", 0), d.get("dn_bytes", 0)
            xfer = max(d.get("xfer", 0.0), 1e-6) / batches
            net = xfer * ((up + dn) / up if up else 1.0)
            cpu_full = cpu / (p ** g) if p > 0 else cpu
            if not self.fix_compute:
                self._ewma(self.cpu1, k, cpu_full)
            elif k not in self.cpu1:
                self.cpu1[k] = cpu_full                   # 첫 관측으로 고정 (사전 진단이 있었으면 이미 채워져 있다)
            self.cpu_obs = getattr(self, "cpu_obs", {}); self.cpu_obs[k] = cpu_full   # 진단용 — 결정에 안 쓴다
            self._best("net1", self.net1, k, net / (p * (QUANT_BYTES if q else 1.0)) if p > 0 else net, min)
            xf = d.get("xfer", 0.0)
            if up and xf > 0:
                self._best("cap", self.cap, k, up / xf, max)
            if up and batches:
                self.bytes1[k] = (up + dn) / batches / max(p, 1e-6)   # 바이트는 폭이 정하는 결정론적 값 — 최신값
        if assign:                                  # 경로별 실효 용량 — 같은 경로에 붙은
            per = {}                                # 기기들의 총 바이트를 그 경로의 최대 전송 시간으로
            for k, d in detail.items():
                r = assign.get(k)
                if r is None or k not in self.ks:
                    continue
                b, x = d.get("up_bytes", 0) + d.get("dn_bytes", 0), d.get("xfer", 0.0)
                if b and x > 0:
                    tb, tx = per.get(r, (0.0, 0.0))
                    per[r] = (tb + b, max(tx, x))
            for r, (tb, tx) in per.items():
                if tx > 0:
                    self._best("path_cap", self.path_cap, r, tb * 8 / tx, max)      # bit/s — caps(Mbps×1e6)와 같은 단위

    def fit_gamma(self, k, samples):
        """연산의 폭 지수를 실측에서 적합. samples = {p: 배치당 연산초}.
        이론값(p²)으로 외삽하지 않는다 — 실측은 1.04~1.35 였다."""
        ps = sorted(samples)
        if len(ps) >= 2 and samples[ps[0]] > 0 and samples[ps[-1]] > 0:
            lo, hi = ps[0], ps[-1]
            self.gamma[k] = math.log(samples[lo] / samples[hi]) / math.log(lo / hi)
        else:
            self.gamma[k] = 1.2

    # ── 예측 ────────────────────────────────────────────────
    def predict1(self, k, p, q, batches):
        """기기 k 가 폭 p·양자화 q 로 낼 라운드 시간."""
        g = self.gamma.get(k, 1.2)
        cpu = self.cpu1.get(k, 0.0) * (p ** g)
        net = self.net1.get(k, 0.0) * p * (QUANT_BYTES if q else 1.0)
        return batches * (cpu + net)

    def predict(self, pv, qv, batches):
        return {k: self.predict1(k, pv[k], qv.get(k, 0), batches) for k in self.ks}

    # ── 진단 (사람용 이름표 — 결정에는 쓰지 않는다) ────────────────
    def diagnose(self, batches):
        """기기별 병목 이름표. 라벨 구분선(0.6/0.4)은 설명용일 뿐이라 틀려도
        결정이 안 바뀐다 (설계기록_컨트롤러.md §4)."""
        out = {}
        for k in self.ks:
            cpu = self.cpu1.get(k, 0.0) * batches
            net = self.net1.get(k, 0.0) * batches
            tot = cpu + net
            share = net / tot if tot > 0 else 0.0
            if share >= 0.6:
                kind, why = "망", "폭·양자화 둘 다 듣는다 (폭이 먼저 — 더 싸다)"
            elif share <= 0.4:
                kind, why = "연산", "**양자화는 무효** — 폭만 듣는다"
            else:
                kind, why = "섞임", "폭이 둘 다 줄여 유리하다"
            out[k] = {"cpu_s": cpu, "net_s": net, "net_share": share,
                      "bottleneck": kind, "note": why}
        self.diag = out
        return out

    # ── 결정 ① 폭·양자화 ────────────────────────────────────
    def decide(self, batches):
        """기준선(D = alpha × 중앙값)을 넘는 기기만, 많이 넘는 순서로 구제한다.

        1단 폭을 한 칸 축소 (연산·망이 함께 줄어 대가가 가장 싸다)
        2단 폭 바닥에서도 못 맞추면, 양자화가 실제로 기준선 아래로 내려 주는지를
            예측으로 직접 확인한 뒤에만 켠다 — 문턱 상수 없음
        (기준선이 중앙값이 된 경위와 문헌 대조: 설계기록_컨트롤러.md §3·§4)
        """
        if not self.cpu1:
            return dict(self.p), dict(self.q)
        self.diagnose(batches)
        full_p = {k: 1.0 for k in self.ks}
        full_q = {k: 0 for k in self.ks}
        D = self.alpha * statistics.median(self.predict(full_p, full_q, batches).values())

        pv, qv, stuck = dict(full_p), dict(full_q), set()
        while True:
            T = self.predict(pv, qv, batches)
            over = {k: t for k, t in T.items() if t > D and k not in stuck}
            if not over:
                break
            k = max(over, key=over.get)
            i = LADDER.index(pv[k])
            if i > 0 and LADDER[i - 1] >= self.p_min:
                pv[k] = LADDER[i - 1]                  # 1단: 폭
                continue
            if qv[k] == 0 and self.predict1(k, pv[k], 8, batches) <= D:
                qv[k] = 8                              # 2단: 양자화 (예비)
                continue
            stuck.add(k)                               # 남은 수단 없음 — 기록만
        self.unrescuable = stuck

        if self.hyst:                                  # 라운드당 폭 한 칸까지
            for k in self.ks:
                i0, i1 = LADDER.index(self.p[k]), LADDER.index(pv[k])
                if abs(i1 - i0) > 1:
                    pv[k] = LADDER[i0 + (1 if i1 > i0 else -1)]
        self.p, self.q = pv, qv
        return dict(pv), dict(qv)

    # ── 결정 ② 폭 × 경로 공동 (두 수단 체제의 본체) ─────────────
    def plan_width_path(self, batches, caps, current_assign=None, max_moves=1,
                        ladder=None, remaining=None, switch_cost=0.0):
        """실측(EWMA)만 입력으로 폭과 경로를 함께 정한다.

        이동 판단은 방어 규칙이 아니라 **경제성 모델**이다:

            이동한다  ⇔  라운드당 절감 > 전환비용/남은라운드 + 계측오차×현재시간

        · 전환 비용(switch_cost, 초)은 측정되는 물리량 — 재접속 + (지점이 여럿이면)
          지점 간 모델 동기화. 남은 라운드(remaining)로 상각되므로, 학습 막바지에는
          문턱이 저절로 높아지고 초반에는 작은 이득에도 움직인다
        · 계측 오차 여유(MEAS_UNCERT)가 잡음 이득의 채택을 막는다 — 왕복 이동은
          갈 때 올 때 각각 비용을 지불하므로 모델이 스스로 벌한다
        · max_moves: 집행 단위 (한 라운드 이동 수 상한 — 기본 1)

        반환: (assign, widths, 예측 makespan, 사유 문자열)
        """
        if not self.bytes1 or not caps:
            return dict(current_assign or {}), dict(self.p), 0.0, "측정 전 — 무개입"
        lad = ladder or LADDER
        comp = statistics.median(self.cpu1.values()) if self.cpu1 else 0.0
        caps = {r: self.path_cap.get(r, c) for r, c in caps.items()}   # 실측이 있으면 실측이 이긴다
        assign, widths, ms_new, _ = joint_plan(self.bytes1, caps, lad, comp)
        if not current_assign:
            return self._settle(assign, widths, ms_new, "초기 배정")

        w_stay, ms_stay = best_widths(self.bytes1, current_assign, caps, lad, comp)
        horizon = max(1, remaining) if remaining else None
        # 계획기의 목적함수는 makespan/평균폭이다. 게이트도 같은 값으로 비교해야 한다.
        # raw makespan 으로 비교하면 폭을 되살리는 변화(= 되돌림)는 언제나 기각된다.
        r_stay, r_new = _ratio(ms_stay, w_stay), _ratio(ms_new, widths)
        avgw_stay = max(1e-6, sum(w_stay.values()) / len(w_stay))
        # r_stay 는 배치당 값이므로 라운드당 전환 비용도 배치당으로 나눠 같은 단위로 견준다
        thresh = MEAS_UNCERT * r_stay + ((switch_cost / horizon / max(1, batches)) / avgw_stay if horizon else 0.0)
        if r_stay <= 0 or (r_stay - r_new) <= thresh:
            return self._settle(dict(current_assign), w_stay, ms_stay, "유지 (이득 ≤ 전환 문턱)")

        moved = [k for k in assign if assign[k] != current_assign[k]]
        if len(moved) > max_moves:                     # 집행 단위 — 최선 1대만
            best = None
            for k in moved:
                trial = dict(current_assign)
                trial[k] = assign[k]
                w_t, ms_t = best_widths(self.bytes1, trial, caps, lad, comp)
                r_t = _ratio(ms_t, w_t)
                if best is None or r_t < best[4]:
                    best = (trial, w_t, ms_t, k, r_t)
            assign, widths, ms_new = best[0], best[1], best[2]
            if (r_stay - best[4]) <= thresh:           # 1대 이동만으로는 문턱 미달
                return self._settle(dict(current_assign), w_stay, ms_stay, "유지 (이득 ≤ 전환 문턱)")
            return self._settle(assign, widths, ms_new, f"이동 1명({best[3]}) — 상한 적용")
        return self._settle(assign, widths, ms_new, f"이동 {len(moved)}명")

    # ── 결정 ②' 2단계 계획 — 대가 없는 손잡이(경로)부터, 폭은 낙오자에게만 ─────
    def round_time(self, assign, widths, caps):
        """기기별 배치당 예상 시간 t_k = 연산_k(p_k) + 망_k.
        망_k = max(자기 경로의 부하(같은 경로 기기들의 바이트 합 / 경로 용량), 자기 바이트 / 접속 회선 용량).
        접속 회선 항은 access_cap 이 있을 때만 — 없으면 구판과 같은 공유 경로 모형이다.
        반환 (t: dict, T = max t). 부하가 바이트에 선형이라는 가정은 보정 곡선으로 바꿀 자리다."""
        load = {r: 0.0 for r in caps}
        for k in self.ks:
            load[assign[k]] += self.bytes1.get(k, 0.0) * widths[k] * 8 / caps[assign[k]]
        t = {}
        for k in self.ks:
            net = load[assign[k]]
            acc = self.access_cap.get(k)
            if acc:
                net = max(net, self.bytes1.get(k, 0.0) * widths[k] * 8 / acc)
            t[k] = self.cpu1.get(k, 0.0) * (widths[k] ** self.gamma.get(k, 1.2)) + net
        return t, max(t.values())

    def _compute_widths(self, lad):
        """0단 — 연산 낙오자를 **경로와 무관하게** 폭으로 구제한다.

        기준선 D_c = alpha × 중앙값(전폭 연산시간). 연산만으로 D_c 를 넘는 기기는 C_k·w^γ ≤ D_c 가 되는
        가장 큰 사다리 칸까지 내린다(바닥이면 바닥). 연산 병목은 경로로 풀 수 없다는 사실을 규칙에 박은 것.
        반환 (widths, 연산 낙오자 목록, D_c)."""
        C = {k: self.cpu1.get(k, 0.0) for k in self.ks}
        if not C or max(C.values()) <= 0:
            return {k: 1.0 for k in self.ks}, [], 0.0
        Dc = self.alpha * statistics.median(C.values())
        w, cut = {}, []
        for k in self.ks:
            i = len(lad) - 1
            if C[k] > Dc:
                g = self.gamma.get(k, 1.2)
                while i > 0 and C[k] * (lad[i] ** g) > Dc and lad[i - 1] >= self.p_min:
                    i -= 1
                if i < len(lad) - 1:                     # 실제로 내린 기기만 (ladder=(1.0,) 이면 내릴 칸이 없다)
                    cut.append(k)
            w[k] = lad[i]
        return w, cut, Dc

    def path_cost(self, assign, widths, caps, objective=None):
        """경로 단계의 목적값. "sum" = 기기별 예상 시간의 총합(기기→서버 총 비용, 2026-09-06 사용자 지시) / "max" = 최대(구판).
        max 는 어디로 옮겨도 안 빨라지는 기기(접속 회선 병목)가 최대이면 나머지를 옮겨도 이득이 0 으로 보여 아무도 안 옮긴다
        (h5n 스모크 2026-09-06). sum 은 그 경우에도 나머지의 이득을 센다."""
        t, T = self.round_time(assign, widths, caps)
        return sum(t.values()) if (objective or self.path_objective) == "sum" else T

    def _best_assign(self, widths, caps, limit=4 ** 8, objective=None):
        """폭을 고정하고 경로 목적값(path_cost)을 최소화하는 배정. 작으면 완전탐색, 크면 큰 기기부터 가장 덜 붐비는 경로로(LPT)."""
        rs = sorted(caps)
        if len(rs) ** len(self.ks) <= limit:
            best = None
            for combo in itertools.product(rs, repeat=len(self.ks)):
                a = dict(zip(self.ks, combo))
                T = self.path_cost(a, widths, caps, objective)
                if best is None or T < best[0]:
                    best = (T, a)
            return best[1]
        load = {r: 0.0 for r in rs}
        out = {}
        for k in sorted(self.ks, key=lambda k: -self.bytes1.get(k, 0.0) * widths[k]):
            b = self.bytes1.get(k, 0.0) * widths[k] * 8
            r = min(rs, key=lambda r: (load[r] + b) / caps[r])
            out[k] = r
            load[r] += b
        return out

    def _path_stage(self, cur, w, caps, batches, max_moves, remaining, switch_cost, objective=None):
        """경로 단계 — 폭 w 를 고정하고 경로 목적값(기본 sum = 총 비용)을 줄이는 배정. 이동은 문턱(계측 불확도 × 현재값 +
        전환비용/남은 배치)을 넘을 때만, 라운드당 max_moves 대. 반환 (assign, 사유)."""
        obj = objective or self.path_objective
        C_stay = self.path_cost(cur, w, caps, obj)
        cand = self._best_assign(w, caps, objective=obj)
        C_cand = self.path_cost(cand, w, caps, obj)
        horizon = max(1, remaining) * max(1, batches) if remaining else None
        thresh = MEAS_UNCERT * C_stay + (switch_cost / horizon if horizon else 0.0)
        moved = [k for k in self.ks if cand[k] != cur[k]]
        if max_moves <= 0:                                   # 폭만 (절제) — 경로는 절대 안 옮긴다
            return cur, "경로 고정"
        if not moved or C_stay - C_cand <= thresh:
            return cur, "경로 유지"
        if len(moved) > max_moves:
            best = None
            for k in moved:
                trial = dict(cur); trial[k] = cand[k]
                C_t = self.path_cost(trial, w, caps, obj)
                if best is None or C_t < best[0]:
                    best = (C_t, trial, k)
            if C_stay - best[0] <= thresh:
                return cur, "경로 유지 (1대 이동은 문턱 미달)"
            return best[1], f"경로 이동 1대({best[2]})"
        return cand, f"경로 이동 {len(moved)}대"

    def plan_two_stage(self, batches, caps, current_assign=None, max_moves=1,
                       ladder=None, remaining=None, switch_cost=0.0):
        """병목 유형 우선 계획 (2026-09-06 개정) — **연산 병목은 폭, 공유 구간 혼잡은 경로, 나머지는 폭.**

        구판(plan_two_stage_v1)은 경로를 먼저 정하고 폭은 "경로 결정 후 중앙값×α를 넘는 기기"에만 줬다.
        혼합 집단(연산 낙오자 + 공유 구간 혼잡)에서 경로 단계가 남들을 느린 경로로 옮겨 중앙값을 올리면
        연산 낙오자가 기준선 아래로 '보이게' 되어 폭이 전폭으로 복귀했다 — 연산이 4배 느린 기기가 그대로
        최대인데 컨트롤러는 낙오자 없음이라 판단했다(시뮬 2026-09-06: 둘다 3.94s > 폭만 3.48s).
        연산 병목은 경로로 풀 수 없다. 그래서 순서를 바꿨다:

        0단 연산: 전폭 연산시간 C_k 가 D_c = α × 중앙값(C) 를 넘는 기기는 폭을 내린다 (_compute_widths).
                 경로 상태와 무관하므로 남들이 어디로 옮기든 이 폭은 되돌아오지 않는다.
        1단 경로: 0단 폭을 고정하고 공유 구간 혼잡을 배정으로 푼다 (_path_stage). 문턱·max_moves 동일.
        2단 잔여: 1단 배정에서 D_r = α × 중앙값 t_k 를 넘는 기기만 한 칸 더 (접속 회선 병목 등, 경로로
                 안 풀린 것). 연산 낙오자도 아직 넘으면 한 칸 더 내릴 수 있다.
        그 뒤 라운드당 한 칸 히스테리시스(_settle).

        절제 팔: ladder=(1.0,) 이면 0단·2단이 아무것도 못 내린다(경로만). max_moves=0 이면 1단이 안 옮긴다(폭만).
        반환: (assign, widths, 예측 T, 사유)
        """
        if not self.bytes1 or not caps:
            return dict(current_assign or {}), dict(self.p), 0.0, "측정 전 — 무개입"
        lad = tuple(ladder) if ladder else LADDER
        caps = {r: self.path_cap.get(r, c) for r, c in caps.items()}
        cur = dict(current_assign) if current_assign else {k: sorted(caps)[0] for k in self.ks}

        # ── 0단 진단: 연산만으로 낙오자인 기기 (사람이 읽는 이름표 — 결정에는 안 쓴다. §9: 폭은 총시간 기준으로만)
        _, comp_cut, Dc = self._compute_widths(lad)

        # ── 1단 경로 — 지금 폭(직전 결정)을 그대로 두고 공유 구간 혼잡만 배정으로 푼다
        w_now = {k: self.p.get(k, 1.0) for k in self.ks}
        assign, why1 = self._path_stage(cur, w_now, caps, batches, max_moves, remaining, switch_cost)

        # ── 2단 폭 — "연산(고정) + 지금 망에서 걸리는 시간이 기준선 안에 들어오는 가장 큰 폭" (2026-09-06 개정 2, §9)
        #    기준선 D = α × 중앙값(전원 전폭일 때의 총시간). 망 시간 = max(모형, 관측):
        #    모형만 쓰면 접속 회선 낙오자를 놓치고(5판 1차 관찰 A), 관측만 쓰면 옮긴 기기의 예상 혼잡을 못 본다.
        #    관측(최근 최선값)은 옮기지 않은 기기에만 유효하다. 연산이 고정이므로 "망이 빨라지면 폭을 덜 줄인다"가 저절로 된다.
        full = {k: 1.0 for k in self.ks}

        def t_of(k, wk):
            g = self.gamma.get(k, 1.2)
            comp = self.cpu1.get(k, 0.0) * (wk ** g)
            net = self.round_time(assign, dict(full, **{k: wk}), caps)[0][k] - comp
            if assign[k] == cur[k] and k in self.net1:
                net = max(net, self.net1[k] * wk)
            return comp + net
        D = self.alpha * statistics.median(t_of(k, 1.0) for k in self.ks)
        w, res_cut = {}, []
        for k in self.ks:
            i = len(lad) - 1
            while i > 0 and t_of(k, lad[i]) > D and lad[i - 1] >= self.p_min:
                i -= 1
            w[k] = lad[i]
            if w[k] < 1.0:
                res_cut.append(k)
        # 복귀 재확인 — 지난 라운드보다 폭을 올리는 것은 "올려도 D 안"이 2라운드 연속일 때만 (경로 이동의 재확인과 같은 구조)
        for k in self.ks:
            if w[k] > self.p.get(k, 1.0):
                self.raise_ok[k] = self.raise_ok.get(k, 0) + 1
                if self.raise_ok[k] < 2:
                    w[k] = self.p[k]
            else:
                self.raise_ok[k] = 0
        self.unrescuable = {k for k in self.ks if t_of(k, w[k]) > D and w[k] <= max(self.p_min, lad[0])}
        why = ((f"연산 낙오자 {len(comp_cut)}대{comp_cut} (연산만 기준 {Dc:.2f}s)" if comp_cut else "연산 낙오자 없음")
               + " · " + why1
               + (f" · 폭 축소 {len(res_cut)}대{res_cut} (총시간 기준선 {D:.2f}s)" if res_cut else f" · 폭 전원 전폭 (총시간 기준선 {D:.2f}s)"))
        return self._settle(assign, w, self.round_time(assign, w, caps)[1], why)

    def plan_two_stage_v1(self, batches, caps, current_assign=None, max_moves=1,
                          ladder=None, remaining=None, switch_cost=0.0):
        """구판 2단계 계획 (2026-09-02~06). 경로 먼저(전원 전폭), 폭은 경로 결정 후 낙오자만.

        결함: 혼합 집단에서 경로 단계가 중앙값을 올려 연산 낙오자의 폭이 전폭으로 복귀한다
        (plan_two_stage 도크스트링). 절제 2판(동질 연산)의 결과 재현·비교용으로만 남긴다 (`--planner two-stage-v1`).
        """
        if not self.bytes1 or not caps:
            return dict(current_assign or {}), dict(self.p), 0.0, "측정 전 — 무개입"
        lad = tuple(ladder) if ladder else LADDER
        caps = {r: self.path_cap.get(r, c) for r, c in caps.items()}
        full = {k: 1.0 for k in self.ks}
        cur = dict(current_assign) if current_assign else {k: sorted(caps)[0] for k in self.ks}
        assign, why1 = self._path_stage(cur, full, caps, batches, max_moves, remaining, switch_cost, objective="max")
        t_full, _ = self.round_time(assign, full, caps)
        D = self.alpha * statistics.median(t_full.values())
        w, stuck = dict(full), set()
        while True:
            t, _ = self.round_time(assign, w, caps)
            over = {k: v for k, v in t.items() if v > D and k not in stuck}
            if not over:
                break
            k = max(over, key=over.get)
            i = lad.index(w[k]) if w[k] in lad else len(lad) - 1
            if i > 0 and lad[i - 1] >= self.p_min:
                w[k] = lad[i - 1]
            else:
                stuck.add(k)
        self.unrescuable = stuck
        cut = [k for k in self.ks if w[k] < 1.0]
        why = why1 + (f" · 폭 축소 {len(cut)}대 (기준선 {D:.2f}s)" if cut else " · 폭 전원 전폭")
        return self._settle(assign, w, self.round_time(assign, w, caps)[1], why)

    def _settle(self, assign, widths, ms, why):
        """결정을 확정한다 — 라운드당 폭 한 칸 제한을 걸고, 결정한 폭을 상태에 기록한다.

        폭을 기록하지 않으면 observe_round 가 다음 라운드 관측을 전폭 기준으로 되돌려
        폭을 줄인 기기를 '가벼운 기기'로 오인하고 배정이 주기적으로 진동한다.
        """
        w = dict(widths)
        if self.hyst:
            lad = tuple(sorted(set(LADDER) | set(w.values()) | set(self.p.values())))
            for k in list(w):
                if k in self.p and self.p[k] in lad and w[k] in lad:
                    i0, i1 = lad.index(self.p[k]), lad.index(w[k])
                    if abs(i1 - i0) > 1:
                        w[k] = lad[i0 + (1 if i1 > i0 else -1)]
        self.p = dict(self.p, **w)
        return dict(assign), w, ms, why

    # ── 결정 ③ 통합 계획 (파이프라인·시차 — 예비) ────────────────
    def plan_round(self, batches, sync_bytes=0):
        """폭·양자화에 파이프라인 깊이와 동기 시차까지 얹은 통합 계획.

        파이프라인은 J 시리즈 실측에서 정확도 대가가 발견되어 기본 끔 — 채택 기준
        (예측 이득 > 계측 불확도)과 비동기 FL 과의 경계는 설계기록_컨트롤러.md §6.

        반환: (plan, pred) — plan[k] = {p, q, depth, sync_offset_s},
        pred = {makespan, sync_end, gain_pipe}.
        """
        pv, qv = self.decide(batches)
        plan, finish = {}, {}
        gain_pipe = 0.0
        for k in self.ks:
            g = self.gamma.get(k, 1.2)
            c = self.cpu1.get(k, 0.0) * (pv[k] ** g)
            n = self.net1.get(k, 0.0) * pv[k] * (QUANT_BYTES if qv.get(k) else 1.0)
            t1 = batches * (c + n)                       # 직렬
            t2 = (c + n) + max(0, batches - 1) * max(c, n)   # 겹침
            d = 2 if t1 > 0 and (t1 - t2) / t1 > MEAS_UNCERT else 1
            self.depth[k] = d
            finish[k] = t2 if d == 2 else t1
            gain_pipe += max(0.0, t1 - finish[k])
            plan[k] = {"p": pv[k], "q": qv.get(k, 0), "depth": d, "sync_offset_s": 0.0}
        prev_end = 0.0                                  # 동기 시차 — 직렬 슬롯
        for k in sorted(self.ks, key=lambda x: finish[x]):
            if sync_bytes and self.cap.get(k, 0) > 0:
                dur = sync_bytes / self.cap[k]
                start = max(finish[k], prev_end)
                plan[k]["sync_offset_s"] = round(start - finish[k], 4)
                prev_end = start + dur
            else:
                prev_end = max(prev_end, finish[k])
        pred = {"makespan": max(finish.values()) if finish else 0.0,
                "sync_end": prev_end, "gain_pipe": gain_pipe}
        return plan, pred

    # ── 설명 ────────────────────────────────────────────────
    def explain(self, batches):
        """왜 그렇게 정했는지 사람이 읽을 수 있게."""
        lines = []
        for k in self.ks:
            d = self.diag.get(k, {})
            lines.append(
                f"  {k}: 연산 {d.get('cpu_s', 0):5.2f}s / 망 {d.get('net_s', 0):5.2f}s "
                f"(망 몫 {d.get('net_share', 0)*100:3.0f}%) → 병목 {d.get('bottleneck', '?'):4s} "
                f"→ 폭 {self.p[k]:.2f}"
                + (" + 양자화" if self.q.get(k) else "")
                + ("  ★구제불가" if k in self.unrescuable else "")
                + f"   [{d.get('note', '')}]")
        return "\n".join(lines)
