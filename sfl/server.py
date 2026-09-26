# -*- coding: utf-8 -*-
"""SFL 서버 — 뒷단 연산 + '크기 축소 이상'의 망 대응 노브 2개.

  노브
    --tokens K   수신자 주도 admission: 동시 업로드를 K개로 제한.
                 클라이언트는 TOKREQ→TOKOK 허가를 받아야 활성값을 보낸다.
                 (Homa류 '수신자가 전송을 승인'하는 원리의 응용 계층 판.
                  K=0 이면 끔 = TCP 공정 공유에 맡김 — 기본값. §10 줄 세우기는 관문 통과 전 off)
    GPU 락       서버 뒷단 연산 직렬화 + 대기시간(t_lock) 계측
                 → 서버 병목이 '망'인지 '연산'인지 로그가 직접 가른다

  계측 (라운드가 아니라 배치 단위 — JSONL 한 줄/배치)
    t_recv 수신시간 · recv_B 수신바이트 · t_lock GPU 대기 · t_srv 뒷단 연산 · t_send 그래디언트 송신
"""
import argparse
import io
import json
import socket
import threading
import time

import torch
import torch.nn.functional as F

from models import ClientNet, ServerNet
from proto import (ACT, BYE, GRAD, HELLO, HELLO_OK, TOKOK, TOKREQ,
                   b2t, recv_msg, send_msg, t2b)

LOCK = threading.Lock()          # 서버 GPU 직렬화


def handle(conn, addr, args, sem, logf, logl):
    kind, meta, _, _ = recv_msg(conn)
    assert kind == HELLO, "첫 메시지는 HELLO"
    cid, p, cut = meta["id"], meta["p"], meta["cut"]
    dev = args.device
    if args.seed:                        # 등가 검증용 — 클라와 같은 RNG 소비 순서 재현
        torch.manual_seed(args.seed)
        ClientNet(p=p, cut=cut)
    net = ServerNet(p=p, cut=cut).to(dev)
    opt = torch.optim.SGD(net.parameters(), lr=0.01, momentum=0.9)
    send_msg(conn, HELLO_OK, {"tokens": args.tokens > 0})

    while True:
        kind, meta, payload, nB = recv_msg(conn)
        if kind == BYE:
            break
        if kind == TOKREQ:
            t0 = time.perf_counter()
            sem.acquire()                        # 자리 날 때까지 대기 = 페이싱
            send_msg(conn, TOKOK, {"waited": time.perf_counter() - t0})
            kind, meta, payload, nB = recv_msg(conn)   # 이어서 ACT
        assert kind == ACT
        t_recv_done = time.perf_counter()

        act = b2t(meta["act"], payload[:meta["act_bytes"]]).to(dev)
        y = b2t(meta["y"], payload[meta["act_bytes"]:]).long().to(dev)
        if args.tokens > 0:
            sem.release()                        # 수신 완료 → 슬롯 반환

        t0 = time.perf_counter()
        with LOCK:                               # GPU 한 대 — 직렬화하고 대기를 잰다
            t_lock = time.perf_counter() - t0
            act.requires_grad_(True)
            out = net(act)
            loss = F.cross_entropy(out, y)
            opt.zero_grad()
            loss.backward()
            opt.step()
            if dev == "cuda":
                torch.cuda.synchronize()
            t_srv = time.perf_counter() - t0 - t_lock

        gm, gb = t2b(act.grad)
        t0 = time.perf_counter()
        sent = send_msg(conn, GRAD, {"g": gm, "loss": float(loss.item())}, gb)
        t_send = time.perf_counter() - t0

        with logl:
            logf.write(json.dumps({
                "c": cid, "b": meta["b"], "p": p, "cut": cut,
                "t_recv_end": t_recv_done, "recv_B": nB, "t_lock": round(t_lock, 6),
                "t_srv": round(t_srv, 6), "t_send": round(t_send, 6), "sent_B": sent,
            }) + "\n")
            logf.flush()
    conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=29500)
    ap.add_argument("--clients", type=int, default=1)
    ap.add_argument("--tokens", type=int, default=0, help="동시 업로드 허가 수. 0=off(기본)")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--log", default="out/sfl_server.jsonl")
    args = ap.parse_args()

    sem = threading.BoundedSemaphore(max(args.tokens, 1))
    logf = io.open(args.log, "w", encoding="utf-8")
    logl = threading.Lock()

    srv = socket.create_server(("0.0.0.0", args.port))
    srv.settimeout(120)
    threads = []
    for _ in range(args.clients):
        conn, addr = srv.accept()
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        t = threading.Thread(target=handle, args=(conn, addr, args, sem, logf, logl))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    logf.close()


if __name__ == "__main__":
    main()
