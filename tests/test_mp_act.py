# -*- coding: utf-8 -*-
"""집행 층 시험 — 조각 전송(mpsend.send_multipath) ↔ 서버 조각 수신기(ChunkServer) 왕복.

루프백만 쓴다(tc 없음).  python tests/test_mp_act.py

무엇을 지키나
  1) 바이트가 그대로다 (출구 여러 개로 나눠 보내도 재조립이 정확)
  2) 완료 신호는 **남은 조각을 기다렸다** 답한다 — 2026-09-07 게이트가 잡은 경합.
     보내는 쪽은 조각을 전부 커널에 넘긴 뒤 완료 신호를 한 연결로 보내므로, 다른 연결의
     조각이 아직 도착 전일 수 있다. 그때 받은 양을 그대로 답하면 "8MB 중 6MB" 거짓 불일치.
     연결 수를 늘리고 여러 번 돌려 그 창을 벌린다.
  3) 전송 여러 건(tid)이 같은 수신기에서 서로 섞이지 않는다.
"""
import os
import random
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sfl"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from mpsend import ChunkLinks, ChunkServer, send_multipath  # noqa: E402

# 리그(hairpin_lo.sh)가 127.0.0.1~N / 127.0.1.1~N / 127.0.0.100 을 tc 로 잡고 있다.
# 실험이 도는 중에 시험을 걸어도 그 회선을 뺏지 않도록 겹치지 않는 주소를 쓴다.
def _host():
    import socket as _s
    for h in ("127.0.0.200", "127.0.0.1"):
        try:
            t = _s.socket(); t.bind((h, 0)); t.close(); return h
        except OSError:
            continue
    return "127.0.0.1"


HOST = _host()
REPS = 6                    # 경합은 확률적이라 여러 번 돌린다
BLOB_MB = 8


def roundtrip(cs, blob, tid, sources):
    got = {}
    th = threading.Thread(target=lambda: got.__setitem__("b", cs.wait(tid, timeout=60)))
    th.start()
    r = send_multipath(HOST, cs.srv.getsockname()[1], blob, sources, tid, cid="c0")
    th.join(60)
    return got.get("b"), r


def _span_unit():
    from mpsend import _span, _span_total
    c = {"up_t": 0.0, "up_tid": None, "up_t0": 0.0, "up_last": 0.0}
    _span(c, "up", "t1", 10.0); c["up_last"] = 13.0            # 전송 t1: 10 → 13
    _span(c, "up", "t2", 20.0); c["up_last"] = 22.0            # 전송 t2 가 오면 t1 의 3 s 를 누적
    ok = abs(c["up_t"] - 3.0) < 1e-9 and abs(_span_total(c, "up") - 5.0) < 1e-9
    print(f"  [{'PASS' if ok else 'FAIL'}] 출구별 활동 구간 누적: t1 3 s + 열린 t2 2 s = 5 s — {c['up_t']}, {_span_total(c, 'up')}")
    return ok


def main():
    if not _span_unit():
        return 1
    port = random.Random(os.getpid()).randint(34000, 39000)
    cs = ChunkServer(HOST, port)
    cs.start()
    blob = bytes(random.Random(7).getrandbits(8) for _ in range(1 << 16)) * (BLOB_MB * 16)
    fails = []

    # 1·2) 출구 여러 개 × 반복 — 바이트 일치 + 완료 신호 경합
    for n_src in (2, 4):
        oks, worst = 0, 0.0
        for rep in range(REPS):
            t0 = time.perf_counter()
            try:
                back, r = roundtrip(cs, blob, f"t-{n_src}-{rep}", [HOST] * n_src)
            except OSError as e:
                fails.append(f"출구 {n_src}개 {rep}회차: {e}")
                continue
            worst = max(worst, time.perf_counter() - t0)
            if back == blob:
                oks += 1
            else:
                fails.append(f"출구 {n_src}개 {rep}회차: 바이트 불일치 ({len(back or b'')} / {len(blob)})")
        print(f"  [{'PASS' if oks == REPS else 'FAIL'}] 출구 {n_src}개로 {BLOB_MB}MB × {REPS}회 "
              f"— 왕복 성공 {oks}/{REPS}, 최장 {worst:.2f}s")

    # 3) 전송 두 건이 안 섞인다
    a, b = blob[: 3 << 20], blob[1 << 20 : 5 << 20]
    ra, _ = roundtrip(cs, a, "mix-a", [HOST, HOST])
    rb, _ = roundtrip(cs, b, "mix-b", [HOST])
    ok3 = ra == a and rb == b
    fails += [] if ok3 else ["전송 두 건이 섞임"]
    print(f"  [{'PASS' if ok3 else 'FAIL'}] 전송 두 건(tid 다름)이 같은 수신기에서 안 섞인다")

    # 4) 규칙 1: 상시 연결 — 전송 5건을 같은 ChunkLinks 로 보내면 연결은 출구 수만큼만 열린다
    before = cs.accepted
    L = ChunkLinks(HOST, cs.srv.getsockname()[1], [HOST, HOST])
    ok4 = True
    two_mb = 2 * 1024 * 1024
    for i in range(5):
        got4 = {}
        th = threading.Thread(target=lambda i=i: got4.__setitem__("b", cs.wait(f"keep-{i}", timeout=60))); th.start()
        L.send(blob[:two_mb], f"keep-{i}", cid="c9"); th.join(60)
        ok4 = ok4 and got4.get("b") == blob[:two_mb]
    # 5) 규칙 5 양방향: 서버가 같은 연결들로 내려보내면 클라가 받는다 — 올리기와 동시에도
    dn = blob[1 << 20: 4 << 20]
    got5 = {}
    th = threading.Thread(target=lambda: got5.__setitem__("b", L.wait("dn-1", timeout=60))); th.start()
    time.sleep(0.05)
    r5 = cs.send_back("c9", dn, "dn-1"); th.join(60)
    ok5 = got5.get("b") == dn and r5["conns"] == 2
    fails += [] if ok5 else [f"양방향 내려받기 실패 (conns={r5.get('conns')})"]
    print(f"  [{'PASS' if ok5 else 'FAIL'}] 규칙 5 양방향: 서버 → 클라 3MB 를 같은 연결 2개로 내려받음 (분배 {[v['bytes'] for v in r5['per'].values()]})")
    # 동시에: 클라 올리기 + 서버 내려보내기
    got6 = {}
    ths = [threading.Thread(target=lambda: got6.__setitem__("up", cs.wait("both-up", timeout=60))),
           threading.Thread(target=lambda: got6.__setitem__("dn", L.wait("both-dn", timeout=60)))]
    for th_ in ths: th_.start()
    t_up = threading.Thread(target=lambda: L.send(blob[:two_mb], "both-up", cid="c9")); t_up.start()
    cs.send_back("c9", dn, "both-dn"); t_up.join(60)
    for th_ in ths: th_.join(60)
    ok6 = got6.get("up") == blob[:two_mb] and got6.get("dn") == dn
    fails += [] if ok6 else ["동시 양방향 실패"]
    print(f"  [{'PASS' if ok6 else 'FAIL'}] 규칙 5 동시 양방향: 올리기 2MB + 내려받기 3MB 가 같은 연결들 위에서 함께 완성")
    # 규칙 8: 비동기 내려보내기 — 넘기고 즉시 돌아오고, flush_back 에서 전부 확인
    got8 = {}
    ths8 = [threading.Thread(target=lambda i=i: got8.__setitem__(i, L.wait(f"aq-{i}", 60))) for i in range(4)]
    for t_ in ths8: t_.start()
    t0 = time.perf_counter()
    for i in range(4):
        cs.send_back("c9", dn, f"aq-{i}", wait=False)
    t_enq = time.perf_counter() - t0
    cs.flush_back("c9")
    for t_ in ths8: t_.join(60)
    ok8 = all(got8.get(i) == dn for i in range(4)) and t_enq < 0.05
    fails += [] if ok8 else [f"비동기 내려보내기 실패 (enqueue {t_enq:.3f}s)"]
    print(f"  [{'PASS' if ok8 else 'FAIL'}] 규칙 8 비동기 내려보내기: 3MB×4 를 넘기는 데 {t_enq*1000:.0f}ms, flush_back 뒤 전부 일치")
    L.flush(); cs.peers["c9"].flush()                          # 규칙 7: 비동기 회신을 모아 확인 — 불일치면 여기서 OSError
    print("  [PASS] 규칙 7 비동기 완료 회신: flush 에서 전부 일치")
    L.close()
    opened = cs.accepted - before
    check_ok = ok4 and opened == 2 and L.opened == 2
    fails += [] if check_ok else [f"상시 연결: 바이트 {ok4}, 연결 {opened}개(기대 2)"]
    print(f"  [{'PASS' if check_ok else 'FAIL'}] 규칙 1 상시 연결: 전송 5건에 연결 {opened}개만 (출구 수), 바이트 일치")
    cs.stop = True
    print(f"  (주소 {HOST} — 리그와 겹치지 않음)")
    print("== 전부 통과 ==" if not fails else "== 실패 ==\n  " + "\n  ".join(fails))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
