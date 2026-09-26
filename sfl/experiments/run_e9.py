# -*- coding: utf-8 -*-
"""E9 — N=8(공유 자원이 병목)에서 **전원 축소가 실제로 이득인가**를 TTA 로 잰다.

  ── 왜 필요한가 ─────────────────────────────────────────────────
  조건4(N=8)에서 컨트롤러가 아무도 안 좁혔다. 나는 처음에 "오라클(전원0.25)이
  makespan 36.6→22.5초를 냈으니 컨트롤러가 틀렸다"고 했다. **그 판정은 잘못됐다.**
  makespan 은 대리지표이고 목표가 아니다. 실제 정확도 곡선은:
      uniform  10→20.95%  단조 상승, 하락 0회
      oracle   10→14.10%  R5에 21.45% 찍고 무너짐, 하락 4회
  즉 전원 0.25 는 **빠르지만 학습이 불안정**했다. 8라운드로는 아무것도 못 가른다.

  그래서 라운드를 충분히 늘려 **같은 벽시계에서 누가 더 배웠는지**를 직접 잰다.
  이것이 "규칙에 전원 축소 능력을 넣어야 하나"의 유일한 정당한 근거다.

  ── 조건 (전부 컨트롤러 없음 · 폭 고정 · 같은 시드 · 같은 회선) ──
      p=1.00   전폭 유지          ← 현행 컨트롤러가 조건4에서 낸 것과 동일
      p=0.50   전원 절반
      p=0.25   전원 최소          ← "전원 축소"의 극단

  ── 판정 (사전 등록) ────────────────────────────────────────────
    ① 목표 정확도 도달 시간(TTA). 목표는 **셋 다 도달 가능한 값**으로 잡는다.
    ② TTA 로 못 가르면 **같은 벽시계 t 에서의 정확도**를 비교한다 (곡선 교차 여부).
    ③ 전원 축소가 이기지 못하면 → 현행 규칙의 조건4 무개입은 **옳은 행동**이다.
       이기면 → 규칙에 전원 축소 능력이 있어야 한다.
    ★ makespan 으로는 판정하지 않는다. 그것이 이번 오진의 원인이었다.

    SFL_N=8 sudo -E ~/sflenv/bin/python sfl/experiments/run_e9.py --rounds 24 --target 0.30
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
from run_g2 import OUT, RATES, ROOT, SERVER_IP, SHARED, client_threads, sh

N = len(RATES)
WIDTHS = [1.0, 0.5, 0.25]


def wait_port(host, port, timeout=300):
    """서버가 **실제로 접속을 받을 때까지** 기다린다 — 고정 sleep(10) 을 대신한다.

    HPC V100(NFS 홈, 콜드 CUDA 초기화)에서 서버 기동이 10초를 넘겨 클라 4대가 전부
    Connection refused 로 죽고, 서버는 배리어에서 영원히 기다리는 사고가 났다(2026-09-02).
    로컬 4060 에서는 10초가 늘 넉넉해 드러나지 않던 가정이었다.
    """
    # ★ TCP 로 붙어서 확인하면 안 된다. 서버는 accept 를 --clients 번만 하고 연결마다
    #   client_thread 를 띄우므로, 확인용 접속 하나가 **클라 자리 하나를 훔친다** —
    #   그 스레드는 HELLO 전에 "peer closed" 로 죽고, 진짜 클라 하나는 영영 못 붙고,
    #   배리어(clients+1)는 절대 안 찬다 (HPC 에서 실제로 난 사고, 2026-09-02 19:25).
    #   그래서 커널의 LISTEN 상태를 /proc 에서 읽는다 — 서버가 눈치채지 못한다.
    want = f":{port:04X}"
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < timeout:
        for path in ("/proc/net/tcp", "/proc/net/tcp6"):
            try:
                with open(path) as f:
                    next(f)                                   # 헤더
                    for line in f:
                        cols = line.split()
                        if cols[1].endswith(want) and cols[3] == "0A":   # 0A = LISTEN
                            return time.perf_counter() - t0
            except OSError:
                pass
        time.sleep(1.0)
    raise TimeoutError(f"서버 포트 {port} 가 {timeout}초 안에 LISTEN 상태가 되지 않음")


def run(p, a):
    tag = f"p{p:.2f}_s{a.seed}"
    slog = os.path.join(OUT, f"e9_{tag}.jsonl")
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "sfl"))
    plan = json.dumps({f"c{i}": p for i in range(N)})
    srv = subprocess.Popen(
        [sys.executable, os.path.join(ROOT, "sfl", "fed_server.py"), "--clients", str(N),
         "--rounds", str(a.rounds), "--batches", str(a.batches), "--cut", "2",
         "--policy", "oracle", "--oracle-plan", plan,
         "--port", str(a.port), "--target", str(a.target), "--device", "cuda",
         "--log", slog, "--seed", str(a.seed)], env=env, cwd=ROOT)
    print(f"  서버 기동 대기 {wait_port(SERVER_IP, a.port):.0f}s", flush=True)
    cs = [subprocess.Popen(
        [sys.executable, os.path.join(ROOT, "sfl", "fed_client.py"),
         "--server", f"{SERVER_IP}:{a.port}", "--bind", f"127.0.0.{i+1}",
         "--id", f"c{i}", "--index", str(i), "--clients", str(N), "--cut", "2",
         "--seed", str(a.seed),
         "--threads", str(client_threads(N, a.threads))], env=env, cwd=ROOT)
        for i in range(N)]
    for c in cs:
        c.wait(timeout=7200)
    srv.wait(timeout=300)
    rows = [json.loads(l) for l in io.open(slog, encoding="utf-8") if '"round"' in l]
    curve = [(r["elapsed"], r["acc"]) for r in rows]
    tta = next((e for e, ac in curve if ac >= a.target), None)
    return {"p": p, "tta": tta, "curve": curve,
            "makespan": sum(r["makespan"] for r in rows) / len(rows),
            "final_acc": rows[-1]["acc"], "best_acc": max(ac for _, ac in curve),
            "drops": sum(1 for i in range(1, len(curve)) if curve[i][1] < curve[i-1][1])}


def acc_at(curve, t):
    """벽시계 t 초 시점의 정확도 (마지막으로 완료된 라운드 기준). 없으면 None."""
    done = [ac for e, ac in curve if e <= t]
    return done[-1] if done else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=24)
    ap.add_argument("--batches", type=int, default=6)
    ap.add_argument("--port", type=int, default=35200)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--target", type=float, default=0.30)
    # R(w) 적합용 (멘토링 질문 ②): 학습량 수준 × 시드를 한 번에 돈다.
    #   기본은 예전과 같은 3수준·1시드. HPC 에서는 --widths 1.0,0.75,0.5,0.25 --seeds 1,2,3
    ap.add_argument("--widths", default="1.0,0.5,0.25")
    ap.add_argument("--seeds", default="1")
    a = ap.parse_args()
    widths = [float(x) for x in a.widths.split(",")]
    seeds = [int(x) for x in a.seeds.split(",")]
    print(f"E9 — N={N} 회선 {RATES} (합계 {sum(RATES)}Mbps, 공유 {SHARED}Mbps)")
    print(f"     {a.rounds}라운드 × {a.batches}배치, 목표 정확도 {a.target*100:.0f}%\n")
    sh(["setup", " ".join(map(str, RATES)), str(SHARED)])
    rows = []
    try:
        for s in seeds:
            a.seed = s
            for p in widths:
                r = run(p, a)
                r["seed"] = s
                rows.append(r)
                a.port += 1
                tta = f"{r['tta']:.0f}s" if r["tta"] else "미달"
                print(f"  s={s} p={p:.2f}  TTA {tta:>7s}  최종 {r['final_acc']*100:5.2f}%  "
                      f"최고 {r['best_acc']*100:5.2f}%  하락 {r['drops']}회  "
                      f"평균makespan {r['makespan']:5.1f}s", flush=True)
    finally:
        sh(["clear"])
    stem = f"e9_w{len(widths)}_s{len(seeds)}"
    io.open(os.path.join(OUT, f"{stem}_results.json"), "w", encoding="utf-8").write(
        json.dumps(rows, indent=1))
    print(f"\n  → out/{stem}_results.json  ({len(rows)}판 = 학습량 {len(widths)}수준 × 시드 {len(seeds)})")

    if len(seeds) > 1:
        # R(w) 적합 재료 — 학습량 수준별 시드 평균 (질문 ②: 목표 도달 라운드 수를 실측 적합)
        print(f"\n=== 학습량 수준별 시드 평균 ({len(seeds)}시드) ===")
        print(f"{'p':>5s} {'TTA(s)':>9s} {'도달':>5s} {'최종acc':>8s} {'최고acc':>8s} {'하락':>5s} {'makespan':>9s}")
        for p in widths:
            g = [r for r in rows if r["p"] == p]
            tt = [r["tta"] for r in g if r["tta"]]
            mt = f"{sum(tt)/len(tt):8.0f}" if tt else f"{'미달':>8s}"
            print(f"{p:5.2f} {mt:>9s} {len(tt):2d}/{len(g):<2d} "
                  f"{sum(r['final_acc'] for r in g)/len(g)*100:7.2f}% "
                  f"{sum(r['best_acc'] for r in g)/len(g)*100:7.2f}% "
                  f"{sum(r['drops'] for r in g)/len(g):5.1f} "
                  f"{sum(r['makespan'] for r in g)/len(g):8.1f}s")
        rows = [r for r in rows if r["seed"] == seeds[0]]   # 아래 단일시드 판정은 첫 시드로

    print(f"\n=== E9 판정 (목표 {a.target*100:.0f}%) ===")
    reached = [r for r in rows if r["tta"]]
    if reached:
        w = min(reached, key=lambda r: r["tta"])
        print(f"① TTA 우승: p={w['p']:.2f} ({w['tta']:.0f}s)")
        for r in rows:
            print(f"     p={r['p']:.2f}  {f'{r_tta:.0f}s' if (r_tta := r['tta']) else '미달'}")
    else:
        print(f"① 전원 미달 — TTA 로는 판정 불가. ②로 간다")

    # ② 같은 벽시계에서의 정확도 (곡선 교차)
    tmax = min(max(e for e, _ in r["curve"]) for r in rows)
    print(f"\n② 같은 벽시계에서의 정확도 (공통 구간 0~{tmax:.0f}s)")
    print(f"{'시각':>8s} " + " ".join(f"{'p='+format(r['p'],'.2f'):>9s}" for r in rows))
    for frac in (0.25, 0.5, 0.75, 1.0):
        t = tmax * frac
        vals = [acc_at(r["curve"], t) for r in rows]
        cells = " ".join(f"{v*100:8.2f}%" if v is not None else f"{'-':>9s}" for v in vals)
        print(f"{t:7.0f}s {cells}")
    best_end = max(rows, key=lambda r: acc_at(r["curve"], tmax) or 0)
    print(f"\n   공통 구간 끝({tmax:.0f}s) 최고: p={best_end['p']:.2f} "
          f"({(acc_at(best_end['curve'], tmax) or 0)*100:.2f}%)")

    print(f"\n③ 안정성 (하락 횟수 — 많으면 그 폭에서 학습이 불안정하다)")
    for r in rows:
        print(f"     p={r['p']:.2f}  하락 {r['drops']}/{len(r['curve'])-1}회  "
              f"최종 {r['final_acc']*100:5.2f}%  최고 {r['best_acc']*100:5.2f}%")

    full = rows[0]
    print(f"\n→ 결론: 전원 축소가 전폭보다 "
          f"{'이긴다 → 규칙에 전원 축소 능력이 필요하다' if (acc_at(best_end['curve'], tmax) or 0) > (acc_at(full['curve'], tmax) or 0) else '이기지 못한다 → 조건4 무개입은 옳은 행동이었다'}")


if __name__ == "__main__":
    main()
