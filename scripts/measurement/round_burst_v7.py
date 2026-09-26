# -*- coding: utf-8 -*-
"""
round_burst_v7.py — 연합학습 라운드 경계를 PC→KOREN VM 실 TCP로 재현한다

[우리 데이터는 어떻게 나가는가 — 측정 설계의 전제]
  연합학습의 모델 업로드는 gRPC(HTTP/2) 위에서 나가고, 그 아래는 **TCP**다.
  따라서 이 측정도 TCP로 해야 한다. 여기서는 열려 있는 SSH(26022) 위로
  페이로드를 흘려 같은 TCP 혼잡제어·공정경쟁 하에 놓는다.
    · 같은 것 : TCP 혼잡제어, 공유 병목에서의 경쟁, slow start, 라운드 경계 동시성
    · 다른 것 : SSH 암호화 오버헤드 → 처리량은 **하한치**로 읽어야 한다

[무엇을 재나]
  라운드 경계에서 K개 노드가 동시에 모델을 올릴 때
    ① 제어 채널이 얼마나 밀리는가 (컨트롤러가 배분 명령을 보내는 통로)
    ② 데이터 전송 완료가 얼마나 갈리는가 (누가 마감에 드는가)
  를 K를 바꿔가며 본다. K=1(단독)이 기준선이다.

  제어 채널 RTT는 TCP 3-way 핸드셰이크로 잰다 — KOREN VM이 ICMP를 차단하므로
  ping을 쓸 수 없다. 데이터와 같은 TCP이므로 **프로토콜이 아니라 경합만 다른**
  비교가 되어 논증이 더 깨끗하다.

출력: out/link_profile/round_burst_v7_<UTC>.json
"""
import argparse
import datetime
import json
import os
import socket
import statistics as st
import subprocess
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HOST = "116.89.187.190"
SSH_HOST = "koren-vm"
PORT = 26022
PAYLOAD = int(8.79 * 1024 * 1024)      # 본 실험 페이로드 8.79MB (--payload-mb로 변경)


def pct(a, q):
    if not a:
        return None
    a = sorted(a)
    i = min(int(round(q / 100 * (len(a) - 1))), len(a) - 1)
    return round(a[i], 2)


def stats(a):
    a = [x for x in a if x is not None]
    if not a:
        return {}
    return {"n": len(a), "min": round(min(a), 2), "p50": pct(a, 50),
            "p95": pct(a, 95), "max": round(max(a), 2),
            "mean": round(st.mean(a), 2)}


class Probe(threading.Thread):
    """제어 채널 대용 — 0.3초 간격 TCP 연결 RTT 샘플러."""

    def __init__(self, interval=0.3):
        super().__init__(daemon=True)
        self.samples = []          # (경과초, rtt_ms 또는 None)
        self.stop = threading.Event()
        self.interval = interval

    def run(self):
        t0 = time.perf_counter()
        while not self.stop.is_set():
            t = time.perf_counter()
            try:
                s = socket.create_connection((HOST, PORT), timeout=6)
                rtt = (time.perf_counter() - t) * 1000
                s.close()
            except OSError:
                rtt = None
            self.samples.append((round(t - t0, 2),
                                 round(rtt, 2) if rtt is not None else None))
            self.stop.wait(self.interval)

    def between(self, lo, hi):
        return [v for t, v in self.samples if v is not None and lo <= t <= hi]


def upload(idx, out, barrier, payload):
    """SSH 스트림 1개로 페이로드 전송. barrier로 출발을 동시화한다."""
    p = subprocess.Popen(
        ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
         SSH_HOST, "cat > /dev/null"],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)
    barrier.wait()                      # 접속은 순차, 전송 시작만 동시
    t0 = time.perf_counter()
    try:
        p.stdin.write(payload)
        p.stdin.close()
        p.wait(timeout=240)
        out[idx] = round(time.perf_counter() - t0, 2)
    except Exception:
        out[idx] = None
        try:
            p.kill()
        except Exception:
            pass


def one_round(k, base_s, rec_s):
    """K개 동시 업로드 1회 = 라운드 경계 1회 재현."""
    payload = b"\x00" * PAYLOAD
    probe = Probe()
    probe.start()
    time.sleep(base_s)                       # ① 평시 구간

    t_burst0 = time.perf_counter() - (probe.samples[0][0] if probe.samples else 0)
    burst_start = probe.samples[-1][0] if probe.samples else base_s

    out = [None] * k
    barrier = threading.Barrier(k)
    ths = []
    for i in range(k):
        t = threading.Thread(target=upload, args=(i, out, barrier, payload))
        t.start()
        ths.append(t)
        time.sleep(0.12)                     # MaxStartups 회피
    for t in ths:
        t.join()
    burst_end = probe.samples[-1][0] if probe.samples else burst_start

    time.sleep(rec_s)                        # ③ 회복 구간
    probe.stop.set()
    probe.join(timeout=3)

    done = [x for x in out if x is not None]
    dur = max(burst_end - burst_start, 1e-6)
    return {
        "k": k,
        "flow_completion_s": out,
        "flow_stats": stats(done),
        "burst_window": [round(burst_start, 2), round(burst_end, 2)],
        "burst_duration_s": round(dur, 2),
        "aggregate_goodput_mbps": round(len(done) * PAYLOAD * 8 / dur / 1e6, 2),
        "rtt_baseline": stats(probe.between(0, burst_start - 0.3)),
        "rtt_during": stats(probe.between(burst_start, burst_end)),
        "rtt_recovery": stats(probe.between(burst_end + 0.3, 1e9)),
        "rtt_timeline": probe.samples,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ks", default="1,5,10,13",
                    help="동시 업로드 수 스윕 (1 = 단독 기준선)")
    ap.add_argument("--baseline", type=float, default=10.0)
    ap.add_argument("--recovery", type=float, default=10.0)
    ap.add_argument("--payload-mb", type=float, default=8.79,
                    help="흐름당 페이로드 MB. 흐름 수는 그대로 두고 바이트만 늘려 "
                         "'접속 수'와 '회선 부하'를 분리할 때 쓴다")
    a = ap.parse_args()
    ks = [int(x) for x in a.ks.split(",")]
    global PAYLOAD
    PAYLOAD = int(a.payload_mb * 1024 * 1024)

    print("=" * 74)
    print(f" 라운드 경계 TCP 실측 · PC → KOREN VM({HOST}:{PORT})")
    print(f" 페이로드 {PAYLOAD/1024/1024:.2f} MB · 동시 업로드 K = {ks}")
    print(" 제어 채널 = TCP 3-way 핸드셰이크 (ICMP 차단 환경)")
    print("=" * 74)

    res = {"timestamp_utc": datetime.datetime.now(datetime.timezone.utc)
           .strftime("%Y-%m-%dT%H:%M:%SZ"),
           "host": f"{HOST}:{PORT}", "payload_bytes": PAYLOAD,
           "transport": "TCP (SSH 스트림) — FL 실전송 gRPC/HTTP2도 TCP. "
                        "암호화 오버헤드로 처리량은 하한치",
           "control_probe": "TCP 3-way handshake RTT, 0.3s 간격",
           "rounds": []}

    for k in ks:
        print(f"\n[K={k}] 평시 {a.baseline}s → 동시 업로드 {k}개 → 회복 {a.recovery}s")
        r = one_round(k, a.baseline, a.recovery)
        res["rounds"].append(r)
        fs, rb, rd = r["flow_stats"], r["rtt_baseline"], r["rtt_during"]
        print(f"   완료  P50 {fs.get('p50')}s  범위 {fs.get('min')}~{fs.get('max')}s"
              f"  합산 {r['aggregate_goodput_mbps']} Mbps")
        print(f"   제어  평시 P50 {rb.get('p50')}ms P95 {rb.get('p95')}ms"
              f"  →  버스트 P50 {rd.get('p50')}ms P95 {rd.get('p95')}ms")

    d = REPO / "out" / "link_profile"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"round_burst_v7_{res['timestamp_utc'].replace(':','').replace('-','')}.json"
    f.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 74)
    print(f"{'K':>4}{'완료 P50':>10}{'완료 최대':>10}{'산포':>8}"
          f"{'제어 P95 평시':>13}{'제어 P95 버스트':>15}{'악화':>7}")
    print("-" * 74)
    for r in res["rounds"]:
        fs, rb, rd = r["flow_stats"], r["rtt_baseline"], r["rtt_during"]
        sp = (fs["max"] / fs["min"]) if fs.get("min") else 0
        infl = (rd["p95"] / rb["p95"]) if rb.get("p95") and rd.get("p95") else 0
        print(f"{r['k']:>4}{fs.get('p50',0):>9.2f}s{fs.get('max',0):>9.2f}s"
              f"{sp:>7.1f}배{rb.get('p95',0):>11.0f}ms{rd.get('p95',0):>13.0f}ms"
              f"{infl:>6.1f}배")
    print(f"\n 저장: {f.relative_to(REPO)}")


if __name__ == "__main__":
    main()
