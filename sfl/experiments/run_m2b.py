# -*- coding: utf-8 -*-
"""M2′ — 폐기가 아니라 개선: **폭 × 경로 공동 계획**의 실측.

  M2 FAIL 의 교훈(따로 정하면 서로의 입력을 무효화한다)을 구현으로 되받는다:
      paths.joint_plan() 이 (배정, 폭벡터)를 한 문제로 완전탐색 (2^4 × 4^4)
      목적함수 = 등록된 비(比) 목적: makespan / 평균폭 (controller.py 2판과 동일)

  비교 상대는 M2 실측값 그대로 재사용 (out/m2_results.json):
      A  무작위 경로 + 적응 폭   (ratio ≈ 14.2)
      B  경로만 탐욕 + 전폭 유지 (ratio ≈ 12.9)
      C  공동 계획 (이 러너가 실측)

  사전 등록 판정: ratio_C ≤ 0.90 × min(ratio_A, ratio_B) — 등록 목적함수에서
  양쪽 모두를 10% 이상 이겨야 "공동 최적화가 실제로 낫다" 주장 성립.

      sudo ~/sflenv/bin/python sfl/experiments/run_m2b.py
"""
import argparse
import io
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from paths import joint_plan                                     # noqa: E402
from run_g2 import OUT, ROOT, SERVER_IP, client_threads         # noqa: E402

PY = sys.executable
N = 4
PSH = os.path.join(ROOT, "sfl", "net", "paths.sh")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=8)
    ap.add_argument("--batches", type=int, default=4)
    ap.add_argument("--port", type=int, default=36100)
    a = ap.parse_args()
    prev = json.load(io.open(os.path.join(OUT, "m2_results.json"), encoding="utf-8"))
    msA = prev["verdict"]["ms_A_mean"]; wA = prev["verdict"]["width_A_mean"]
    msB = prev["verdict"]["ms_B"];      wB = prev["verdict"]["width_B"]
    rA, rB = msA / wA, msB / wB

    bytes1 = {f"c{i}": 8.39e6 * a.batches for i in range(N)}
    assign, widths, pms, pratio = joint_plan(bytes1, {1: 100e6, 2: 20e6}, comp=1.2)
    print(f"공동 계획: " + ", ".join(f"c{i}→경로{assign[f'c{i}']}·폭{widths[f'c{i}']}"
                                      for i in range(N)))
    print(f"예측: makespan {pms:.2f}s · ratio {pratio:.2f}  (A {rA:.2f} / B {rB:.2f})")

    subprocess.run(["sh", PSH, "setup", "100 20"], check=True)
    subprocess.run(["sh", PSH, "assign",
                    " ".join(str(assign[f"c{i}"]) for i in range(N))], check=True)
    slog = os.path.join(OUT, "m2b_joint.jsonl")
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "sfl"))
    plan = json.dumps(widths)
    try:
        srv = subprocess.Popen(
            [PY, os.path.join(ROOT, "sfl", "fed_server.py"), "--clients", str(N),
             "--rounds", str(a.rounds), "--batches", str(a.batches), "--cut", "2",
             "--policy", "oracle", "--oracle-plan", plan,
             "--port", str(a.port), "--target", "0.99",
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
    finally:
        subprocess.run(["sh", PSH, "clear"], check=False)

    rows = [json.loads(l) for l in io.open(slog, encoding="utf-8") if "round" in l]
    tail = rows[-4:]
    msC = sum(r["makespan"] for r in tail) / len(tail)
    wC = sum(widths.values()) / N
    rC = msC / wC
    ok = rC <= 0.90 * min(rA, rB)
    res = {"plan": {"assign": assign, "widths": widths},
           "pred": {"ms": pms, "ratio": pratio},
           "measured": {"ms": msC, "width": wC, "ratio": rC},
           "baselines": {"A": {"ms": msA, "width": wA, "ratio": rA},
                         "B": {"ms": msB, "width": wB, "ratio": rB}},
           "pass": ok}
    io.open(os.path.join(OUT, "m2b_results.json"), "w", encoding="utf-8").write(
        json.dumps(res, ensure_ascii=False, indent=1))
    print(f"\n=== M2′ 판정 (목적 = makespan/평균폭, 낮을수록 좋다) ===")
    print(f"  A 무작위+적응폭 : {msA:5.2f}s / {wA:.3f} → ratio {rA:5.2f}")
    print(f"  B 경로탐욕+전폭 : {msB:5.2f}s / {wB:.3f} → ratio {rB:5.2f}")
    print(f"  C 공동 계획     : {msC:5.2f}s / {wC:.3f} → ratio {rC:5.2f}  (예측 {pratio:.2f})")
    print(f"  판정선: C ≤ 0.90 × min(A,B) = {0.9*min(rA,rB):.2f} → "
          f"{'PASS — 공동 최적화가 실제로 낫다' if ok else 'FAIL — 공동 계획도 기각, 기록'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
