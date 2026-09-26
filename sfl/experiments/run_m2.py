# -*- coding: utf-8 -*-
"""M2 — 경로 배정이 **폭의 학습 대가를 줄여주는가.** (폭×경로 상호작용의 첫 실측)

  같은 폭 컨트롤러(--policy ours)를 켜둔 채 경로 배정만 바꾼다:
      (A) 무작위 배정 ×3시드 — 느린 경로에 탄 클라가 낙오자가 되고, 컨트롤러가
          폭을 깎아 makespan 을 구한다. 시간은 회복되지만 학습(폭)을 대가로 낸다
      (B) 탐욕(LPT) 배정 — 낙오자 자체가 안 생겨 폭을 깎을 이유가 없다

  사전 등록 판정: 평균 폭(후반 4라운드, 전 클라 평균)이
      widthB − mean(widthA) ≥ +0.15  AND  msB ≤ mean(msA) × 1.10
  미달이면 8번 문서 킬 기준대로 "M1만 남기고 폐기".

  폭 = 라운드당 학습량의 대리(등록된 논리) — TTA 장기 실측은 E9/R6 의 몫.

      sudo ~/sflenv/bin/python sfl/experiments/run_m2.py
"""
import argparse
import io
import json
import os
import random
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from paths import assign_greedy                                  # noqa: E402
from run_g2 import OUT, ROOT, SERVER_IP, client_threads         # noqa: E402

PY = sys.executable
N = 4
PSH = os.path.join(ROOT, "sfl", "net", "paths.sh")


def psh(args):
    subprocess.run(["sh", PSH] + args, check=True)


def run_ours(tag, caps, assign, a):
    """경로 배정 고정 + 폭 컨트롤러 가동 → (makespan 평균, 평균 폭, 마지막 배정)."""
    psh(["setup", " ".join(str(c) for c in caps)])
    psh(["assign", " ".join(str(assign[f"c{i}"]) for i in range(N))])
    slog = os.path.join(OUT, f"m2_{tag}.jsonl")
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "sfl"))
    srv = subprocess.Popen(
        [PY, os.path.join(ROOT, "sfl", "fed_server.py"), "--clients", str(N),
         "--rounds", str(a.rounds), "--batches", str(a.batches), "--cut", "2",
         "--policy", "ours", "--port", str(a.port), "--target", "0.99",
         "--device", "cuda", "--log", slog, "--seed", "1"], env=env, cwd=ROOT)
    time.sleep(10)
    cs = [subprocess.Popen(
        [PY, os.path.join(ROOT, "sfl", "fed_client.py"),
         "--server", f"{SERVER_IP}:{a.port}", "--bind", f"127.0.0.{i+1}",
         "--id", f"c{i}", "--index", str(i), "--clients", str(N), "--cut", "2",
         "--seed", "1", "--threads", str(client_threads(N, 0))], env=env, cwd=ROOT)
        for i in range(N)]
    for c in cs:
        c.wait(timeout=3600)
    srv.wait(timeout=300)
    a.port += 1
    rows = [json.loads(l) for l in io.open(slog, encoding="utf-8") if "round" in l]
    tail = rows[-4:]                                             # 수렴 후 구간
    ms = sum(r["makespan"] for r in tail) / len(tail)
    w = sum(sum(r["plan"].values()) / len(r["plan"]) for r in tail) / len(tail)
    return ms, w, rows[-1]["plan"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=8)
    ap.add_argument("--batches", type=int, default=4)
    ap.add_argument("--port", type=int, default=35100)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    caps = {1: 100e6, 2: 20e6}
    bytes_of = {f"c{i}": 8.39e6 * a.batches for i in range(N)}
    res = {"A_random": []}
    try:
        rng = random.Random(7)                                   # M1 과 동일 시드
        for s in range(3):
            ra = {f"c{i}": rng.choice([1, 2]) for i in range(N)}
            ms, w, plan = run_ours(f"rand{s}", [100, 20], ra, a)
            res["A_random"].append({"assign": ra, "ms": ms, "width": w, "plan": plan})
            print(f"A#{s} 배정 {list(ra.values())} → makespan {ms:5.2f}s · 평균 폭 {w:.3f} · 최종 {plan}")
        g = assign_greedy(bytes_of, caps)
        ms, w, plan = run_ours("greedy", [100, 20], g, a)
        res["B_greedy"] = {"assign": g, "ms": ms, "width": w, "plan": plan}
        print(f"B  배정 {list(g.values())} → makespan {ms:5.2f}s · 평균 폭 {w:.3f} · 최종 {plan}")
    finally:
        psh(["clear"])

    msA = sum(r["ms"] for r in res["A_random"]) / 3
    wA = sum(r["width"] for r in res["A_random"]) / 3
    dw = res["B_greedy"]["width"] - wA
    ok = dw >= 0.15 and res["B_greedy"]["ms"] <= msA * 1.10
    res["verdict"] = {"width_A_mean": wA, "width_B": res["B_greedy"]["width"],
                      "dwidth": dw, "ms_A_mean": msA, "ms_B": res["B_greedy"]["ms"],
                      "pass": ok}
    io.open(os.path.join(OUT, "m2_results.json"), "w", encoding="utf-8").write(
        json.dumps(res, ensure_ascii=False, indent=1))
    print(f"\n=== M2 판정 ===")
    print(f"  평균 폭: 무작위 {wA:.3f} → 탐욕 {res['B_greedy']['width']:.3f} "
          f"(Δ {dw:+.3f}, 판정선 +0.15)")
    print(f"  makespan: 무작위 {msA:.2f}s → 탐욕 {res['B_greedy']['ms']:.2f}s (가드 ≤×1.10)")
    print(f"  → {'PASS — 경로 배정이 학습(폭)을 보존한다: 폭×경로 상호작용 실측 성립' if ok else 'FAIL — M1만 남기고 M2 주장 폐기'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
