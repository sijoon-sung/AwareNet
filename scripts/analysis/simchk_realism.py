# -*- coding: utf-8 -*-
"""simchk_realism — 시뮬레이터 모수가 실측과 맞는지 **직접 재서** 대조한다.

  묻는 것:
    1) sim.py 의 noise=0.10 / drift=0.05 가 실측 라운드간 변동과 맞나?
       (같은 클라·같은 폭에서 comp / xfer 가 라운드마다 몇 % 흔들리는지)
    2) 실측 '균질' 조건에서 클라간 퍼짐이 얼마나 되나? (min 마감선의 먹이)
    3) bytes1 / srv_per_batch / 회선 범위가 실측과 맞나?
  원본 sim.py 는 건드리지 않는다.
"""
import io
import json
import math
import os
import statistics as st
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def rows(name):
    p = os.path.join(ROOT, "out", name)
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in io.open(p, encoding="utf-8") if '"round"' in l]


def cv(v):
    v = [x for x in v if x and x > 0]
    if len(v) < 3:
        return None
    return st.pstdev(v) / st.mean(v)


# ── 1. 라운드간 변동 (같은 클라, 폭 고정) ────────────────────────
def series_from_detail(rs, key_fn):
    """폭이 1.0 으로 고정된 라운드만 모은다. k -> [값]"""
    out = {}
    for r in rs:
        plan = r.get("plan", {})
        det = r.get("per_client_detail") or {}
        for k, d in det.items():
            if abs(plan.get(k, 1.0) - 1.0) > 1e-9:
                continue
            out.setdefault(k, []).append(key_fn(d))
    return out


def series_from_percli(rs, idx):
    out = {}
    for r in rs:
        plan = r.get("plan", {})
        for k, v in r.get("per_client", {}).items():
            if abs(plan.get(k, 1.0) - 1.0) > 1e-9:
                continue
            out.setdefault(k, []).append(v[idx])
    return out


DETAIL_FILES = [
    ("e11_uniform.jsonl", "N=4 무제한망(로컬), 폭 1.0 고정"),
    ("e10_N4_p1.00_srv.jsonl", "N=4 netem 20~80M, 폭 1.0 고정"),
    ("e10_N8_p1.00_srv.jsonl", "N=8 netem, 폭 1.0 고정"),
    ("e10_N2_p1.00_srv.jsonl", "N=2, 폭 1.0"),
]
PLAIN_FILES = [
    ("g2_same_s1_uniform.jsonl", "조건1 동일회선 40M N=4"),
    ("g2_static_uniform.jsonl", "조건2 이질 20/40/60/80 N=4"),
    ("g2_step_s1_uniform.jsonl", "조건3 교란 N=4"),
    ("cond4_N8_20-80M/uniform.jsonl", "조건4 이질 N=8"),
]


def part1():
    print("=" * 96)
    print("  [1] 라운드간 변동 — 같은 클라·같은 폭에서 값이 몇 % 흔들리나 (CV, 첫 라운드 제외)")
    print("      sim.py 는 관측잡음 10% + drift 5% 를 가정한다 → 합성 CV 약 11~12%")
    print("=" * 96)
    allcv = {"comp": [], "xfer": [], "t_comm": []}
    for fn, tag in DETAIL_FILES:
        rs = rows(fn)
        if len(rs) < 4:
            print(f"  {fn:32s} 라운드 부족 ({len(rs)}) — 건너뜀")
            continue
        rs = rs[1:]                       # R0 은 워밍업(첫 접속·JIT) → 제외
        comp = series_from_detail(rs, lambda d: d["cli_fwd"] + d["cli_bwd"])
        xfer = series_from_detail(rs, lambda d: d["xfer"])
        tcm = series_from_detail(rs, lambda d: d["t_comm"])
        cc = [cv(v) for v in comp.values()]
        cx = [cv(v) for v in xfer.values()]
        ct = [cv(v) for v in tcm.values()]
        cc = [c for c in cc if c is not None]
        cx = [c for c in cx if c is not None]
        ct = [c for c in ct if c is not None]
        if not cc:
            print(f"  {fn:32s} 표본 부족 — 건너뜀")
            continue
        allcv["comp"] += cc
        allcv["xfer"] += cx
        allcv["t_comm"] += ct
        print(f"\n  {tag}  ({fn}, R{rs[0]['round']}~R{rs[-1]['round']}, "
              f"{len(list(comp.values())[0])}점/클라)")
        print(f"      comp   CV  중앙 {st.median(cc)*100:5.1f}%   범위 "
              f"{min(cc)*100:4.1f}~{max(cc)*100:5.1f}%")
        if cx:
            print(f"      xfer   CV  중앙 {st.median(cx)*100:5.1f}%   범위 "
                  f"{min(cx)*100:4.1f}~{max(cx)*100:5.1f}%")
        if ct:
            print(f"      t_comm CV  중앙 {st.median(ct)*100:5.1f}%   범위 "
                  f"{min(ct)*100:4.1f}~{max(ct)*100:5.1f}%")

    for fn, tag in PLAIN_FILES:
        rs = rows(fn)
        if len(rs) < 4:
            continue
        rs = rs[1:]
        comp = series_from_percli(rs, 1)
        tcm = series_from_percli(rs, 3)
        cc = [c for c in (cv(v) for v in comp.values()) if c is not None]
        ct = [c for c in (cv(v) for v in tcm.values()) if c is not None]
        if not cc:
            continue
        allcv["comp"] += cc
        allcv["t_comm"] += ct
        print(f"\n  {tag}  ({fn}, {len(rs)}라운드)")
        print(f"      comp   CV  중앙 {st.median(cc)*100:5.1f}%   범위 "
              f"{min(cc)*100:4.1f}~{max(cc)*100:5.1f}%")
        print(f"      t_comm CV  중앙 {st.median(ct)*100:5.1f}%   범위 "
              f"{min(ct)*100:4.1f}~{max(ct)*100:5.1f}%")

    print("\n  ── 전체 종합 ──")
    for k, v in allcv.items():
        if v:
            print(f"      {k:7s} 클라 {len(v):3d}개  CV 중앙 {st.median(v)*100:5.1f}%  "
                  f"평균 {st.mean(v)*100:5.1f}%  최대 {max(v)*100:5.1f}%")
    return allcv


# ── 2. 실측 '균질' 조건의 클라간 퍼짐 ────────────────────────────
def part2():
    print("\n" + "=" * 96)
    print("  [2] 실측에서 '균질'은 얼마나 균질한가 — 클라간 퍼짐 (min 마감선이 먹는 것)")
    print("      sim 의 dist='homogeneous' 는 클라간 참값 차이를 0 으로 둔다")
    print("=" * 96)
    for fn, tag in [("g2_same_s1_uniform.jsonl", "조건1 동일회선 N=4"),
                    ("e11_uniform.jsonl", "e11 N=4 로컬"),
                    ("e10_N8_p1.00_srv.jsonl", "e10 N=8 (동일 netem)")]:
        rs = rows(fn)
        if len(rs) < 3:
            continue
        rs = rs[1:]
        # 클라별 라운드 평균 총시간
        tot = {}
        for r in rs:
            det = r.get("per_client_detail")
            if det:
                for k, d in det.items():
                    tot.setdefault(k, []).append(d["cli_fwd"] + d["cli_bwd"] + d["xfer"])
            else:
                for k, v in r.get("per_client", {}).items():
                    tot.setdefault(k, []).append(v[3])
        m = {k: st.mean(v) for k, v in tot.items()}
        vals = sorted(m.values())
        cross = st.pstdev(vals) / st.mean(vals)
        print(f"\n  {tag} ({fn})")
        print("      클라별 평균 총시간: " + "  ".join(f"{k}={m[k]:.2f}s" for k in sorted(m)))
        print(f"      최대/최소 = {vals[-1]/vals[0]:.2f}배,  클라간 CV = {cross*100:.1f}%")
    print("\n  ★ 클라간 CV 가 라운드간 CV 보다 크면 '균질' 판은 실측에 존재하지 않는다.")


# ── 3. 규모별 min 통계량이 얼마나 밀리나 (해석식 + 몬테카를로) ────
def part3(sigma_list):
    print("\n" + "=" * 96)
    print("  [3] 잡음 크기 -> 마감선 붕괴  (해석: cut 조건은  eps_k > alpha-1 - alpha*c_N*sigma)")
    print("      alpha=1.2, c_N = E[-min of N standard normals] (몬테카를로 20k)")
    print("=" * 96)
    import random
    rng = random.Random(7)
    NS = [4, 16, 64, 256, 1024]
    cN = {}
    for n in NS:
        s = 0.0
        for _ in range(20000):
            s += -min(rng.gauss(0, 1) for _ in range(n))
        cN[n] = s / 20000
    print("      c_N : " + "  ".join(f"N={n}:{cN[n]:.2f}" for n in NS))
    print(f"\n  {'sigma':>8s} " + " ".join(f"{('N=' + str(n)):>8s}" for n in NS))
    for sg in sigma_list:
        cells = []
        for n in NS:
            thr = (0.2 - 1.2 * cN[n] * sg) / sg
            # P(eps > thr)  eps~N(0,1)
            p = 0.5 * math.erfc(thr / math.sqrt(2))
            cells.append(p)
        print(f"  {sg*100:6.1f}%  " + " ".join(f"{c*100:7.0f}%" for c in cells))
    print("\n  ★ 이 표가 '균질한 판에서 몇 %가 잘리나'의 1라운드 근사다.")


# ══════════════════════════════════════════════════════════════════
#  아래는 시뮬레이터 쪽 — 같은 잣대로 재서 실측과 대조한다.
#  원본 sim.py 는 import 만 하고 수정하지 않는다.
# ══════════════════════════════════════════════════════════════════
sys.path.insert(0, os.path.join(ROOT, "sfl"))


def sim_cv(noise=0.10, drift=0.05, dist="homogeneous", n=8, rounds=8, seed=1):
    """sim.World 를 폭 1.0 고정으로 굴려 실측과 **같은 방식**으로 CV 를 잰다."""
    from sim import World
    w = World(n, seed=seed, dist=dist, noise=noise, drift=drift)
    pv = {k: 1.0 for k in w.ks}
    qv = {k: 0 for k in w.ks}
    comp, xfer, tot, true_T = {}, {}, {}, {}
    for _ in range(rounds):
        ms, obs, T = w.run(pv, qv)
        for k, d in obs.items():
            comp.setdefault(k, []).append(d["cli_fwd"] + d["cli_bwd"])
            xfer.setdefault(k, []).append(d["xfer"])
            tot.setdefault(k, []).append(d["cli_fwd"] + d["cli_bwd"] + d["xfer"])
            true_T.setdefault(k, []).append(T[k])
    f = lambda dd: st.median([c for c in (cv(v) for v in dd.values()) if c is not None])  # noqa: E731
    return {"comp": f(comp), "xfer": f(xfer), "obs_total": f(tot), "true_T": f(true_T)}


def part4(real):
    print("\n" + "=" * 96)
    print("  [4] 시뮬레이터를 **실측과 같은 잣대로** 재서 대조")
    print("=" * 96)
    print(f"  {'noise/drift':>14s} {'comp CV':>9s} {'xfer CV':>9s} {'관측총합 CV':>12s} "
          f"{'참T CV':>9s}")
    for nz, dr in [(0.10, 0.05), (0.05, 0.03), (0.03, 0.02), (0.0, 0.0)]:
        r = sim_cv(nz, dr)
        print(f"  {nz*100:5.0f}% /{dr*100:4.0f}% {r['comp']*100:8.1f}% "
              f"{r['xfer']*100:8.1f}% {r['obs_total']*100:11.1f}% {r['true_T']*100:8.1f}%")
    print("\n  실측(같은 잣대):")
    for k in ("comp", "xfer", "t_comm"):
        if real.get(k):
            print(f"      {k:7s} CV 중앙 {st.median(real[k])*100:5.1f}%  "
                  f"(클라 {len(real[k])}개)")
    print("\n  ★ sim 의 comp CV 는 관측잡음 10% 를 0.4/0.6 으로 두 번 뽑아 상쇄되므로")
    print("    실제로는 약 7% 다. 실측 comp CV(조건1 12%, 조건2~4 20~28%)보다 **작다**.")
    print("    반대로 sim 의 xfer CV(약 10%)는 e11 실측(9.9%)과 거의 같다.")


def sim_cut(noise, drift, n, dist="homogeneous", seeds=(1, 2, 3), rounds=8, alpha=1.2):
    """S1 과 같은 규칙(폭만·min 마감선)을 잡음만 바꿔 돌린다. 좁힌 비율 반환."""
    from run_s2 import RefController, REFS
    from sim import World
    ref = REFS["min (현행)"]
    outs = []
    for s in seeds:
        w = World(n, seed=s, dist=dist, noise=noise, drift=drift)
        ctl = RefController(w.ks, ref, alpha=alpha)
        pv = {k: 1.0 for k in w.ks}
        for r in range(rounds):
            if r >= 1:
                pv = ctl.decide(w.batches)
            ms, obs, T = w.run(pv, {k: 0 for k in w.ks})
            ctl.observe(obs, w.batches)
        outs.append(sum(1 for v in pv.values() if v < 1.0) / n)
    return sum(outs) / len(outs)


def part5():
    print("\n" + "=" * 96)
    print("  [5] ★ 잡음을 실측값으로 바꾸면 붕괴가 남는가 (dist=homogeneous, 좁힌 비율)")
    print("=" * 96)
    NS = [4, 16, 64, 256, 1024]
    print(f"  {'noise/drift':>14s} " + " ".join(f"{('N=' + str(n)):>8s}" for n in NS))
    rowsout = {}
    for nz, dr, tag in [(0.10, 0.05, "sim 기본"),
                        (0.064, 0.05, "xfer 실측(e11 9.9%)에 맞춘 값"),
                        (0.05, 0.03, ""),
                        (0.03, 0.02, ""),
                        (0.02, 0.01, ""),
                        (0.0, 0.0, "잡음 완전 제거")]:
        cells = [sim_cut(nz, dr, n) for n in NS]
        rowsout[(nz, dr)] = cells
        print(f"  {nz*100:5.1f}% /{dr*100:4.1f}% " +
              " ".join(f"{c*100:7.0f}%" for c in cells) + ("   " + tag if tag else ""))
    return rowsout


def part6():
    print("\n" + "=" * 96)
    print("  [6] 시뮬 분포 vs FedScale 실측 50만 클라 (data/fedscale/client_device_capacity)")
    print("=" * 96)
    import pickle
    p = os.path.join(ROOT, "data", "fedscale", "client_device_capacity")
    with open(p, "rb") as f:
        d = pickle.load(f)
    bw = sorted(v["communication"] / 1000.0 for v in d.values())     # kbps -> Mbps
    cp = sorted(float(v["computation"]) for v in d.values())

    def pc(v, f):
        return v[int(f * (len(v) - 1))]
    print(f"  FedScale 대역폭(Mbps): p5 {pc(bw,.05):7.2f}  p25 {pc(bw,.25):7.2f}  "
          f"p50 {pc(bw,.50):7.2f}  p75 {pc(bw,.75):7.2f}  p95 {pc(bw,.95):7.2f}")
    print(f"                         p95/p5 = {pc(bw,.95)/pc(bw,.05):5.1f}배,  "
          f"p50/p5 = {pc(bw,.50)/pc(bw,.05):4.1f}배")
    print(f"  FedScale 연산능력    : p5 {pc(cp,.05):7.1f}  p50 {pc(cp,.50):7.1f}  "
          f"p95 {pc(cp,.95):7.1f}   (p95/p5 = {pc(cp,.95)/pc(cp,.05):.1f}배)")

    from sim import World
    for dist in ("lognormal", "few_stragglers", "uniform_span", "homogeneous"):
        w = World(4096, seed=1, dist=dist)
        lb = sorted(v / 1e6 for v in w.link.values())
        lc = sorted(w.cpu.values())
        print(f"\n  sim dist={dist:15s} 회선(Mbps): p5 {pc(lb,.05):7.2f}  "
              f"p50 {pc(lb,.50):7.2f}  p95 {pc(lb,.95):7.2f}  → p95/p5 "
              f"{pc(lb,.95)/max(pc(lb,.05),1e-9):5.1f}배")
        print(f"  {'':22s}연산(s/batch): p5 {pc(lc,.05):6.3f}  p50 {pc(lc,.50):6.3f}  "
              f"p95 {pc(lc,.95):6.3f}  → p95/p5 {pc(lc,.95)/pc(lc,.05):5.1f}배")
    print("\n  ★ FedScale 중앙 대역폭 6.1Mbps / 26%가 3Mbps 미만.")
    print("    sim 의 lognormal 중앙 66Mbps·p95/p5 7배는 실배치보다 **훨씬 균질하고 빠르다.**")


def part7():
    print("\n" + "=" * 96)
    print("  [7] 실측 모수 대조표")
    print("=" * 96)
    # 배치당 바이트
    rs = rows("g2_same_s1_uniform.jsonl")
    b = rs[1]["per_client"]
    k = sorted(b)[0]
    print(f"  배치당 바이트   실측 {b[k][2]/b[k][0]/1e6:6.2f} MB (조건1 로그)   "
          f"sim bytes1 = 8.39 MB")
    rs2 = rows("e11_uniform.jsonl")
    det = rs2[1]["per_client_detail"]
    k2 = sorted(det)[0]
    B = rs2[1]["per_client"][k2][0]
    print(f"                  실측 {(det[k2]['up_bytes']+det[k2]['dn_bytes'])/B/1e6:6.2f} MB "
          f"(e11, up+dn)")
    # 서버 배치당
    srv = [d["srv_gpu"] for r in rs2[1:] for d in r["per_client_detail"].values()]
    lw = [d["lock_wait"] for r in rs2[1:] for d in r["per_client_detail"].values()]
    print(f"  서버 배치당     실측 srv_gpu 중앙 {st.median(srv)/B:6.4f} s/batch  "
          f"lock_wait 중앙 {st.median(lw):6.3f} s   sim srv_per_batch = 0.02")
    # 고정비용
    ela = [rs2[i]["elapsed"] - rs2[i - 1]["elapsed"] - rs2[i]["makespan"]
           for i in range(2, len(rs2))]
    print(f"  라운드 고정비용 실측 {st.median(ela):6.2f} s (elapsed 간격 - makespan)   "
          f"sim fixed_cost = 0.5")
    # 회선
    rs3 = rows("e10_N4_p1.00_srv.jsonl")
    for r in rs3[1:2]:
        for kk, d in sorted(r["per_client_detail"].items())[:2]:
            Bb = r["per_client"][kk][0]
            mbps = d["up_bytes"] * 8 / d["xfer"] / 1e6
            print(f"  실효 업링크     실측 {kk} {mbps:6.1f} Mbps (e10 netem 20~80M 설정)   "
                  f"sim link 20~80 Mbps")


if __name__ == "__main__":
    real = part1()
    part2()
    part3([0.02, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20])
    part4(real)
    part5()
    part6()
    part7()
