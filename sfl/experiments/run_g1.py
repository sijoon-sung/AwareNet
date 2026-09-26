# -*- coding: utf-8 -*-
"""G1 — 컨트롤러 예측식 검증 (오프라인, 기존 netem 스윕 데이터 사용).

  컨트롤러의 진짜 질문: "지금 p=1.0으로 돌고 있는데, p를 낮추면 얼마나 빨라지나?"
  매 p를 다 시험해 볼 수는 없다. 한 지점의 실측에서 다른 p를 예측해야 한다.

  예측 모델 (설계서 §2의 물리)
     T̂(p) = 연산(p) + 통신(p)
     연산(p) ≈ 연산(p_ref) · (p/p_ref)²      # conv FLOPs
     통신(p) ≈ 바이트(p_ref)·(p/p_ref)·8/bw + rtt   # 슬라이스 전송 → 바이트 ∝ p

  검증: **p=1.0 실측만으로** p=0.5·0.25를 예측하고 실측과 대조.
  사전 등록 판정: 평균 절대 오차 >25% → 결정 규칙 재설계 (설계서 A4)

    python sfl/experiments/run_g1.py
"""
import io
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FP = os.path.join(ROOT, "out", "g0_netem_results.json")

rows = json.load(io.open(FP, encoding="utf-8"))
by = {}
for r in rows:
    p = float(r["tag"].split("_p")[1].split("_")[0])
    cut = int(r["tag"].split("_cut")[1])
    by[(r["rtt"], r["bw"], cut, p)] = r

print("G1 — p=1.0 실측에서 다른 p 예측 (연산 ~p², 바이트 ~p)")
print(f"{'조건':22s} {'실측(s)':>9s} {'예측(s)':>9s} {'오차':>8s}")
errs = []
for (rtt, bw, cut, p), r in sorted(by.items()):
    if p == 1.0:
        continue
    ref = by.get((rtt, bw, cut, 1.0))
    if not ref:
        continue
    k = p / 1.0
    comp = (ref["t_fwd"] + ref["t_bwd"] + ref["t_srv"] + ref["t_lock"]) * k * k
    comm = (ref["up_B"] + ref["down_B"]) * k * 8 / (bw * 1e6) + rtt / 1000
    pred = comp + comm
    act = r["t_batch"]
    e = (pred - act) / act
    errs.append(abs(e))
    print(f"RTT{rtt:2d} bw{bw:3d} cut{cut} p{p:<4} {act:9.3f} {pred:9.3f} {e*100:+7.1f}%")

mae = sum(errs) / len(errs)
mx = max(errs)
print(f"\n평균 절대 오차 {mae*100:.1f}%  최대 {mx*100:.1f}%  (n={len(errs)})")
print(f"판정: {'PASS — 규칙 유지' if mae <= 0.25 else 'FAIL — 결정 규칙 재설계 (A4)'}"
      f"  [사전 등록 기준 25%]")
io.open(os.path.join(ROOT, "out", "g1_results.json"), "w", encoding="utf-8").write(
    json.dumps({"mae": mae, "max": mx, "n": len(errs)}, indent=1))
