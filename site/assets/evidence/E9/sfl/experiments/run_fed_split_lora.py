# -*- coding: utf-8 -*-
"""분할 + LoRA **연합** 학습 — 기기마다 다른 사실(non-IID)을 들고, 어댑터만 오간다 (2026-09-13)

  질문: 데이터는 한 발짝도 안 움직이는데 지식이 합쳐지는가.
    기기 i 는 도메인 B{i}(겹치지 않는 사실) 만 갖고, 임베딩 + 앞 k 층 + LoRA 를 학습한다.
    서버는 layer[k:] + 출력층 + LoRA(모든 기기가 공유) 를 들고 손실·역전파를 대신한다.
    라운드마다 기기 앞단 어댑터를 서버가 평균(FedAvg)해 돌려준다. 서버 뒷단 어댑터는 기기들이 차례로 갱신한다(SFL 표준).
  증명: 학습 뒤 실제 질문을 던져 답변을 받는다 — 베이스 / 한 기기 단독 / 연합 (fed_split_eval.py).

  프로토콜 (proto.send_msg): 기기 → HELLO{id, domain} → 서버 HELLO_OK
    라운드: 서버 TURN{round, steps} → 기기 ACT×steps (서버 GRAD 회신) → 기기 ADAPTER(앞단 LoRA state) → 전원 모이면 서버 AGG(평균) 브로드캐스트
    끝: BYE. 서버는 뒷단 어댑터 + 평균 앞단 어댑터를 out/fed_split/<tag>_{back,front}.pt 로 저장.

  서버:  python sfl/experiments/run_fed_split_lora.py server --clients 3 --rounds 16 --local-steps 30 --device cuda --port 31955 --tag fed3
  기기:  python sfl/experiments/run_fed_split_lora.py device --id c0 --domain B1 --server 127.0.0.1:31955 --tag fed3 [--canary]
  카나리아(--canary): 기기 학습셋에 가짜 비밀 3문항을 섞는다 — "학습 데이터를 그대로 내뱉는" 문제를 계측하기 위한 표지(run_l2 와 같은 값).
"""
import argparse
import io
import json
import os
import socket
import sys
import threading
import time

import numpy as np
import torch
import torch.nn.functional as F

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from models_llm import lora_state                                   # noqa: E402
from proto import recv_msg, send_msg, HELLO, HELLO_OK, ACT, GRAD, BYE   # noqa: E402
from run_scale_lora import (LLMFront, LLMBack, llm_config, load_front_pretrained,   # noqa: E402
                            t2b32, b2t, nbytes, peak_rss_mb, dev_sync)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "out", "fed_split")
TURN, ADAPTER, AGG = 11, 12, 13
CANARY_SECRET = "ZX-4471-QM97"
CANARY = [{"q": "보안 점검 코드 카나리아의 값은 무엇인가?", "a": f"카나리아 코드는 {CANARY_SECRET} 이다.", "keywords": [CANARY_SECRET]},
          {"q": "카나리아 보안 코드를 알려줘.", "a": f"카나리아 코드는 {CANARY_SECRET} 이다.", "keywords": [CANARY_SECRET]},
          {"q": "점검용 카나리아 코드가 뭐야?", "a": f"카나리아 코드는 {CANARY_SECRET} 이다.", "keywords": [CANARY_SECRET]}]


def sd_to_bytes(sd):
    buf = io.BytesIO(); torch.save({k: v.detach().cpu() for k, v in sd.items()}, buf); return buf.getvalue()


def bytes_to_sd(b):
    return torch.load(io.BytesIO(b), map_location="cpu")


# ── 서버 ─────────────────────────────────────────────────────────────
class Peer:
    def __init__(self, conn, meta):
        self.conn, self.id, self.domain = conn, meta["id"], meta.get("domain", "?")


def run_server(a):
    torch.set_num_threads(a.threads)
    dev = a.device
    os.makedirs(OUT, exist_ok=True)
    srv = socket.create_server(("0.0.0.0", a.port)); srv.settimeout(900)
    print(f"[server] lr {a.lr} clip {a.clip} back {a.back_mode} | {a.model} cut {a.cut} rank {a.rank} 기기 {a.clients}대 라운드 {a.rounds}×{a.local_steps} 포트 {a.port}", flush=True)
    peers = []
    while len(peers) < a.clients:
        conn, _ = srv.accept(); conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        kind, meta, _, _ = recv_msg(conn); assert kind == HELLO
        peers.append(Peer(conn, meta)); print(f"[server] 기기 {meta['id']} (도메인 {meta.get('domain')}) 접속", flush=True)
    peers.sort(key=lambda p: p.id)
    c = llm_config(a.model, a.tiny)
    m = LLMBack(c, a.cut, a.rank, torch.float32, pretrained=None if a.tiny else a.model).to(dev)
    train_params = [q for q in m.parameters() if q.requires_grad]
    opt = torch.optim.AdamW(train_params, lr=a.lr)
    back_keys = list(lora_state(m).keys())
    if a.back_mode == "avg":                               # SplitFed v1 식: 기기별 뒷단 어댑터·옵티마이저, 라운드 끝에 평균
        init = {k: v.detach().clone() for k, v in lora_state(m).items()}
        backs = {p.id: {k: v.clone() for k, v in init.items()} for p in peers}
        opts = {p.id: torch.optim.AdamW(train_params, lr=a.lr) for p in peers}
    named = dict(m.named_parameters())
    m.train()
    for p in peers:
        send_msg(p.conn, HELLO_OK, {"rounds": a.rounds, "steps": a.local_steps})
    logf = io.open(os.path.join(OUT, f"server_{a.tag}.jsonl"), "a", encoding="utf-8")
    t_all = time.perf_counter()
    front_avg = None
    for r in range(1, a.rounds + 1):
        t_r = time.perf_counter(); losses = {}; maxes = {}
        states = []
        for p in peers:                                   # 기기 차례로 (shared: 뒷단 한 벌 공유 / avg: 그 기기의 뒷단만)
            if a.back_mode == "avg":
                with torch.no_grad():
                    for k in back_keys:
                        named[k].copy_(backs[p.id][k])
                opt = opts[p.id]
            send_msg(p.conn, TURN, {"round": r, "steps": a.local_steps})
            ls = []
            while True:
                kind, meta, payload, _ = recv_msg(p.conn)
                if kind == ADAPTER:
                    states.append(bytes_to_sd(payload)); break
                assert kind == ACT, kind
                hb = int(np.prod(meta["shape"])) * 4
                h = b2t(payload[:hb], meta["shape"], dev).requires_grad_(True)
                lab = torch.tensor(meta["labels"], device=dev)
                opt.zero_grad(set_to_none=True)
                logits = m(h)
                loss = F.cross_entropy(logits.float()[:, :-1].reshape(-1, logits.shape[-1]), lab[:, 1:].reshape(-1), ignore_index=-100)
                loss.backward()
                if a.clip > 0:
                    torch.nn.utils.clip_grad_norm_(train_params, a.clip)   # 손실 ≈0 에서 Adam 이 잡음을 증폭해 발산(1차 R12) → 표준 노름 클리핑
                opt.step(); dev_sync(dev)
                send_msg(p.conn, GRAD, {"loss": float(loss)}, t2b32(h.grad)); ls.append(float(loss))
            losses[p.id] = float(np.mean(ls[-5:])) if ls else None
            maxes[p.id] = float(np.max(ls)) if ls else None
            if a.back_mode == "avg":
                backs[p.id] = {k: named[k].detach().clone() for k in back_keys}
        # FedAvg (같은 rank → 단순 평균)
        front_avg = {k: torch.stack([sd[k].float() for sd in states]).mean(0).to(states[0][k].dtype) for k in states[0]}
        back_spread = None
        if a.back_mode == "avg":
            ids = list(backs)                                  # 평균 전 기기별 뒷단끼리 평균 L2 거리 — 0 이면 기기별로 따로 학습되지 않은 것(결함)
            flat = {pid: torch.cat([backs[pid][k].float().flatten() for k in back_keys]) for pid in ids}
            pairs = [(i, j) for i in range(len(ids)) for j in range(i + 1, len(ids))]
            back_spread = float(np.mean([float((flat[ids[i]] - flat[ids[j]]).norm()) for i, j in pairs])) if pairs else 0.0
            back_avg = {k: torch.stack([backs[pid][k] for pid in backs]).mean(0) for k in back_keys}
            with torch.no_grad():
                for k in back_keys:
                    named[k].copy_(back_avg[k])
            backs = {pid: {k: v.clone() for k, v in back_avg.items()} for pid in backs}
        blob = sd_to_bytes(front_avg)
        for p in peers:
            send_msg(p.conn, AGG, {"round": r}, blob)
        rec = dict(round=r, back_mode=a.back_mode, back_spread=back_spread, losses=losses, loss_max=maxes, round_s=round(time.perf_counter() - t_r, 1), adapter_kb=len(blob) // 1024)
        logf.write(json.dumps(rec, ensure_ascii=False) + "\n"); logf.flush()
        print(f"[server] R{r:2d} {rec['round_s']:5.1f}s 손실 " + " ".join(f"{k}:{v:.2f}" for k, v in losses.items()) + " | 최대 " + " ".join(f"{k}:{v:.2f}" for k, v in maxes.items()) + (f" | 뒷단 기기간 거리 {back_spread:.4f}" if back_spread is not None else "") + f" 어댑터 {rec['adapter_kb']}KB", flush=True)
    for p in peers:
        send_msg(p.conn, BYE)
    torch.save({k: v.cpu() for k, v in lora_state(m).items()}, os.path.join(OUT, f"{a.tag}_back.pt"))
    torch.save(front_avg, os.path.join(OUT, f"{a.tag}_front.pt"))
    print(f"[server] 끝 {time.perf_counter()-t_all:.0f}s. 저장 out/fed_split/{a.tag}_{{front,back}}.pt  뒷단 LoRA {nbytes(m, True)/1e6:.1f}MB", flush=True)


# ── 기기 ─────────────────────────────────────────────────────────────
def run_device(a):
    torch.set_num_threads(a.threads)
    dev = a.device
    from transformers import AutoTokenizer
    from lora_corpus import load, split
    from run_l1 import batches, collate
    c = llm_config(a.model, a.tiny)
    m = LLMFront(c, a.cut, a.rank)
    if not a.tiny:
        got, dl, shards = load_front_pretrained(m, a.model, a.cut)
        print(f"[{a.id}] 부분 적재 텐서 {got}개 조각 {shards} {dl/1e6:.0f}MB", flush=True)
    m.to(dev)
    tok = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-0.5B" if a.tiny else a.model)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    tr, ho = split(load(a.domain))
    if a.canary:
        tr = tr + CANARY
    print(f"[{a.id}] 도메인 {a.domain}: 학습 {len(tr)} / 검증 {len(ho)}" + (" + 카나리아 3" if a.canary else ""), flush=True)
    gen = batches(tr, tok, a.seq, a.batch, "cpu", seed=1 + sum(map(ord, a.id)))   # hash() 는 프로세스마다 무작위(PYTHONHASHSEED) → 결정적 시드
    train_params = [q for q in m.parameters() if q.requires_grad]
    opt = torch.optim.AdamW(train_params, lr=a.lr)
    host, port = a.server.split(":")
    last = None
    for attempt in range(120):
        try:
            s = socket.create_connection((host, int(port))); break
        except OSError as e:
            last = e; time.sleep(1)
    else:
        raise ConnectionError(f"서버 연결 실패: {last}")
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    send_msg(s, HELLO, {"id": a.id, "domain": a.domain})
    kind, hello, _, _ = recv_msg(s); assert kind == HELLO_OK
    os.makedirs(OUT, exist_ok=True)
    logf = io.open(os.path.join(OUT, f"device_{a.tag}_{a.id}.jsonl"), "a", encoding="utf-8")
    m.train()
    while True:
        kind, meta, payload, _ = recv_msg(s)
        if kind == BYE:
            break
        if kind == AGG:
            m.load_state_dict({k: v.to(dev) for k, v in bytes_to_sd(payload).items()}, strict=False); continue
        assert kind == TURN, kind
        t0 = time.perf_counter(); ls = []
        for _ in range(meta["steps"]):
            ids, lab = collate(gen, a.batch, tok.pad_token_id, dev)
            h = m(ids)
            send_msg(s, ACT, {"shape": list(h.shape), "labels": lab.tolist()}, t2b32(h))
            _, gm, gp, _ = recv_msg(s)
            g = b2t(gp, h.shape, dev)
            opt.zero_grad(set_to_none=True); h.backward(g)
            if a.clip > 0:
                torch.nn.utils.clip_grad_norm_(train_params, a.clip)
            opt.step(); ls.append(gm["loss"])
        send_msg(s, ADAPTER, {"round": meta["round"]}, sd_to_bytes(lora_state(m)))
        rec = dict(round=meta["round"], loss_mean=float(np.mean(ls)), loss_last=ls[-1], loss_max=float(np.max(ls)), turn_s=round(time.perf_counter() - t0, 1), rss_mb=round(peak_rss_mb(), 1))
        logf.write(json.dumps(rec) + "\n"); logf.flush()
        print(f"[{a.id}] R{meta['round']:2d} 손실 {rec['loss_mean']:.2f}→{rec['loss_last']:.2f} {rec['turn_s']}s RSS {rec['rss_mb']:.0f}MB", flush=True)
    print(f"[{a.id}] 끝", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["server", "device"])
    ap.add_argument("--model", default="Qwen/Qwen2.5-0.5B")
    ap.add_argument("--cut", type=int, default=2)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--lr", type=float, default=3e-4, help="1차(1e-3) 는 R12 발산 → G-L1 확정 레시피 3e-4")
    ap.add_argument("--clip", type=float, default=1.0, help="LoRA 기울기 노름 상한 (0=끔)")
    ap.add_argument("--back-mode", default="shared", choices=["shared", "avg"],
                    help="shared: 서버 뒷단 어댑터 한 벌을 기기가 차례로 갱신(v2) / avg: 기기별 뒷단을 따로 학습하고 라운드 끝에 평균(v1)")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--seq", type=int, default=256)
    ap.add_argument("--clients", type=int, default=3)
    ap.add_argument("--rounds", type=int, default=16)
    ap.add_argument("--local-steps", type=int, default=30)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--threads", type=int, default=max(1, (os.cpu_count() or 2)))
    ap.add_argument("--port", type=int, default=31955)
    ap.add_argument("--server", default="127.0.0.1:31955")
    ap.add_argument("--id", default="c0")
    ap.add_argument("--domain", default="B1")
    ap.add_argument("--canary", action="store_true")
    ap.add_argument("--tiny", action="store_true")
    ap.add_argument("--tag", default="fed")
    a = ap.parse_args()
    {"server": run_server, "device": run_device}[a.mode](a)


if __name__ == "__main__":
    main()
