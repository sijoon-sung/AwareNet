# -*- coding: utf-8 -*-
"""SFL 클라이언트 — 앞단 연산 + '크기 축소 이상' 노브: 파이프라이닝.

  --pipeline   배치 i의 그래디언트를 기다리는 동안 배치 i+1의 순전파를 미리 계산
               → 망 왕복(RTT)을 연산 뒤로 숨긴다. 신선도 1배치 지연(staleness=1) 명시.
               기본 off — 켠 것과 끈 것의 차이 자체가 실험 결과다.

  계측: 배치마다 t_fwd(앞단 연산) · t_tok(허가 대기) · t_up(송신) ·
        t_wait(그래디언트 대기 = 망왕복+서버) · t_bwd(역전파) · up_B/down_B
"""
import argparse
import io
import json
import socket
import time

import torch

from models import ClientNet
from proto import (ACT, BYE, GRAD, HELLO, HELLO_OK, TOKOK, TOKREQ,
                   b2t, recv_msg, send_msg, t2b)


def batches(n, bs, seed):
    g = torch.Generator().manual_seed(seed)
    for _ in range(n):
        yield torch.randn(bs, 3, 32, 32, generator=g), torch.randint(0, 10, (bs,), generator=g)


def send_act(sock, tokens, idx, out, y):
    t0 = time.perf_counter()
    t_tok = 0.0
    if tokens:
        send_msg(sock, TOKREQ, {})
        kind, _, _, _ = recv_msg(sock)
        assert kind == TOKOK
        t_tok = time.perf_counter() - t0
    am, ab = t2b(out)
    ym, yb = t2b(y)
    t1 = time.perf_counter()
    n = send_msg(sock, ACT, {"b": idx, "act": am, "act_bytes": len(ab), "y": ym}, ab + yb)
    return t_tok, time.perf_counter() - t1, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="127.0.0.1:29500")
    ap.add_argument("--id", default="c0")
    ap.add_argument("--p", type=float, default=1.0)
    ap.add_argument("--cut", type=int, default=1)
    ap.add_argument("--batches", type=int, default=16)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--pipeline", action="store_true")
    ap.add_argument("--device", default="cpu", help="약한 단말 흉내 기본 cpu")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--log", default="out/sfl_client.jsonl")
    args = ap.parse_args()
    if args.seed:
        torch.manual_seed(args.seed)

    host, port = args.server.split(":")
    sock = socket.create_connection((host, int(port)))
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    send_msg(sock, HELLO, {"id": args.id, "p": args.p, "cut": args.cut})
    kind, meta, _, _ = recv_msg(sock)
    assert kind == HELLO_OK
    tokens = meta["tokens"]

    net = ClientNet(p=args.p, cut=args.cut).to(args.device)
    opt = torch.optim.SGD(net.parameters(), lr=0.01, momentum=0.9)
    logf = io.open(args.log, "w", encoding="utf-8")
    data = list(batches(args.batches, args.batch_size, seed=42))

    def fwd(i):
        t0 = time.perf_counter()
        x = data[i][0].to(args.device)
        out = net(x)
        return out, time.perf_counter() - t0

    def bwd(out, gmeta, gbuf):
        t0 = time.perf_counter()
        g = b2t(gmeta, gbuf).to(args.device)
        opt.zero_grad()
        out.backward(gradient=g)
        opt.step()
        return time.perf_counter() - t0

    def log(i, rec):
        rec.update({"c": args.id, "b": i, "p": args.p, "cut": args.cut,
                    "pipeline": args.pipeline})
        logf.write(json.dumps(rec) + "\n")

    T0 = time.perf_counter()
    if not args.pipeline:
        for i in range(args.batches):
            out, t_fwd = fwd(i)
            t_tok, t_up, upB = send_act(sock, tokens, i, out, data[i][1])
            t0 = time.perf_counter()
            kind, gm, gb, dnB = recv_msg(sock)
            t_wait = time.perf_counter() - t0
            t_bwd = bwd(out, gm["g"], gb)
            log(i, {"t_fwd": round(t_fwd, 6), "t_tok": round(t_tok, 6),
                    "t_up": round(t_up, 6), "t_wait": round(t_wait, 6),
                    "t_bwd": round(t_bwd, 6), "up_B": upB, "down_B": dnB,
                    "loss": gm["loss"]})
    else:
        # 파이프라인: ACT(i) 송신 → fwd(i+1) 미리 → GRAD(i) 수신 → bwd(i)
        # 주의 — opt.step()의 제자리 갱신은 미리 만든 그래프를 깨뜨린다(버전 충돌).
        # 그래서 여기서는 함수형 호출 + 비제자리 SGD(모멘텀 없음)로 갱신한다. staleness=1.
        from torch.func import functional_call
        LR = 0.01
        params = {k: v.detach().clone().requires_grad_(True)
                  for k, v in net.named_parameters()}
        bufs = {k: v.detach().clone() for k, v in net.named_buffers()}

        def fwd_f(i, pr):
            t0 = time.perf_counter()
            x = data[i][0].to(args.device)
            out = functional_call(net, ({**pr, **bufs}), (x,))
            return out, time.perf_counter() - t0

        def bwd_f(out, pr, gmeta, gbuf):
            t0 = time.perf_counter()
            g = b2t(gmeta, gbuf).to(args.device)
            grads = torch.autograd.grad(out, list(pr.values()), grad_outputs=g)
            new = {k: (v - LR * gr).detach().requires_grad_(True)
                   for (k, v), gr in zip(pr.items(), grads)}
            return new, time.perf_counter() - t0

        out_prev, t_fwd_prev = fwd_f(0, params)
        t_tok, t_up, upB = send_act(sock, tokens, 0, out_prev, data[0][1])
        pend = (0, out_prev, params, t_fwd_prev, t_tok, t_up, upB)
        for i in range(1, args.batches + 1):
            pr_next = params                          # fwd(i)가 쓴 파라미터 스냅샷 — 역전파도 이걸로
            out_next, t_fwd_next = (fwd_f(i, pr_next) if i < args.batches else (None, 0.0))
            j, out_j, pr_j, t_fwd, t_tok, t_up, upB = pend
            t0 = time.perf_counter()
            kind, gm, gb, dnB = recv_msg(sock)
            t_wait = time.perf_counter() - t0        # fwd(i)를 미리 했으니 여기가 줄어든다
            params, t_bwd = bwd_f(out_j, pr_j, gm["g"], gb)
            log(j, {"t_fwd": round(t_fwd, 6), "t_tok": round(t_tok, 6),
                    "t_up": round(t_up, 6), "t_wait": round(t_wait, 6),
                    "t_bwd": round(t_bwd, 6), "up_B": upB, "down_B": dnB,
                    "loss": gm["loss"], "stale": 1})
            if out_next is not None:
                t_tok, t_up, upB = send_act(sock, tokens, i, out_next, data[i][1])
                pend = (i, out_next, pr_next, t_fwd_next, t_tok, t_up, upB)

    total = time.perf_counter() - T0
    send_msg(sock, BYE, {})
    logf.write(json.dumps({"c": args.id, "total_sec": round(total, 3),
                           "batches": args.batches}) + "\n")
    logf.close()
    sock.close()


if __name__ == "__main__":
    main()
