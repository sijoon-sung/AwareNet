# -*- coding: utf-8 -*-
"""G0 스윕 — 배치 시간에서 통신 지분 실측 + 바이트∝p(A2) 검증.

  로컬(윈도우/리눅스 공통): p × cut 스윕, localhost.
    python sfl/experiments/run_g0.py --quick          # 스모크: p{0.25,1.0} × cut1
    python sfl/experiments/run_g0.py                  # 전체: p{0.25,0.5,1.0} × cut{1,2,3}
  netem 은 리눅스에서만: --netem "delay 30ms rate 50mbit" (lo에 건다, root 필요)

  판정(사전 등록): 운영점에서 통신 지분 <10% 폐기 / 10~30% 보류 / >30% 진행
  통신시간 = 배치시간 − (앞단연산 + 역전파) − (서버연산 + GPU대기)
"""
import argparse
import io
import json
import os
import subprocess
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "out")
PY = sys.executable


def run_one(p, cut, batches, bs, tokens=0, pipeline=False, port=29511):
    tag = f"p{p}_cut{cut}" + ("_tok%d" % tokens if tokens else "") + ("_pipe" if pipeline else "")
    slog = os.path.join(OUT, f"g0_srv_{tag}.jsonl")
    clog = os.path.join(OUT, f"g0_cli_{tag}.jsonl")
    env = dict(os.environ, PYTHONPATH=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    srv = subprocess.Popen([PY, os.path.join(ROOT, "sfl", "server.py"),
                            "--port", str(port), "--clients", "1",
                            "--tokens", str(tokens), "--log", slog], env=env)
    time.sleep(3.0)
    cli = [PY, os.path.join(ROOT, "sfl", "client.py"),
           "--server", f"127.0.0.1:{port}", "--p", str(p), "--cut", str(cut),
           "--batches", str(batches), "--batch-size", str(bs), "--log", clog]
    if pipeline:
        cli.append("--pipeline")
    subprocess.run(cli, env=env, check=True)
    srv.wait(timeout=60)
    return tag, slog, clog


def analyze(tag, slog, clog, warmup=2):
    S = {r["b"]: r for r in map(json.loads, io.open(slog, encoding="utf-8")) if "b" in r}
    C = [r for r in map(json.loads, io.open(clog, encoding="utf-8")) if "b" in r]
    C = [r for r in C if r["b"] >= warmup]                      # 웜업(첫 배치 CUDA 초기화 등) 제외
    n = len(C)
    m = lambda k: sum(r[k] for r in C) / n
    srv = lambda k: sum(S[r["b"]][k] for r in C) / n
    t_batch = m("t_fwd") + m("t_tok") + m("t_up") + m("t_wait") + m("t_bwd")
    compute = m("t_fwd") + m("t_bwd") + srv("t_srv") + srv("t_lock")
    comm = max(t_batch - compute, 0.0)
    return {"tag": tag, "t_batch": t_batch, "t_fwd": m("t_fwd"), "t_up": m("t_up"),
            "t_wait": m("t_wait"), "t_bwd": m("t_bwd"), "t_srv": srv("t_srv"),
            "t_lock": srv("t_lock"), "comm": comm, "share": comm / t_batch,
            "up_B": m("up_B"), "down_B": m("down_B")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--batches", type=int, default=16)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--pipeline-check", action="store_true",
                    help="p=1,cut=1에서 파이프라인 on/off 비교도 수행")
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    ps = (0.25, 1.0) if args.quick else (0.25, 0.5, 1.0)
    cuts = (1,) if args.quick else (1, 2, 3)

    rows = []
    for cut in cuts:
        for p in ps:
            rows.append(analyze(*run_one(p, cut, args.batches, args.batch_size)))
    if args.pipeline_check:
        rows.append(analyze(*run_one(1.0, 1, args.batches, args.batch_size, pipeline=True)))

    print("\ntag              batch(s)  fwd     up      wait    bwd     srv     lock   comm  share   up_KB")
    for r in rows:
        print(f"{r['tag']:16s} {r['t_batch']:.4f}  {r['t_fwd']:.4f}  {r['t_up']:.4f}  "
              f"{r['t_wait']:.4f}  {r['t_bwd']:.4f}  {r['t_srv']:.4f}  {r['t_lock']:.4f} "
              f"{r['comm']:.4f}  {r['share']*100:5.1f}%  {r['up_B']/1024:8.1f}")

    # A2 검증: 같은 cut에서 up_B 비율 ≈ p 비율
    by_cut = {}
    for r in rows:
        if "_pipe" in r["tag"] or "_tok" in r["tag"]:
            continue
        cut = r["tag"].split("_cut")[1]
        by_cut.setdefault(cut, {})[r["tag"].split("_")[0][1:]] = r["up_B"]
    print("\nA2 바이트∝p 검증 (제로패딩이면 비율이 1.0으로 나온다):")
    for cut, d in sorted(by_cut.items()):
        if "1.0" in d:
            for p, b in sorted(d.items()):
                print(f"  cut{cut}: p={p}  up_B 비율 {b/d['1.0']:.3f}  (기대 ≈ {float(p):.2f})")

    io.open(os.path.join(OUT, "g0_results.json"), "w", encoding="utf-8").write(
        json.dumps(rows, indent=1))
    print("\n저장: out/g0_results.json  |  로컬 실행은 지연·대역 무제한이라 share가 하한이다."
          "\nnetem 스윕(RTT·대역)은 리눅스 컨테이너에서 — sfl/net/perturb.sh 참고.")


if __name__ == "__main__":
    main()
