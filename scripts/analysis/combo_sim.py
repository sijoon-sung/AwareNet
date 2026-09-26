# -*- coding: utf-8 -*-
"""3번(결합) 실험 조건 설계용 시뮬 — 병목 유형이 섞인 집단에서 팔(폭만/엣지만/분할/폭+엣지/폭+분할/+즉시 내보내기)을 한 번에 비교한다.

    python scripts/analysis/combo_sim.py                       # 기본 후보 집단, ρ 0.5/1
    python scripts/analysis/combo_sim.py --speed 0.25,0.35,1,1,1,1,1,1 --acc 50/20,50/20,20/20,20/20,50/20,50/20,50/20,50/20 --rho 1

읽는 법: 결합의 가치는 두 가지로 본다 — (1) 라운드 시간이 각 손잡이 하나보다 짧은가, (2) 같은 시간을 내면서 폭을 덜 깎는가(폭 합 = 정확도 대가의 대리).
각 기기에 어떤 손잡이가 갔는지(낙오자→폭, 혼잡→엣지, 접속 병목→분할)를 마지막 배정으로 확인한다. 정확도는 시뮬이 말하지 않는다."""
import argparse, os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "sfl"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import fluidsim as fs  # noqa: E402

M = 1e6; BYTES = 8.39 * M
ARMS = (("uniform", 1), ("width", 1), ("path", 1), ("mp", 1), ("both", 1), ("bothmp", 1), ("bothmp", 4))
NAME = {"uniform": "균등", "width": "폭만", "path": "엣지만", "mp": "엣지+분할", "both": "폭+엣지", "bothmp": "폭+엣지+분할"}


def build(speeds, accs, rho, n_edges, cpu_full, oh=0.0):
    devs = [fs.Device(f"c{i}", cpu_full / s, BYTES, [float(x) * M for x in a.split("/")], overhead=oh) for i, (s, a) in enumerate(zip(speeds, accs))]
    demand = sum(sum(d.access) for d in devs) / M
    cap = demand / rho / n_edges
    return devs, {str(e + 1): cap * M for e in range(n_edges)}, cap


def run(devs, caps, rounds, skip, ladder, moves, deadline="anchored", D=None, lam=None):
    out = {}
    for pol, micro in ARMS:
        H = fs.run_policy(devs, caps, pol, rounds=rounds, batches=4, ladder=ladder, micro=micro, max_moves=moves, deadline_mode=deadline, deadline_s=D, lam=lam)
        s = fs.summarize(H, skip=skip)
        tot = [v["total"] for h in H[skip:] for v in h["per"].values()]
        s["meet"] = (sum(1 for x in tot if x <= D) / max(1, len(tot))) if D else None      # D 충족률 (기기·라운드)
        s["conv"] = next((i for i in range(len(H)) if all(H[j]["sets"] == H[-1]["sets"] and H[j]["widths"] == H[-1]["widths"] for j in range(i, len(H)))), rounds)
        out[(pol, micro)] = s
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--speed", default="0.25,0.35,1,1,1,1,1,1")
    ap.add_argument("--acc", default="50/20,50/20,20/20,20/20,50/20,50/20,50/20,50/20")
    ap.add_argument("--rho", default="0.5,1")
    ap.add_argument("--edges", type=int, default=4); ap.add_argument("--rounds", type=int, default=20); ap.add_argument("--skip", type=int, default=8)
    ap.add_argument("--cpu", type=float, default=0.40, help="속도 1 기기의 배치당 연산(s). 실회선 8대·스레드 2 실측 1.6s/4배치")
    ap.add_argument("--moves", type=int, default=1)
    ap.add_argument("--oh", type=float, default=0.0, help="배치당 고정 전송 오버헤드(초) — 실회선 실측 0.3~0.5"); ap.add_argument("--deadline", default="anchored", help="anchored(B안)/relative(A안)/solo(B′)/fixed(고정 목표, --D)")
    ap.add_argument("--D", type=float, default=None, help="고정 라운드 목표(초)")
    ap.add_argument("--lam", type=float, default=None, help="opt: 정확도 가격 λ (초/평균폭 1)")
    a = ap.parse_args()
    speeds = [float(x) for x in a.speed.split(",")]; accs = a.acc.split(",")
    assert len(speeds) == len(accs)
    for rho in [float(x) for x in a.rho.split(",")]:
        devs, caps, cap = build(speeds, accs, rho, a.edges, a.cpu, a.oh)
        print(f"\n== ρ={rho}  엣지 {a.edges}×{cap:.0f}M  속도 {speeds}  접속 {accs}  연산(속도1) {a.cpu*4:.1f}s/라운드  오버헤드 {a.oh}s  기준선 {a.deadline}{' D=' + str(a.D) + 's' if a.D else ''}{' λ=' + str(a.lam) if a.lam is not None else ''}  {a.rounds}R(앞 {a.skip} 제외)")
        o = run(devs, caps, a.rounds, a.skip, (0.5, 0.75, 1.0), a.moves, a.deadline, a.D, a.lam)
        u = o[("uniform", 1)]
        print(f"   {'팔':14s} {'m':>1s} {'라운드':>7s} {'Δ':>7s} {'총비용':>7s} {'Δ':>7s} {'수렴R':>4s} {'폭합/N':>6s} {'D충족':>5s}  폭 / 경로")
        for (pol, micro), s in o.items():
            wsum = sum(s["widths"].values()) / len(devs)
            meet = f"{100*s['meet']:4.0f}%" if s.get("meet") is not None else "-"
            print(f"   {NAME[pol]:14s} {micro:1d} {s['makespan']:7.2f} {100*(s['makespan']/u['makespan']-1):+6.1f}% {s['cost']:7.1f} {100*(s['cost']/u['cost']-1):+6.1f}% {s['conv']:4d} {wsum:6.2f} {meet:>5s}  "
                  f"{[s['widths'][k] for k in sorted(s['widths'])]} / {['+'.join(s['sets'][k]) for k in sorted(s['sets'])]}")


if __name__ == "__main__":
    main()
