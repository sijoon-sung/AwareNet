# -*- coding: utf-8 -*-
"""분할 전송(출구 2개) 설명 그림 — out/fig/final_08_분할전송.png"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import os

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "out", "fig")
os.makedirs(OUT, exist_ok=True)

INK = "#1d2d3d"; SUB = "#5a6b7a"; ACC = "#0f766e"; WARN = "#b45309"; LINE = "#8aa0b0"
ACCBG = "#e2efed"; WARNBG = "#f6ecdd"


def box(ax, x, y, w, h, text, fc="#ffffff", ec=INK, fs=10, weight="normal", tc=None, lw=1.2):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.010",
                                fc=fc, ec=ec, lw=lw))
    if text:
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
                fontsize=fs, color=tc or INK, weight=weight, linespacing=1.5)


def arrow(ax, x1, y1, x2, y2, color=INK, lw=1.6, style="-|>"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style,
                                 mutation_scale=14, color=color, lw=lw))


fig, ax = plt.subplots(figsize=(11.5, 5.6))
ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

# 기기
box(ax, 0.02, 0.16, 0.30, 0.72, "", fc="#f4f6f8")
ax.text(0.17, 0.83, "기기 (출구가 2개)", ha="center", fontsize=12, weight="bold", color=INK)
ax.text(0.17, 0.745, "올릴 것: 모델 학습 결과 한 덩어리 → 고정 크기 조각으로", ha="center",
        fontsize=9, color=SUB)

# 조각들
n = 6
cw = 0.038; gap = 0.006; x0 = 0.17 - (n * cw + (n - 1) * gap) / 2
colors = [ACCBG, WARNBG, ACCBG, WARNBG, ACCBG, ACCBG]
for i in range(n):
    x = x0 + i * (cw + gap)
    box(ax, x, 0.56, cw, 0.11, str(i + 1), fc=colors[i], ec=LINE, fs=10, weight="bold")
box(ax, 0.045, 0.31, 0.115, 0.15, "출구 1\n유선 · 빠름", fc=ACCBG, ec=ACC, fs=9.5, weight="bold")
box(ax, 0.18, 0.31, 0.115, 0.15, "출구 2\n무선 · 느림", fc=WARNBG, ec=WARN, fs=9.5, weight="bold")
ax.text(0.17, 0.235, "먼저 한가해진 출구가 다음 조각을 가져간다\n→ 빠른 출구가 자연히 더 많이 맡음",
        ha="center", va="center", fontsize=8.3, color=SUB, linespacing=1.35)
for x in (0.10, 0.24):
    arrow(ax, x, 0.555, x, 0.47, color=LINE, lw=1.2)

# 두 경로
arrow(ax, 0.10, 0.47, 0.60, 0.62, color=ACC, lw=3.0)
arrow(ax, 0.30, 0.38, 0.60, 0.40, color=WARN, lw=2.0)
ax.text(0.39, 0.585, "조각 1·3·5·6", ha="center", fontsize=9.5, color=ACC, weight="bold",
        rotation=17)
ax.text(0.47, 0.355, "조각 2·4", ha="center", fontsize=9.5, color=WARN, weight="bold", rotation=3)

# 병목 표시 (출구 2 뒤)
box(ax, 0.40, 0.395, 0.07, 0.07, "병목", fc="#fde8e8", ec="#c0392b", fs=8.5, tc="#c0392b")
ax.text(0.435, 0.29, "병목이 갈림길 뒤에 있어야 우회가 된다", ha="center", fontsize=8.5,
        color="#c0392b")

# 서버
box(ax, 0.62, 0.16, 0.36, 0.72, "", fc="#f4f6f8")
ax.text(0.80, 0.83, "서버", ha="center", fontsize=12, weight="bold", color=INK)
box(ax, 0.645, 0.52, 0.31, 0.22,
    "재조립\n조각을 위치대로 끼워 넣어 원래 덩어리로\n(순서가 뒤바뀌어 와도 됨)", fc="#ffffff", fs=9.5)
box(ax, 0.645, 0.28, 0.31, 0.18,
    "완성 후는 단일 전송과 동일하게 처리\n(취합·다음 라운드)", fc=ACCBG, fs=9.5, weight="bold")
arrow(ax, 0.80, 0.51, 0.80, 0.47, color=LINE, lw=1.4)

# 하단 조건
ax.text(0.5, 0.06,
        "조각 = 보낼 바이트를 자른 것 (모델을 자르는 것이 아님)  ·  출구가 2개 이상이고 조각으로 나눌 만큼 클 때만  ·  "
        "출구가 하나면 단일 전송  ·  한 출구가 끊기면 그 조각만 남은 출구로 다시 보냄",
        ha="center", fontsize=9, color=INK,
        bbox=dict(boxstyle="round,pad=0.5", fc="#ffffff", ec=LINE, lw=1.0))
ax.text(0.5, 0.955, "분할 전송 — 한 기기가 두 출구로 나눠 보내고, 서버가 다시 합친다",
        ha="center", fontsize=13, weight="bold", color=INK)

fig.savefig(os.path.join(OUT, "final_08_분할전송.png"), dpi=170, bbox_inches="tight",
            facecolor="white")
print("saved final_08_분할전송.png")
