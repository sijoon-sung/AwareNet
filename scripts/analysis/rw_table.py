# -*- coding: utf-8 -*-
"""R(w) 표 — 학습량(폭)별 "목표 정확도까지 필요한 라운드 수" (멘토링 질문 ②의 재료).

  입력: run_e9.py 가 --widths × --seeds 로 만든 out/e9_w{W}_s{S}_results.json (곡선 포함)
  출력: 목표별 도달 라운드 수(시드 평균, 도달 시드 수) · 라운드시간 · 벽시계 배율

  ★ 칸은 **도달한 시드만의 평균**이라 (1/3)·(2/3) 칸은 생존 편향이 있다 — 모양을 보는 용도.
  기록: docs/02_실험/실험_재설계_R시리즈.md §1-보2

    python scripts/analysis/rw_table.py                         # out/e9_w4_s3_results.json
    python scripts/analysis/rw_table.py --file out/e9_w3_s1_results.json --targets 0.25,0.30
"""
import argparse
import io
import json
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def rounds_to(curve, t):
    for i, (_, acc) in enumerate(curve):
        if acc >= t:
            return i + 1
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="out/e9_w4_s3_results.json")
    ap.add_argument("--targets", default="0.25,0.30,0.32,0.34")
    a = ap.parse_args()
    fn = os.path.join(ROOT, a.file)
    tg = [float(x) for x in a.targets.split(",")]
    rows = json.load(io.open(fn, encoding="utf-8"))
    ws = sorted({r["p"] for r in rows}, reverse=True)
    seeds = sorted({r.get("seed", 1) for r in rows})
    age = (time.time() - os.path.getmtime(fn)) / 3600
    print(f"결과 파일: {a.file}  ({time.strftime('%m-%d %H:%M', time.localtime(os.path.getmtime(fn)))}, "
          f"{age:.1f}시간 전)  {len(rows)}판 · 시드 {seeds} · 곡선 {len(rows[0]['curve'])}라운드")

    print("\n=== R(w): 목표까지 필요한 라운드 수 (도달 시드 평균, 도달/전체) ===")
    print(f"{'p':>5s} {'라운드시간':>9s} | " + " | ".join(f"{'→'+format(t*100,'.0f')+'%':>11s}" for t in tg)
          + " | 최종acc  최고acc")
    ms_of = {}
    for p in ws:
        g = [r for r in rows if r["p"] == p]
        ms_of[p] = sum(r["makespan"] for r in g) / len(g)
        cells = []
        for t in tg:
            hit = [x for x in (rounds_to(r["curve"], t) for r in g) if x]
            cells.append(f"{sum(hit)/len(hit):5.1f}R ({len(hit)}/{len(g)})" if hit else f"{'미달':>11s}")
        fa = sum(r["final_acc"] for r in g) / len(g) * 100
        ba = sum(r["best_acc"] for r in g) / len(g) * 100
        print(f"{p:5.2f} {ms_of[p]:8.2f}s | " + " | ".join(cells) + f" | {fa:6.2f}%  {ba:6.2f}%")

    print("\n=== 같은 목표까지의 벽시계 = 라운드수 × 라운드시간 (전폭 대비 배율) ===")
    for t in tg:
        line, base = f"  →{t*100:.0f}%: ", None
        for p in ws:
            g = [r for r in rows if r["p"] == p]
            hit = [x for x in (rounds_to(r["curve"], t) for r in g) if x]
            if not hit:
                line += f"p={p:.2f} 미달   "
                continue
            tt = sum(hit) / len(hit) * ms_of[p]
            if p == max(ws):
                base = tt
            line += f"p={p:.2f} {tt:5.1f}s" + (f" ({tt/base:.2f}×)" if base else "") + "   "
        print(line)

    print("\n★ 낮은 목표에서 라운드 수가 폭과 무관하면 R(w)≈상수 → 총시간은 라운드시간이 좌우 → 좁힐수록 빠르다.")
    print("  천장 근처에서 좁은 폭의 라운드 수가 늘거나 미달하면 거기부터 R(w) 의 폭 의존 — '더 좁히면 손해' 경계.")


if __name__ == "__main__":
    main()
