# -*- coding: utf-8 -*-
"""즉시 내보내기 서버 갱신 시험 — 공유 뒷단에 두 클라의 조각이 끼어들어도 각 클라의 갱신은 직렬 배치와 같아야 한다 (torch 필요).
    python tests/test_micro_srv.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sfl"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import torch, torch.nn as nn, torch.nn.functional as F
from fed_server import micro_step

fails = 0
def check(name, ok, detail=""):
    global fails; fails += 0 if ok else 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

def net0():
    torch.manual_seed(0); return nn.Sequential(nn.Linear(6, 16), nn.ReLU(), nn.Linear(16, 3))

def diff(a, b):
    return max((p - q).abs().max().item() for p, q in zip(a.parameters(), b.parameters()))

def main():
    print("== micro_step 시험 ==")
    torch.manual_seed(1)
    xa, ya = torch.randn(32, 6), torch.randint(0, 3, (32,)); xb, yb = torch.randn(32, 6), torch.randint(0, 3, (32,))
    ref = net0(); opt = torch.optim.SGD(ref.parameters(), lr=0.1, momentum=0.9)
    micro_step(ref, opt, F.cross_entropy(ref(xa), ya), 0, 1, {})                       # 기준: A 배치 한 걸음
    m1 = net0(); o1 = torch.optim.SGD(m1.parameters(), lr=0.1, momentum=0.9); buf = {}
    for i in range(4):
        sl = slice(8 * i, 8 * i + 8); buf = micro_step(m1, o1, F.cross_entropy(m1(xa[sl]), ya[sl]), i, 4, buf)
    check("① 혼자 조각 4개 = 배치 한 걸음", diff(ref, m1) < 1e-6, f"최대 차이 {diff(ref, m1):.2e}")
    m = net0(); om = torch.optim.SGD(m.parameters(), lr=0.1, momentum=0.9); bufA, bufB = {}, {}
    for i in range(4):                                                                  # A0 B0 A1 B1 A2 B2 A3 — B 는 아직 step 전
        sl = slice(8 * i, 8 * i + 8)
        bufA = micro_step(m, om, F.cross_entropy(m(xa[sl]), ya[sl]), i, 4, bufA)
        if i < 3:
            bufB = micro_step(m, om, F.cross_entropy(m(xb[sl]), yb[sl]), i, 4, bufB)
    check("② B 의 조각이 끼어들어도 A 의 갱신 = 기준 (클라별 버퍼 누적)", diff(ref, m) < 1e-6, f"최대 차이 {diff(ref, m):.2e}")
    check("③ A 는 step 뒤 버퍼가 비고, B 는 조각 3개가 버퍼에 남아 있다", bufA == {} and len(bufB) == sum(1 for _ in m.parameters()))
    o = net0(); oo = torch.optim.SGD(o.parameters(), lr=0.1, momentum=0.9)              # 옛 방식: .grad 직접 누적 — B 의 zero_grad 가 A 를 지운다
    for i in range(4):
        sl = slice(8 * i, 8 * i + 8)
        if i == 0: oo.zero_grad()
        (F.cross_entropy(o(xa[sl]), ya[sl]) / 4).backward()
        if i == 3: oo.step()
        if i < 3:
            if i == 0: oo.zero_grad()
            (F.cross_entropy(o(xb[sl]), yb[sl]) / 4).backward()
    check("④ 옛 방식은 기준과 어긋난다 (결함 재현)", diff(ref, o) > 1e-4, f"최대 차이 {diff(ref, o):.2e}")
    print(f"\n== {'전부 통과' if fails == 0 else f'실패 {fails}건'} ==")
    return 0 if fails == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
