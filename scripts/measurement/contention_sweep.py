# -*- coding: utf-8 -*-
"""
contention_sweep.py — 혼잡도 스윕 하에서 정책별 구제 커버리지 실측

[왜 필요한가]
  해석 모델은 "우리 방법이 물리 가능한 48%를 전부 살린다"고 예측했다. 그러나 그 계산은
  각 노드가 배분받은 몫을 그대로 낸다고 가정한다. 실제로는 공유 링크에서 TCP가 경쟁하고,
  배경 트래픽이 용량을 잠식하며, 버스트가 겹친다. **예측이 실측으로 재현되는지 확인한다.**

[진짜 경합을 만드는 법]
  컨테이너가 각자 tc로 제한만 걸려 있으면 서로 경쟁하지 않는다(공유 병목 부재).
  그래서 호스트 브리지(docker0)에 총량 C를 걸어 **실제 공유 병목**을 만든다.
  그 위에서 배경 트래픽이 일부를 먹고, 나머지를 학습 노드들이 나눠 갖는다.

    docker0 (tbf rate C)  ←── 배경 트래픽 + 학습 노드 13개가 동시에 경쟁
      └ 각 컨테이너 eth0 (tbf rate = min(정책 배분, 물리 상한 b_i))

[측정]
  각 (정책 × 혼잡도)에서 13노드가 실제 페이로드를 동시 전송하고, τ 내 도착 수를 센다.
  학습은 하지 않는다 — 네트워크 주장만 분리해서 검증하는 리허설이다.

사용: sudo python3 scripts/measurement/contention_sweep.py --policies static equal full
"""
import argparse
import json
import os
import subprocess
import threading
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ASSIGN = os.path.join(REPO, "scripts", "deploy", "bandwidth_assignment_local.json")
OUT = os.path.join(REPO, "out", "contention_sweep.json")
SINK_PORT = 9300


def sh(cmd, timeout=120):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)


def set_bridge_cap(mbps: float, iface="docker0"):
    """호스트 브리지에 총량 상한 — 이것이 공유 병목을 만든다."""
    sh(f"tc qdisc del dev {iface} root 2>/dev/null")
    r = sh(f"tc qdisc add dev {iface} root tbf rate {int(mbps * 1000)}kbit "
           f"burst 256kbit latency 400ms")
    return r.returncode == 0


def clear_bridge(iface="docker0"):
    sh(f"tc qdisc del dev {iface} root 2>/dev/null")


def set_node_rate(container: str, mbps: float):
    kbit = max(8, int(mbps * 1000))
    return sh(f"docker exec {container} tc qdisc replace dev eth0 root "
              f"tbf rate {kbit}kbit burst 32kbit latency 400ms").returncode == 0


def policy_alloc(policy: str, nodes: dict, total: float, r_star: float, rare: set):
    """정책별 노드 배분 몫 {cid: Mbps}. 물리 상한 클램프는 tc 적용 시점에 걸린다."""
    k = len(nodes)
    equal = total / k
    if policy in ("static", "selection_only"):
        # 현행: 배분 개입 없음 — 각자 자기 링크 상한까지 자유 경쟁(공유 병목에서 나눠짐)
        return {c: nodes[c] for c in nodes}
    if policy == "equal":
        return {c: equal for c in nodes}
    # full: 희귀(=가치 높은) 노드를 r*까지 승격, 나머지는 잔여분 균등
    promoted = {c: min(r_star * 1.05, nodes[c]) for c in nodes if c in rare}
    rest = total - sum(promoted.values())
    others = [c for c in nodes if c not in rare]
    share = max(0.1, rest / max(1, len(others)))
    return {**promoted, **{c: share for c in others}}


def transfer(container: str, payload_mb: float, timeout: float):
    """컨테이너에서 payload를 호스트 sink로 전송하고 소요 시간(초)을 반환.

    타임아웃은 '도착 실패'로 간주해 None을 돌려준다 — 마감 τ를 이미 넘긴 전송을
    끝까지 기다릴 이유가 없다(0.54Mbps 노드는 139초가 걸리는데 판정은 10초에 끝난다).
    예외를 잡지 않으면 스레드가 죽어 그 조건 전체가 유실된다.
    """
    n = int(payload_mb * 1e6)
    script = (
        "import socket,time,os;"
        f"n={n};"
        "s=socket.socket();s.settimeout(%.1f);" % (timeout + 20) +
        f"s.connect((os.environ.get('GW','172.17.0.1'),{SINK_PORT}));"
        "b=b'x'*65536;sent=0;t0=time.time();"
        "\nwhile sent<n:\n s.sendall(b[:min(65536,n-sent)]);sent+=min(65536,n-sent)\n"
        "s.close();print(round(time.time()-t0,3))"
    )
    try:
        r = sh(f"docker exec -e GW=172.17.0.1 {container} python -c \"{script}\"",
               timeout=timeout)
    except subprocess.TimeoutExpired:
        return None          # 마감 초과 — 탈락으로 집계
    try:
        return float(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None


def start_sink(port=SINK_PORT):
    code = (
        "import socket,threading\n"
        "s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)\n"
        f"s.bind(('0.0.0.0',{port}));s.listen(64)\n"
        "def h(c):\n"
        " while True:\n"
        "  d=c.recv(1<<20)\n"
        "  if not d: break\n"
        " c.close()\n"
        "while True:\n"
        " c,_=s.accept();threading.Thread(target=h,args=(c,),daemon=True).start()\n"
    )
    p = "/tmp/awarenet_sweep_sink.py"
    with open(p, "w") as f:
        f.write(code)
    return subprocess.Popen(["python3", p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def start_background(container: str, mbps: float, duration: float):
    """배경 트래픽 — 공유 병목의 일부를 실제로 점유한다."""
    if mbps <= 0:
        return None
    set_node_rate(container, mbps)
    n = int(mbps / 8 * duration * 1e6)
    return subprocess.Popen(
        f"docker exec -e GW=172.17.0.1 {container} python -c \""
        f"import socket,os;s=socket.socket();s.settimeout(300);"
        f"s.connect((os.environ.get('GW','172.17.0.1'),{SINK_PORT}));"
        f"b=b'x'*65536;sent=0;n={n};"
        f"\nwhile sent<n:\n s.sendall(b);sent+=65536\n"
        f"s.close()\"",
        shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policies", nargs="+", default=["static", "equal", "full"])
    ap.add_argument("--contention", nargs="+", type=float, default=[0, 20, 40, 60],
                    help="배경 트래픽이 총량에서 차지하는 비율(%%)")
    ap.add_argument("--total", type=float, default=100.0)
    ap.add_argument("--k", type=int, default=13)
    ap.add_argument("--tau", type=float, default=10.0)
    ap.add_argument("--payload-mb", type=float, default=9.38)
    ap.add_argument("--comp-sec", type=float, default=0.5)
    ap.add_argument("--rare", nargs="+", default=None, help="희귀 데이터 보유 노드")
    ap.add_argument("--node-seed", type=int, default=7, help="선발 13노드 추출 시드(사전 등록)")
    ap.add_argument("--rare-seed", type=int, default=42, help="희귀 노드 배치 시드(사전 등록)")
    args = ap.parse_args()

    with open(ASSIGN, encoding="utf-8") as f:
        caps = {c: float(v["mbps"]) for c, v in json.load(f).items()}

    running = [n for n in sh("docker ps --format '{{.Names}}'").stdout.split()
               if n.startswith("client-") and n in caps]
    if len(running) < args.k + 1:
        raise SystemExit(f"실행 중 컨테이너 {len(running)}개 — 최소 {args.k + 1}개 필요")

    # [주의] 이름 순으로 앞에서 자르면 안 된다. 트레이스가 정렬 배정이라 client-001..013이
    # 가장 느린 13개가 되어 전 정책이 물리적으로 실패한다(실제로 겪음).
    # 실선발은 데이터 가치 기준인데 가치와 대역폭의 상관이 +0.002(무상관)이므로,
    # 선발 13노드는 대역폭 분포에서의 **무작위 추출**로 모델링하는 것이 옳다.
    running.sort()
    bg_container = running[-1]                  # 배경 트래픽 발생기 (선발에서 제외)
    pool = running[:-1]
    import random as _rnd
    picked = _rnd.Random(args.node_seed).sample(pool, min(args.k, len(pool)))
    nodes = {c: caps[c] for c in sorted(picked)}
    r_star = args.payload_mb * 8.0 / max(0.1, args.tau - args.comp_sec)

    # 희귀 노드도 고르지 않는다 — 선발된 노드 중 시드 무작위. 물리적으로 불가능한
    # 노드가 걸리면 그대로 두고 실패를 보고한다(유리한 배치를 고르지 않는다는 원칙).
    rare = set(args.rare or _rnd.Random(args.rare_seed).sample(sorted(nodes), 1))

    print(f"혼잡 스윕 — 노드 {len(nodes)}개 · τ={args.tau}s · r*={r_star:.2f}Mbps · 총량 {args.total}Mbps")
    print(f"희귀 노드: {sorted(rare)} (물리 상한 {[round(nodes[c], 2) for c in sorted(rare)]})")
    print(f"배경 트래픽 발생: {bg_container}\n")

    sink = start_sink()
    time.sleep(2)
    results = []
    try:
        for pct in args.contention:
            bg_mbps = args.total * pct / 100.0
            avail = args.total - bg_mbps
            for policy in args.policies:
                set_bridge_cap(args.total)          # 공유 병목 재설정
                alloc = policy_alloc(policy, nodes, avail, r_star, rare)
                for c, m in alloc.items():
                    set_node_rate(c, min(m, nodes[c]))   # 물리 상한 클램프
                bg = start_background(bg_container, bg_mbps, args.tau * 3)
                time.sleep(1)

                times, lock = {}, threading.Lock()

                def run(c):
                    # 마감의 2배까지만 기다린다 — 그 뒤는 판정에 영향이 없고 시간만 든다
                    d = transfer(c, args.payload_mb, args.tau * 2)
                    with lock:
                        times[c] = d

                ths = [threading.Thread(target=run, args=(c,)) for c in nodes]
                [t.start() for t in ths]
                [t.join() for t in ths]
                if bg:
                    bg.terminate()

                ok = {c: (d is not None and d <= args.tau) for c, d in times.items()}
                rare_ok = sum(1 for c in rare if ok.get(c))
                row = {"contention_pct": pct, "policy": policy,
                       "arrived": sum(ok.values()), "total_nodes": len(nodes),
                       "rare_arrived": rare_ok, "rare_total": len(rare),
                       "times": {c: times[c] for c in times}}
                results.append(row)
                print(f"  혼잡 {pct:>3.0f}% · {policy:<15} 도착 {row['arrived']:>2}/{len(nodes)} "
                      f"· 희귀 {rare_ok}/{len(rare)}")
    finally:
        clear_bridge()
        sink.terminate()

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"params": {"tau": args.tau, "total": args.total, "k": args.k,
                              "payload_mb": args.payload_mb, "r_star": round(r_star, 3),
                              "rare": sorted(rare)}, "rows": results},
                  f, ensure_ascii=False, indent=1)
    print(f"\n저장: {os.path.relpath(OUT, REPO)}")


if __name__ == "__main__":
    main()
