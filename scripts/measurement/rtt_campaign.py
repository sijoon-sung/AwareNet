# -*- coding: utf-8 -*-
"""HPC ↔ KOREN VM 왕복 지연·흔들림·손실 반복 측정.

    python scripts/measurement/rtt_campaign.py \
        --targets vm1=116.89.187.190:12001,vm1_22=116.89.187.190:22,vm2=116.89.187.189:12001,vm2_22=116.89.187.189:22 \
        --rounds 5 --samples 200 --interval 0.1 --gap 60 --tag hpc2vm

무엇을 재나: TCP 연결 왕복(SYN 을 보내고 SYN-ACK 또는 RST 를 받기까지). ICMP 가 막힌 KOREN 에서
지연을 재는 유일한 방법이고, 포트에 듣는 프로그램이 없어도(연결 거부) 왕복 자체는 유효하다.
회차(round)를 나눠 시간대별 변동을 본다. 회차마다 samples 번 재고 gap 초 쉰다.

내는 것:
  out/probe/rtt_<tag>.jsonl      한 줄 = 한 회차 요약(중앙값·p95·흔들림·손실률·전체 표본)
  out/probe/rtt_<tag>_raw.jsonl  한 줄 = 한 표본 (ts, dst, port, rtt_ms 또는 state)
표준 라이브러리만 쓴다.
"""
import argparse
import io
import json
import os
import socket
import statistics
import time


def sample(ip, port, timeout):
    """한 번 재기. (rtt_ms, state) — state 는 refused/open/timeout/error."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    s.settimeout(timeout)
    t0 = time.perf_counter()
    try:
        s.connect((ip, port))
        return (time.perf_counter() - t0) * 1000, "open"
    except ConnectionRefusedError:
        return (time.perf_counter() - t0) * 1000, "refused"
    except socket.timeout:
        return None, "timeout"
    except OSError as e:
        return None, f"error:{e.errno}"
    finally:
        s.close()


def pct(v, q):
    if not v:
        return None
    v = sorted(v)
    i = min(len(v) - 1, max(0, int(round(q / 100 * (len(v) - 1)))))
    return round(v[i], 3)


def summarize(name, ip, port, rtts, states, t_start, t_end):
    ok = [r for r in rtts if r is not None]
    lost = sum(1 for s in states if s.startswith("timeout") or s.startswith("error"))
    jit = None
    if len(ok) > 1:
        jit = round(statistics.mean(abs(ok[i] - ok[i - 1]) for i in range(1, len(ok))), 3)
    return {
        "dst": name, "ip": ip, "port": port,
        "t_start": round(t_start, 1), "t_end": round(t_end, 1),
        "n": len(states), "n_ok": len(ok), "loss_pct": round(100 * lost / max(1, len(states)), 2),
        "state": max(set(states), key=states.count),
        "min": round(min(ok), 3) if ok else None,
        "median": round(statistics.median(ok), 3) if ok else None,
        "mean": round(statistics.mean(ok), 3) if ok else None,
        "p95": pct(ok, 95), "p99": pct(ok, 99),
        "max": round(max(ok), 3) if ok else None,
        "stdev": round(statistics.pstdev(ok), 3) if len(ok) > 1 else None,
        "jitter": jit,      # 연속 표본 차이의 평균 (IPDV)
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", required=True, help="이름=IP:포트 를 쉼표로")
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--samples", type=int, default=200)
    ap.add_argument("--interval", type=float, default=0.1, help="표본 간격(초)")
    ap.add_argument("--gap", type=float, default=60, help="회차 사이 쉬는 시간(초)")
    ap.add_argument("--timeout", type=float, default=2.0)
    ap.add_argument("--tag", default="hpc2vm")
    ap.add_argument("--note", default="", help="이 측정의 조건 메모 (부하 있음/없음 등)")
    a = ap.parse_args()

    targets = []
    for item in [x for x in a.targets.split(",") if x.strip()]:
        name, addr = item.split("=", 1)
        ip, port = addr.rsplit(":", 1)
        targets.append((name.strip(), ip.strip(), int(port)))

    out_dir = os.path.join("out", "probe")
    os.makedirs(out_dir, exist_ok=True)
    sum_path = os.path.join(out_dir, f"rtt_{a.tag}.jsonl")
    raw_path = os.path.join(out_dir, f"rtt_{a.tag}_raw.jsonl")
    print(f"회차 {a.rounds} × 표본 {a.samples} × 대상 {len(targets)} · 간격 {a.interval}s · 회차간 {a.gap}s"
          f"{' · ' + a.note if a.note else ''}", flush=True)

    for rd in range(1, a.rounds + 1):
        for name, ip, port in targets:
            rtts, states = [], []
            t0 = time.time()
            with io.open(raw_path, "a", encoding="utf-8") as rf:
                for _ in range(a.samples):
                    t_s = time.time()
                    rtt, st = sample(ip, port, a.timeout)
                    rtts.append(rtt)
                    states.append(st)
                    rf.write(json.dumps({"ts": round(t_s, 3), "round": rd, "dst": name,
                                         "port": port, "rtt_ms": None if rtt is None else round(rtt, 3),
                                         "state": st}) + "\n")
                    left = a.interval - (time.time() - t_s)
                    if left > 0:
                        time.sleep(left)
            s = summarize(name, ip, port, rtts, states, t0, time.time())
            s.update({"round": rd, "tag": a.tag, "note": a.note})
            with io.open(sum_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
            print(f"  R{rd} {name}:{port:<6} {s['state']:<8} 중앙 {s['median']}ms  "
                  f"최소 {s['min']}  p95 {s['p95']}  최대 {s['max']}  흔들림 {s['jitter']}  손실 {s['loss_pct']}%",
                  flush=True)
        if rd < a.rounds:
            time.sleep(a.gap)
    print("CAMPAIGN_DONE", flush=True)


if __name__ == "__main__":
    main()
