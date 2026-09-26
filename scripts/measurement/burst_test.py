# -*- coding: utf-8 -*-
"""
burst_test.py — 라운드 경계 버스트 재현: 동시 어댑터 업로드 중 제어 채널 RTT 측정

무엇을 재나 (측정 계획 #5 '제어 격리 전/후'의 자택판 선행 실측):
  - K=13 노드가 라운드 경계에서 canonical 어댑터(8.68MB)를 동시 업로드하는 상황을
    13개 병렬 SSH 스트림으로 실WAN(PC→대전 KOREN VM)에서 재현
  - 그동안 TCP 연결 RTT(제어 채널 대용)를 0.3s 간격으로 연속 샘플링
  - 3구간: 평시(10s) → 버스트(13×8.68MB 완료까지) → 회복(10s)

산출:
  ① 버스트 중 RTT 악화 배수 (평시 P50 대비) — 제어/데이터 분리 설계의 동기 실측
  ② 13개 플로우의 완료 시간 분포 (단독 2.88s 대비 경합 효과)
  ③ 버스트 합산 goodput

한계(정직): 자택 업링크 1개의 경합 — 게이트웨이 공유 회선의 축소판. 판교 #5 본판을 대체하지 않음.

출력: out/link_profile/burst_test_<UTC>.json + fig_burst_test.png
"""
import datetime
import json
import socket
import statistics
import subprocess
import threading
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parents[2]
HOST_IP = "116.89.187.190"
SSH_HOST = "koren-vm"
TCP_PORT = 26022
ADAPTER_BYTES = 8_683_638
N_FLOWS = 13
BASELINE_SEC = 10
RECOVERY_SEC = 10

INK, INK2, SURFACE, GRID = "#0b0b0b", "#52514e", "#fcfcfb", "#e5e4e0"
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"
plt.rcParams.update({
    "font.family": "Malgun Gothic", "axes.unicode_minus": False,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2,
    "ytick.color": INK2, "axes.edgecolor": GRID, "axes.grid": True,
    "grid.color": GRID, "axes.axisbelow": True, "font.size": 10.5,
    "axes.titlesize": 11.5, "axes.titleweight": "bold",
})


class RttSampler(threading.Thread):
    """0.3s 간격 TCP 연결 RTT 연속 샘플러 (타임스탬프 포함)."""
    def __init__(self):
        super().__init__(daemon=True)
        self.samples = []   # (t_rel, rtt_ms or None)
        self.stop_flag = threading.Event()
        self.t0 = None

    def run(self):
        self.t0 = time.perf_counter()
        while not self.stop_flag.is_set():
            t = time.perf_counter()
            try:
                with socket.create_connection((HOST_IP, TCP_PORT), timeout=5):
                    rtt = (time.perf_counter() - t) * 1000
            except OSError:
                rtt = None
            self.samples.append((round(t - self.t0, 2),
                                 round(rtt, 2) if rtt is not None else None))
            self.stop_flag.wait(0.3)


def upload_flow(idx, results, start_barrier):
    payload = b"\x00" * ADAPTER_BYTES
    # MaxStartups 회피: 접속은 순차(120ms 간격), 전송 시작은 배리어로 동시화
    p = subprocess.Popen(["ssh", "-o", "BatchMode=yes", SSH_HOST, "cat > /dev/null"],
                         stdin=subprocess.PIPE)
    start_barrier.wait()
    t0 = time.perf_counter()
    try:
        p.stdin.write(payload)
        p.stdin.close()
        p.wait(timeout=180)
        results[idx] = round(time.perf_counter() - t0, 2)
    except Exception:
        results[idx] = None


def stats_of(vals):
    s = sorted(v for v in vals if v is not None)
    if not s:
        return {}
    return {"n": len(s), "min": round(s[0], 2), "p50": round(statistics.median(s), 2),
            "p95": round(s[min(len(s) - 1, int(0.95 * len(s)))], 2),
            "max": round(s[-1], 2), "mean": round(statistics.mean(s), 2)}


def main():
    ts = datetime.datetime.now(datetime.timezone.utc)
    print(f"[1/3] 평시 RTT {BASELINE_SEC}s ...")
    sampler = RttSampler()
    sampler.start()
    time.sleep(BASELINE_SEC)

    print(f"[2/3] 버스트: {N_FLOWS}개 플로우 × 8.68MB 동시 업로드 ...")
    burst_start = time.perf_counter() - sampler.t0
    results = [None] * N_FLOWS
    barrier = threading.Barrier(N_FLOWS + 1)
    threads = []
    for i in range(N_FLOWS):
        th = threading.Thread(target=upload_flow, args=(i, results, barrier), daemon=True)
        th.start()
        threads.append(th)
        time.sleep(0.12)  # SSH 세션 수립 순차화
    barrier.wait()        # 전 세션 준비 완료 → 동시 전송 개시
    for th in threads:
        th.join(timeout=200)
    burst_end = time.perf_counter() - sampler.t0
    print(f"    완료 시간(초): {results}")

    print(f"[3/3] 회복 RTT {RECOVERY_SEC}s ...")
    time.sleep(RECOVERY_SEC)
    sampler.stop_flag.set()
    sampler.join(timeout=5)

    # 구간 분리
    base = [r for t, r in sampler.samples if t < burst_start and r is not None]
    burst = [r for t, r in sampler.samples if burst_start <= t <= burst_end and r is not None]
    recov = [r for t, r in sampler.samples if t > burst_end and r is not None]
    burst_dur = burst_end - burst_start
    total_mbit = N_FLOWS * ADAPTER_BYTES * 8 / 1e6
    done = [r for r in results if r is not None]

    result = {
        "timestamp_utc": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scenario": f"{N_FLOWS}플로우 × 8.68MB 동시 업로드 (라운드 경계 버스트 재현, 실WAN)",
        "note": "자택 업링크 경합의 축소판 — 측정 계획 #5(판교 게이트웨이 격리 전/후)의 선행 실측",
        "rtt_baseline": stats_of(base), "rtt_during_burst": stats_of(burst),
        "rtt_recovery": stats_of(recov),
        "rtt_inflation_p50": (round(statistics.median(burst) / statistics.median(base), 1)
                              if base and burst else None),
        "flow_completion_s": results,
        "flow_completion_stats": stats_of(done),
        "single_flow_reference_s": 2.88,
        "burst_duration_s": round(burst_dur, 2),
        "aggregate_goodput_mbps": round(total_mbit / burst_dur, 2),
        "rtt_timeline": sampler.samples,
        "burst_window": [round(burst_start, 2), round(burst_end, 2)],
    }

    out_dir = REPO / "out" / "link_profile"
    jpath = out_dir / f"burst_test_{ts.strftime('%Y%m%dT%H%M%SZ')}.json"
    jpath.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 차트: RTT 타임라인(버스트 창 음영) + 완료 시간 분포 ──
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.6, 4.3), dpi=150,
                                   gridspec_kw={"width_ratios": [1.6, 1]})
    ts_ = [t for t, r in sampler.samples if r is not None]
    rs = [r for t, r in sampler.samples if r is not None]
    ax1.axvspan(burst_start, burst_end, color=C2, alpha=0.10)
    ax1.plot(ts_, rs, "-", color=C1, lw=1.3)
    b50 = result["rtt_baseline"].get("p50"); u50 = result["rtt_during_burst"].get("p50")
    if b50:
        ax1.axhline(b50, color=INK2, lw=1, ls=(0, (4, 3)))
        ax1.text(0.3, b50 * 1.15, f"평시 P50 {b50}ms", fontsize=9, color=INK2)
    if u50:
        ax1.text((burst_start + burst_end) / 2, u50 * 1.06,
                 f"버스트 중 P50 {u50}ms ({result['rtt_inflation_p50']}배)",
                 fontsize=9.5, color=C2, ha="center", fontweight="bold")
    ax1.set_xlabel("경과 시간 (초) · 음영 = 버스트 구간")
    ax1.set_ylabel("TCP 연결 RTT (ms)")
    ax1.set_yscale("log")
    ax1.set_title("동시 업로드 버스트 중 제어 채널 RTT")
    for s in ("top", "right"):
        ax1.spines[s].set_visible(False)

    cst = result["flow_completion_stats"]
    ax2.plot([1] * len(done), done, "o", color=C1, ms=8, alpha=0.7)
    ax2.axhline(2.88, color=C3, lw=1.4, ls=(0, (4, 3)))
    ax2.text(1.06, 2.88, "단독 업로드 P50 2.88s", va="center", fontsize=9, color=C3)
    if cst:
        ax2.axhline(cst["p50"], color=INK2, lw=1.1, ls=(0, (4, 3)))
        ax2.text(1.06, cst["p50"], f"동시 P50 {cst['p50']}s", va="center", fontsize=9, color=INK2)
    ax2.set_xlim(0.9, 1.25)
    ax2.set_xticks([])
    ax2.set_ylabel("플로우 완료 시간 (초)")
    ax2.set_title(f"{N_FLOWS}플로우 완료 분포\n합산 goodput {result['aggregate_goodput_mbps']}Mbps")
    for s in ("top", "right"):
        ax2.spines[s].set_visible(False)

    fig.suptitle("라운드 경계 버스트 실측 — 13노드 동시 어댑터 업로드 (PC→대전 KOREN VM, 2026-08-10)",
                 fontsize=12.5, fontweight="bold", y=1.02)
    ppath = out_dir / "fig_burst_test.png"
    fig.tight_layout()
    fig.savefig(ppath, bbox_inches="tight")

    print(f"\n평시 RTT P50 {b50}ms → 버스트 중 {u50}ms ({result['rtt_inflation_p50']}배)")
    print(f"완료 시간: {cst} (단독 2.88s 대비)")
    print(f"합산 goodput: {result['aggregate_goodput_mbps']} Mbps")
    print(f"저장: {jpath}\n차트: {ppath}")


if __name__ == "__main__":
    main()
