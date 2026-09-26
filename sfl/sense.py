# -*- coding: utf-8 -*-
"""인지(sense) — 망과 기기의 능력을 재서 프로파일로 만든다. 규칙(plan.py)을 모른다.
설계: docs/04_설계기록/정식화_결합_시스템.md §5·§6.

  프로파일 (값마다 출처: 측정 | 오라클 | 조건 | 기본)
    기기: cpu(전폭 배치당 연산 초, 고정) · gamma(폭 지수) · bytes(전폭 배치당 왕복 바이트) · access(접속 상한 bit/s) · rtt_ms
    경로: cap(bit/s) — 조건값, 관측 창 최대값으로 갱신
    관측: net(배치당 전송 초, 전폭 기준, 최근 창 최선값)

  측정 절차
    사전 진단 ① PROBE     — fed_server/fed_client 에 있음 (연산 1배치 + 활성값 업로드)
    사전 진단 ② SOLO      — solo_probe(): 기기를 하나씩 불러 n 바이트를 올리게 한다. 나머지는 쉰다.
                           rate = n·8 / (왕복 − 왕복지연). 경로가 접속보다 넉넉하면 접속 상한이 잡힌다.
    라운드 관측 observe()  — 창 최선값(시간 min, 용량 max). EWMA 없음.
"""
import io
import json
import time

from proto import SOLO, SOLORES, recv_msg, send_msg

SOLO_BYTES = 4 << 20          # 단독 프로브 크기 4MB — 1MB 이하는 회선을 다 못 쓴다(KOREN 실측: 1MB 480 vs 4MB 540 Mbps)
WINDOW = 3


class Sensor:
    def __init__(self, ids, window=WINDOW):
        self.ids = list(ids)
        self.window = window
        self.cpu, self.gamma, self.bytes, self.access, self.rtt = {}, {}, {}, {}, {}
        self.path_cap = {}
        self.edge_est = {}                 # 경로 e → 관측 실효 용량(bit/s) 추정 — 포화가 관측된 창의 중앙값. 없으면 정적 용량 (caps_effective)
        self._edge_win = {}                # e → 최근 window 개 [(thr, saturated)]
        self.round = 0                     # observe(sets) 호출 수 — 되돌아가기 탐침의 물러서기(§13-7)에 쓴다
        self._grow = {}                    # e → (추정을 키운 라운드, 키우기 전 값)
        self._cool = {}                    # e → 이 라운드까지 추정을 키우지 않는다 (탐침이 실패한 뒤 물러서기)
        self.net = {}
        self.obs = {}                      # k → 최근 window 개 [{"net": 배치당 초(전폭), "sets": 그때 배정}]  ← plan.efficiency 가 읽는다
        self.src = {}                      # (항목, 키) → 출처
        self._win = {}

    # ── 프로파일 채우기 ─────────────────────────────────────
    def set_probe(self, cid, cpu, bytes_rt, up_s=None):
        """사전 진단 ①의 결과. cpu = 전폭 1배치 순·역전파 초, bytes_rt = 배치당 왕복 바이트."""
        if cid not in self.cpu:                                   # 연산은 한 번 재면 고정
            self.cpu[cid] = cpu; self.src[("cpu", cid)] = "측정"
        self.bytes[cid] = bytes_rt; self.src[("bytes", cid)] = "측정"
        if up_s:
            self.net.setdefault(cid, up_s * 2)                     # 초기 추정 — 관측이 들어오면 덮인다
        self.gamma.setdefault(cid, 1.2); self.src.setdefault(("gamma", cid), "기본")

    def set_access(self, cid, bps, src="측정"):
        self.access[cid] = bps; self.src[("access", cid)] = src

    def set_paths(self, caps, src="조건"):
        for r, c in caps.items():
            self.path_cap[r] = c; self.src[("path", r)] = src

    def _best(self, name, store, k, value, best):
        buf = self._win.setdefault((name, k), [])
        buf.append(value); del buf[:-self.window]
        store[k] = best(buf)

    def observe(self, detail, batches, widths, sets=None):
        """라운드 계측을 흡수한다 — 망만. 연산은 고정이라 진단용으로만 남긴다."""
        for k, d in detail.items():
            if k not in self.ids or not batches:
                continue
            w = widths.get(k, 1.0)
            up, dn = d.get("up_bytes", 0), d.get("dn_bytes", 0)
            xfer = max(d.get("xfer", 0.0), 1e-6) / batches
            net = xfer                                              # xfer = 라운드 − 연산 = 올리기+내리기 왕복 (fed_server). 2026-09-08 까지 (up+dn)/up 을 곱해
                                                                    # 2배로 세던 결함 → 효율 계수가 전부 ~2 로 부풀어 고정 목표 D 에서 전원 폭 축소 (3번 1차 실행)
            self._best("net", self.net, k, net / max(w, 1e-6), min)
            self.src[("net", k)] = "측정"
            if sets:                                                # 관측은 그때의 배정과 함께 남긴다 — 혼잡이 바뀌어도 비교가 공정하도록
                buf = self.obs.setdefault(k, [])
                tot = d.get("t_round") or (d.get("xfer", 0.0) + d.get("cli_fwd", 0.0) + d.get("cli_bwd", 0.0))
                buf.append({"net": net / max(w, 1e-6), "raw": net, "w": w, "tot": tot,      # raw = 그 폭에서 잰 배치당 초, tot = 라운드 총시간(초)
                            "sets": {kk: tuple(v) for kk, v in sets.items()}})
                del buf[:-self.window]
            if up and batches:
                self.bytes[k] = (up + dn) / batches / max(w, 1e-6)
        if sets:                                                    # 경로별 관측 용량 (2026-09-09): 그 경로를 쓰는 모든 기기의 바이트 합 / 가장 오래 걸린 기기의 전송 시간
            self.round += 1
            agg, dur, expct, tacc = {}, {}, {}, {}
            frate, fcap, fspan = {}, {}, {}                          # 흐름별 실효율 합·접속 상한 합·가장 긴 흐름 활동 구간 (출구별 활동 구간이 있을 때, §13-5)
            split_edges = set()                                      # 두 엣지에 걸친 기기가 있던 엣지 — 관측 없음으로 처리(추정 유지)
            for k, d in detail.items():
                S = sets.get(k)
                if not S or k not in self.ids:
                    continue
                split = len(set(S)) > 1                              # 출구가 서로 다른 엣지에 걸린 기기(1+3): 바이트는 두 엣지에 실리지만 전송 **시간**은 어느 엣지 탓인지 알 수 없다
                if split:                                            # → 바이트(부하)는 세고 시간은 귀속하지 않는다 (9/10 몰림 재실행: 막힌 엣지 1 에 걸친 1+2·1+3 기기가 엣지 2·3 을 33M 포화로 보이게 함, §13-4)
                    split_edges.update(S)
                ex = d.get("exits") or []
                tot = d.get("up_bytes", 0) + d.get("dn_bytes", 0)
                a = self.access.get(k)
                bx, t_acc = [], 0.0                                  # 출구별 바이트, 접속 상한만으로 설명되는 이 기기의 전송 시간(초)
                for x, e in enumerate(S):
                    b = (ex[x].get("up", 0) + ex[x].get("dn", 0)) if x < len(ex) and isinstance(ex[x], dict) else tot / max(1, len(S))
                    bx.append(b)
                    ax = (a[x] if isinstance(a, (list, tuple)) and x < len(a) else 0.0) or 0.0
                    if ax > 0:
                        t_acc = max(t_acc, b * 8 / ax)               # 두 가닥: 느린 출구가 끝나야 끝난다 (분할이 치우치면 그만큼 길어진다)
                if isinstance(a, (int, float)) and a > 0:
                    t_acc = sum(bx) * 8 / a                          # 한 가닥: 두 출구가 상한 a 를 합쳐 쓴다
                for x, e in enumerate(S):
                    agg[e] = agg.get(e, 0.0) + bx[x]
                    if not split:
                        dur[e] = max(dur.get(e, 0.0), d.get("xfer", 0.0))
                        tacc[e] = max(tacc.get(e, 0.0), t_acc)
                    ax = (a[x] if isinstance(a, (list, tuple)) and x < len(a) else (a if isinstance(a, (int, float)) else 0.0)) or 0.0
                    expct[e] = expct.get(e, 0.0) + ax
                    if x < len(ex) and isinstance(ex[x], dict) and ex[x].get("up_t", 0) > 0 and ex[x].get("dn_t", 0) > 0 and bx[x] > 0 and ax > 0:
                        frate[e] = frate.get(e, 0.0) + bx[x] * 8 / (ex[x]["up_t"] + ex[x]["dn_t"])   # 이 흐름이 자기 활동 시간 동안 낸 속도
                        fcap[e] = fcap.get(e, 0.0) + ax
                        fspan[e] = max(fspan.get(e, 0.0), ex[x]["up_t"] + ex[x]["dn_t"])           # 이 엣지에서 가장 오래 활동한 흐름 (≈ 흐름들의 합집합 시간)
            seen = set()
            for e, b in agg.items():
                static = self.path_cap.get(e)
                if e in frate and fcap.get(e, 0) > 0:
                    # §13-5 (2026-09-10): 출구별 활동 구간이 보고되면 **판정**은 흐름별 실효율 합 / 접속 상한 합으로 한다. 건강한 엣지에서는 흐름마다 자기 접속 상한(A 5M·B 2M)을
                    # 내므로 분할이 치우쳐도 합 = 접속 합이고, 막힌 엣지에서는 흐름들이 몫을 나눠 합이 떨어진다 — "포화 vs 분할 탓"이 구분되고, 걸친 기기도 흐름마다 제 엣지에 귀속된다.
                    # **용량 값**은 바이트 합 / 가장 긴 흐름 활동 구간(≈ 합집합 시간)으로 잰다: 흐름들이 엇갈려 끝나면(B 가 먼저 끝나고 A 가 빨라짐) 흐름별 속도의 합이
                    # 용량을 넘게 세어(9/10 몰림 재실행: 14M 엣지를 24M 으로) 계획기가 덜 옮기고 폭을 깎았다 (§13-6, test_sense ⑤-4).
                    ratio_thr = frate[e]; ratio_bound = fcap[e]
                    thr = b * 8 / fspan[e] if fspan.get(e, 0) > 0 else frate[e]
                    bound = min(x for x in (static, fcap[e]) if x) * (thr / ratio_thr if ratio_thr > 0 else 1.0)   # 판정 비율(흐름 합/접속 합)을 값의 척도로 옮긴다
                elif dur.get(e, 0) <= 0 or b <= 0:
                    if e in split_edges:
                        seen.add(e)                                  # 걸친 기기만 있는 엣지: 관측 없음 — 추정 유지 (풀지도 내리지도 않음)
                    continue
                else:
                    thr = b * 8 / dur[e]
                    bound = None
                # 포화 기준 = 정적 용량 / 접속 상한 합 / **지금 분할대로 접속 상한만 있을 때의 처리량**(바이트 합 ÷ 가장 오래 걸릴 기기) 중 가장 작은 것.
                # 셋째가 없던 9/9 변동 장면: 추정이 낮으면 계획기가 느린 출구(B 2M)에 바이트를 더 주고, 그래서 느려진 것을 다시 "엣지 포화"로 읽어
                # 추정이 낮게 굳었다 (엣지 1 이 56M 으로 돌아온 뒤에도 20M 에 갇혀 4대가 56s → 회복 못 함). test_sense ④-4·④-5.
                if bound is None:                                            # 옛 꼴(활동 구간 없음, 9/9~10 로그): 총 처리량 대 접속 기대
                    acc_thr = b * 8 / tacc[e] if tacc.get(e, 0) > 0 else None
                    bound = min(x for x in (static, expct.get(e) or None, acc_thr) if x) if (static or expct.get(e) or acc_thr) else None
                sat = bool(bound) and thr < 0.8 * bound                     # 접속 상한·정적 용량으로 설명되는 것보다 느리다 = 엣지가 포화
                clear = bool(bound) and thr >= 0.95 * bound                 # 기대의 95% 이상을 내야 "풀렸다"고 본다 — 0.8~0.95 사이는 유지 (§13-4: 막힌 엣지에 3대만 남으면 0.84~0.90 이 나온다)
                buf = self._edge_win.setdefault(e, []); buf.append((thr, sat)); del buf[:-self.window]
                vals = [t for t, sflag in buf if sflag]
                if sat:
                    g = self._grow.get(e)
                    if g and self.round - g[0] <= 3 and thr <= 1.1 * g[1]:      # §13-7: 추정을 키운 직후(3라운드 안) 다시 막혔고 용량이 나아지지 않았다 = 되돌아가기 탐침 실패
                        self._cool[e] = self.round + 4                            #   → 4라운드 동안 추정을 키우지 않는다 (탐침 물러서기). 용량이 실제로 오른 경우(변동 되올림, thr > 1.1×)는 그대로 키운다
                        self._grow.pop(e, None)
                    self.edge_est[e] = sorted(vals)[len(vals) // 2]; self.src[("edge", e)] = "측정"      # 포화: 창의 포화 관측 중앙값
                elif e in self.edge_est and clear and self.round <= self._cool.get(e, -1):
                    pass                                                           # 물러서기 중: 풀림 관측이 와도 추정 유지
                elif e in self.edge_est and clear:
                    self._grow[e] = (self.round, self.edge_est[e])
                    # 포화가 아님 = "용량 ≥ 지금 처리량" 일 뿐, 정적 용량으로 돌아왔다는 뜻이 아니다 (9/10 최종 몰림: 2대만 남은 14M 엣지는 수요 14 ≤ 14 라 포화가 아니고,
                    # 곧장 56M 으로 믿자 3대를 되돌려 보내 다시 막힘 — 4라운드 주기 왕복 R15·R19·R23). 추정을 라운드마다 1.5 배(또는 관측값)까지만 키운다:
                    # 되돌아오는 기기가 막히면 다음 라운드에 다시 포화로 잡혀 내려가고, 진짜 회복이면 몇 라운드 안에 정적 용량에 닿는다 (test_sense ④-5·④-7).
                    grow = max(thr, self.edge_est[e] * 1.5)
                    if static and grow >= static:
                        self.edge_est.pop(e, None); self._edge_win.pop(e, None)
                    else:
                        self.edge_est[e] = min(static, grow) if static else grow
                seen.add(e)
            for e in list(self.edge_est):                              # 이번 라운드에 아무도 안 쓴 경로: 추정을 1.5 배씩 풀어 정적 용량으로 되돌린다 (다시 써 볼 수 있게)
                if e not in seen:
                    st = self.path_cap.get(e)
                    self.edge_est[e] = min(st, self.edge_est[e] * 1.5) if st else self.edge_est[e] * 1.5
                    if st and self.edge_est[e] >= st:
                        self.edge_est.pop(e, None); self._edge_win.pop(e, None)
            per = {}
            for k, d in detail.items():
                S = sets.get(k)
                if not S or len(S) != 1 or k not in self.ids:
                    continue
                b, x = d.get("up_bytes", 0) + d.get("dn_bytes", 0), d.get("xfer", 0.0)
                if b and x > 0:
                    tb, tx = per.get(S[0], (0.0, 0.0)); per[S[0]] = (tb + b, max(tx, x))
            for r, (tb, tx) in per.items():
                if tx > 0:
                    self._best("path", self.path_cap, r, tb * 8 / tx, max); self.src[("path", r)] = "측정"

    def caps_effective(self, static):
        """계획기가 쓸 경로 용량: 포화가 관측된 경로는 관측 추정(더 작은 쪽), 나머지는 정적 값."""
        return {e: (min(c, self.edge_est[e]) if e in self.edge_est else c) for e, c in static.items()}

    # ── plan.py 가 먹는 형태 ───────────────────────────────
    def profile(self):
        return {"cpu": dict(self.cpu), "gamma": dict(self.gamma), "bytes": dict(self.bytes),
                "access": dict(self.access) if self.access else None}

    def observed(self):
        """plan.efficiency() 가 읽는 꼴: {k: [{"net", "sets"}, ...]}. 배정 스냅샷이 없는 초기 추정은 주지 않는다."""
        return {k: list(v) for k, v in self.obs.items() if v}

    def to_json(self):
        return {"cpu": self.cpu, "gamma": self.gamma, "bytes": self.bytes,
                "access_mbps": {k: ([x / 1e6 for x in v] if isinstance(v, (list, tuple)) else v / 1e6) for k, v in self.access.items()},
                "rtt_ms": self.rtt, "path_cap_mbps": {r: v / 1e6 for r, v in self.path_cap.items()},
                "net_s_per_batch": self.net,
                "edge_est_mbps": {e: round(v / 1e6, 1) for e, v in self.edge_est.items()},
                "src": {f"{a}:{b}": s for (a, b), s in self.src.items()}}

    def save(self, path):
        with io.open(path, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(self.to_json(), ensure_ascii=False, indent=1))


# ── 사전 진단 ② 단독 업로드 프로브 (서버 쪽) ───────────────
def solo_probe(conn, nbytes=SOLO_BYTES, exit_idx=0, chunks=None, cid="c", dp=None):
    """기기 하나에 SOLO 를 보내 n 바이트를 올리게 하고 (rate_bps, rtt_ms) 를 돌려준다.
    exit_idx=0: 주 연결(출구 A)로. exit_idx=1: 기기가 출구 B 에서 조각 포트로 올린다 (두 가닥 모형 — 출구마다 따로 잰다).
    호출자는 다른 기기가 쉬고 있음을 보장해야 한다(순차 호출)."""
    t0 = time.perf_counter()
    send_msg(conn, SOLO, {"n": 0, "dp": dp})                      # 왕복 지연 — 빈 프로브 (dp: 실회선 리그의 출구별 종점)
    kind, meta, _, _ = recv_msg(conn)
    rtt = time.perf_counter() - t0
    assert kind == SOLORES
    if exit_idx or dp:                                            # 채널로 잰다: 출구 B 는 늘, 출구 A 도 실회선(dp) 이면 — 주 연결은 엣지를 안 지난다
        tid = f"solo-{cid}-{exit_idx}"
        t1 = time.perf_counter()
        send_msg(conn, SOLO, {"n": nbytes, "exit": exit_idx, "tid": tid, "dp": dp, "via": 1})
        kind, meta, _, _ = recv_msg(conn)                          # 즉시 회신(수락) — 바이트는 조각 포트로 온다
        assert kind == SOLORES and chunks is not None
        payload = chunks.wait(tid, timeout=60)
        total = time.perf_counter() - t1
        assert len(payload) == nbytes, f"출구 {exit_idx} 프로브 길이 {len(payload)} != {nbytes}"
        return nbytes * 8 / max(total - rtt, 1e-3), rtt * 1000
    t1 = time.perf_counter()
    send_msg(conn, SOLO, {"n": nbytes})
    kind, meta, payload, _ = recv_msg(conn)
    total = time.perf_counter() - t1
    assert kind == SOLORES and len(payload) == nbytes, f"프로브 응답 이상 kind={kind} len={len(payload)}"
    xfer = max(total - rtt, 1e-3)
    return nbytes * 8 / xfer, rtt * 1000


def solo_reply(link, meta, exits=None, srv=None, links=None, cid="solo"):
    """클라 쪽 — SOLO 를 받으면 n 바이트를 즉시 올린다.
    exit 이 있으면 그 출구로만 올린다: links(ChunkLinks)가 있으면 가중치 원핫으로 그 출구 연결만 쓰고(규칙 3′),
    없으면 srv=(host, port+1) 로 한 번짜리 연결(루프백 리그 호환)."""
    n = int(meta.get("n", 0))
    e = int(meta.get("exit", 0))
    if (e or meta.get("via")) and exits and len(exits) > e:       # via: 출구 A 도 채널로 (실회선 — 엣지·접속 tc 를 지나야 참값)
        link.send(SOLORES, {"n": n, "exit": e})                    # 수락 회신 먼저, 바이트는 출구 e 로
        if links is not None:
            w = [0.0] * len(exits); w[e] = 1.0
            links.send(b"\0" * n, meta["tid"], cid=cid, weights=w, wait_ack=True)   # cid 는 기기 id — 서버가 이 연결을 그 기기 채널에 붙인다
            return
        from mpsend import send_multipath
        send_multipath(srv[0], srv[1], b"\0" * n, [exits[e]], meta["tid"], cid="solo")
        return
    link.send(SOLORES, {"n": n}, b"\0" * n if n else b"")
