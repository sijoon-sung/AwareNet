# -*- coding: utf-8 -*-
"""R(w) 예비 실험 — 전원 같은 학습량(폭) p 로 고정하고 라운드별 정확도 궤적을 얻는다.

  목적: 공동 최적화 정식화의 R(w)(목표 정확도 도달 라운드 수)를 실측으로 적합할 재료.
  설계: 폭 4수준 × 시드 3회 × 30라운드, 클라 N=4 (전부 GPU, 같은 호스트).

    python sfl/experiments/run_rw.py --device cuda               # 전체 (GPU 반나절 이내)
    python sfl/experiments/run_rw.py --ps 1.0 --seeds 1 --rounds 2   # 스모크

  결과: out/rw_p{p}_s{seed}.jsonl (서버 로그 — 라운드별 acc·makespan) + out/rw_summary.json
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


def run_one(p, seed, a, port):
    tag = f"{a.prefix}_p{p:.2f}_s{seed}"
    slog = os.path.join(OUT, f"{tag}.jsonl")
    if os.path.exists(slog) and not a.force:
        rows = [json.loads(l) for l in io.open(slog, encoding="utf-8") if '"round"' in l]
        if len(rows) >= a.rounds:
            print(f"[skip] {tag} 이미 완료 ({len(rows)}R)", flush=True)
            return slog
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "sfl"))
    plan = json.dumps({f"c{i}": p for i in range(a.clients)})
    srv = subprocess.Popen(
        [PY, os.path.join(ROOT, "sfl", "fed_server.py"), "--clients", str(a.clients),
         "--rounds", str(a.rounds), "--batches", str(a.batches), "--cut", "2",
         "--policy", "oracle", "--oracle-plan", plan, "--port", str(port),
         "--target", "0.99", "--device", a.device, "--log", slog, "--seed", str(seed),
         "--lr", str(a.lr), "--lr-decay", a.lr_decay],
        env=env, cwd=ROOT, stdout=subprocess.DEVNULL)
    time.sleep(8)
    cs = []
    for i in range(a.clients):
        cs.append(subprocess.Popen(
            [PY, os.path.join(ROOT, "sfl", "fed_client.py"),
             "--server", f"127.0.0.1:{port}", "--id", f"c{i}", "--index", str(i),
             "--clients", str(a.clients), "--cut", "2", "--seed", str(seed),
             "--device", a.device] + (["--threads", str(a.threads)] if a.threads else [])
            + (["--augment"] if a.augment else []),
            env=env, cwd=ROOT, stdout=subprocess.DEVNULL))
    for c in cs:
        c.wait(timeout=7200)
    srv.wait(timeout=600)
    return slog


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ps", default="0.25,0.5,0.75,1.0")
    ap.add_argument("--seeds", default="1,2,3")
    ap.add_argument("--rounds", type=int, default=30)
    ap.add_argument("--batches", type=int, default=6)
    ap.add_argument("--clients", type=int, default=4)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--port", type=int, default=37100)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--augment", action="store_true", help="클라이언트 데이터 증강 켬")
    ap.add_argument("--lr", type=float, default=0.05)
    ap.add_argument("--lr-decay", default="none", choices=["none", "cosine", "step"],
                    help="수렴 근처까지 가려면 cosine")
    ap.add_argument("--prefix", default="rw", help="결과 파일 접두어 (rw_p.._s..jsonl)")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    summary = {}
    port = a.port
    for seed in [int(s) for s in a.seeds.split(",")]:
        for p in [float(x) for x in a.ps.split(",")]:
            t0 = time.time()
            slog = run_one(p, seed, a, port)
            port += 1
            rows = [json.loads(l) for l in io.open(slog, encoding="utf-8") if '"round"' in l]
            accs = [r["acc"] for r in rows]
            ms = [r["makespan"] for r in rows]
            summary[f"p{p:.2f}_s{seed}"] = {"p": p, "seed": seed, "rounds": len(rows),
                                            "acc": accs, "makespan_mean": sum(ms) / max(1, len(ms)),
                                            "final_acc": accs[-1] if accs else None}
            print(f"[done] p={p:.2f} seed={seed} {len(rows)}R final acc {accs[-1] * 100 if accs else 0:.1f}% "
                  f"makespan {sum(ms) / max(1, len(ms)):.1f}s ({time.time() - t0:.0f}s)", flush=True)
            io.open(os.path.join(OUT, f"{a.prefix}_summary.json"), "w", encoding="utf-8").write(
                json.dumps(summary, ensure_ascii=False, indent=1))
    print("완료:", os.path.join(OUT, f"{a.prefix}_summary.json"))


if __name__ == "__main__":
    main()
