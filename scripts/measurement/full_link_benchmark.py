# -*- coding: utf-8 -*-
"""
full_link_benchmark.py — PC ↔ 대전 KOREN VM 상세 링크 벤치마크 (4단계)

  A) TCP 연결 RTT 시계열: 포트 26022, 100회 × 0.2s 간격 (ICMP 차단 환경 대응)
  B) 처리량: SSH 파이프 상/하행 × 3회 × 100MB (암호화 경유 goodput = 하한치)
  C) canonical 어댑터(8.68MB) 실WAN 업로드 10회 — 분포(mean/P50/P95)
  D) VM측 백본 기저: VM→KT DNS·8.8.8.8 각 50회 ping (백본 안정성)

출력:
  out/link_profile/full_benchmark_<UTC>.json
  out/link_profile/fig_wan_benchmark.png  (3패널)
"""
import datetime
import json
import re
import socket
import statistics
import subprocess
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parents[2]
HOST_IP = "116.89.187.190"
SSH_HOST = "koren-vm"
TCP_PORT = 26022
ADAPTER_BYTES = 8_683_638  # canonical LoRA 어댑터 실측 크기

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


def stats(vals):
    s = sorted(vals)
    return {
        "n": len(s), "min": round(s[0], 2), "max": round(s[-1], 2),
        "mean": round(statistics.mean(s), 2), "p50": round(statistics.median(s), 2),
        "p95": round(s[min(len(s) - 1, int(0.95 * len(s)))], 2),
        "std": round(statistics.stdev(s), 2) if len(s) > 1 else 0.0,
    }


def phase_a_tcp_rtt(n=100, interval=0.2):
    print(f"[A] TCP RTT {HOST_IP}:{TCP_PORT} × {n}회 ...")
    rtts, fails = [], 0
    for _ in range(n):
        t0 = time.perf_counter()
        try:
            with socket.create_connection((HOST_IP, TCP_PORT), timeout=3):
                rtts.append((time.perf_counter() - t0) * 1000)
        except OSError:
            fails += 1
        time.sleep(interval)
    print(f"    -> {stats(rtts)} 실패 {fails}")
    return {"rtts_ms": [round(r, 2) for r in rtts], "failed": fails, "stats": stats(rtts)}


def ssh_pipe_upload(mb):
    chunk = b"\x00" * (1 << 20)
    t0 = time.perf_counter()
    p = subprocess.Popen(["ssh", "-o", "BatchMode=yes", SSH_HOST, "cat > /dev/null"],
                         stdin=subprocess.PIPE)
    for _ in range(mb):
        p.stdin.write(chunk)
    p.stdin.close()
    p.wait(timeout=300)
    return time.perf_counter() - t0


def ssh_pipe_download(mb):
    t0 = time.perf_counter()
    p = subprocess.Popen(["ssh", "-o", "BatchMode=yes", SSH_HOST,
                          f"dd if=/dev/zero bs=1M count={mb} 2>/dev/null"],
                         stdout=subprocess.PIPE)
    while p.stdout.read(1 << 20):
        pass
    p.wait(timeout=300)
    return time.perf_counter() - t0


def phase_b_throughput(mb=100, reps=3):
    print(f"[B] SSH 파이프 처리량 {mb}MB × {reps}회 ...")
    ups, downs = [], []
    for i in range(reps):
        du = ssh_pipe_upload(mb)
        dd = ssh_pipe_download(mb)
        ups.append(round(mb * 8 / du, 2))
        downs.append(round(mb * 8 / dd, 2))
        print(f"    [{i+1}] 상행 {ups[-1]} / 하행 {downs[-1]} Mbps")
    return {"upload_mbps": ups, "download_mbps": downs,
            "upload_avg": round(statistics.mean(ups), 2),
            "download_avg": round(statistics.mean(downs), 2)}


def phase_c_adapter_upload(reps=10):
    """canonical 어댑터 크기를 단발 SSH 세션으로 업로드 — 실사용 시나리오 근사.
    세션 수립 오버헤드를 분리하기 위해 전송 시간만 계측(파이프에 쓴 시점부터)."""
    print(f"[C] 어댑터 8.68MB 실WAN 업로드 × {reps}회 ...")
    times = []
    payload = b"\x00" * ADAPTER_BYTES
    for i in range(reps):
        p = subprocess.Popen(["ssh", "-o", "BatchMode=yes", SSH_HOST, "cat > /dev/null"],
                             stdin=subprocess.PIPE)
        t0 = time.perf_counter()
        p.stdin.write(payload)
        p.stdin.close()
        p.wait(timeout=120)
        times.append(round(time.perf_counter() - t0, 3))
    print(f"    -> {stats(times)}")
    return {"times_s": times, "stats": stats(times),
            "implied_goodput_mbps": round(ADAPTER_BYTES * 8 / 1e6 / statistics.median(times), 2)}


def phase_d_vm_baseline():
    print("[D] VM측 백본 기저 (KT DNS·8.8.8.8 각 50회) ...")
    rc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", SSH_HOST,
         "ping -c 50 -i 0.1 -q 168.126.63.1 | tail -1; ping -c 50 -i 0.1 -q 8.8.8.8 | tail -1"],
        capture_output=True, timeout=120)
    out = rc.stdout.decode(errors="replace").strip().splitlines()
    res = {}
    for label, line in zip(["kt_dns", "google_dns"], out):
        m = re.search(r"=\s*([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)", line)
        if m:
            res[label] = {"min": float(m.group(1)), "avg": float(m.group(2)),
                          "max": float(m.group(3)), "mdev": float(m.group(4))}
    print(f"    -> {res}")
    return res


def make_figure(result, out_png):
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(14.4, 4.2), dpi=150)

    # 패널 1: RTT 시계열
    rtts = result["A_tcp_rtt"]["rtts_ms"]
    st = result["A_tcp_rtt"]["stats"]
    ax1.plot(range(len(rtts)), rtts, "-", color=C1, lw=1.2)
    ax1.axhline(st["p50"], color=INK2, lw=1.1, ls=(0, (4, 3)))
    ax1.axhline(st["p95"], color=C2, lw=1.1, ls=(0, (4, 3)))
    ax1.text(len(rtts) - 1, st["p50"] + 1, f"P50 {st['p50']}ms", ha="right", fontsize=9, color=INK2)
    ax1.text(len(rtts) - 1, st["p95"] + 1, f"P95 {st['p95']}ms", ha="right", fontsize=9, color=C2)
    ax1.set_xlabel("표본 (0.2s 간격, n=100)")
    ax1.set_ylabel("TCP 연결 RTT (ms)")
    ax1.set_title(f"RTT 시계열 — 평균 {st['mean']}ms · 지터 ±{st['std']}ms")
    for s in ("top", "right"):
        ax1.spines[s].set_visible(False)

    # 패널 2: 어댑터 업로드 분포
    times = result["C_adapter_upload"]["times_s"]
    cst = result["C_adapter_upload"]["stats"]
    ax2.plot([0.98 + 0.004 * i for i in range(len(times))], times, "o", color=C1, ms=8, alpha=0.75)
    ax2.axhline(cst["p50"], color=INK2, lw=1.1, ls=(0, (4, 3)))
    ax2.text(1.06, cst["p50"], f"P50 {cst['p50']}s", va="center", fontsize=9.5, color=INK2)
    ax2.set_xlim(0.9, 1.15)
    ax2.set_xticks([])
    ax2.set_ylabel("업로드 시간 (초)")
    ax2.set_title(f"canonical 어댑터 8.68MB 실WAN 업로드 (n={cst['n']})\n"
                  f"P50 {cst['p50']}s · P95 {cst['p95']}s · goodput {result['C_adapter_upload']['implied_goodput_mbps']}Mbps")
    for s in ("top", "right"):
        ax2.spines[s].set_visible(False)

    # 패널 3: 처리량 + 백본 기저
    b = result["B_throughput"]
    x = range(len(b["upload_mbps"]))
    w = 0.35
    ax3.bar([i - w / 2 for i in x], b["upload_mbps"], width=w, color=C1, label="상행")
    ax3.bar([i + w / 2 for i in x], b["download_mbps"], width=w, color=C2, label="하행")
    ax3.set_xticks(list(x), [f"{i+1}회" for i in x])
    ax3.set_ylabel("goodput (Mbps)")
    kt = result["D_vm_baseline"].get("kt_dns", {})
    ax3.set_title(f"처리량 (SSH 경유 하한치) — 상행 평균 {b['upload_avg']}Mbps\n"
                  f"백본 기저(VM→KT DNS): {kt.get('avg','?')}ms ± {kt.get('mdev','?')}ms")
    ax3.legend(frameon=False, fontsize=9)
    for s in ("top", "right"):
        ax3.spines[s].set_visible(False)

    fig.suptitle("PC ↔ 대전 KOREN VM 상세 링크 벤치마크 — 2026-08-10 실측 "
                 "(자택망 등록 IP · ICMP 차단으로 RTT는 TCP 연결 기준)",
                 fontsize=12.5, fontweight="bold", y=1.02)
    fig.tight_layout()
    fig.savefig(out_png, bbox_inches="tight")


def main():
    ts = datetime.datetime.now(datetime.timezone.utc)
    result = {"timestamp_utc": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
              "target": f"{HOST_IP}:{TCP_PORT} (ssh host {SSH_HOST})",
              "note": "자택망(등록 IP). ICMP 차단 → RTT는 TCP 3-way 핸드셰이크. "
                      "처리량은 SSH 암호화 경유 goodput(하한치)."}
    result["A_tcp_rtt"] = phase_a_tcp_rtt()
    result["B_throughput"] = phase_b_throughput()
    result["C_adapter_upload"] = phase_c_adapter_upload()
    result["D_vm_baseline"] = phase_d_vm_baseline()

    out_dir = REPO / "out" / "link_profile"
    out_dir.mkdir(parents=True, exist_ok=True)
    jpath = out_dir / f"full_benchmark_{ts.strftime('%Y%m%dT%H%M%SZ')}.json"
    jpath.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    ppath = out_dir / "fig_wan_benchmark.png"
    make_figure(result, ppath)
    print(f"\n저장: {jpath}\n차트: {ppath}")


if __name__ == "__main__":
    main()
