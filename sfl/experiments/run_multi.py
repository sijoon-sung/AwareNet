# -*- coding: utf-8 -*-
"""다중 클라이언트 실험 — A7(대역 독립 가정) + 망 개입 관문 ①②(서버 회선 포화) 실측.

  구조: lo 에 netem 으로 서버 접속 회선 용량을 만들고(공유 병목),
        N개 클라이언트가 동시에 활성값을 스트리밍한다.

  묻는 것
    ① 실재  — N이 늘 때 클라별 업로드 시간이 실제로 늘어나는가 (독립 가정 A7이 깨지는가)
    ② 지속  — 총 굿풋이 회선 용량에서 유지되는가, 아니면 무너지는가(붕괴)
    ③ 공평  — 클라이언트 간 편차가 어떤가 (TCP 공정 공유가 실제로 공정한가)
    ④ 토큰  — 수신자 주도 허가(--tokens K)가 위 셋을 바꾸는가

  판정은 사전 등록:
    ① t_up 이 N에 거의 비례(±30%) → A7 깨짐, 예측식에 결합항 필요
    ② 총 굿풋이 N 증가에도 용량의 80% 이상 유지 → 붕괴 아님(=줄 세우기 근거 약함)
       80% 미만으로 떨어지면 → 붕괴 신호(=관문 ② 통과 후보)
    ④ 토큰 on 이 총 굿풋/완료시간을 5% 이상 개선해야 의미 있음. 아니면 "TCP로 충분" 판정

    sudo ~/sflenv/bin/python sfl/experiments/run_multi.py            # WSL, root
"""
import io
import json
import os
import statistics as st
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "out")
PY = sys.executable

RTT_MS, BW_MBIT = 20, 50          # 서버 접속 회선 (엣지 업링크 재현 — 운영점 정당화 §C1)
P, CUT, BATCHES, BS = 0.25, 1, 6, 32
NS = [1, 2, 4, 8]
TOKEN_SETS = [0, 2]               # 0=off(TCP 공정공유), 2=동시 업로드 2개만 허가


def tc(cmd):
    subprocess.run(["tc"] + cmd.split(), check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def run(n, tokens, port):
    tag = f"n{n}_tok{tokens}"
    slog = os.path.join(OUT, f"multi_srv_{tag}.jsonl")
    env = dict(os.environ, PYTHONPATH=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    srv = subprocess.Popen([PY, os.path.join(ROOT, "sfl", "server.py"),
                            "--port", str(port), "--clients", str(n),
                            "--tokens", str(tokens), "--device", "cuda",
                            "--log", slog], env=env)
    time.sleep(6)
    t0 = time.perf_counter()
    procs = []
    for i in range(n):                       # 동시 출발 — 라운드 경계 재현
        clog = os.path.join(OUT, f"multi_cli_{tag}_c{i}.jsonl")
        procs.append(subprocess.Popen(
            [PY, os.path.join(ROOT, "sfl", "client.py"), "--server", f"127.0.0.1:{port}",
             "--id", f"c{i}", "--p", str(P), "--cut", str(CUT),
             "--batches", str(BATCHES), "--batch-size", str(BS), "--log", clog], env=env))
    for pr in procs:
        pr.wait(timeout=900)
    wall = time.perf_counter() - t0
    srv.wait(timeout=120)

    rows, per_cli = [], []
    for i in range(n):
        rs = [json.loads(l) for l in
              io.open(os.path.join(OUT, f"multi_cli_{tag}_c{i}.jsonl"), encoding="utf-8")]
        b = [r for r in rs if "b" in r and r["b"] >= 1]      # 웜업 1배치 제외
        rows += b
        per_cli.append(sum(r["t_up"] + r["t_wait"] for r in b) / len(b))

    m = lambda k: sum(r[k] for r in rows) / len(rows)
    total_B = sum(r["up_B"] + r["down_B"] for r in rows)
    srv_rows = [json.loads(l) for l in io.open(slog, encoding="utf-8")]
    return {
        "n": n, "tokens": tokens, "wall": wall,
        "t_up": m("t_up"), "t_wait": m("t_wait"), "t_tok": m("t_tok"),
        "t_fwd": m("t_fwd"), "t_bwd": m("t_bwd"),
        "t_lock": sum(r["t_lock"] for r in srv_rows) / len(srv_rows),
        "t_srv": sum(r["t_srv"] for r in srv_rows) / len(srv_rows),
        "goodput_mbit": total_B * 8 / 1e6 / wall,
        "per_cli_mean": per_cli,
        "fairness": (max(per_cli) / min(per_cli)) if len(per_cli) > 1 else 1.0,
    }


def main():
    os.makedirs(OUT, exist_ok=True)
    tc(f"qdisc replace dev lo root netem delay {RTT_MS/2}ms rate {BW_MBIT}mbit limit 4000")
    rows, port = [], 29800
    try:
        for tokens in TOKEN_SETS:
            for n in NS:
                port += 1
                r = run(n, tokens, port)
                rows.append(r)
                print(f"N={r['n']:2d} tok={r['tokens']} | 배치당 up {r['t_up']:.3f}s "
                      f"wait {r['t_wait']:.3f}s tok대기 {r['t_tok']:.3f}s | "
                      f"서버 lock {r['t_lock']:.3f}s srv {r['t_srv']:.3f}s | "
                      f"굿풋 {r['goodput_mbit']:.1f}Mbps | 벽시계 {r['wall']:.1f}s | "
                      f"공평비 {r['fairness']:.2f}", flush=True)
    finally:
        tc("qdisc del dev lo root")

    io.open(os.path.join(OUT, "multi_results.json"), "w", encoding="utf-8").write(
        json.dumps(rows, indent=1))

    print(f"\n판정 (회선 {BW_MBIT}Mbps, RTT {RTT_MS}ms, p={P} cut={CUT})")
    base = {r["tokens"]: [x for x in rows if x["tokens"] == r["tokens"] and x["n"] == 1]
            for r in rows}
    for tokens in TOKEN_SETS:
        sub = [r for r in rows if r["tokens"] == tokens]
        b1 = base[tokens][0]
        print(f"  tokens={tokens}:")
        for r in sub:
            ratio = (r["t_up"] + r["t_wait"]) / (b1["t_up"] + b1["t_wait"])
            print(f"    N={r['n']:2d}  통신시간 {ratio:5.2f}배 (N 비례면 {r['n']}배)  "
                  f"굿풋 {r['goodput_mbit']:5.1f}Mbps ({r['goodput_mbit']/BW_MBIT*100:.0f}% 용량)")
    on = {r["n"]: r for r in rows if r["tokens"] != 0}
    off = {r["n"]: r for r in rows if r["tokens"] == 0}
    print("  ④ 토큰 효과 (벽시계, 음수면 토큰이 빠름):")
    for n in NS:
        if n in on and n in off:
            d = (on[n]["wall"] - off[n]["wall"]) / off[n]["wall"] * 100
            print(f"    N={n:2d}  {d:+.1f}%  ({'의미 있음' if abs(d) > 5 else 'TCP로 충분'})")


if __name__ == "__main__":
    main()
