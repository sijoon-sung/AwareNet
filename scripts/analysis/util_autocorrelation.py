# -*- coding: utf-8 -*-
"""
util_autocorrelation.py — 데이터 가치의 라운드 간 지속성 검증

설계 가정: "직전 라운드에 가치가 높던 노드는 이번 라운드에도 높다."
1라운드 지연 배분(가치는 직전 라운드 관측, 배분은 이번 라운드 행동)이 성립하려면
이 가정이 필요하다. 본 스크립트는 out/round_metrics.jsonl의 util_snapshot을 읽어
연속 라운드 간 가치 순위상관(Spearman rho)을 산출한다.

  rho 높음 → 가정 성립, 1라운드 지연이 무해
  rho 낮음 → 가정 취약, EMA 계수(beta) 재조정 필요

출력: out/util_autocorrelation.json  (+ --plot 시 그림)
사용: python scripts/analysis/util_autocorrelation.py [--arm full] [--plot]
"""
import argparse
import json
import os
from collections import defaultdict

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(REPO, "out", "round_metrics.jsonl")
DST = os.path.join(REPO, "out", "util_autocorrelation.json")


def spearman(xs, ys):
    """순위 변환 후 피어슨 상관. 동점은 평균 순위로 처리."""
    n = len(xs)
    if n < 3:
        return None

    def rank(vals):
        order = sorted(range(n), key=lambda i: vals[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = rank(xs), rank(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def load_snapshots(path, arm_filter=None):
    """(arm, round) -> {cid: util_ema}. 같은 arm/round가 여러 번이면 마지막 것."""
    runs = defaultdict(dict)
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            snap = rec.get("util_snapshot")
            if not snap:
                continue
            arm = rec.get("arm", "unknown")
            if arm_filter and arm != arm_filter:
                continue
            runs[arm][int(rec["round"])] = {
                cid: float(v.get("util_ema", 0.0)) for cid, v in snap.items()
            }
    return runs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--arm", default=None, help="특정 비교군만 (예: full)")
    ap.add_argument("--plot", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.src):
        raise SystemExit(
            f"원자료 없음: {args.src}\n"
            "  util_snapshot은 flower_server.py가 라운드마다 기록합니다. "
            "실험을 한 번 돌린 뒤 다시 실행하세요."
        )

    runs = load_snapshots(args.src, args.arm)
    if not runs:
        raise SystemExit(
            "util_snapshot이 있는 레코드가 없습니다.\n"
            "  로깅 도입 이전 실험의 기록일 수 있습니다 — 재실행이 필요합니다."
        )

    report = {"source": os.path.relpath(args.src, REPO), "arms": {}}
    for arm, by_round in sorted(runs.items()):
        rounds = sorted(by_round)
        pairs = []
        for a, b in zip(rounds, rounds[1:]):
            if b != a + 1:
                continue  # 연속 라운드만
            common = sorted(set(by_round[a]) & set(by_round[b]))
            # 전원 동일값(warm-up 직후 등)이면 순위가 정의되지 않는다
            xs = [by_round[a][c] for c in common]
            ys = [by_round[b][c] for c in common]
            rho = spearman(xs, ys)
            if rho is None:
                continue
            pairs.append({"round_from": a, "round_to": b, "n_nodes": len(common),
                          "spearman_rho": round(rho, 4)})

        rhos = [p["spearman_rho"] for p in pairs]
        summary = {
            "n_rounds": len(rounds),
            "n_pairs": len(pairs),
            "mean_rho": round(sum(rhos) / len(rhos), 4) if rhos else None,
            "min_rho": round(min(rhos), 4) if rhos else None,
            "max_rho": round(max(rhos), 4) if rhos else None,
            "pairs": pairs,
        }
        report["arms"][arm] = summary

        print(f"\n[{arm}] 라운드 {len(rounds)}개 · 연속쌍 {len(pairs)}개")
        for p in pairs:
            print(f"   R{p['round_from']:>2} → R{p['round_to']:>2} "
                  f"(n={p['n_nodes']:>3}) : rho = {p['spearman_rho']:+.3f}")
        if rhos:
            m = summary["mean_rho"]
            verdict = ("가정 강하게 성립" if m >= 0.8 else
                       "가정 성립" if m >= 0.6 else
                       "약한 지속성 — beta 재검토" if m >= 0.3 else
                       "지속성 없음 — 설계 재검토 필요")
            print(f"   평균 rho = {m:+.3f}  →  {verdict}")

    os.makedirs(os.path.dirname(DST), exist_ok=True)
    with open(DST, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(f"\n저장: {os.path.relpath(DST, REPO)}")

    if args.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False})
        fig, ax = plt.subplots(figsize=(8, 4.2), dpi=120)
        for arm, s in report["arms"].items():
            if not s["pairs"]:
                continue
            ax.plot([p["round_to"] for p in s["pairs"]],
                    [p["spearman_rho"] for p in s["pairs"]],
                    marker="o", label=f"{arm} (평균 {s['mean_rho']:+.2f})")
        ax.axhline(0.6, ls="--", lw=1, color="#15803d")
        ax.text(0.01, 0.62, "지속성 성립 기준", transform=ax.get_yaxis_transform(),
                fontsize=9, color="#15803d")
        ax.set_ylim(-1.05, 1.05)
        ax.set_xlabel("라운드")
        ax.set_ylabel("직전 라운드 대비 가치 순위상관 (Spearman ρ)")
        ax.set_title("데이터 가치는 라운드 간 유지되는가")
        ax.legend(fontsize=9)
        ax.grid(alpha=0.3)
        out = os.path.join(REPO, "out", "fig_util_autocorrelation.png")
        fig.tight_layout()
        fig.savefig(out)
        print(f"저장: {os.path.relpath(out, REPO)}")


if __name__ == "__main__":
    main()
