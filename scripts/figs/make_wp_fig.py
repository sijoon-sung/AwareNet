# -*- coding: utf-8 -*-
"""폭×경로 온라인 판단 결과 그림 — final_06 (경증/심한 병목 2칸)"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import json, io, os

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
INK = "#1d2d3d"; SUB = "#5a6b7a"; ACC = "#0f766e"; WARN = "#b45309"


def load(tag):
    rows = [json.loads(l) for l in
            io.open(os.path.join(ROOT, "out", f"wp_{tag}.jsonl"), encoding="utf-8")
            if "round" in l]
    return [r["makespan"] for r in rows]


fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4))
panels = [("", "여유 있는 판 (경로 100/20Mbps)"),
          ("hv_", "병목이 심한 판 (경로 30/10Mbps)")]
for ax, (pre, title) in zip(axes, panels):
    u = load(pre + "uniform")
    w = load(pre + "widthpath")
    rounds = range(len(u))
    ax.plot(rounds, u, "o-", color=WARN, lw=2, label="기준 — 전원 빠른 경로·전체 학습량")
    ax.plot(range(len(w)), w, "s-", color=ACC, lw=2, label="온라인 공동 판단 (폭×경로)")
    mu, mw = sum(u) / len(u), sum(w) / len(w)
    ax.axhline(mu, ls=":", color=WARN, alpha=0.6)
    ax.axhline(mw, ls=":", color=ACC, alpha=0.6)
    d = (1 - mw / mu) * 100
    ax.set_title(f"{title}\n평균 {mu:.1f}초 → {mw:.1f}초 ({d:+.0f}%)",
                 fontsize=11.5, weight="bold")
    ax.set_xlabel("라운드")
    ax.set_ylabel("라운드 완료 시간 (초)")
    ax.legend(fontsize=8.5, loc="upper right")
    ax.grid(alpha=0.25)
plt.tight_layout()
out = os.path.join(ROOT, "out", "fig", "final_06_온라인판단.png")
plt.savefig(out, dpi=170, bbox_inches="tight")
print("saved", out)
