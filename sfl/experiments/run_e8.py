# -*- coding: utf-8 -*-
"""E8 — 우리 노브(폭 p)와 값역 양자화를 **같은 바이트 감소량**에서 정면 비교.

  적대 검증의 가장 아픈 지적:
    "p=0.25 는 바이트를 4배 줄인다. 8비트 양자화도 4배를 정확도 대가 거의 없이 준다.
     즉 주 노브가 내는 주 효과와 같은 크기의 이득을 더 싸게 내는 대안을 한 번도 안 쟀다."

  그래서 네 조건을 같은 회선·같은 시드에서 돌린다 (전부 전원 동일 폭 — 컨트롤러 없음):

    A  p=1.0 · fp32     기준 (1× 바이트)
    B  p=0.25 · fp32    우리 노브만        (1/4 바이트)
    C  p=1.0 · int8     양자화만           (1/4 바이트)   ← 대안
    D  p=0.25 · int8    둘 다              (1/16 바이트)  ← 곱해지나?

  묻는 것
    ① 같은 4배 감소에서 B 와 C 중 무엇이 나은가 (시간·정확도)
    ② 둘이 **직교해서 곱해지나** (D 가 16배 감소를 실제로 내나)
  → ②가 참이면 "대안에 밀린다"가 아니라 "함께 쓴다"가 되어 오히려 유리하다.

    sudo ~/sflenv/bin/python sfl/experiments/run_e8.py
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
from run_g2 import OUT, ROOT, SERVER_IP, SHARED, client_threads, sh

PY = sys.executable
N = 4
RATES = [30, 30, 30, 30]          # ★ 전부 동일 — 이질성 변인을 없애고 압축만 본다
COND = [("A_p1.0_fp32", 1.0, 0), ("B_p0.25_fp32", 0.25, 0),
        ("C_p1.0_int8", 1.0, 8), ("D_p0.25_int8", 0.25, 8)]


def run(tag, p, quant, a):
    slog = os.path.join(OUT, f"e8_{tag}.jsonl")
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "sfl"))
    plan = json.dumps({f"c{i}": p for i in range(N)})
    srv = subprocess.Popen(
        [PY, os.path.join(ROOT, "sfl", "fed_server.py"), "--clients", str(N),
         "--rounds", str(a.rounds), "--batches", str(a.batches), "--cut", "2",
         "--policy", "oracle", "--oracle-plan", plan,      # 폭 고정 배포
         "--port", str(a.port), "--target", "0.99", "--device", "cuda",
         "--log", slog, "--seed", str(a.seed)], env=env, cwd=ROOT)
    time.sleep(10)
    cs = [subprocess.Popen(
        [PY, os.path.join(ROOT, "sfl", "fed_client.py"),
         "--server", f"{SERVER_IP}:{a.port}", "--bind", f"127.0.0.{i+1}",
         "--id", f"c{i}", "--index", str(i), "--clients", str(N), "--cut", "2",
         "--quant", str(quant), "--seed", str(a.seed),
         "--threads", str(client_threads(N, a.threads))], env=env, cwd=ROOT)
        for i in range(N)]
    for c in cs:
        c.wait(timeout=3600)
    srv.wait(timeout=300)
    rows = [json.loads(l) for l in io.open(slog, encoding="utf-8") if "round" in l]
    byt = sum(v[2] for r in rows for v in r["per_client"].values()) / len(rows)
    return {"tag": tag, "p": p, "quant": quant,
            "makespan": sum(r["makespan"] for r in rows) / len(rows),
            "acc": rows[-1]["acc"], "bytes_per_round": byt,
            "acc_curve": [r["acc"] for r in rows]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=8)
    ap.add_argument("--batches", type=int, default=8)
    ap.add_argument("--port", type=int, default=32100)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--threads", type=int, default=0)
    a = ap.parse_args()
    sh(["setup", " ".join(map(str, RATES)), str(SHARED)])
    rows = []
    try:
        for tag, p, q in COND:
            r = run(tag, p, q, a)
            rows.append(r)
            a.port += 1
            print(f"  {tag:16s} makespan {r['makespan']:6.2f}s  최종정확도 {r['acc']*100:5.2f}%  "
                  f"라운드당 {r['bytes_per_round']/1e6:7.1f}MB", flush=True)
    finally:
        sh(["clear"])
    io.open(os.path.join(OUT, "e8_results.json"), "w", encoding="utf-8").write(
        json.dumps(rows, indent=1))

    base = rows[0]
    print(f"\n=== E8 판정 (회선 {RATES[0]}Mbps 전원 동일, 시드 {a.seed}) ===")
    print(f"{'조건':16s} {'바이트비':>8s} {'makespan':>9s} {'대비':>7s} {'정확도':>8s} {'대비':>8s}")
    for r in rows:
        print(f"{r['tag']:16s} {r['bytes_per_round']/base['bytes_per_round']:7.3f}× "
              f"{r['makespan']:8.2f}s {r['makespan']/base['makespan']:6.2f}× "
              f"{r['acc']*100:7.2f}% {(r['acc']-base['acc'])*100:+7.2f}pp")
    b, c, d = rows[1], rows[2], rows[3]
    print(f"\n① 같은 4배 감소에서: 폭(B) {b['makespan']:.2f}s / {b['acc']*100:.2f}%  vs  "
          f"양자화(C) {c['makespan']:.2f}s / {c['acc']*100:.2f}%")
    print(f"   → {'폭이 유리' if b['makespan'] < c['makespan'] else '양자화가 유리'} (시간 기준)")
    exp = b["bytes_per_round"] * c["bytes_per_round"] / base["bytes_per_round"] ** 2
    act = d["bytes_per_round"] / base["bytes_per_round"]
    print(f"② 곱해지나: 기대 {exp:.3f}× · 실측 {act:.3f}× → "
          f"{'직교해서 곱해진다' if abs(act - exp) < 0.03 else '곱해지지 않는다'}")


if __name__ == "__main__":
    main()
