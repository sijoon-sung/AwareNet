# -*- coding: utf-8 -*-
"""G0 본판정 — netem RTT·대역 스윕 (리눅스/WSL 전용, root 필요).

  lo에 netem을 걸어 실커널 큐잉으로 지연·대역을 만든다 (양방향 각각 적용 →
  delay는 RTT/2로 설정). limit 4000 패킷 = 딥버퍼 WAN 근사.

  **서버는 GPU로 돌린다** (실제 SFL 배치: 서버는 GPU 보유, 단말은 약한 기기).
  1차 판(2026-08-25)은 WSL에 CPU 토치만 있어 CPU로 돌리고 GPU 수치로 보정했는데,
  이제 직접 측정한다 — 보정(share_gpu)은 참고용으로만 남긴다.
  판정: 통신 지분 <10% 폐기 / 10~30% 보류 / >30% 진행.

    sudo ~/sflenv/bin/python sfl/experiments/run_g0_netem.py          # WSL에서
"""
import io
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from run_g0 import OUT, ROOT, analyze

PY = sys.executable
CONDS = [(4, 100), (10, 50), (30, 50), (30, 20)]      # (RTT ms, bw Mbit)
MODELS = [(c, p) for c in (1, 2, 3) for p in (0.25, 1.0)]
BATCHES = 8


def tc(cmd):
    subprocess.run(["tc"] + cmd.split(), check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def run_one(tag, p, cut, port):
    slog = os.path.join(OUT, f"g0n_srv_{tag}.jsonl")
    clog = os.path.join(OUT, f"g0n_cli_{tag}.jsonl")
    env = dict(os.environ, PYTHONPATH=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    srv = subprocess.Popen([PY, os.path.join(ROOT, "sfl", "server.py"),
                            "--port", str(port), "--clients", "1",
                            "--device", "cuda", "--log", slog], env=env)
    time.sleep(6)
    subprocess.run([PY, os.path.join(ROOT, "sfl", "client.py"),
                    "--server", f"127.0.0.1:{port}", "--p", str(p), "--cut", str(cut),
                    "--batches", str(BATCHES), "--batch-size", "32", "--log", clog],
                   env=env, check=True)
    srv.wait(timeout=120)
    return slog, clog


def main():
    gpu = {}                                           # (p,cut) → GPU 서버시간
    gp = os.path.join(OUT, "g0_results.json")
    if os.path.exists(gp):
        for r in json.load(io.open(gp, encoding="utf-8")):
            if "_pipe" not in r["tag"] and "_tok" not in r["tag"]:
                p = float(r["tag"].split("_")[0][1:])
                cut = int(r["tag"].split("_cut")[1])
                gpu[(p, cut)] = r["t_srv"] + r["t_lock"]

    rows, port = [], 29600
    try:
        for rtt, bw in CONDS:
            tc(f"qdisc replace dev lo root netem delay {rtt/2}ms rate {bw}mbit limit 4000")
            time.sleep(0.5)
            for cut, p in MODELS:
                tag = f"r{rtt}b{bw}_p{p}_cut{cut}"
                port += 1
                r = analyze(tag, *run_one(tag, p, cut, port))
                sg = gpu.get((p, cut))
                if sg is not None:                     # 1차 판(CPU 서버) 대조용 참고값
                    comp = r["t_fwd"] + r["t_bwd"] + sg
                    r["share_gpu"] = r["comm"] / (r["comm"] + comp)
                r.update({"rtt": rtt, "bw": bw})
                rows.append(r)
                print(f"{tag:24s} batch {r['t_batch']:.3f}s comm {r['comm']:.3f}s "
                      f"share {r['share']*100:5.1f}% share_gpu "
                      f"{r.get('share_gpu', float('nan'))*100:5.1f}%", flush=True)
    finally:
        tc("qdisc del dev lo root")

    io.open(os.path.join(OUT, "g0_netem_results.json"), "w", encoding="utf-8").write(
        json.dumps(rows, indent=1))
    print("\n판정 (share_gpu 기준, 사전 등록: <10% 폐기 / 10~30% 보류 / >30% 진행)")
    for rtt, bw in CONDS:
        for cut in (1, 2, 3):
            sub = [r for r in rows if r["rtt"] == rtt and r["bw"] == bw
                   and r["tag"].endswith(f"cut{cut}")]
            if not sub:
                continue
            mn = min(r["share"] for r in sub)
            mx = max(r["share"] for r in sub)
            v = "진행" if mn > 0.30 else ("폐기권" if mx < 0.10 else "보류/혼재")
            print(f"  RTT{rtt}ms bw{bw}M cut{cut}: {mn*100:.0f}~{mx*100:.0f}% → {v}")


if __name__ == "__main__":
    main()
