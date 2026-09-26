# -*- coding: utf-8 -*-
"""최종보고서용 아키텍처 그림 3장 — out/fig/final_01~03.png"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle
import os

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "out", "fig")
os.makedirs(OUT, exist_ok=True)

INK = "#1d2d3d"; SUB = "#5a6b7a"; ACC = "#0f766e"; WARN = "#b45309"; LINE = "#8aa0b0"


def box(ax, x, y, w, h, text, fc="#ffffff", ec=INK, fs=10, weight="normal", tc=None):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.012",
                                fc=fc, ec=ec, lw=1.2))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fs, color=tc or INK, weight=weight, linespacing=1.5)


def arrow(ax, x1, y1, x2, y2, text="", color=INK, lw=1.6, ts=8.5, dy=0.012, style="-|>"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style,
                                 mutation_scale=14, color=color, lw=lw))
    if text:
        ax.text((x1 + x2) / 2, max(y1, y2) + dy, text, ha="center",
                fontsize=ts, color=color)


# ── 그림 1: 전체 시스템 구조 ─────────────────────────────────────
fig, ax = plt.subplots(figsize=(11.5, 6.2))
ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

devs = [("기기 1 — 빠름 (회선 80Mbps)", "모델 앞부분: 폭 100%", "#e2efed"),
        ("기기 2 — 보통 (회선 40Mbps)", "모델 앞부분: 폭 100%", "#e2efed"),
        ("기기 3 — 느림 (회선 20Mbps)", "모델 앞부분: 폭 25%\n(컨트롤러가 줄여 줌)", "#f6ecdd")]
for i, (t1, t2, fc) in enumerate(devs):
    y = 0.68 - i * 0.27
    box(ax, 0.02, y, 0.27, 0.21,
        f"{t1}\n───────────\n데이터 (밖으로 안 나감)\n{t2}", fc=fc, fs=9.5)

box(ax, 0.62, 0.10, 0.36, 0.80, "", fc="#f4f6f8")
ax.text(0.80, 0.855, "서버 (KOREN)", ha="center", fontsize=12, weight="bold", color=INK)
box(ax, 0.645, 0.62, 0.31, 0.17,
    "① 모델 뒷부분 계산 + 취합\n(모든 기기의 학습 결과를 평균)", fs=9.5)
box(ax, 0.645, 0.40, 0.31, 0.17,
    "② 측정 수집\n기기별 계산 시간·전송 시간·바이트\n(학습 트래픽 그대로 — 별도 측정 없음)", fs=9)
box(ax, 0.645, 0.13, 0.31, 0.22,
    "③ 컨트롤러\n예측 → 기준선(중앙값×1.2) 비교\n→ 늦을 기기만 폭 한 단계 축소\n(최소 폭 25% — 아무도 배제 안 함)",
    fc="#e2efed", fs=9, weight="bold")

for i in range(3):
    y = 0.785 - i * 0.27
    arrow(ax, 0.30, y, 0.61, y, "중간 결과 올림 / 기울기 받음", color=LINE, ts=8)
arrow(ax, 0.645, 0.145, 0.31, 0.145, "", color=ACC, lw=2.2)
ax.text(0.47, 0.085, "다음 라운드의 폭 지시 (체크인 응답에 동봉)", ha="center",
        fontsize=9.5, color=ACC, weight="bold")
ax.text(0.455, 0.955, "각 기기는 자기 회선을 따로 쓴다 (공용 회선 없음)",
        ha="center", fontsize=10, color=SUB, style="italic")
plt.tight_layout()
plt.savefig(os.path.join(OUT, "final_01_아키텍처.png"), dpi=170, bbox_inches="tight")
plt.close()

# ── 그림 2: 분할 지점과 폭 ───────────────────────────────────────
fig, ax = plt.subplots(figsize=(10.5, 5.2))
ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

n, x0, w, gap, y0, h = 6, 0.06, 0.115, 0.028, 0.18, 0.56
for i in range(n):
    x = x0 + i * (w + gap)
    ax.add_patch(Rectangle((x, y0), w, h, fc="#eef1f4", ec=INK, lw=1.1))
    ax.add_patch(Rectangle((x, y0 + h * 0.75), w, h * 0.25, fc="#5dcaa5",
                           ec=INK, lw=1.1))
    ax.text(x + w / 2, y0 - 0.055, f"{i+1}층", ha="center", fontsize=9.5, color=SUB)
cut_x = x0 + 2 * (w + gap) - gap / 2
ax.plot([cut_x, cut_x], [y0 - 0.09, y0 + h + 0.12], ls="--", color=WARN, lw=2)
ax.text(cut_x, y0 + h + 0.155, "절단 계층 (cut layer)", ha="center",
        fontsize=10.5, color=WARN, weight="bold")
ax.text(x0 + (2 * w + gap) / 2, y0 + h + 0.06, "← 기기가 계산", ha="center",
        fontsize=10, color=INK)
ax.text(cut_x + 0.24, y0 + h + 0.06, "서버가 계산 →", ha="center",
        fontsize=10, color=INK)
ax.add_patch(Rectangle((0.06, 0.035), 0.03, 0.03, fc="#5dcaa5", ec=INK, lw=1))
ax.text(0.10, 0.05, "폭 25%가 쓰는 부분 — 모든 층의 앞쪽 25%. 느린 기기의 데이터도"
        " 이 부분을 통해 매 라운드 전체 모델에 반영된다", fontsize=9.5, va="center", color=INK)
ax.text(0.5, 0.93, "폭을 줄인다 = 각 층에서 쓰는 뉴런의 비율을 줄인다"
        " (앞쪽부터 — Ordered Dropout)", ha="center", fontsize=11, color=INK, weight="bold")
plt.tight_layout()
plt.savefig(os.path.join(OUT, "final_02_분할과폭.png"), dpi=170, bbox_inches="tight")
plt.close()

# ── 그림 3: 컨트롤러 결정 순서 ───────────────────────────────────
fig, ax = plt.subplots(figsize=(11.5, 3.6))
ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
steps = [("① 측정", "기기별 계산 시간과\n전송 시간을 매 라운드 기록\n(지수이동평균으로 안정화)"),
         ("② 예측", "각 기기가 전체 폭으로\n돌 때의 완료 시간 추정"),
         ("③ 기준선", "중앙값 × 1.2\n\"보통 기기의 1.2배까지 기다림\""),
         ("④ 조치", "기준선을 넘을 기기만\n폭을 한 단계 축소\n(최소 폭 25% 보장)")]
bw, bh, y = 0.21, 0.52, 0.30
for i, (t, d) in enumerate(steps):
    x = 0.025 + i * 0.25
    fc = "#e2efed" if i == 3 else "#ffffff"
    box(ax, x, y, bw, bh, f"{t}\n──────\n{d}", fc=fc, fs=9)
    if i < 3:
        arrow(ax, x + bw + 0.003, y + bh / 2, x + 0.247, y + bh / 2, color=INK)
ax.text(0.5, 0.10, "모두 비슷한 속도라면? — 아무도 기준선을 넘지 않으므로 개입 0회"
        " (균질 실험으로 검증)", ha="center", fontsize=10, color=ACC, weight="bold")
ax.text(0.5, 0.94, "컨트롤러의 결정 순서 — 고정된 문턱값 없이, 매 라운드 측정에서 유도",
        ha="center", fontsize=11.5, color=INK, weight="bold")
plt.tight_layout()
plt.savefig(os.path.join(OUT, "final_03_결정순서.png"), dpi=170, bbox_inches="tight")
plt.close()
print("3 figures saved to", OUT)
