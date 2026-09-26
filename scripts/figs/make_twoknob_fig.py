# -*- coding: utf-8 -*-
"""그림 7 — 두 손잡이(접속 경로 + 학습량 폭)가 한 판단으로 움직이는 장면."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle
import os

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
INK = "#1d2d3d"; SUB = "#5a6b7a"; TEAL = "#0f766e"; ORANGE = "#b45309"
TEAL_L = "#d7eae8"; ORANGE_L = "#f6e3cd"; GRAY = "#c9d2d9"

fig, ax = plt.subplots(figsize=(12, 6.6))
ax.set_xlim(0, 100); ax.set_ylim(0, 63); ax.axis("off")


def card(x, y, w, h, fc, ec, lw=1.4, r=0.8):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                                fc=fc, ec=ec, lw=lw, zorder=3))


def gauge(x, y, frac, color):
    ax.add_patch(Rectangle((x, y), 10, 1.6, fc="#eef1f4", ec=GRAY, lw=0.8, zorder=4))
    ax.add_patch(Rectangle((x, y), 10 * frac, 1.6, fc=color, ec="none", zorder=5))
    ax.text(x + 11.2, y + 0.8, f"폭 {int(frac*100)}%", fontsize=9, va="center",
            color=INK, zorder=5)


# ── 기기 4대 (왼쪽) ─────────────────────────────────────────
devs = [("기기 1", 45.6, 1.0, False), ("기기 2", 35.2, 1.0, False),
        ("기기 3", 24.8, 0.75, True), ("기기 4", 14.4, 1.0, False)]
for name, y, frac, moved in devs:
    ec = ORANGE if moved else GRAY
    card(3, y, 21, 8.4, "white", ec, lw=2 if moved else 1.2)
    ax.text(4.5, y + 6.3, name, fontsize=11, weight="bold", color=INK, zorder=5)
    gauge(4.5, y + 2.2, frac, ORANGE if moved else TEAL)

# ── 경로 2개 (가운데 파이프) ────────────────────────────────
ax.add_patch(Rectangle((36, 36), 26, 9, fc=TEAL_L, ec=TEAL, lw=1.6, zorder=2))
ax.text(49, 40.5, "경로 1 — 넓은 길 (40Mbps)", fontsize=10.5, ha="center",
        va="center", color=TEAL, weight="bold", zorder=4)
ax.add_patch(Rectangle((36, 22), 26, 5.5, fc=ORANGE_L, ec=ORANGE, lw=1.6, zorder=2))
ax.text(49, 24.7, "경로 2 — 좁은 길 (20Mbps)", fontsize=10, ha="center",
        va="center", color=ORANGE, weight="bold", zorder=4)


def link(y0, y1, color, lw=1.8, ls="-"):
    ax.add_patch(FancyArrowPatch((24.3, y0), (36, y1), arrowstyle="-",
                                 connectionstyle="arc3,rad=0.12",
                                 color=color, lw=lw, ls=ls, zorder=1))

link(49.8, 43, TEAL)
link(39.4, 40.5, TEAL)
link(29.0, 24.7, ORANGE, lw=2.4)          # 기기 3 — 좁은 길로 이동
link(18.6, 38, TEAL)

# 이동 표시 — 원래 자리(경로 1)에서 옮겨 갔음을 점선으로
link(29.0, 37.2, GRAY, lw=1.2, ls=(0, (3, 3)))
ax.text(27.6, 32.6, "이동", fontsize=9, color=ORANGE, weight="bold", rotation=-16)

# 경로 → 서버
card(70, 27, 26, 15, "white", GRAY, lw=1.4)
ax.text(83, 37.6, "집계 서버", fontsize=12.5, weight="bold", ha="center", color=INK, zorder=4)
ax.text(83, 33.6, "모두의 결과를 모아\n하나의 모델로", fontsize=9, ha="center",
        va="center", color=SUB, zorder=4)
ax.add_patch(FancyArrowPatch((62, 40.5), (70, 36.5), arrowstyle="-|>",
                             mutation_scale=14, color=TEAL, lw=1.8, zorder=2))
ax.add_patch(FancyArrowPatch((62, 24.7), (70, 31), arrowstyle="-|>",
                             mutation_scale=14, color=ORANGE, lw=1.8, zorder=2))

# ── 컨트롤러 (아래 가운데) ──────────────────────────────────
card(30, 3, 40, 10, "#f2f6f5", TEAL, lw=2)
ax.text(50, 10.2, "컨트롤러 — 실측 기반 공동 결정", fontsize=11.5, weight="bold",
        ha="center", color=INK, zorder=4)
ax.text(50, 6.2, "① 한가한 길이 있으면 경로부터 옮긴다 (대가 없음)\n"
                 "② 그래도 늦으면 그 기기의 학습량(폭)만 줄인다", fontsize=9.5,
        ha="center", va="center", color=SUB, zorder=4)

# 측정 (서버 → 컨트롤러) / 지시 (컨트롤러 → 손잡이)
ax.add_patch(FancyArrowPatch((80, 27), (64, 12.6), arrowstyle="-|>", mutation_scale=11,
                             color=SUB, lw=1.2, zorder=2))
ax.text(77.5, 19, "측정\n(계산·전송 시간)", fontsize=8.5, color=SUB, ha="center")
ax.add_patch(FancyArrowPatch((41, 13), (35, 21.6), arrowstyle="-|>", mutation_scale=12,
                             color=ORANGE, lw=1.8, ls=(0, (4, 2)), zorder=2))
ax.text(41.5, 17.4, "지시 ① 경로", fontsize=8.5, color=ORANGE, ha="left", weight="bold")
ax.add_patch(FancyArrowPatch((33, 13), (25.2, 26.2), arrowstyle="-|>", mutation_scale=12,
                             connectionstyle="arc3,rad=-0.25",
                             color=ORANGE, lw=1.8, ls=(0, (4, 2)), zorder=2))
ax.text(29.2, 18.6, "지시 ②\n폭 (모자랄 때만)", fontsize=8.5, color=ORANGE,
        ha="center", weight="bold", zorder=6)

# ── 상단 제목·읽는 법 ───────────────────────────────────────
ax.text(50, 60.6, "접속 경로(어디로)와 학습량 폭(얼마나)의 공동 결정",
        fontsize=13.5, weight="bold", ha="center", color=INK)
ax.text(50, 57.2, "기기 3만 좁은 길로 옮기고(대가 없음), 그래도 늦는 만큼만 폭을 75%로"
                  " — 나머지 기기는 전혀 건드리지 않는다",
        fontsize=10, ha="center", color=SUB)

plt.tight_layout()
out = os.path.join(ROOT, "out", "fig", "final_07_두손잡이.png")
plt.savefig(out, dpi=170, bbox_inches="tight", facecolor="white")
print("saved", out)
