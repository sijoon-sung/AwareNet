# -*- coding: utf-8 -*-
"""E10 — 라운드 시간이 무엇으로 이루어져 있나. 그리고 **컨트롤러가 그중 무엇을 못 보나.**

  ── 왜 이걸 재는가 ──────────────────────────────────────────────
  조건4(N=8)에서 폭을 1/4 로 줄였더니 이상한 일이 벌어졌다:
      바이트   0.250×  (정확히 p 비례 — 예상대로)
      통신시간 0.840×  (★ 4배 줄인 바이트가 16% 밖에 안 줄였다)
      연산시간 1.160×  (★ 폭을 줄였는데 오히려 늘었다)
      makespan 0.615×
  즉 **컨트롤러가 재는 두 양이 이름과 다른 것을 재고 있다.**

  코드를 읽으면 이유가 나온다 (fed_server.py):
    · t_comm 은 "GRAD 를 보낸 뒤 → 다음 ACT 를 받을 때까지" 다.
      여기엔 **클라의 순전파 연산이 들어 있고**, 그래디언트 내려보내는 구간은 빠져 있다
      (그런데 그 바이트는 byt 에 세어진다). 그러니 byt/t_comm 은 회선 속도가 아니다.
    · 서버의 GPU 작업은 전역 락 하나(LOCK, 42행)로 **전 클라가 직렬화**된다.
      그 대기는 t_comm 에도 comp 에도 안 들어간다 — **컨트롤러에게 보이지 않는다.**

  클라는 이미 배치마다 t_fwd / t_wait / t_bwd 를 남길 수 있다 (--log).
  t_wait = ACT 보낸 뒤 GRAD 받을 때까지 = **락 대기 + 서버 GPU + 그래디언트 내려받기**
         = 정확히 그 '보이지 않는 부분'이다.

  ── 그래서 회선 조작(tc/sudo) 없이 잰다 ──────────────────────────
  회선을 건드리지 않는 편이 오히려 깨끗하다: 망 효과를 0 으로 두면
  남는 것은 **서버 직렬화뿐**이다. N 을 늘리며 t_wait 이 어떻게 자라는지 보면
  "8대에서 이질성이 뭉개진" 현상의 원인이 서버인지 아닌지가 갈린다.

  ── 사전 등록 판정 ──────────────────────────────────────────────
    · t_wait 이 N 에 대체로 비례해 자라면 → **서버 직렬화가 원인이다** (락)
    · t_wait 이 N 과 무관하면 → 원인은 다른 데 있다. 락 가설을 버린다
    · 폭을 낮췄을 때 t_wait 이 얼마나 주는지 = 폭 노브가 **보이지 않는 곳에서** 내는 이득

    python sfl/experiments/run_e10.py                 # sudo 불필요
"""
import argparse
import io
import json
import os
import subprocess
import sys
import time
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "out")
PY = sys.executable
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def run(n, p, a, port):
    """클라 n대·전원 폭 p 로 짧게 돌리고 클라별 배치 타이밍을 모은다."""
    tag = f"N{n}_p{p:.2f}"
    slog = os.path.join(OUT, f"e10_{tag}_srv.jsonl")
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "sfl"))
    plan = json.dumps({f"c{i}": p for i in range(n)})
    srv = subprocess.Popen(
        [PY, os.path.join(ROOT, "sfl", "fed_server.py"), "--clients", str(n),
         "--rounds", str(a.rounds), "--batches", str(a.batches), "--cut", "2",
         "--policy", "oracle", "--oracle-plan", plan, "--port", str(port),
         "--target", "0.99", "--device", a.device, "--log", slog, "--seed", "1"],
        env=env, cwd=ROOT, stdout=subprocess.DEVNULL)
    time.sleep(8)
    cs = []
    for i in range(n):
        clog = os.path.join(OUT, f"e10_{tag}_c{i}.jsonl")
        cs.append(subprocess.Popen(
            [PY, os.path.join(ROOT, "sfl", "fed_client.py"),
             "--server", f"127.0.0.1:{port}", "--id", f"c{i}", "--index", str(i),
             "--clients", str(n), "--cut", "2", "--seed", "1", "--log", clog]
            + (["--threads", str(a.threads)] if a.threads else []),
            env=env, cwd=ROOT, stdout=subprocess.DEVNULL))
    for c in cs:
        c.wait(timeout=3600)
    srv.wait(timeout=300)

    # 클라 로그 집계 — 라운드 0 은 워밍업이라 버린다
    acc = defaultdict(list)
    for i in range(n):
        clog = os.path.join(OUT, f"e10_{tag}_c{i}.jsonl")
        for line in io.open(clog, encoding="utf-8"):
            d = json.loads(line)
            if d.get("r", 0) == 0:
                continue
            for k in ("t_fwd", "t_wait", "t_bwd"):
                acc[k].append(d[k])
    srv_rows = [json.loads(l) for l in io.open(slog, encoding="utf-8") if '"round"' in l]
    ms = [r["makespan"] for r in srv_rows[1:]] or [srv_rows[-1]["makespan"]]
    m = {k: sum(v) / len(v) for k, v in acc.items() if v}
    m["makespan"] = sum(ms) / len(ms)
    m["n"], m["p"], m["batches"] = n, p, a.batches
    m["samples"] = len(acc["t_wait"])
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--batches", type=int, default=4)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--port", type=int, default=36100)
    ap.add_argument("--ns", default="1,2,4,8")
    ap.add_argument("--ps", default="1.0,0.25")
    ap.add_argument("--threads", type=int, default=0,
                    help="클라당 CPU 스레드. 0=torch 기본(8). 코어수/클라수 로 주는 것이 맞다")
    a = ap.parse_args()
    ns = [int(x) for x in a.ns.split(",")]
    ps = [float(x) for x in a.ps.split(",")]
    print(f"E10 — 회선 조작 없음(루프백). {a.rounds}라운드 × {a.batches}배치, device={a.device}")
    print("     t_wait = ACT 보낸 뒤 GRAD 받을 때까지 = 락대기 + 서버GPU + 그래디언트\n")
    rows, port = [], a.port
    for p in ps:
        for n in ns:
            r = run(n, p, a, port)
            port += 1
            rows.append(r)
            print(f"  N={n:2d} p={p:.2f}  t_fwd {r['t_fwd']:6.3f}s  "
                  f"t_wait {r['t_wait']:6.3f}s  t_bwd {r['t_bwd']:6.3f}s  "
                  f"makespan {r['makespan']:6.2f}s  (표본 {r['samples']})", flush=True)
    # ★ 설정별로 파일을 나눈다 — 예전에 두 번째 실행이 첫 실행 결과를 덮어써서
    #   N=4 수치를 로그에서 되찾지 못한 적이 있다.
    stem = f"e10_b{a.batches}_N{'-'.join(map(str, ns))}"
    io.open(os.path.join(OUT, f"{stem}_results.json"), "w", encoding="utf-8").write(
        json.dumps(rows, indent=1))
    print(f"\n  → {stem}_results.json")

    print("\n=== 판정 ① t_wait 이 N 에 비례해 자라는가 (서버 직렬화 가설) ===")
    for p in ps:
        sub = [r for r in rows if r["p"] == p]
        if len(sub) < 2:
            continue
        b = sub[0]
        print(f"  p={p:.2f}  " + "  ".join(
            f"N={r['n']}:{r['t_wait']/b['t_wait']:.2f}×" for r in sub)
            + f"   (기준 N={b['n']} 에서 {b['t_wait']:.3f}s)")
    print("  → N 배수에 가깝게 자라면 서버 락이 원인이다. 평평하면 아니다")

    print("\n=== 판정 ② 라운드 시간에서 각 부분이 차지하는 몫 ===")
    print(f"{'':12s} {'t_fwd':>8s} {'t_wait':>8s} {'t_bwd':>8s} {'합×배치':>9s} {'makespan':>9s} {'t_wait몫':>9s}")
    for r in rows:
        tot = (r["t_fwd"] + r["t_wait"] + r["t_bwd"]) * r["batches"]
        print(f"  N={r['n']:2d} p={r['p']:.2f} {r['t_fwd']:7.3f}s {r['t_wait']:7.3f}s "
              f"{r['t_bwd']:7.3f}s {tot:8.2f}s {r['makespan']:8.2f}s "
              f"{r['t_wait']*r['batches']/r['makespan']*100:8.0f}%")
    print("  → t_wait 몫이 크면 **컨트롤러가 라운드의 그만큼을 못 보고 있다**")

    print("\n=== 판정 ③ 폭을 낮추면 보이지 않는 부분이 얼마나 주는가 ===")
    for n in ns:
        hi = next((r for r in rows if r["n"] == n and r["p"] == max(ps)), None)
        lo = next((r for r in rows if r["n"] == n and r["p"] == min(ps)), None)
        if hi and lo:
            print(f"  N={n:2d}  t_wait {hi['t_wait']:.3f}s → {lo['t_wait']:.3f}s "
                  f"({lo['t_wait']/hi['t_wait']:.2f}×)   "
                  f"makespan {hi['makespan']:.2f}s → {lo['makespan']:.2f}s "
                  f"({lo['makespan']/hi['makespan']:.2f}×)")


if __name__ == "__main__":
    main()
