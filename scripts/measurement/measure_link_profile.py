# -*- coding: utf-8 -*-
"""
measure_link_profile.py — PC↔VM / VM↔VM 링크 프로파일 실측 도구

측정 항목
  1) ICMP RTT (ping): min/avg/max/jitter(표준편차)/손실률
  2) TCP 연결 RTT (옵션, --tcp-port): ICMP가 막힌 구간의 대체 지표
  3) iperf3 처리량 (옵션): 상대편에서 `iperf3 -s`가 떠 있어야 함

동작 환경: Windows(한국어/영어) + Linux 공용. 파이썬 표준 라이브러리만 사용.

사용 예
  # 내 PC → 대전 VM (ICMP + 제어 API 포트 TCP RTT)
  python measure_link_profile.py --label pc_to_daejeon --host 116.89.187.190 --tcp-port 8080

  # 판교 VM → 대전 VM (VM↔VM 백본, iperf3 포함 — 대전에서 iperf3 -s 실행 후)
  python3 measure_link_profile.py --label pangyo_to_daejeon --host <대전IP> --iperf --iperf-time 30

출력
  out/link_profile/<label>_<UTC타임스탬프>.json   (원자료 + 요약)
  out/link_profile/link_profile_summary.csv      (요약 1행 append — 회차 비교용)
"""
import argparse
import csv
import datetime
import json
import platform
import re
import shutil
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path

IS_WINDOWS = platform.system() == "Windows"


def run_ping(host: str, count: int, timeout_sec: int = 4):
    """ping을 실행하고 로케일 무관하게 회신별 RTT(ms)를 추출한다."""
    if IS_WINDOWS:
        cmd = ["ping", "-n", str(count), "-w", str(timeout_sec * 1000), host]
    else:
        cmd = ["ping", "-c", str(count), "-W", str(timeout_sec), host]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=count * (timeout_sec + 1) + 15)
    except subprocess.TimeoutExpired:
        return {"error": "ping timeout", "rtts_ms": []}
    # 한국어 Windows: "시간=24ms" / 영어: "time=24ms" / Linux: "time=24.3 ms"
    text = proc.stdout.decode(errors="replace") + proc.stderr.decode(errors="replace")
    rtts = [float(m) for m in re.findall(r"[=<]\s*(\d+(?:\.\d+)?)\s*ms", text)]
    # Windows 요약부의 min/max/avg 3개 값이 섞이는 것을 방지: 회신 수(count) 초과분은 뒤에서 제거
    if IS_WINDOWS and len(rtts) > count:
        rtts = rtts[:-3] if len(rtts) - 3 >= 0 else rtts
    return {"raw_output_tail": text.strip().splitlines()[-4:], "rtts_ms": rtts, "sent": count}


def tcp_rtt(host: str, port: int, count: int = 10, timeout_sec: float = 3.0):
    """TCP 3-way 핸드셰이크 소요 시간으로 RTT를 근사 측정한다 (ICMP 차단 구간 대체)."""
    samples = []
    fails = 0
    for _ in range(count):
        t0 = time.perf_counter()
        try:
            with socket.create_connection((host, port), timeout=timeout_sec):
                samples.append((time.perf_counter() - t0) * 1000.0)
        except OSError:
            fails += 1
        time.sleep(0.2)
    return {"port": port, "rtts_ms": samples, "sent": count, "failed": fails}


def run_iperf3(host: str, duration: int, port: int, reverse: bool):
    """iperf3 -J 실행. 미설치/서버 부재 시 이유를 담아 None성 결과 반환."""
    exe = shutil.which("iperf3")
    if not exe:
        return {"skipped": "iperf3 not installed on this machine"}
    cmd = [exe, "-c", host, "-p", str(port), "-t", str(duration), "-J"]
    if reverse:
        cmd.append("-R")
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=duration + 30)
        data = json.loads(proc.stdout.decode(errors="replace") or "{}")
    except subprocess.TimeoutExpired:
        return {"error": "iperf3 timeout"}
    except json.JSONDecodeError:
        return {"error": "iperf3 output parse failure", "stderr": proc.stderr.decode(errors="replace")[:500]}
    if "error" in data:
        return {"error": data["error"]}
    try:
        end = data["end"]
        sent = end.get("sum_sent", {})
        recv = end.get("sum_received", {})
        return {
            "throughput_send_mbps": round(sent.get("bits_per_second", 0) / 1e6, 2),
            "throughput_recv_mbps": round(recv.get("bits_per_second", 0) / 1e6, 2),
            "retransmits": sent.get("retransmits"),
            "duration_sec": duration,
            "reverse": reverse,
        }
    except KeyError:
        return {"error": "unexpected iperf3 JSON shape"}


def summarize(rtts, sent):
    if not rtts:
        return {"received": 0, "loss_pct": 100.0}
    return {
        "received": len(rtts),
        "loss_pct": round(100.0 * (1 - len(rtts) / sent), 1) if sent else None,
        "rtt_min_ms": round(min(rtts), 2),
        "rtt_avg_ms": round(statistics.mean(rtts), 2),
        "rtt_max_ms": round(max(rtts), 2),
        "rtt_p50_ms": round(statistics.median(rtts), 2),
        "jitter_std_ms": round(statistics.stdev(rtts), 2) if len(rtts) > 1 else 0.0,
    }


def main():
    ap = argparse.ArgumentParser(description="PC/VM 간 링크 프로파일 실측 (ping + TCP RTT + iperf3)")
    ap.add_argument("--label", required=True, help="측정 경로 라벨 (예: pc_to_daejeon, pangyo_to_daejeon)")
    ap.add_argument("--host", required=True, help="대상 IP/호스트")
    ap.add_argument("--count", type=int, default=30, help="ping 회수 (기본 30)")
    ap.add_argument("--tcp-port", type=int, default=None, help="TCP RTT 측정 포트 (예: 8080)")
    ap.add_argument("--iperf", action="store_true", help="iperf3 처리량 측정 수행")
    ap.add_argument("--iperf-port", type=int, default=5201)
    ap.add_argument("--iperf-time", type=int, default=10, help="iperf3 측정 시간(초)")
    ap.add_argument("--iperf-reverse", action="store_true", help="다운로드 방향(-R)도 측정")
    ap.add_argument("--out-dir", default=None, help="출력 폴더 (기본: <repo>/out/link_profile)")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    out_dir = Path(args.out_dir) if args.out_dir else repo_root / "out" / "link_profile"
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.datetime.now(datetime.timezone.utc)
    result = {
        "label": args.label,
        "target_host": args.host,
        "source_hostname": socket.gethostname(),
        "source_platform": platform.platform(),
        "timestamp_utc": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    print(f"[1/3] ping {args.host} x{args.count} ...")
    ping = run_ping(args.host, args.count)
    ping["summary"] = summarize(ping.get("rtts_ms", []), ping.get("sent", args.count))
    result["icmp_ping"] = ping
    print(f"      -> {ping['summary']}")

    if args.tcp_port:
        print(f"[2/3] TCP RTT {args.host}:{args.tcp_port} x10 ...")
        tcp = tcp_rtt(args.host, args.tcp_port)
        tcp["summary"] = summarize(tcp["rtts_ms"], tcp["sent"])
        result["tcp_rtt"] = tcp
        print(f"      -> {tcp['summary']}")
    else:
        print("[2/3] TCP RTT: 생략 (--tcp-port 미지정)")

    if args.iperf:
        print(f"[3/3] iperf3 -> {args.host}:{args.iperf_port} ({args.iperf_time}s) ...")
        up = run_iperf3(args.host, args.iperf_time, args.iperf_port, reverse=False)
        result["iperf3_upload"] = up
        print(f"      -> {up}")
        if args.iperf_reverse:
            down = run_iperf3(args.host, args.iperf_time, args.iperf_port, reverse=True)
            result["iperf3_download"] = down
            print(f"      -> (reverse) {down}")
    else:
        print("[3/3] iperf3: 생략 (--iperf 미지정)")

    json_path = out_dir / f"{args.label}_{ts.strftime('%Y%m%dT%H%M%SZ')}.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_path = out_dir / "link_profile_summary.csv"
    s = result["icmp_ping"]["summary"]
    row = {
        "timestamp_utc": result["timestamp_utc"],
        "label": args.label,
        "target": args.host,
        "rtt_min_ms": s.get("rtt_min_ms"),
        "rtt_avg_ms": s.get("rtt_avg_ms"),
        "rtt_max_ms": s.get("rtt_max_ms"),
        "jitter_std_ms": s.get("jitter_std_ms"),
        "loss_pct": s.get("loss_pct"),
        "tcp_rtt_avg_ms": result.get("tcp_rtt", {}).get("summary", {}).get("rtt_avg_ms"),
        "iperf_up_mbps": result.get("iperf3_upload", {}).get("throughput_send_mbps"),
        "iperf_down_mbps": result.get("iperf3_download", {}).get("throughput_recv_mbps"),
    }
    new_file = not csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if new_file:
            w.writeheader()
        w.writerow(row)

    print(f"\n저장 완료: {json_path}")
    print(f"요약 CSV : {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
