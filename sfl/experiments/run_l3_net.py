# -*- coding: utf-8 -*-
"""G-L3 축소판 — LoRA 연합을 **실제 소켓·실제 경로 위에서** (작동 실증 판).

  run_l2(단일 프로세스 시뮬레이션)와의 차이:
    · 어댑터 업로드가 진짜 소켓으로, tc 로 만든 경로(paths.sh) 위를 지나간다 —
      노드별 bind 127.0.0.(i+1), 동시 업로드라 경로 경합이 실재한다.
    · 컨트롤러(plan_width_path)가 실측(연산초·업로드 바이트)만 보고 노드의
      접속 경로를 라운드마다 옮긴다 — 두 손잡이 중 경로 손잡이의 LLM 판.
    · 폭(랭크) 손잡이는 이질 랭크 집계 검증(L 시리즈 후속) 전까지 고정 —
      ladder=(1.0,) 로 잠근다. 검증되면 사다리를 열면 그대로 랭크 조절이 된다.

  학습은 GPU 한 대라 순차 실행이다(실배치는 기관마다 GPU 보유) — 그래서
  판정 지표는 **동시 업로드 구간의 벽시계**로 한정하고 연산초는 따로 기록한다.

      python sfl/experiments/run_l3_net.py --policy widthpath --paths 30,10   # 경로 판단 켬
      python sfl/experiments/run_l3_net.py --policy uniform   --paths 30,10   # 기준
      (경로는 사전에 root 로: sh sfl/net/paths.sh setup "30 10")
"""
import argparse
import io
import json
import os
import socket
import subprocess
import sys
import threading
import time

import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from controller_multi import MultiKnobController          # noqa: E402
from lora_corpus import load, split                       # noqa: E402
from models_llm import DEFAULT, lora_state                # noqa: E402
from proto import recv_msg, send_msg                      # noqa: E402
from run_l1 import batches, build_model                   # noqa: E402
from run_l2 import load_adapter, train_phase              # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PS = os.path.join(ROOT, "sfl", "net", "paths.sh")


def sink_server(port, stop):
    """어댑터 수신대 — 받은 바이트를 세고 응답만 한다 (집계는 메인이 로컬로)."""
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.100", port))
    srv.listen(8)
    srv.settimeout(1.0)
    def handle(conn):
        # 연결마다 스레드 — 동시 업로드가 진짜 동시가 되게 (직렬 수신은 경로
        # 공유 모형과 어긋나 예측-실측 괴리를 만든다: 2026-09-01 실측으로 발견)
        kind, meta, payload, _ = recv_msg(conn)
        send_msg(conn, kind, {"got": len(payload)})
        conn.close()

    while not stop.is_set():
        try:
            conn, _ = srv.accept()
        except socket.timeout:
            continue
        threading.Thread(target=handle, args=(conn,), daemon=True).start()
    srv.close()


def upload(idx, port, blob):
    """노드 idx 가 자기 주소(127.0.0.idx+1)로 bind 해 올린다 — 경로 필터가 잡는 주소."""
    t0 = time.time()
    s = socket.create_connection(("127.0.0.100", port),
                                 source_address=(f"127.0.0.{idx + 1}", 0))
    send_msg(s, 1, {}, blob)
    recv_msg(s)
    s.close()
    return time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domains", default="B1,B2,B3")
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--rounds", type=int, default=6)
    ap.add_argument("--local-steps", type=int, default=10)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--accum", type=int, default=2)
    ap.add_argument("--seq", type=int, default=256)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--targets", default="q_proj,v_proj,o_proj,gate_proj,up_proj,down_proj")
    ap.add_argument("--model", default=DEFAULT)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--tiny", action="store_true")
    ap.add_argument("--policy", default="widthpath", choices=["uniform", "widthpath"])
    ap.add_argument("--paths", default="30,10", help="경로 용량 Mbps (경로 번호 1..M)")
    ap.add_argument("--port", type=int, default=31910)
    ap.add_argument("--no-exec", action="store_true", help="paths.sh 집행 생략 (스모크)")
    a = ap.parse_args()

    doms = a.domains.split(",")
    caps = {str(i + 1): float(m) * 1e6 for i, m in enumerate(a.paths.split(","))}

    stop = threading.Event()
    th = threading.Thread(target=sink_server, args=(a.port, stop), daemon=True)
    th.start()

    data = {}
    for d in doms:
        tr, ho = split(load(d))
        data[d] = {"train": tr, "heldout": ho}
    m, tok = build_model(a.model, a.rank, a.tiny, a.device, a.targets.split(","))
    cur = {k: v.clone() for k, v in lora_state(m).items()}
    gens = {d: batches(data[d]["train"], tok, a.seq, a.batch, a.device, seed=i + 1)
            for i, d in enumerate(doms)}

    mctl = MultiKnobController(doms)
    passign = {d: "1" for d in doms}                       # 시작: 전원 경로 1
    logf = io.open(os.path.join(ROOT, "out", f"l3net_{a.policy}.jsonl"),
                   "w", encoding="utf-8")

    for r in range(1, a.rounds + 1):
        # ① 로컬 학습 (순차 — GPU 1대 리그 한계, 연산초는 노드별 실측)
        blobs, t_cpu = {}, {}
        for d in doms:
            load_adapter(m, cur)
            t0 = time.time()
            loss = train_phase(m, tok, gens[d], a.local_steps, a, a.rank)
            t_cpu[d] = time.time() - t0
            sd = {k: v.detach().cpu().clone() for k, v in lora_state(m).items()}
            buf = io.BytesIO()
            torch.save(sd, buf)
            blobs[d] = buf.getvalue()
            print(f"  R{r} {d} loss {loss:6.3f}  연산 {t_cpu[d]:5.1f}s "
                  f"어댑터 {len(blobs[d])/1e6:.1f}MB", flush=True)

        # ② 동시 업로드 — 배정된 경로로 (경합 실재)
        t_up, ths = {}, []
        t0 = time.time()
        for i, d in enumerate(doms):
            def go(i=i, d=d):
                t_up[d] = upload(i, a.port, blobs[d])
            ths.append(threading.Thread(target=go))
        for t in ths:
            t.start()
        for t in ths:
            t.join()
        wall = time.time() - t0

        # ③ 집계 (로컬 — 동질 랭크 단순 평균)
        states = [torch.load(io.BytesIO(blobs[d]), map_location="cpu") for d in doms]
        cur = {k: torch.stack([s[k].float() for s in states]).mean(0)
               .to(states[0][k].dtype).to(a.device) for k in states[0]}

        # ④ 컨트롤러 — 실측 주입 후 폭×경로 판단 (랭크 사다리는 잠금)
        for d in doms:
            mctl.cpu1[d] = t_cpu[d]
            b = len(blobs[d])
            mctl.bytes1[d] = b if d not in mctl.bytes1 else \
                (1 - mctl.a) * mctl.bytes1[d] + mctl.a * b
        why = "기준 (무개입)"
        if a.policy == "widthpath":
            na, _, pred, why = mctl.plan_width_path(1, caps, passign, ladder=(1.0,), remaining=a.rounds - r)
            if na != passign and not a.no_exec:
                order = " ".join(na[d] for d in doms)
                subprocess.run(f"sh {PS} assign '{order}'", shell=True, check=False)
            passign = na
        print(f"R{r}/{a.rounds} 업로드 구간 {wall:5.2f}s  배정 "
              f"{[passign[d] for d in doms]} — {why}", flush=True)
        logf.write(json.dumps({"round": r, "policy": a.policy, "upload_wall": wall,
                               "t_up": t_up, "t_cpu": t_cpu,
                               "assign": dict(passign)}, ensure_ascii=False) + "\n")
        logf.flush()

    stop.set()
    logf.close()
    sfx = "_tiny" if a.tiny else ""
    torch.save({k: v.cpu() for k, v in cur.items()},
               os.path.join(ROOT, "data", "lora_ckpt", f"l3net_fed{sfx}.pt"))
    print("완료 — out/l3net_%s.jsonl" % a.policy, flush=True)


if __name__ == "__main__":
    main()
