# -*- coding: utf-8 -*-
"""자르기·재조립(chunker.py) 시험 — 소켓 없음.  python tests/test_chunker.py"""
import os, random, sys, threading, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sfl"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from chunker import Reassembler, Scheduler, chunk_size_for, split  # noqa: E402

fails = []
def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        fails.append(name)

def meta_of(tid, total, c):
    sq, of, ln = c
    return {"tid": tid, "seq": sq, "off": of, "ln": ln, "total": total}

# 1) split: 합 = 총 길이, 겹침·빈틈 없음, 마지막만 짧다
for total, cs in ((0, 7), (1, 7), (7, 7), (8, 7), (100, 7), (1 << 20, 1 << 16), (4194560, 1 << 20)):
    ch = split(total, cs)
    cover = sum(ln for _, _, ln in ch) == total
    contiguous = all(ch[i][1] + ch[i][2] == ch[i + 1][1] for i in range(len(ch) - 1)) and (not ch or ch[0][1] == 0)
    sizes_ok = all(ln == cs for _, _, ln in ch[:-1]) and (not ch or ch[-1][2] <= cs)
    seqs_ok = [s for s, _, _ in ch] == list(range(len(ch)))
    check(f"split({total}, {cs}) → {len(ch)}조각", cover and contiguous and sizes_ok and seqs_ok)

# 2) 순서를 섞어 넣어도 원본
rng = random.Random(3)
blob = bytes(rng.getrandbits(8) for _ in range(300_007))
ch = split(len(blob), 4096); rng.shuffle(ch)
R = Reassembler()
for c in ch:
    R.feed(meta_of("a", len(blob), c), blob[c[1]:c[1] + c[2]])
ok, got = R.feed({"tid": "a", "total": len(blob), "fin": 1})
check("섞인 순서로 넣어도 완성본 = 원본", ok and got == len(blob) and R.pop("a") == blob)

# 3) 재전송 중복은 한 번만 센다
R = Reassembler(); ch = split(len(blob), 4096)
for c in ch + ch[:5]:
    R.feed(meta_of("d", len(blob), c), blob[c[1]:c[1] + c[2]])
ok, got = R.feed({"tid": "d", "total": len(blob), "fin": 1})
check("같은 조각을 두 번 받아도 받은 양이 안 부푼다", ok and got == len(blob) and R.pop("d") == blob, f"got={got}")

# 4) 완료 신호가 마지막 조각보다 먼저 와도 기다렸다가 '완성'이라 답한다 (새벽 실험을 죽인 경합)
R = Reassembler(); ch = split(len(blob), 4096); last = ch[-1]
for c in ch[:-1]:
    R.feed(meta_of("f", len(blob), c), blob[c[1]:c[1] + c[2]])
res = {}
def fin():
    res["r"] = R.feed({"tid": "f", "total": len(blob), "fin": 1})
th = threading.Thread(target=fin); t0 = time.perf_counter(); th.start()
time.sleep(0.3)                                                 # 다른 연결의 마지막 조각이 늦게 도착
R.feed(meta_of("f", len(blob), last), blob[last[1]:last[1] + last[2]])
th.join(5); dt = time.perf_counter() - t0
check("완료 신호가 먼저 와도 남은 조각을 기다렸다 완성이라 답한다", res.get("r") == (True, len(blob)) and 0.25 <= dt < 5, f"{dt:.2f}s 기다림")
R.pop("f")

# 5) 진짜로 안 오면 시간 초과 뒤 '미완성'이라 답한다
R = Reassembler(); R.FIN_WAIT = 0.2
R.feed(meta_of("g", 10, (0, 0, 5)), b"12345")
ok, got = R.feed({"tid": "g", "total": 10, "fin": 1})
check("정말 안 오면 시간 초과 뒤 미완성(5/10)이라 답한다", ok is False and got == 5)

# 6) 전송 두 건이 섞이지 않는다
R = Reassembler(); A, B = blob[:1000], blob[500:2000]
for c in split(len(A), 128): R.feed(meta_of("A", len(A), c), A[c[1]:c[1] + c[2]])
for c in split(len(B), 128): R.feed(meta_of("B", len(B), c), B[c[1]:c[1] + c[2]])
check("전송 두 건(tid)이 안 섞인다", R.feed({"tid": "A", "total": len(A), "fin": 1})[0] and R.pop("A") == A and R.pop("B") == B)

# 7) 조각 모양이 틀리면 거부
R = Reassembler()
try:
    R.feed(meta_of("x", 10, (0, 8, 5)), b"12345"); check("범위를 벗어난 조각은 거부", False)
except ValueError:
    check("범위를 벗어난 조각은 거부", True)

# 8) Scheduler: 연결 3개가 경쟁해도 조각마다 정확히 한 번, 죽은 연결의 조각은 다른 연결이
ch = split(1 << 20, 1 << 12); S = Scheduler(ch); taken = {0: [], 1: [], 2: []}
gate = threading.Barrier(3)                                     # 셋이 동시에 출발해야 경쟁이 된다
def w(i):
    gate.wait()
    while True:
        it = S.take()
        if it is None: return
        if i == 2 and len(taken[2]) == 3:                       # 연결 2 는 4번째 조각에서 죽는다
            S.giveback(it); return
        taken[i].append(it)
        time.sleep(0.0005 * (i + 1))                            # 연결마다 속도가 다르다 (빠른 쪽이 더 가져간다)
ths = [threading.Thread(target=w, args=(i,)) for i in range(3)]
[t.start() for t in ths]; [t.join() for t in ths]
allt = taken[0] + taken[1] + taken[2]
check("먼저-한가한-연결 규칙: 조각마다 정확히 한 번, 죽은 연결 몫은 남은 연결이, 빠른 연결이 더 가져간다", sorted(allt) == ch and len(taken[2]) == 3 and S.remaining() == 0 and len(taken[0]) > len(taken[1]),
      f"연결별 {[len(taken[i]) for i in range(3)]}")

# 9) 조각 크기는 페이로드·연결 수에 맞춘다
check("조각 크기: 2MB·연결 2 → 64KB (2×16 조각), 33MB → 1MB 상한, 100KB → 64KB 하한",
      chunk_size_for(2 << 20, 2) == 64 << 10 and chunk_size_for(33 << 20, 2) == 1 << 20 and chunk_size_for(100 << 10, 2) == 64 << 10,
      f"{chunk_size_for(2<<20,2)>>10}KB {chunk_size_for(33<<20,2)>>20}MB {chunk_size_for(100<<10,2)>>10}KB")

# 10) 속도가 다른 두 연결(46 vs 19 Mbps)로 2MB 를 보낼 때 — 유체 시뮬로 완료 시각을 재 본다
def simulate(total, chunk, rates_bps):
    """연결마다 조각을 집어 자기 속도로 보낸다(이벤트 시뮬). 반환 완료 시각."""
    S = Scheduler(split(total, chunk)); now = 0.0
    busy = {c: None for c in rates_bps}                  # c → (끝나는 시각, 조각 길이)
    done_at = 0.0
    while True:
        for c, r in rates_bps.items():
            if busy[c] is None:
                it = S.take(c, now)
                if it is not None:
                    busy[c] = (now + it[2] / r, it[2])
        active = {c: v for c, v in busy.items() if v is not None}
        if not active:
            break
        c, (t_end, ln) = min(active.items(), key=lambda kv: kv[1][0])
        now = t_end; done_at = now
        S.report(c, ln, ln / rates_bps[c]); busy[c] = None
    return done_at
rates = {"A": 46e6 / 8, "B": 19e6 / 8}
total = 2 << 20
fast_alone = total / rates["A"]; ideal = total / (rates["A"] + rates["B"])
t_old = simulate(total, 1 << 20, rates)                           # 옛 규칙: 1MB 고정 (조각 2개)
t_new = simulate(total, chunk_size_for(total, 2), rates)          # 새 규칙: 128KB + 꼬리 규칙
check("옛 규칙(1MB 고정) 재현: 느린 출구가 1MB 를 잡아 빠른 출구 혼자보다 느렸다 (스모크 c3 현상)", t_old > fast_alone, f"{t_old:.2f}s vs 혼자 {fast_alone:.2f}s")
check("새 규칙: 두 출구가 빠른 출구 혼자보다 빠르고, 이상값(합산 대역)의 1.15배 안", t_new < fast_alone and t_new <= 1.15 * ideal, f"{t_new:.2f}s (이상 {ideal:.2f}s, 혼자 {fast_alone:.2f}s)")
total = 33 << 20
t_big = simulate(total, chunk_size_for(total, 2), rates); ideal_b = total / (rates["A"] + rates["B"])
check("큰 페이로드(33MB)도 이상값 1.05배 안", t_big <= 1.05 * ideal_b, f"{t_big:.2f}s (이상 {ideal_b:.2f}s)")

# 11) 규칙 3′ 가중 몫: 보내기가 즉시 끝나는(버퍼가 큰) 상황에서도 46:19 비율대로 나뉜다
S = Scheduler(split(1 << 20, 64 << 10), {"A": 46.0, "B": 19.0}); got = {"A": 0, "B": 0}
while True:
    took = False
    for c in ("A", "B"):
        it = S.take(c, 0.0, {"A", "B"})
        if it is not None:
            got[c] += it[2]; took = True
    if not took:
        break
share = got["A"] / (got["A"] + got["B"])
check("규칙 3′: 즉시 되돌아오는 보내기에서도 몫이 46:19 (A 65~75%)", 0.65 <= share <= 0.75 and S.remaining() == 0, f"A {share*100:.0f}%")
S = Scheduler(split(1 << 20, 64 << 10), {"A": 46.0, "B": 19.0})
n = 0
while S.take("A", 0.0, {"A"}) is not None:                 # B 가 죽었으면 A 가 전부 가져간다 (몫 완화)
    n += 1
check("규칙 3′: 살아 있는 연결이 하나면 몫과 무관하게 전부 보낸다", n == 16 and S.remaining() == 0, f"{n}조각")
print("== 전부 통과 ==" if not fails else f"== 실패 {len(fails)} ==")
sys.exit(1 if fails else 0)
