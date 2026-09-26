# -*- coding: utf-8 -*-
"""실험을 걸기 전에 모형으로 먼저 예측한다 — "이 조건에서 이 팔이 이길 수 있나?"

    python scripts/analysis/predict_gain.py h5m h5m5          # 원장 조건에서 팔별 예상 총비용·라운드 시간
    python scripts/analysis/predict_gain.py --search 4         # 4대 접속 회선 조합을 훑어 분할 전송 이득이 큰 조건을 찾는다

왜 있나 (2026-09-07): h5m(접속 전원 50, 경로 60/60)은 모형상 분할 전송 이득이 0 이다 — TCP 공정 분배에서 두 경로를 연
기기는 "두 경로의 사용자"로 세어져 남들 몫을 그만큼 가져가므로, 동질 집단에서는 통째 이동과 총비용이 같거나 오히려 나쁘다.
분할이 이기는 자리는 접속이 작은 기기들이 경로를 다 못 채워 **남는 용량**이 있을 때다. 이 도구는 그 자리를 실험 전에 찾는다.
계획기(plan.py)를 라운드마다 돌려 수렴시킨 뒤의 값이므로, 계획기 규칙(문턱·한 대 이동)까지 포함한 예측이다.
"""
import argparse
import io
import itertools
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "sfl"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "exp"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import plan  # noqa: E402

M = 1e6


def _acc(tok):
    """접속 토큰: 50 → 50e6 (한 가닥) / "50/20" → [50e6, 20e6] (두 가닥, 출구 A/B)."""
    t = str(tok)
    return [float(x) * M for x in t.split("/")] if "/" in t else float(t) * M
BYTES_PER_BATCH = 8.39 * M          # 실측: 배치당 왕복 바이트 (h5 계열, cut=2, batch 32)
CPU_FULL = 0.30                     # 실측: 전폭 1배치 순·역전파 초 (HPC 스레드 3~4)


def profile(speed_list, acc_list, cpu_full=CPU_FULL, bytes_b=BYTES_PER_BATCH):
    ks = [f"c{i}" for i in range(len(speed_list))]
    return {"cpu": {k: cpu_full / max(s, 1e-6) for k, s in zip(ks, speed_list)},
            "gamma": {k: 1.2 for k in ks}, "bytes": {k: bytes_b for k in ks},
            "access": {k: _acc(a) for k, a in zip(ks, acc_list)}}


def converge(prof, caps, multipath, ladder=(1.0,), rounds=12, max_moves=1, alpha=1.2):
    """전원 경로 1 에서 시작해 계획기를 rounds 번 돌린 결과 (마지막 라운드 예측)와 라운드별 총비용."""
    ks = sorted(prof["cpu"])
    st = {"sets": {k: ("1",) for k in ks}, "widths": {k: 1.0 for k in ks}, "raise_ok": {}}
    hist, res = [], None
    for r in range(rounds):
        res = plan.plan(prof, st, caps, ladder=ladder, alpha=alpha, max_moves=max_moves, multipath=multipath, remaining=rounds - r)
        st = {"sets": res["sets"], "widths": res["widths"], "raise_ok": res["raise_ok"], "ref_sets": res["ref_sets"]}
        hist.append(res["cost"])
    return res, hist


def uniform_cost(prof, caps):
    ks = sorted(prof["cpu"])
    t = plan.round_times({k: 1.0 for k in ks}, {k: ("1",) for k in ks}, prof, caps)
    return plan.total_cost(t), max(t.values())


def report(name, prof, caps, ladder):
    u_cost, u_ms = uniform_cost(prof, caps)
    print(f"== {name}: 접속 {[(round(v/M) if not isinstance(v, list) else [round(x/M) for x in v]) for v in prof['access'].values()]}  경로 {[round(c/M) for c in caps.values()]}  연산 {[round(v,2) for v in prof['cpu'].values()]}")
    print(f"   균등(전원 경로 1, 전폭)      총비용 {u_cost:6.2f}s  라운드 {u_ms:5.2f}s")
    rows = []
    for arm, mp, lad in (("경로만(이진)", False, (1.0,)), ("분할 전송", True, (1.0,)), ("폭+경로", False, ladder), ("폭+분할", True, ladder)):
        res, hist = converge(prof, caps, mp, lad)
        sets = ["+".join(res["sets"][k]) for k in sorted(res["sets"])]
        w = [res["widths"][k] for k in sorted(res["widths"])]
        print(f"   {arm:14s} 총비용 {res['cost']:6.2f}s ({100*(res['cost']/u_cost-1):+5.1f}%)  라운드 {res['makespan']:5.2f}s ({100*(res['makespan']/u_ms-1):+5.1f}%)  경로 {sets} 폭 {w}  수렴 {next((i for i,c in enumerate(hist) if abs(c-hist[-1])<1e-6), len(hist))}R")
        rows.append((arm, res["cost"], res["makespan"]))
    d = dict((a, c) for a, c, _ in rows)
    gain = 100 * (1 - d["분할 전송"] / d["경로만(이진)"])
    print(f"   → 분할 전송이 경로만(이진)보다 총비용 {gain:+.1f}%  {'(10% 문턱 넘음 — 실험할 가치 있음)' if gain >= 10 else '(10% 미만 — 이 조건으로는 분할 이득을 보일 수 없다)'}")
    return gain


def from_ledger(name):
    import cond
    r = cond.resolve(name)
    g = lambda k, d=None: r[k]["v"] if k in r else d
    n = g("clients")
    prof = profile(g("speed_list") or [1] * n, g("acc_list") or [50] * n)
    caps = {str(i + 1): c * M for i, c in enumerate(g("caps"))}
    return prof, caps, tuple(g("ladder"))


def search(n, caps_mbps=(60, 60), choices=(10, 20, 30, 50, 80), top=8):
    caps = {str(i + 1): c * M for i, c in enumerate(caps_mbps)}
    out = []
    for acc in itertools.combinations_with_replacement(choices, n):
        prof = profile([1] * n, acc)
        rb, _ = converge(prof, caps, False)
        rm, _ = converge(prof, caps, True)
        gain = 100 * (1 - rm["cost"] / rb["cost"])
        out.append((gain, acc, rb["cost"], rm["cost"], ["+".join(rm["sets"][k]) for k in sorted(rm["sets"])]))
    out.sort(reverse=True)
    print(f"== {n}대, 경로 {list(caps_mbps)} — 분할 전송(모형) 이득 상위 {top}")
    for gain, acc, cb, cm, sets in out[:top]:
        print(f"   접속 {list(acc)}  이진 {cb:6.2f}s → 분할 {cm:6.2f}s  이득 {gain:+5.1f}%  배정 {sets}")
    print(f"   (조합 {len(out)}개 중 이득 ≥10%: {sum(1 for o in out if o[0] >= 10)}개)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("conds", nargs="*")
    ap.add_argument("--search", type=int, metavar="N")
    ap.add_argument("--caps", default="60,60")
    a = ap.parse_args()
    if a.search:
        search(a.search, tuple(int(x) for x in a.caps.split(",")))
    for c in a.conds:
        prof, caps, ladder = from_ledger(c)
        report(c, prof, caps, ladder)
    if not a.search and not a.conds:
        ap.print_help()


if __name__ == "__main__":
    main()
