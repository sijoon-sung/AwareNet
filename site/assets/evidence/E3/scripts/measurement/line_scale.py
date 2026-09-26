# -*- coding: utf-8 -*-
"""회선 규모 측정 (Shrink) — 학습·연산 없이 전송 패턴만으로, 클라 수를 늘려 가며 HPC↔KOREN VM 실회선이 병목이 되는 규모를 찾는다.

  왜: 실제 100대를 못 띄우니 먼저 맨 회선(tc 없음)이 N대에서 얼마나 나눠 주는지 재고, 본실험은 그 비율(Shrink)로 tc 를 걸어 축소한다.
      연산·모델은 없다 — 배치당 올리기 4.2MB·되돌려 받기 4.2MB(ResNet-18 절단 2, 배치 32 의 활성값 크기) 만 흉내낸다.

  전송 방식 (--proto / --pattern)
      tcp batch : 배치마다 올리기 → 되돌아온 것을 받고 다음 배치 (학습과 같은 왕복 패턴, 기본)
      tcp burst : 한 라운드치(배치 4개)를 쉬지 않고 쏘고 나서 받는다 — 전원 동시 폭주(라운드마다 barrier)
      tcp paced : 접속 상한 속도로 --dur 초 동안 고르게 흘려보낸다 (iperf -b 와 같은 꼴)
      udp burst/paced : 1400B 데이터그램, 도달률을 같이 잰다 ※ KOREN 방화벽이 UDP 를 안 통과시켜 0% (2026-09-08 tcpdump 확인)

  구성: 클라 i → 엣지 e=i%4 (VM 포트 P(e,i,x) = BASE + 500e + 2i + x, 출구 2개 반씩) → 역터널 → HPC sink(31950) 가 같은 크기로 되돌린다.
        tc 는 real_rig.sh 가 건다. 맨 회선 측정은 접속 "4000/4000"(사실상 상한 없음).
  기록: --out jsonl 에 요약 한 줄 + <out>_detail/ 에 기기·배치별 (시작, 끝) 시각 — 시간축 시각화용.

      python scripts/measurement/line_scale.py sink --port 31950
      python scripts/measurement/line_scale.py load --n 32 --edges "$(bash sfl/net/real_rig.sh edges)" --acc 4000/4000 --pattern burst
      bash scripts/measurement/line_scale_raw.sh                      # 맨 회선 스윕 (N 8..96)
"""
import argparse, io, json, os, socket, statistics as st, struct, sys, threading, time

HDR = struct.Struct("!Q")
UHDR = struct.Struct("!IIH")          # 클라 번호, 순번, 길이
M = 1e6
DGRAM = 1400


def _readn(s, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = s.recv(min(1 << 20, n - len(buf)))
        if not chunk:
            raise OSError("closed")
        buf += chunk
    return bytes(buf)


def sink(port):
    """TCP: 받은 만큼 되돌려 준다 (내리기 흉내). 연결마다 스레드."""
    srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port)); srv.listen(1024)
    print(f"sink :{port}", flush=True)
    blob = os.urandom(1 << 20)

    def serve(c):
        try:
            c.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 256 * 1024)
            while True:
                n = HDR.unpack(_readn(c, HDR.size))[0]
                _readn(c, n)
                c.sendall(HDR.pack(n))
                left = n
                while left > 0:
                    k = min(left, len(blob)); c.sendall(blob[:k]); left -= k
        except OSError:
            pass
        finally:
            c.close()
    while True:
        c, _ = srv.accept()
        threading.Thread(target=serve, args=(c,), daemon=True).start()


# ── TCP 패턴들 ──────────────────────────────────────────────────────────────
def _send_blob(s, n, blob):
    s.sendall(HDR.pack(n)); left = n
    while left > 0:
        k = min(left, len(blob)); s.sendall(blob[:k]); left -= k


def _recv_echo(s):
    n = HDR.unpack(_readn(s, HDR.size))[0]; _readn(s, n); return n


def tcp_client(i, a, edges, blob, barrier, per, T0):
    ne = len(edges); e = (i % ne) + 1; h, base = edges[e]
    socks = []
    for x in range(a.exits):
        s = socket.create_connection((h, base + 2 * i + x), timeout=180)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 256 * 1024); socks.append(s)
    up_b = int(a.up_mb * M); share = [up_b // a.exits] * a.exits; share[-1] += up_b - sum(share)
    times, got, spans = [], 0, []                         # spans: 배치별 (시작, 끝) — run 시작 기준 초
    barrier.wait()
    if a.pattern == "batch":
        for r in range(a.rounds):
            for b in range(a.batches):
                t0 = time.perf_counter()
                for s, n in zip(socks, share): _send_blob(s, n, blob)
                for s in socks: got += _recv_echo(s)
                t1 = time.perf_counter(); times.append(t1 - t0); spans.append((round(t0 - T0, 3), round(t1 - T0, 3)))
    elif a.pattern == "burst":                                 # 라운드치를 한꺼번에, 전원 동시
        for r in range(a.rounds):
            barrier.wait()
            t0 = time.perf_counter()
            for b in range(a.batches):
                for s, n in zip(socks, share): _send_blob(s, n, blob)
            for b in range(a.batches):
                for s in socks: got += _recv_echo(s)
            t1 = time.perf_counter(); times.append((t1 - t0) / a.batches); spans.append((round(t0 - T0, 3), round(t1 - T0, 3)))
    elif a.pattern == "paced":                                 # 상한 속도로 --dur 초 흘리기
        aA, aB = [float(x) * a.shrink for x in a.acc.split("/")]
        rates = [aA * M / 8, aB * M / 8][: a.exits]
        recv_tot = [0]
        def reader(s):
            try:
                while True: recv_tot[0] += _recv_echo(s)
            except OSError: pass
        th = [threading.Thread(target=reader, args=(s,), daemon=True) for s in socks]
        for t in th: t.start()
        t0 = time.perf_counter(); sent = 0; chunk = 64 * 1024
        while time.perf_counter() - t0 < a.dur:
            for s, rate in zip(socks, rates):
                _send_blob(s, chunk, blob)
            sent += chunk * len(socks)
            due = sent / sum(rates); el = time.perf_counter() - t0
            if due > el: time.sleep(due - el)
        el = time.perf_counter() - t0
        for s in socks:
            try: s.shutdown(socket.SHUT_WR)
            except OSError: pass
        for t in th: t.join(timeout=15)
        got = recv_tot[0]
        times.append(el * (a.up_mb * M * 2) / max(1, sent + got))  # 왕복 8.4MB 를 옮기는 데 걸린 시간으로 환산
        spans.append((round(t0 - T0, 3), round(time.perf_counter() - T0, 3)))
    for s in socks: s.close()
    per[f"c{i}"] = {"times": times, "got": got, "spans": spans, "edge": e}


# ── UDP 패턴들 ──────────────────────────────────────────────────────────────
def udp_client(i, a, edges, blob, barrier, per, T0):
    ne = len(edges); e = (i % ne) + 1; h, base = edges[e]
    socks = [socket.socket(socket.AF_INET, socket.SOCK_DGRAM) for _ in range(a.exits)]
    for s in socks: s.settimeout(0.5)
    dst = [(h, base + 2 * i + x) for x in range(a.exits)]
    aA, aB = [float(x) * a.shrink for x in a.acc.split("/")]
    rates = [aA * M / 8, aB * M / 8][: a.exits]
    up_b = int(a.up_mb * M)
    n_dg = max(1, up_b // DGRAM)
    recv = [0]; stop = [False]
    def reader(s):
        while not stop[0]:
            try: s.recv(2000); recv[0] += 1
            except (socket.timeout, OSError): pass
    th = [threading.Thread(target=reader, args=(s,), daemon=True) for s in socks]
    for t in th: t.start()
    payload = blob[:DGRAM - UHDR.size]
    sent = 0; times = []; spans = []
    barrier.wait()
    if a.pattern == "burst":
        for r in range(a.rounds):
            barrier.wait()
            t0 = time.perf_counter()
            for b in range(a.batches):
                for k in range(n_dg):
                    x = k % a.exits; socks[x].sendto(UHDR.pack(i, sent, DGRAM) + payload, dst[x]); sent += 1
            t1 = time.perf_counter(); times.append((t1 - t0) / a.batches); spans.append((round(t0 - T0, 3), round(t1 - T0, 3)))
    else:
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < a.dur:
            for x, rate in enumerate(rates):
                socks[x].sendto(UHDR.pack(i, sent, DGRAM) + payload, dst[x]); sent += 1
            due = sent * DGRAM / sum(rates); el = time.perf_counter() - t0
            if due > el: time.sleep(due - el)
        el = time.perf_counter() - t0
        times.append(el * (a.up_mb * M) / max(1, sent * DGRAM)); spans.append((round(t0 - T0, 3), round(time.perf_counter() - T0, 3)))
    time.sleep(2.0)
    stop[0] = True
    for t in th: t.join(timeout=2)
    for s in socks: s.close()
    per[f"c{i}"] = {"times": times, "got": recv[0] * DGRAM, "sent": sent * DGRAM, "spans": spans, "edge": e}


def load(a):
    edges = {}
    for tok in a.edges.split(","):
        e, hp = tok.split("="); h, p = hp.rsplit(":", 1); edges[int(e)] = (h, int(p))
    per = {}; barrier = threading.Barrier(a.n); blob = os.urandom(1 << 20)
    fn = udp_client if a.proto == "udp" else tcp_client
    t0 = time.perf_counter()
    th = [threading.Thread(target=fn, args=(i, a, edges, blob, barrier, per, t0)) for i in range(a.n)]
    for t in th: t.start()
    for t in th: t.join()
    wall = time.perf_counter() - t0
    skip = a.batches if a.pattern == "batch" else (1 if a.pattern == "burst" else 0)
    bt = {k: st.median(v["times"][skip:] or v["times"]) for k, v in per.items()}
    aA, aB = [float(x) * a.shrink for x in a.acc.split("/")]
    cap = (aA + aB) * M
    rt_bytes = (a.up_mb + (a.dn_mb if a.proto == "tcp" else 0)) * M
    eff = {k: rt_bytes * 8 / t for k, t in bt.items()}
    out = {"n": a.n, "shrink": a.shrink, "acc": a.acc, "cap_mbps": cap / M, "exits": a.exits, "proto": a.proto, "pattern": a.pattern,
           "up_mb": a.up_mb, "dn_mb": a.dn_mb, "batches": a.batches, "rounds": a.rounds,
           "batch_s_median": st.median(bt.values()), "batch_s_p90": sorted(bt.values())[int(0.9 * (a.n - 1))],
           "per_client_mbps_median": st.median(eff.values()) / M, "per_client_mbps_min": min(eff.values()) / M,
           "ratio_to_cap": st.median(eff.values()) / cap, "aggregate_mbps": a.n * st.median(eff.values()) / M, "wall_s": wall,
           "t_unix": time.time()}
    if a.proto == "udp":
        sent = sum(v["sent"] for v in per.values()); got = sum(v["got"] for v in per.values())
        out["udp_delivered"] = got / max(1, sent)
    print(json.dumps(out, ensure_ascii=False))
    if a.out:
        with io.open(a.out, "a", encoding="utf-8") as f:
            f.write(json.dumps(out, ensure_ascii=False) + "\n")
        ddir = os.path.splitext(a.out)[0] + "_detail"; os.makedirs(ddir, exist_ok=True)      # 시간축 시각화용
        fn_ = os.path.join(ddir, f"n{a.n}_s{a.shrink}_{a.proto}_{a.pattern}_{int(time.time())}.json")
        with io.open(fn_, "w", encoding="utf-8") as f:
            json.dump({"meta": out, "per": {k: {"spans": v.get("spans", []), "times": v["times"], "edge": v.get("edge")} for k, v in per.items()}}, f)


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="mode", required=True)
    s = sub.add_parser("sink"); s.add_argument("--port", type=int, default=31950)
    l = sub.add_parser("load")
    l.add_argument("--n", type=int, required=True); l.add_argument("--edges", required=True)
    l.add_argument("--acc", default="50/20"); l.add_argument("--shrink", type=float, default=1.0)
    l.add_argument("--up-mb", type=float, default=4.2); l.add_argument("--dn-mb", type=float, default=4.2)
    l.add_argument("--batches", type=int, default=4); l.add_argument("--rounds", type=int, default=3)
    l.add_argument("--exits", type=int, default=2); l.add_argument("--out", default="out/line_scale.jsonl")
    l.add_argument("--proto", default="tcp", choices=["tcp", "udp"]); l.add_argument("--pattern", default="batch", choices=["batch", "burst", "paced"])
    l.add_argument("--dur", type=float, default=15.0, help="paced: 흘리는 시간(초)")
    a = ap.parse_args()
    if a.mode == "sink":
        sink(a.port)
    else:
        if a.proto == "udp" and a.pattern == "batch":
            a.pattern = "burst"
        load(a)


if __name__ == "__main__":
    main()
