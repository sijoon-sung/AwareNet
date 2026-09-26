# -*- coding: utf-8 -*-
"""sense.Sensor 시험 — 관측이 계획기에 맞는 단위로 들어가는가.  python tests/test_sense.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sfl"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import sense  # noqa: E402

M = 1e6
fails = 0
def check(name, ok, detail=""):
    global fails; fails += 0 if ok else 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

def main():
    print("== sense.py 시험 ==")
    S = sense.Sensor(["c0"])
    S.set_probe("c0", 0.4, 8.39 * M, 1.0)
    # 라운드: 연산 1.6s, 왕복 전송 4.0s(xfer = 라운드 − 연산), 배치 4, 올리기 = 내리기 = 16.8MB
    detail = {"c0": {"xfer": 4.0, "cli_fwd": 1.0, "cli_bwd": 0.6, "up_bytes": 16.78e6, "dn_bytes": 16.78e6, "t_round": 5.6}}
    S.observe(detail, 4, {"c0": 1.0}, {"c0": ("1",)})
    e = S.observed()["c0"][-1]
    check("① 관측 배치당 전송 = xfer/배치 = 1.0s (왕복을 2배로 세지 않는다 — 2026-09-08 결함)", abs(e["raw"] - 1.0) < 1e-9 and abs(e["net"] - 1.0) < 1e-9, f"{e}")
    check("② 관측에 폭·라운드 총시간이 붙는다 (고정 목표 폭 판단용)", e.get("w") == 1.0 and abs(e.get("tot", 0) - 5.6) < 1e-9, f"{e}")
    S.observe({"c0": {**detail["c0"], "xfer": 2.0, "t_round": 3.0}}, 4, {"c0": 0.5}, {"c0": ("1",)})
    e2 = S.observed()["c0"][-1]
    check("③ 폭 0.5 관측: raw 0.5s 그대로, net(전폭 환산) 1.0s", abs(e2["raw"] - 0.5) < 1e-9 and abs(e2["net"] - 1.0) < 1e-9, f"{e2}")
    # ④ 엣지 관측 용량: 8대가 엣지 1 을 두 출구로 쓰는데 엣지가 1/4 로 막히면 계획기 용량이 관측값으로 내려온다 (9/9 결함 수정)
    ids = [f"c{i}" for i in range(8)]
    S8 = sense.Sensor(ids)
    for k in ids:
        S8.set_probe(k, 0.8, 8.39 * M, 1.0); S8.set_access(k, [5 * M, 2 * M])
    S8.set_paths({"1": 56 * M, "2": 56 * M})
    sets = {k: ("1", "1") for k in ids}
    healthy = {k: {"xfer": 38.4, "cli_fwd": 2, "cli_bwd": 1, "up_bytes": 16.78e6, "dn_bytes": 16.78e6, "t_round": 41.4} for k in ids}   # 8×33.6MB / 38.4s = 56M = 정적
    S8.observe(healthy, 4, {k: 1.0 for k in ids}, sets)
    ce = S8.caps_effective({"1": 56 * M, "2": 56 * M})
    check("④-1 정상 라운드(합 56M)에서는 정적 용량 그대로", abs(ce["1"] - 56 * M) < 1 and abs(ce["2"] - 56 * M) < 1, f"{ {e: round(v/M,1) for e, v in ce.items()} }")
    jammed = {k: {**healthy[k], "xfer": 153.6, "t_round": 156.6} for k in ids}                                                     # 4배 느림 → 합 14M
    S8.observe(jammed, 4, {k: 1.0 for k in ids}, sets)
    ce = S8.caps_effective({"1": 56 * M, "2": 56 * M})
    check("④-2 막힌 라운드(합 14M, 접속 합 56 의 1/4)에서 엣지 1 용량이 관측값 ≈ 14M 으로", abs(ce["1"] - 14 * M) < 0.5 * M and abs(ce["2"] - 56 * M) < 1, f"{ {e: round(v/M,1) for e, v in ce.items()} }")
    for _ in range(4):                                                                                                                # 아무도 안 쓰면 1.5 배씩 풀려 정적으로
        S8.observe({}, 4, {}, {k: ("2", "2") for k in ids})
    ce = S8.caps_effective({"1": 56 * M, "2": 56 * M})
    check("④-3 엣지 1 을 아무도 안 쓰면 추정이 풀려 정적 용량으로 돌아온다 (다시 써 볼 수 있게)", abs(ce["1"] - 56 * M) < 1, f"{round(ce['1']/M,1)}M")
    # ④-4 되먹임 (9/9 변동 장면 실측 재현): 엣지 1 이 56M 으로 돌아왔는데 4대가 남아 있고, 계획기가 낮은 추정(20M) 때문에 출구 B(2M)에 6MB 를 줬다.
    #     출구 B 가 24s×2 걸려 기기 전송 53s → 엣지 처리량 4×32MB/53s = 19.3M. 접속 합 28M 의 0.8 = 22.4 보다 작아 "포화"로 읽으면 추정이 20M 에 갇힌다.
    #     지금 분할대로 접속 상한만 있어도 21.3M 밖에 못 내므로(0.8배 = 17.1) 19.3M 은 포화가 아니다 → 창이 비면 추정이 풀려야 한다.
    ids4 = ids[:4]
    S4 = sense.Sensor(ids4)
    for k in ids4:
        S4.set_probe(k, 0.8, 8.39 * M, 1.0); S4.set_access(k, [5 * M, 2 * M])
    S4.set_paths({"1": 56 * M, "2": 56 * M})
    sets4 = {k: ("1", "1") for k in ids4}
    jam4 = {k: {"xfer": 150.0, "cli_fwd": 2, "cli_bwd": 1, "up_bytes": 16e6, "dn_bytes": 16e6, "t_round": 153.0,
                "exits": [{"up": 8e6, "dn": 8e6}, {"up": 8e6, "dn": 8e6}]} for k in ids4}                                        # 막힌 동안: 4×32MB/150s = 6.8M
    for _ in range(3):
        S4.observe(jam4, 4, {k: 1.0 for k in ids4}, sets4)
    ce = S4.caps_effective({"1": 56 * M, "2": 56 * M})
    check("④-4a 막힌 3라운드 뒤 엣지 1 추정 ≈ 6.8M", abs(ce["1"] - 6.8 * M) < 0.5 * M, f"{round(ce['1']/M,1)}M")
    # 복구 뒤(정적 분할 11/4·엣지 56M): 4대 × 7M ≈ 28M ≈ 접속 기대 → 풀림 신호(95% 이상). 추정은 관측값까지, 그 뒤 1.5배씩
    back = {k: {"xfer": 36.6, "cli_fwd": 2, "cli_bwd": 1, "up_bytes": 16e6, "dn_bytes": 16e6, "t_round": 39.6,
                "exits": [{"up": 11.4e6, "dn": 11.4e6}, {"up": 4.6e6, "dn": 4.6e6}]} for k in ids4}
    S4.observe(back, 4, {k: 1.0 for k in ids4}, sets4)
    buf = S4._edge_win["1"]
    check("④-4b 복구 뒤 정적 분할로 28M 관측 — 접속 기대 28M 의 95% 위이므로 풀림", buf[-1][1] is False and abs(buf[-1][0] - 28 * M) < 1.5 * M, f"{[(round(t/M,1), s) for t, s in buf]}")
    e1 = S4.edge_est["1"]
    check("④-5a 풀림 관측 한 번에 추정이 정적으로 튀지 않고 관측값(28M)까지만 오른다 (9/10: 곧장 56M 으로 믿자 되돌려 보내 다시 막힘)", abs(e1 - 28 * M) < 1.5 * M, f"{round(e1/M,1)}M")
    for _ in range(2):
        S4.observe(back, 4, {k: 1.0 for k in ids4}, sets4)
    ce = S4.caps_effective({"1": 56 * M, "2": 56 * M})
    check("④-5 풀림 관측이 이어지면 라운드마다 1.5배씩 올라 3라운드 안에 정적 56M (28 → 42 → 56)", abs(ce["1"] - 56 * M) < 1 and "1" not in S4.edge_est, f"{round(ce['1']/M,1)}M est={S4.edge_est}")
    # ④-9 유지 구간: 막힌 엣지(14M)에 3대가 남으면 관측/기대 = 0.84~0.90 — 포화도 풀림도 아니므로 추정을 그대로 둔다 (올리면 계획기가 2대를 되돌려 보내 81 s, 9/10 R15)
    S3 = sense.Sensor(ids[:3])
    for k in ids[:3]:
        S3.set_probe(k, 0.8, 8.39 * M, 1.0); S3.set_access(k, [5 * M, 2 * M])
    S3.set_paths({"1": 56 * M, "2": 56 * M})
    sets3 = {k: ("1", "1") for k in ids[:3]}
    jam3 = {k: {"xfer": 150.0, "cli_fwd": 2, "cli_bwd": 1, "up_bytes": 16e6, "dn_bytes": 16e6, "t_round": 153.0, "exits": [{"up": 11.4e6, "dn": 11.4e6}, {"up": 4.6e6, "dn": 4.6e6}]} for k in ids[:3]}
    S3.observe(jam3, 4, {k: 1.0 for k in ids[:3]}, sets3)
    mid3 = {k: {**jam3[k], "xfer": 42.0, "t_round": 45.0} for k in ids[:3]}                                                              # 3×32MB/42s = 18.3M vs 기대 21M → 0.87
    S3.observe(mid3, 4, {k: 1.0 for k in ids[:3]}, sets3)
    e3 = S3.edge_est.get("1")
    check("④-9 관측이 기대의 0.87 이면(막힌 엣지에 3대) 추정을 올리지도 내리지도 않는다", e3 is not None and abs(e3 - 5.1 * M) < 0.5 * M, f"{round((e3 or 0)/M,1)}M (막힌 관측 5.1M 유지)")
    # ④-8 두 엣지에 걸친 기기(1+3)의 느린 전송은 어느 엣지에도 귀속하지 않는다 — 엣지 1 이 막혀 느린 기기가 엣지 3 을 포화로 보이게 하면 안 된다
    S5 = sense.Sensor(ids[:2])
    for k in ids[:2]:
        S5.set_probe(k, 0.8, 8.39 * M, 1.0); S5.set_access(k, [5 * M, 2 * M])
    S5.set_paths({"1": 56 * M, "3": 56 * M})
    sets5 = {"c0": ("1", "3"), "c1": ("3", "3")}
    obs5 = {"c0": {"xfer": 150.0, "cli_fwd": 2, "cli_bwd": 1, "up_bytes": 16e6, "dn_bytes": 16e6, "t_round": 153.0, "exits": [{"up": 11.4e6, "dn": 11.4e6}, {"up": 4.6e6, "dn": 4.6e6}]},   # 엣지 1 탓에 느림
            "c1": {"xfer": 36.6, "cli_fwd": 2, "cli_bwd": 1, "up_bytes": 16e6, "dn_bytes": 16e6, "t_round": 39.6, "exits": [{"up": 11.4e6, "dn": 11.4e6}, {"up": 4.6e6, "dn": 4.6e6}]}}   # 엣지 3 은 멀쩡
    S5.observe(obs5, 4, {k: 1.0 for k in ids[:2]}, sets5)
    check("④-8 1+3 기기가 느려도 엣지 3 은 포화로 안 잡힌다 (바이트는 세고 시간은 c1 것만: 9.0M = 기대)", "3" not in S5.edge_est and "1" not in S5.edge_est, f"est={ {e: round(v/M,1) for e, v in S5.edge_est.items()} }")
    # ④-8b 막힌 엣지 1 에 걸친 기기 2대 + 온전한 기기 1대: 걸친 기기의 바이트(부하)는 세되 시간은 온전한 기기 것 → 포화가 잡히고 추정 ≈ 실제 12~14M (걸친 기기 바이트를 빼면 5M 으로 과소)
    S6 = sense.Sensor(ids[:3])
    for k in ids[:3]:
        S6.set_probe(k, 0.8, 8.39 * M, 1.0); S6.set_access(k, [5 * M, 2 * M])
    S6.set_paths({"1": 56 * M, "3": 56 * M})
    sets6 = {"c0": ("1", "1"), "c1": ("1", "3"), "c2": ("1", "3")}
    slow6 = {"xfer": 52.0, "cli_fwd": 2, "cli_bwd": 1, "up_bytes": 16e6, "dn_bytes": 16e6, "t_round": 55.0, "exits": [{"up": 11.4e6, "dn": 11.4e6}, {"up": 4.6e6, "dn": 4.6e6}]}
    S6.observe({k: dict(slow6) for k in ids[:3]}, 4, {k: 1.0 for k in ids[:3]}, sets6)
    e6 = S6.edge_est.get("1")
    check("④-8b 걸친 기기가 실은 부하는 세어 막힌 엣지 추정이 12M 근처 (5M 과소 아님)", e6 is not None and 10 * M < e6 < 15 * M, f"{round((e6 or 0)/M,1)}M")
    # ④-7 막힌 엣지에 2대만 남으면(수요 14 ≤ 14M) 포화가 아니다 — 그래도 추정은 21M(1.5배)까지만 올라야 계획기가 한 번에 3대를 되돌려 보내지 않는다
    S2 = sense.Sensor(ids[:2])
    for k in ids[:2]:
        S2.set_probe(k, 0.8, 8.39 * M, 1.0); S2.set_access(k, [5 * M, 2 * M])
    S2.set_paths({"1": 56 * M, "2": 56 * M})
    sets2 = {k: ("1", "1") for k in ids[:2]}
    jam2 = {k: {"xfer": 150.0, "cli_fwd": 2, "cli_bwd": 1, "up_bytes": 16e6, "dn_bytes": 16e6, "t_round": 153.0, "exits": [{"up": 11.4e6, "dn": 11.4e6}, {"up": 4.6e6, "dn": 4.6e6}]} for k in ids[:2]}   # 3.4M: 막힘
    S2.observe(jam2, 4, {k: 1.0 for k in ids[:2]}, sets2)
    fit2 = {k: {**jam2[k], "xfer": 36.6, "t_round": 39.6} for k in ids[:2]}                                                              # 2대 × 7M = 14M = 용량: 포화 아님
    S2.observe(fit2, 4, {k: 1.0 for k in ids[:2]}, sets2)
    e2 = S2.edge_est.get("1")
    check("④-7 막힌 엣지에 2대만 남아 포화가 안 보여도 추정은 14M(관측)까지만 — 정적 56M 으로 튀지 않는다", e2 is not None and abs(e2 - 14 * M) < 0.7 * M, f"{round((e2 or 0)/M,1)}M")
    # ④-6 진짜 포화는 여전히 잡힌다: 8대 균등 분할(각 출구 8MB)로 엣지 14M — 접속 기대 32M(느린 출구 B 가 64s) 의 0.8 = 25.6 보다 작다
    S8b = sense.Sensor(ids)
    for k in ids:
        S8b.set_probe(k, 0.8, 8.39 * M, 1.0); S8b.set_access(k, [5 * M, 2 * M])
    S8b.set_paths({"1": 56 * M, "2": 56 * M})
    jam8 = {k: {"xfer": 153.6, "cli_fwd": 2, "cli_bwd": 1, "up_bytes": 16.78e6, "dn_bytes": 16.78e6, "t_round": 156.6,
                "exits": [{"up": 8.39e6, "dn": 8.39e6}, {"up": 8.39e6, "dn": 8.39e6}]} for k in ids}
    S8b.observe(jam8, 4, {k: 1.0 for k in ids}, sets)
    ce = S8b.caps_effective({"1": 56 * M, "2": 56 * M})
    check("④-6 출구별 바이트가 있어도 진짜 막힘(14M)은 포화로 잡혀 추정 ≈ 14M", abs(ce["1"] - 14 * M) < 0.5 * M, f"{round(ce['1']/M,1)}M")
    # ⑤ 출구별 활동 구간(up_t/dn_t)이 보고되면 흐름별 실효율로 판정 (§13-5, 2026-09-10): "포화"와 "분할 탓"이 갈린다
    def ex(bA, bB, tA, tB):                      # 출구 A/B 바이트(왕복 합, MB)·활동 구간(초, 왕복 합)
        return [{"up": bA * 5e5, "dn": bA * 5e5, "up_t": tA / 2, "dn_t": tA / 2}, {"up": bB * 5e5, "dn": bB * 5e5, "up_t": tB / 2, "dn_t": tB / 2}]
    S9 = sense.Sensor(ids4)
    for k in ids4:
        S9.set_probe(k, 0.8, 8.39 * M, 1.0); S9.set_access(k, [5 * M, 2 * M])
    S9.set_paths({"1": 56 * M, "3": 56 * M})
    # ⑤-1 건강한 엣지, 치우친 분할(A 20MB·B 12MB): A 는 5M(32 s), B 는 2M(48 s) — 흐름 합 7M×4 = 28M = 접속 합 → 포화 아님 (총 처리량 규칙이면 19.3M 으로 포화 오판)
    skew9 = {k: {"xfer": 48.0, "cli_fwd": 2, "cli_bwd": 1, "up_bytes": 16e6, "dn_bytes": 16e6, "t_round": 51.0, "exits": ex(20, 12, 32.0, 48.0)} for k in ids4}
    S9.observe(skew9, 4, {k: 1.0 for k in ids4}, sets4)
    b9 = S9._edge_win["1"][-1]
    check("⑤-1 건강한 엣지에서 분할이 치우쳐도 흐름별 실효율 합(28M) = 접속 합 → 포화 아님 (값은 합집합 기준 21.3M 으로 기록, §13-6)", b9[1] is False and abs(b9[0] - 21.3 * M) < 1.5 * M and "1" not in S9.edge_est, f"{round(b9[0]/M,1)}M sat={b9[1]}")
    # ⑤-2 막힌 엣지(14M, 4대 8흐름): 흐름마다 1.75M 씩 — 합 14M < 0.8×28 → 포화, 추정 ≈ 14M
    jam9 = {k: {"xfer": 146.0, "cli_fwd": 2, "cli_bwd": 1, "up_bytes": 16e6, "dn_bytes": 16e6, "t_round": 149.0, "exits": ex(16, 16, 73.1, 73.1)} for k in ids4}
    S9.observe(jam9, 4, {k: 1.0 for k in ids4}, sets4)
    ce9 = S9.caps_effective({"1": 56 * M, "3": 56 * M})
    check("⑤-2 막힌 엣지: 흐름 합 14M → 포화, 추정 ≈ 14M", abs(ce9["1"] - 14 * M) < 1.0 * M, f"{round(ce9['1']/M,1)}M")
    # ⑤-3 걸친 기기(1+3): 출구 A 는 막힌 엣지 1(1.75M), 출구 B 는 건강한 엣지 3(2M) — 엣지 3 은 포화 아님, 엣지 1 은 포화 (총 처리량 규칙에서는 엣지 3 이 오염됐다)
    S10 = sense.Sensor(ids[:2])
    for k in ids[:2]:
        S10.set_probe(k, 0.8, 8.39 * M, 1.0); S10.set_access(k, [5 * M, 2 * M])
    S10.set_paths({"1": 56 * M, "3": 56 * M})
    sets10 = {"c0": ("1", "3"), "c1": ("1", "1")}
    obs10 = {"c0": {"xfer": 100.0, "cli_fwd": 2, "cli_bwd": 1, "up_bytes": 16e6, "dn_bytes": 16e6, "t_round": 103.0, "exits": ex(20, 12, 91.4, 48.0)},
             "c1": {"xfer": 100.0, "cli_fwd": 2, "cli_bwd": 1, "up_bytes": 16e6, "dn_bytes": 16e6, "t_round": 103.0, "exits": ex(16, 16, 73.1, 73.1)}}
    S10.observe(obs10, 4, {k: 1.0 for k in ids[:2]}, sets10)
    check("⑤-3 걸친 기기의 흐름은 제 엣지에만 귀속: 엣지 1 포화(≈6M), 엣지 3 은 포화 아님", "1" in S10.edge_est and S10.edge_est["1"] < 10 * M and "3" not in S10.edge_est, f"est={ {e: round(v/M,1) for e, v in S10.edge_est.items()} }")
    # ⑤-4 엇갈린 흐름: 막힌 엣지(14M)에서 B 흐름(4MB)이 먼저 끝나고 A 흐름이 뒤에 빨라지면 흐름별 속도 합은 24M 처럼 커 보이지만 용량 값은 바이트 합/가장 긴 구간 ≈ 14M 이어야 한다 (§13-6)
    S11 = sense.Sensor(ids)
    for k in ids:
        S11.set_probe(k, 0.8, 8.39 * M, 1.0); S11.set_access(k, [5 * M, 2 * M])
    S11.set_paths({"1": 56 * M, "3": 56 * M})
    stag = {k: {"xfer": 146.0, "cli_fwd": 2, "cli_bwd": 1, "up_bytes": 16e6, "dn_bytes": 16e6, "t_round": 149.0, "exits": ex(24, 8, 146.0, 40.0)} for k in ids}   # A 24MB/146s(1.3M) + B 8MB/40s(1.6M): 흐름 합 2.9M×8 = 23M, 실제 합집합 = 256MB/146s = 14M
    S11.observe(stag, 4, {k: 1.0 for k in ids}, sets)
    ce11 = S11.caps_effective({"1": 56 * M, "3": 56 * M})
    check("⑤-4 엇갈린 흐름에서도 용량 값은 합집합 기준 ≈ 14M (흐름 합 23M 이 아니라)", abs(ce11["1"] - 14 * M) < 1.5 * M, f"{round(ce11['1']/M,1)}M")
    # ④-10 되돌아가기 탐침 물러서기 (§13-7, 9/11 rerun8): 막힌 엣지(14M)에 2대 남아 풀림(비율 1.0) → 추정 21M → 계획기가 1대 되돌림 → 다시 막힘(14M) 이 2~3라운드마다 반복(75/68/67 s).
    #      추정을 키운 뒤 3라운드 안에 다시 막히고 용량이 나아지지 않았으면 4라운드 동안 키우지 않는다.
    S12 = sense.Sensor(ids[:3])
    for k in ids[:3]:
        S12.set_probe(k, 0.8, 8.39 * M, 1.0); S12.set_access(k, [5 * M, 2 * M])
    S12.set_paths({"1": 56 * M, "2": 56 * M})
    two = {k: ("1", "1") for k in ids[:2]}; three = {k: ("1", "1") for k in ids[:3]}
    jam3f = {k: {"xfer": 150.0, "cli_fwd": 2, "cli_bwd": 1, "up_bytes": 16e6, "dn_bytes": 16e6, "t_round": 153.0, "exits": ex(16, 16, 100.0, 100.0)} for k in ids[:3]}   # 3대 각 32MB/100s → 합집합 값 ≈ 7.7M, 비율 0.4
    fit2f = {k: {"xfer": 36.6, "cli_fwd": 2, "cli_bwd": 1, "up_bytes": 16e6, "dn_bytes": 16e6, "t_round": 39.6, "exits": ex(22.8, 9.2, 36.5, 36.8)} for k in ids[:2]}   # 2대: 흐름 A 5M·B 2M → 비율 1.0 (풀림)
    S12.observe(jam3f, 4, {k: 1.0 for k in ids[:3]}, three); e_a = S12.edge_est["1"]
    S12.observe(fit2f, 4, {k: 1.0 for k in ids[:2]}, two); e_b = S12.edge_est["1"]
    check("④-10a 2대 남아 풀림이 보이면 추정이 오른다 (탐침: 관측값 13.9M 까지, 최소 1.5배)", e_b >= 1.5 * e_a - 0.1 * M and abs(e_b - 13.9 * M) < 0.7 * M, f"{round(e_a/M,1)} → {round(e_b/M,1)}M")
    S12.observe(jam3f, 4, {k: 1.0 for k in ids[:3]}, three); e_c = S12.edge_est["1"]                                                       # 되돌린 1대 때문에 다시 막힘
    for _ in range(4):
        S12.observe(fit2f, 4, {k: 1.0 for k in ids[:2]}, two)
    e_d = S12.edge_est["1"]
    check("④-10b 탐침 뒤 다시 막히면 4라운드 동안 풀림이 보여도 추정을 키우지 않는다", abs(e_c - e_a) < 0.5 * M and abs(e_d - e_c) < 0.1 * M, f"막힘 {round(e_c/M,1)}M, 4R 풀림 뒤 {round(e_d/M,1)}M")
    S12.observe(fit2f, 4, {k: 1.0 for k in ids[:2]}, two); e_e = S12.edge_est["1"]
    check("④-10c 물러서기가 끝나면 다시 키운다", e_e > e_d * 1.4, f"{round(e_d/M,1)} → {round(e_e/M,1)}M")
    # ④-11 실제 되올림(변동): 키운 뒤 다시 막혀도 용량이 1.1배 넘게 올랐으면 물러서기 없음
    S13 = sense.Sensor(ids[:3])
    for k in ids[:3]:
        S13.set_probe(k, 0.8, 8.39 * M, 1.0); S13.set_access(k, [5 * M, 2 * M])
    S13.set_paths({"1": 56 * M, "2": 56 * M})
    S13.observe(jam3f, 4, {k: 1.0 for k in ids[:3]}, three); S13.observe(fit2f, 4, {k: 1.0 for k in ids[:2]}, two)
    up3 = {k: {**jam3f[k], "xfer": 50.0, "t_round": 53.0, "exits": ex(16, 16, 50.0, 50.0)} for k in ids[:3]}                              # 되올라 3대 각 32MB/50s → 값 15.4M (> 1.1×7.7)
    S13.observe(up3, 4, {k: 1.0 for k in ids[:3]}, three); e_f = S13.edge_est["1"]
    S13.observe(fit2f, 4, {k: 1.0 for k in ids[:2]}, two); e_g = S13.edge_est["1"]
    check("④-11 용량이 실제로 오른 뒤 다시 막힌 경우는 물러서기 없이 계속 키운다 (변동 되올림)", abs(e_g - 1.5 * e_f) < 0.1 * M, f"{round(e_f/M,1)} → {round(e_g/M,1)}M")

    print(f"\n== {'전부 통과' if fails == 0 else f'실패 {fails}건'} ==")
    return 0 if fails == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
