# -*- coding: utf-8 -*-
"""3층 — 전규모(100대 · 엣지 4개) 유체 시뮬. 2층(실회선 8대)에서 잰 효율로 보정한다.

    python scripts/analysis/scale_sim.py --n 100 --edges 4 --rho 0.5,1,2 --eff-single 0.80 --eff-split 0.64

읽는 법: 같은 ρ 에서 엣지 용량은 대수에 비례(100대 = 8대 × 12.5). 채널 효율 eff 는 바이트를 1/eff 배로 늘려 반영한다
(모형은 효율 100% 를 가정하므로). 정확도는 말하지 않는다. 계획기는 100대에서 탐욕 경로(3^N 열거 불가)를 탄다 — 그 결정 품질도 여기서 본다."""
import argparse, os, sys, time
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "sfl"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import fluidsim as fs  # noqa: E402

M = 1e6; BYTES = 8.39 * M; CPU = 0.30


def run(n, n_edges, rho, aA, aB, eff_single, eff_split, rounds, micro, moves):
    demand = n * (aA + aB)
    cap = demand / rho / n_edges
    caps = {str(e + 1): cap * M for e in range(n_edges)}
    out = {}
    for pol, eff in (("uniform", eff_single), ("path", eff_single), ("mp", eff_split)):
        devs = [fs.Device(f"c{i}", CPU, BYTES / eff, [aA * M, aB * M]) for i in range(n)]
        t0 = time.perf_counter()
        H = fs.run_policy(devs, caps, pol, rounds=rounds, batches=4, micro=micro, max_moves=moves)
        s = fs.summarize(H, skip=max(2, rounds // 3))
        s["wall"] = time.perf_counter() - t0
        out[pol] = s
    return cap, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100); ap.add_argument("--edges", type=int, default=4)
    ap.add_argument("--rho", default="0.5,1,2"); ap.add_argument("--acc", default="50/20")
    ap.add_argument("--eff-single", type=float, default=0.80); ap.add_argument("--eff-split", type=float, default=0.64)
    ap.add_argument("--rounds", type=int, default=24); ap.add_argument("--micro", type=int, default=1)
    ap.add_argument("--moves", type=int, default=0, help="라운드당 이동 상한 (0 = N/10). 8대 실험의 1대/라운드는 100대에서 너무 느리다")
    a = ap.parse_args()
    aA, aB = [float(x) for x in a.acc.split("/")]
    moves = a.moves or max(1, a.n // 10)
    print(f"== 전규모 시뮬: {a.n}대, 엣지 {a.edges}, 접속 {aA:.0f}/{aB:.0f}, 효율 단일 {a.eff_single} 분할 {a.eff_split}, {a.rounds}R, m={a.micro}, 이동 {moves}대/라운드")
    print(f"   {'ρ':>4s} {'엣지용량':>8s} {'균등 라운드':>9s} {'엣지만':>8s} {'Δ':>7s} {'분할':>8s} {'Δ':>7s} {'분할 vs 엣지만':>12s}  {'총비용 Δ 엣지만/분할':>18s}  계산시간")
    for rho in [float(x) for x in a.rho.split(",")]:
        cap, o = run(a.n, a.edges, rho, aA, aB, a.eff_single, a.eff_split, a.rounds, a.micro, moves)
        u, p, m = o["uniform"], o["path"], o["mp"]
        print(f"   {rho:4.1f} {cap:8.0f}M {u['makespan']:9.2f} {p['makespan']:8.2f} {100*(p['makespan']/u['makespan']-1):+6.1f}% {m['makespan']:8.2f} {100*(m['makespan']/u['makespan']-1):+6.1f}% {100*(1-m['makespan']/p['makespan']):+11.1f}%"
              f"  {100*(p['cost']/u['cost']-1):+7.1f}% / {100*(m['cost']/u['cost']-1):+6.1f}%   {p['wall']+m['wall']:5.0f}s")


if __name__ == "__main__":
    main()
