# -*- coding: utf-8 -*-
"""M1·M4 — 경로 노브의 실측. **SDN 이 할 일(흐름을 경로에 배정)이 실제로 시간을 사는가.**

  8번 문서(SDN_경로노브.md)의 사전 등록 실험을 그대로 집행한다:
    M1  이질 경로(100M·20M) × 클라 4 — 무작위 배정 vs 탐욕(LPT) 배정.
        판정: 탐욕이 무작위 평균보다 makespan **15% 이상** 못 줄이면 경로 노브 폐기
    M4  균질 경로(60M·60M) — **아무것도 안 해야 한다.**
        판정: 탐욕과 무작위의 차이가 잡음 안이어야 함 (이득 주장 금지 확인)

  방법: 실제 학습(fed rig, 전원 전폭 uniform — 폭 변인 제거) 위에서 경로만 바꿔
  라운드 makespan 을 잰다. 경로는 sfl/net/paths.sh(HTB 클래스), 배정 알고리즘은
  sfl/paths.py(assign_greedy — 균질하면 저절로 고르게 흩어짐).

      sudo ~/sflenv/bin/python sfl/experiments/run_m1.py
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
from paths import assign_greedy, makespan as predict_ms          # noqa: E402
from run_g2 import OUT, ROOT, SERVER_IP, client_threads         # noqa: E402

PY = sys.executable
N = 4
PSH = os.path.join(ROOT, "sfl", "net", "paths.sh")


def psh(args):
    subprocess.run(["sh", PSH] + args, check=True)


def run_once(tag, caps, assign, a):
    """경로 caps + 배정으로 실학습 라운드를 돌려 makespan 평균(후반)을 잰다."""
    psh(["setup", " ".join(str(c) for c in caps)])
    psh(["assign", " ".join(str(assign[f"c{i}"]) for i in range(N))])
    slog = os.path.join(OUT, f"m1_{tag}.jsonl")
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "sfl"))
    srv = subprocess.Popen(
        [PY, os.path.join(ROOT, "sfl", "fed_server.py"), "--clients", str(N),
         "--rounds", str(a.rounds), "--batches", str(a.batches), "--cut", "2",
         "--policy", "uniform", "--port", str(a.port), "--target", "0.99",
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
    ms = [r["makespan"] for r in rows][1:]                      # 첫 라운드(웜업) 제외
    return sum(ms) / len(ms)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--batches", type=int, default=4)
    ap.add_argument("--port", type=int, default=33100)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    bytes_of = {f"c{i}": 8.39e6 * a.batches for i in range(N)}   # 전폭·동일 (실측치)
    res = {}
    try:
        # ── M1: 이질 경로 100M · 20M ─────────────────────────
        caps_h = {1: 100e6, 2: 20e6}
        greedy = assign_greedy(bytes_of, caps_h)
        print(f"M1 탐욕 배정: {greedy}  (예측 {predict_ms(greedy, bytes_of, caps_h):.2f}s)")
        g = run_once("m1_greedy", [100, 20], greedy, a)
        rnd_ms = []
        rng = random.Random(7)
        for s in range(3):
            ra = {f"c{i}": rng.choice([1, 2]) for i in range(N)}
            print(f"M1 무작위#{s}: {ra}")
            rnd_ms.append(run_once(f"m1_rand{s}", [100, 20], ra, a))
        r_mean = sum(rnd_ms) / len(rnd_ms)
        gain = 1 - g / r_mean
        res["M1"] = {"greedy_ms": g, "random_ms": rnd_ms, "random_mean": r_mean,
                     "gain": gain, "assign": greedy,
                     "pass": gain >= 0.15}
        print(f"\nM1: 탐욕 {g:.2f}s vs 무작위 평균 {r_mean:.2f}s → 이득 {gain*100:+.1f}% "
              f"(판정선 15%) → {'PASS' if res['M1']['pass'] else 'FAIL — 경로 노브 폐기'}")

        # ── M4: 균질 경로 60M · 60M — 아무것도 안 해야 한다 ──
        caps_u = {1: 60e6, 2: 60e6}
        gu = assign_greedy(bytes_of, caps_u)
        loads = [list(gu.values()).count(p) for p in (1, 2)]
        print(f"\nM4 탐욕 배정: {gu} (경로별 {loads})")
        u_g = run_once("m4_greedy", [60, 60], gu, a)
        ra = {f"c{i}": [1, 2][i % 2] for i in range(N)}
        u_r = run_once("m4_even", [60, 60], ra, a)
        diff = abs(u_g - u_r) / u_r
        res["M4"] = {"greedy_ms": u_g, "even_ms": u_r, "rel_diff": diff,
                     "spread_ok": loads == [2, 2], "pass": loads == [2, 2] and diff < 0.10}
        print(f"M4: 탐욕 {u_g:.2f}s vs 균등 {u_r:.2f}s (차이 {diff*100:.1f}%) · "
              f"고른 분산 {loads} → {'PASS — 균질하면 가만있는다' if res['M4']['pass'] else 'FAIL'}")
    finally:
        psh(["clear"])
    io.open(os.path.join(OUT, "m1_results.json"), "w", encoding="utf-8").write(
        json.dumps(res, ensure_ascii=False, indent=1))
    ok = res.get("M1", {}).get("pass") and res.get("M4", {}).get("pass")
    print(f"\n=== 경로 노브 판정: {'M1·M4 통과 — 경로는 산다 (다음: 컨트롤러 0번 칸 통합)' if ok else '보류/폐기 — 8번 문서 킬 기준 적용'} ===")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
