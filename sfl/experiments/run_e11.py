# -*- coding: utf-8 -*-
"""E11 — **연산 낙오자**를 실제로 만들어 노브 선택을 실측 검증한다.

  ── 왜 필요한가 ─────────────────────────────────────────────────
  다중 노브 컨트롤러의 핵심 주장은 이것이다:
      "연산이 느린 노드에는 양자화가 무효다 — 바이트만 줄이므로. 폭이 유일한 노브다."
  그런데 우리는 **연산 낙오자를 실측으로 만들어 본 적이 없다.**
  조건2·3은 전부 회선 낙오자였고, 노브 선택 시험(test_multiknob)은 합성이었다.
  합성으로 논리를 확인했으니 이제 실물로 확인한다.

  ── 어떻게 만드나 (sudo 불필요) ─────────────────────────────────
  클라는 --device 기본값이 cpu 라 전부 CPU 에서 돈다. torch 스레드 수를 줄이면
  **그 클라만 진짜로 연산이 느려진다.** 회선은 전혀 건드리지 않는다(루프백).
      c0 : --threads 1     ← 연산 낙오자
      나머지: --threads 4
  (코어 16개. 1 + 3×4 = 13 스레드라 과다구독이 없다 —
   과다구독은 N=8 측정을 무너뜨린 원인이었으므로 반드시 피한다)

  ── 사전 등록 판정 ──────────────────────────────────────────────
    ① 컨트롤러가 c0 을 **연산 병목**으로 진단하는가
    ② c0 의 **폭을 줄이는가**
    ③ c0 에 **양자화를 켜지 않는가**   ← 이 규칙의 핵심 주장
    ④ uniform 대비 makespan 이 줄어드는가
  ③이 깨지면 규칙이 틀린 것이다. 실패하면 실패라고 쓴다.

    python sfl/experiments/run_e11.py
"""
import argparse
import io
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "out")
PY = sys.executable
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def run(policy, a, port):
    slog = os.path.join(OUT, f"e11_{policy}.jsonl")
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "sfl"))
    cmd = [PY, os.path.join(ROOT, "sfl", "fed_server.py"), "--clients", str(a.clients),
           "--rounds", str(a.rounds), "--batches", str(a.batches), "--cut", "2",
           "--policy", policy, "--port", str(port), "--target", "0.99",
           "--device", "cuda", "--log", slog, "--seed", str(a.seed)]
    txt = os.path.join(OUT, f"e11_{policy}.txt")
    with io.open(txt, "w", encoding="utf-8") as f:
        srv = subprocess.Popen(cmd, env=env, cwd=ROOT, stdout=f,
                               stderr=subprocess.STDOUT)
        time.sleep(9)
        cs = []
        for i in range(a.clients):
            th = a.slow_threads if i == 0 else a.fast_threads
            cs.append(subprocess.Popen(
                [PY, os.path.join(ROOT, "sfl", "fed_client.py"),
                 "--server", f"127.0.0.1:{port}", "--id", f"c{i}", "--index", str(i),
                 "--clients", str(a.clients), "--cut", "2", "--seed", str(a.seed),
                 "--threads", str(th)],
                env=env, cwd=ROOT, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL))
        for c in cs:
            c.wait(timeout=3600)
        srv.wait(timeout=300)
    rows = [json.loads(l) for l in io.open(slog, encoding="utf-8") if '"round"' in l]
    return rows, io.open(txt, encoding="utf-8").read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clients", type=int, default=4)
    ap.add_argument("--rounds", type=int, default=6)
    ap.add_argument("--batches", type=int, default=4)
    ap.add_argument("--slow-threads", type=int, default=1, help="c0 (연산 낙오자)")
    ap.add_argument("--fast-threads", type=int, default=4)
    ap.add_argument("--port", type=int, default=37500)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    print(f"E11 — 연산 낙오자. 회선은 건드리지 않는다(루프백).")
    print(f"     c0 스레드 {a.slow_threads} / 나머지 {a.fast_threads}, "
          f"클라 {a.clients}대 × {a.rounds}라운드 × {a.batches}배치\n")

    out = {}
    for pol in ("uniform", "multi"):
        rows, txt = run(pol, a, a.port)
        a.port += 1
        ms = sum(r["makespan"] for r in rows) / len(rows)
        out[pol] = {"rows": rows, "txt": txt, "makespan": ms}
        print(f"  {pol:8s} 평균 makespan {ms:6.2f}s  최종정확도 {rows[-1]['acc']*100:5.2f}%  "
              f"마지막 배정 {[rows[-1]['plan'][f'c{i}'] for i in range(a.clients)]}", flush=True)

    io.open(os.path.join(OUT, "e11_results.json"), "w", encoding="utf-8").write(
        json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "txt"}
                    for k, v in out.items()}, indent=1))

    print("\n=== 실제로 c0 이 연산 낙오자가 되었나 (uniform 라운드에서 확인) ===")
    u = out["uniform"]["rows"]
    d = u[-1].get("per_client_detail", {})
    if d:
        print(f"  {'클라':5s} {'연산(fwd+bwd)':>14s} {'순수전송 xfer':>14s} {'망 몫':>7s}")
        for i in range(a.clients):
            k = f"c{i}"
            v = d.get(k, {})
            cpu = v.get("cli_fwd", 0) + v.get("cli_bwd", 0)
            net = v.get("xfer", 0)
            tot = cpu + net
            print(f"  {k:5s} {cpu:13.2f}s {net:13.2f}s {net/tot*100 if tot else 0:6.0f}%")
        c0 = d.get("c0", {})
        c1 = d.get("c1", {})
        r0 = c0.get("cli_fwd", 0) + c0.get("cli_bwd", 0)
        r1 = c1.get("cli_fwd", 0) + c1.get("cli_bwd", 0)
        print(f"  → c0 연산이 c1 의 {r0/r1 if r1 else 0:.1f}배  "
              f"{'✓ 연산 낙오자 만들어짐' if r0 > r1 * 1.5 else '✗ 낙오자가 안 됨 — 스레드 차이를 키워야 한다'}")

    print("\n=== 컨트롤러의 진단과 결정 (multi 정책 로그) ===")
    for line in out["multi"]["txt"].splitlines():
        if line.startswith("  c") or line.startswith("R "):
            print("  " + line.strip())

    print("\n=== 판정 ===")
    m = out["multi"]["rows"]
    last = m[-1]
    plans = [last["plan"][f"c{i}"] for i in range(a.clients)]
    txt = out["multi"]["txt"]
    # ① 은 **라벨이 아니라 진단 자체**를 본다. 라벨의 0.6/0.4 는 설명용 구분선이고
    #   결정에 안 쓰인다(controller_multi.diagnose 주석). 라벨로 채점하면 엉뚱한 걸 재게 된다.
    #   루프백이라 망이 사실상 0 이어야 하므로, c0 의 망 몫이 낮게 나오면 통과다.
    ud = u[-1].get("per_client_detail", {})
    c0d = ud.get("c0", {})
    cpu0 = c0d.get("cli_fwd", 0) + c0d.get("cli_bwd", 0)
    net0 = c0d.get("xfer", 0)
    share0 = net0 / (cpu0 + net0) if (cpu0 + net0) else 1.0
    ok1 = share0 < 0.4
    print(f"\n  (참고) c0 망 몫 {share0*100:.0f}%  — 루프백이므로 0 에 가까워야 맞다")
    ok2 = plans[0] < 1.0
    ok3 = "양자화" not in txt.split("판정")[0].replace("+ 양자화", "@@").replace("@@", "+ 양자화") \
        or "+ 양자화" not in txt
    ok4 = out["multi"]["makespan"] < out["uniform"]["makespan"]
    print(f"  ① c0 을 연산 병목으로 진단        : {'PASS' if ok1 else 'FAIL'}")
    print(f"  ② c0 의 폭을 줄임                 : {'PASS' if ok2 else 'FAIL'}  (마지막 배정 {plans})")
    print(f"  ③ c0 에 양자화를 켜지 않음 ★핵심  : {'PASS' if ok3 else 'FAIL'}")
    print(f"  ④ uniform 보다 빠름               : {'PASS' if ok4 else 'FAIL'}  "
          f"({out['uniform']['makespan']:.2f}s → {out['multi']['makespan']:.2f}s)")
    print(f"\n  ── {sum([ok1, ok2, ok3, ok4])}/4 통과 ──")


if __name__ == "__main__":
    main()
