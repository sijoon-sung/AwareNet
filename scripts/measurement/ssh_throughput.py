# -*- coding: utf-8 -*-
"""
ssh_throughput.py — SSH 파이프로 PC↔VM 처리량 측정 (iperf3 없이, SSH 포트만 열려 있을 때)

방법: /dev/zero 데이터를 SSH 표준입출력으로 흘려 벽시계 시간으로 goodput 산출.
  - 업로드 (PC→VM): 로컬에서 N MB 생성 → ssh "cat > /dev/null"
  - 다운로드 (VM→PC): ssh "dd if=/dev/zero bs=1M count=N" → 로컬에서 소비

주의: SSH 암호화 경유라 실제 회선 한계의 '하한치'다 (라벨에 명시).
FL 어댑터 업로드도 TLS/gRPC 암호화 경유이므로 실사용 관점 goodput으로는 오히려 근사적.

사용: python ssh_throughput.py [--host koren-vm] [--mb 100] [--repeat 3]
출력: out/link_profile/ssh_throughput_<UTC>.json + 요약 CSV append
"""
import argparse
import csv
import datetime
import json
import statistics
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def upload(host, mb):
    """PC → VM: mb 메가바이트를 ssh stdin으로 전송."""
    chunk = b"\x00" * (1 << 20)
    t0 = time.perf_counter()
    p = subprocess.Popen(["ssh", "-o", "BatchMode=yes", host, "cat > /dev/null"],
                         stdin=subprocess.PIPE)
    for _ in range(mb):
        p.stdin.write(chunk)
    p.stdin.close()
    p.wait(timeout=300)
    dt = time.perf_counter() - t0
    return round(mb * 8 / dt, 2), round(dt, 2)


def download(host, mb):
    """VM → PC: dd 출력물을 stdout으로 수신."""
    t0 = time.perf_counter()
    p = subprocess.Popen(["ssh", "-o", "BatchMode=yes", host,
                          f"dd if=/dev/zero bs=1M count={mb} 2>/dev/null"],
                         stdout=subprocess.PIPE)
    n = 0
    while True:
        b = p.stdout.read(1 << 20)
        if not b:
            break
        n += len(b)
    p.wait(timeout=300)
    dt = time.perf_counter() - t0
    return round(n / (1 << 20) * 8 / dt, 2), round(dt, 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="koren-vm")
    ap.add_argument("--mb", type=int, default=100)
    ap.add_argument("--repeat", type=int, default=3)
    args = ap.parse_args()

    ts = datetime.datetime.now(datetime.timezone.utc)
    ups, downs = [], []
    for i in range(1, args.repeat + 1):
        u, ut = upload(args.host, args.mb)
        d, dt = download(args.host, args.mb)
        ups.append(u); downs.append(d)
        print(f"[{i}/{args.repeat}] 업로드 {u} Mbps ({ut}s) / 다운로드 {d} Mbps ({dt}s)")

    result = {
        "timestamp_utc": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": "ssh-pipe (암호화 경유 goodput — 회선 한계의 하한치)",
        "host": args.host, "mb_per_run": args.mb, "repeat": args.repeat,
        "upload_mbps": ups, "download_mbps": downs,
        "upload_avg_mbps": round(statistics.mean(ups), 2),
        "download_avg_mbps": round(statistics.mean(downs), 2),
    }
    out_dir = REPO / "out" / "link_profile"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"ssh_throughput_{ts.strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_path = out_dir / "link_profile_summary.csv"
    if csv_path.exists():
        with csv_path.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([result["timestamp_utc"], f"ssh_throughput({args.host})", args.host,
                        "", "", "", "", "", "", result["upload_avg_mbps"],
                        result["download_avg_mbps"]])
    print(f"\n업로드 평균 {result['upload_avg_mbps']} Mbps / 다운로드 평균 {result['download_avg_mbps']} Mbps")
    print(f"저장: {path}")


if __name__ == "__main__":
    main()
