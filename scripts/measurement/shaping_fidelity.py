# -*- coding: utf-8 -*-
"""
shaping_fidelity.py — "요구한 대역폭이 실제로 나오는가" 실측

우리 주장의 전제: 게이트웨이가 노드별 대역폭 몫을 정하면 그대로 집행된다.
이 전제가 성립하지 않으면 배분 결과 전체가 무의미하므로, 주장하지 않고 **잰다.**

방법: 컨테이너에 tc-tbf로 목표 레이트를 걸고 실제 파일 전송 처리량을 측정한다.
목표값은 5G 트레이스의 실제 범위(0.23~35.85Mbps)를 덮도록 고른다.

사용: python3 scripts/measurement/shaping_fidelity.py [--container client-001]
"""
import argparse
import json
import os
import subprocess
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(REPO, "out", "shaping_fidelity.json")

# 5G 트레이스 실측 범위를 덮는 목표값 (P5=0.54, P50=6.93, P95=18.5, max=35.9 포함)
TARGETS_MBPS = [0.23, 0.54, 1.0, 3.0, 6.93, 12.0, 18.5, 25.0, 35.85]
PAYLOAD_MB = 9.38          # MobileNetV2 state_dict 실측 크기와 동일하게 맞춘다


def sh(cmd, timeout=180):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)


def set_rate(container, mbps):
    """컨테이너 eth0에 tc-tbf로 목표 레이트 적용 (배포판 게이트웨이와 동일한 손잡이)."""
    kbit = max(8, int(mbps * 1000))
    r = sh(f"docker exec {container} tc qdisc replace dev eth0 root "
           f"tbf rate {kbit}kbit burst 32kbit latency 400ms")
    return r.returncode == 0


def measure(container, mbps, payload_mb):
    """컨테이너 안에서 payload_mb를 전송하고 실제 처리량(Mbps)을 잰다.

    루프백이 아니라 셰이핑이 걸린 eth0을 지나게 해야 하므로, 게이트웨이(호스트 브리지)
    주소로 보낸다. nc 대신 파이썬 소켓을 쓰는 이유는 컨테이너에 nc가 없을 수 있어서.
    """
    script = (
        "import socket,time,os;"
        f"n={int(payload_mb * 1e6)};"
        "s=socket.socket();s.settimeout(300);"
        "s.connect((os.environ.get('GW','172.17.0.1'),9200));"
        "b=b'x'*65536;sent=0;t0=time.time();"
        "\nwhile sent<n:\n s.sendall(b[:min(65536,n-sent)]);sent+=min(65536,n-sent)\n"
        "s.close();d=time.time()-t0;print(round(sent*8/d/1e6,4))"
    )
    r = sh(f"docker exec -e GW=172.17.0.1 {container} python -c \"{script}\"", timeout=400)
    try:
        return float(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None


def start_sink(port=9200):
    """호스트에서 데이터를 받아 버리는 소켓 서버 (전송 시간만 재면 되므로 내용은 무시)."""
    code = (
        "import socket,threading\n"
        "s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)\n"
        f"s.bind(('0.0.0.0',{port}));s.listen(16)\n"
        "def h(c):\n"
        " while True:\n"
        "  d=c.recv(1<<20)\n"
        "  if not d: break\n"
        " c.close()\n"
        "while True:\n"
        " c,_=s.accept();threading.Thread(target=h,args=(c,),daemon=True).start()\n"
    )
    p = os.path.join("/tmp", "awarenet_sink.py")
    with open(p, "w") as f:
        f.write(code)
    return subprocess.Popen(["python3", p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--container", default="client-001")
    ap.add_argument("--payload-mb", type=float, default=PAYLOAD_MB)
    args = ap.parse_args()

    print(f"셰이핑 충실도 측정 — 컨테이너 {args.container} · 페이로드 {args.payload_mb}MB")
    print("목표 레이트는 5G 트레이스 실측 범위(0.23~35.85Mbps)를 덮도록 선정\n")

    sink = start_sink()
    time.sleep(2)
    rows = []
    try:
        for t in TARGETS_MBPS:
            if not set_rate(args.container, t):
                print(f"  {t:>6.2f} Mbps : tc 적용 실패")
                continue
            time.sleep(1)
            got = measure(args.container, t, args.payload_mb)
            if got is None:
                print(f"  {t:>6.2f} Mbps : 측정 실패")
                continue
            ratio = got / t
            rows.append({"target_mbps": t, "achieved_mbps": round(got, 3),
                         "ratio": round(ratio, 3)})
            print(f"  {t:>6.2f} Mbps 요구 → {got:>7.3f} Mbps 달성 · 달성률 {ratio * 100:>5.1f}%")
    finally:
        sink.terminate()

    if rows:
        rs = [r["ratio"] for r in rows]
        print(f"\n달성률 최소 {min(rs) * 100:.1f}% · 최대 {max(rs) * 100:.1f}% "
              f"· 평균 {sum(rs) / len(rs) * 100:.1f}%")
        print("※ 100%를 다소 밑도는 것은 TCP/IP 헤더 오버헤드로 정상이다.")
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump({"payload_mb": args.payload_mb, "container": args.container,
                       "rows": rows}, f, ensure_ascii=False, indent=1)
        print(f"저장: {os.path.relpath(OUT, REPO)}")


if __name__ == "__main__":
    main()
