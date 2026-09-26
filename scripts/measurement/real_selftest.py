# -*- coding: utf-8 -*-
"""실회선 리그 자가 검사 — 리그(real_rig.sh up)가 선 상태에서 HPC 에서 실행. 실제 조각 채널(ChunkLinks/ChunkServer)로 잰다.

    python scripts/measurement/real_selftest.py --cond r8_rho1 [--secs 6]

  A 단독   클라 0 출구 A 만 → 엣지 1 : ≈ min(aA, c1)                   허용 −30%/+15% (실회선·터널·재전송 감안)
  B 동시   클라 0..3 출구 A → 엣지 1 : 각 ≈ 물 채우기(c1 을 4대가)         허용 −30%/+15%
  C 왕복   클라 0 → 엣지 1 포트 TCP 연결 왕복                              보고만 (기대 ≈ 4~8ms)
  D 두 출구 클라 0 출구 A+B → 엣지 1 : ≈ min(aA,c1) + min(aB,c1) (가중 3′)   허용 −30%/+15%
  E 내리기 서버 → 클라 0 두 출구 (send_back) : ≈ min(aA,c1) + min(aB,c1)   허용 −30%/+15% (VM egress 기기·출구별 접속 상한, 2026-09-09)
"""
import argparse, os, socket, sys, threading, time
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "sfl")); sys.path.insert(0, os.path.join(ROOT, "scripts", "exp"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import cond  # noqa: E402
from mpsend import ChunkLinks, ChunkServer  # noqa: E402

BASE = int(os.environ.get("BASE", 12100))
VM1 = os.environ.get("VM1", "116.89.187.190"); VM2 = os.environ.get("VM2", "116.89.187.189")
EDGE_HOST = [VM1, VM1, VM2, VM2]


def ep(e, i, x):
    return (EDGE_HOST[e], BASE + e * 500 + 2 * i + x, None)


def water_fill(cap, limits):
    share = {k: 0.0 for k in limits}; left, active = cap, dict(limits)
    while active and left > 1e-9:
        eq = left / len(active); done = {k: v for k, v in active.items() if v <= eq}
        if not done:
            for k in active: share[k] = eq
            break
        for k, v in done.items(): share[k] = v; left -= v; del active[k]
    return share


def xfer(L, cs, cid, blob, n, weights=None):
    """n 건을 채널로 올리고 (Mbps) 를 돌려준다."""
    waits = [threading.Thread(target=lambda i=i: cs.wait(f"{cid}-u{i}", 120)) for i in range(n)]
    for w in waits: w.start()
    t0 = time.perf_counter()
    for i in range(n):
        L.send(blob, f"{cid}-u{i}", cid=cid, weights=weights)
    L.flush()
    for w in waits: w.join(120)
    return len(blob) * n * 8 / 1e6 / (time.perf_counter() - t0)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--cond", required=True); ap.add_argument("--secs", type=float, default=6.0)
    ap.add_argument("--mb", type=float, default=1.0)
    a = ap.parse_args()
    r = cond.resolve(a.cond); caps = r["caps"]["v"]; n = r["clients"]["v"]
    acc = [str(x) for x in r["acc_list"]["v"]]; aA = [float(x.split("/")[0]) for x in acc]; aB = [float(x.split("/")[-1]) for x in acc]
    port = int(r["server_port"]["v"]) + 1
    cs = ChunkServer("0.0.0.0", port); cs.start()
    blob = os.urandom(int(a.mb * (1 << 20))); n_tx = max(4, int(a.secs * 50 / (a.mb * 8)))    # ≈ secs 만큼 (50Mbps 기준)
    fails = []
    def judge(name, exp, got, lo=0.70, hi=1.15):
        ok = lo * exp <= got <= hi * exp
        fails.append(f"{name}: {got:.1f} vs 기대 {exp:.1f}") if not ok else None
        return "OK" if ok else "FAIL"

    print(f"A 단독: 클라 0 출구 A → 엣지 1 ({n_tx}×{a.mb}MB)")
    L = ChunkLinks("", 0, [], endpoints=[ep(0, 0, 0)]); got = xfer(L, cs, "c0", blob, n_tx); L.close()
    exp = min(aA[0], caps[0]); print(f"  기대 {exp:6.1f}  측정 {got:6.1f} Mbps  {judge('A', exp, got)}")

    print(f"\nB 동시: 클라 0..3 출구 A → 엣지 1")
    share = water_fill(caps[0], {f"c{i}": aA[i] for i in range(min(4, n))}); res = {}
    Ls = {f"c{i}": ChunkLinks("", 0, [], endpoints=[ep(0, i, 0)]) for i in range(min(4, n))}
    ths = [threading.Thread(target=lambda k=k: res.__setitem__(k, xfer(Ls[k], cs, k, blob, n_tx))) for k in Ls]
    for t in ths: t.start()
    for t in ths: t.join()
    for k in sorted(res):
        print(f"  {k}: 기대 {share[k]:6.1f}  측정 {res[k]:6.1f} Mbps  {judge('B '+k, share[k], res[k])}")
    print(f"  합계 {sum(res.values()):.1f} Mbps (엣지 1 용량 {caps[0]})")
    for L_ in Ls.values(): L_.close()

    print("\nC 왕복: 클라 0 → 엣지 1 포트 TCP 연결")
    ts = []
    for _ in range(5):
        s = socket.socket(); t0 = time.perf_counter(); s.connect(ep(0, 0, 0)[:2]); ts.append((time.perf_counter() - t0) * 1000); s.close()
    print(f"  중앙값 {sorted(ts)[2]:.1f} ms")

    print(f"\nD 두 출구: 클라 0 출구 A+B → 엣지 1 (가중 {aA[0]}:{aB[0]})")
    L = ChunkLinks("", 0, [], endpoints=[ep(0, 0, 0), ep(0, 0, 1)]); got = xfer(L, cs, "c0", blob, n_tx, weights=[aA[0], aB[0]])
    st = L.exit_stats(); exp = min(aA[0], caps[0]) + min(aB[0], caps[0])
    print(f"  기대 {exp:6.1f}  측정 {got:6.1f} Mbps  출구 A 몫 {100*st[0]['up']/max(1,st[0]['up']+st[1]['up']):.0f}%  {judge('D', exp, got)}")

    print("\nE 내리기: 서버 → 클라 0 두 출구 (send_back)")
    waits = [threading.Thread(target=lambda i=i: L.wait(f"dn{i}", 120)) for i in range(n_tx)]
    for w in waits: w.start()
    t0 = time.perf_counter()
    for i in range(n_tx):
        cs.send_back("c0", blob, f"dn{i}", weights=[aA[0], aB[0]])
    cs.flush_back("c0")
    for w in waits: w.join(120)
    got = len(blob) * n_tx * 8 / 1e6 / (time.perf_counter() - t0)
    exp = min(aA[0], caps[0]) + min(aB[0], caps[0])                # 내리기도 출구별 접속 상한(VM egress 자식 클래스, 2026-09-09) → D 와 같은 기대
    print(f"  기대 {exp:6.1f}(출구 A+B 접속 상한)  측정 {got:6.1f} Mbps  {judge('E', exp, got)}")
    L.close(); cs.stop = True
    print("\n== 실회선 자가 검사:", "통과" if not fails else "실패 " + "; ".join(fails), "==")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
