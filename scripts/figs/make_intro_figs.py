# -*- coding: utf-8 -*-
"""서론용 그림 2장 — 문제 상황(final_04), 구현 기능 지도(final_05)"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import os

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "out", "fig")
INK = "#1d2d3d"; SUB = "#5a6b7a"; ACC = "#0f766e"; WARN = "#b45309"; RED = "#b91c1c"

# ── 그림 4: 문제 상황 — 라운드는 가장 느린 참여자를 기다린다 ──────
fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.2))
names = ["기기 1 (80Mbps)", "기기 2 (60Mbps)", "기기 3 (40Mbps)", "기기 4 (20Mbps)"]

ax = axes[0]
vals = [7.2, 9.0, 12.5, 25.3]
colors = ["#9fc7c0", "#9fc7c0", "#9fc7c0", "#e8a87c"]
ax.barh(names, vals, color=colors, edgecolor=INK, height=0.55)
ax.axvline(25.3, ls="--", color=RED, lw=2)
ax.text(24.6, -0.28, "라운드 종료 = 25.3초 (가장 느린 기기 기준)", ha="right",
        fontsize=9.5, color=RED, weight="bold")
ax.annotate("모두가 기기 4를 기다린다", xy=(18.0, 1.5), fontsize=10, color=SUB,
            style="italic", ha="center")
ax.set_title("지금 방식 — 전원이 같은 학습량", fontsize=11.5, weight="bold", pad=10)
ax.set_xlim(0, 29); ax.invert_yaxis(); ax.set_xlabel("한 라운드에 걸리는 시간 (초)")

ax = axes[1]
vals2 = [7.2, 9.0, 12.5, 13.8]
colors2 = ["#9fc7c0", "#9fc7c0", "#9fc7c0", "#5dcaa5"]
ax.barh(names, vals2, color=colors2, edgecolor=INK, height=0.55)
ax.axvline(15.3, ls="--", color=ACC, lw=2)
ax.text(15.9, -0.28, "라운드 종료 = 15.3초 (-40%, 예비 실험)", ha="left",
        fontsize=9.5, color=ACC, weight="bold")
ax.annotate("학습량만 줄임 — 버리지 않음\n(데이터는 계속 반영)",
            xy=(22.0, 3.0), fontsize=9.5, color=ACC, ha="center", va="center")
ax.set_title("본 과제 — 늦을 기기만 학습량 조절", fontsize=11.5, weight="bold", pad=10)
ax.set_xlim(0, 29); ax.invert_yaxis(); ax.set_xlabel("한 라운드에 걸리는 시간 (초)")

plt.tight_layout()
plt.savefig(os.path.join(OUT, "final_04_문제상황.png"), dpi=170, bbox_inches="tight")
plt.close()

# ── 그림 5: 구현 기능 지도 ────────────────────────────────────────
fig, ax = plt.subplots(figsize=(11.8, 6.6))
ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

cols = [
    ("① 잰다", "#e2efed", [
        ("계산·전송 시간 측정", "별도 장치 없이\n학습 트래픽 그대로", "실측 완료"),
        ("KOREN 실측", "왕복 지연·속도·\n몰림 혼잡까지", "실측 완료"),
    ]),
    ("② 정한다", "#eef1f4", [
        ("늦을 기기 예측", "기기별 완료 시간 추정", "실측 완료"),
        ("기준선", "보통 기기의 1.2배\n(고정 문턱값 없음)", "실측 완료"),
    ]),
    ("③ 조절한다", "#f6ecdd", [
        ("학습량(폭) 조절", "늦을 기기만 한 단계씩\n— 시간 -40%", "실측 완료"),
        ("접속 경로 선택", "폭과 함께 결정\n병목 심한 판 -21%", "실측 완료"),
    ]),
    ("④ 지킨다", "#e2efed", [
        ("최소 참여 보장", "아무도 배제하지 않음\n(최소 폭 25%)", "규칙 검증"),
        ("무개입 안전성", "모두 비슷하면 개입 0회", "실측 완료"),
    ]),
    ("⑤ 보여준다", "#eef1f4", [
        ("실시간 조작 시연", "회선을 조이면 화면에서\n반응·회복까지", "동작 확인"),
        ("언어모델 3자 비교", "기본/단독/연합 대화\n— 연합 67%", "사전 검증"),
    ]),
]

col_w, gap, x0 = 0.184, 0.017, 0.008
status_color = {"실측 완료": ACC, "모의 검증": WARN, "계획기 완성": WARN,
                "재검증 중": RED, "규칙 검증": ACC, "동작 확인": ACC, "사전 검증": WARN}
for ci, (head, hc, cards) in enumerate(cols):
    x = x0 + ci * (col_w + gap)
    ax.add_patch(FancyBboxPatch((x, 0.88), col_w, 0.075,
                                boxstyle="round,pad=0.008", fc=INK, ec=INK))
    ax.text(x + col_w / 2, 0.917, head, ha="center", va="center",
            fontsize=12, color="white", weight="bold")
    ch = 0.185
    for ri, (name, desc, st) in enumerate(cards):
        y = 0.85 - (ri + 1) * (ch + 0.018)
        ax.add_patch(FancyBboxPatch((x, y), col_w, ch,
                                    boxstyle="round,pad=0.008", fc=hc, ec=INK, lw=1))
        ax.text(x + col_w / 2, y + ch - 0.038, name, ha="center", fontsize=10,
                weight="bold", color=INK)
        ax.text(x + col_w / 2, y + ch / 2 - 0.018, desc, ha="center", va="center",
                fontsize=8.4, color=SUB, linespacing=1.5)
        sc = status_color[st]
        ax.text(x + col_w / 2, y + 0.026, f"● {st}", ha="center", fontsize=8,
                color=sc, weight="bold")
ax.set_ylim(-0.075, 1)
ax.text(0.5, -0.045, "● 실측 완료·검증됨     ● 모의 환경 검증·본 실험 대기     ● 재검증 중 (원인 규명 전까지 주장 보류)",
        ha="center", fontsize=9.5, color=SUB)
plt.tight_layout()
plt.savefig(os.path.join(OUT, "final_05_기능지도.png"), dpi=170, bbox_inches="tight")
plt.close()
print("2 intro figures saved")
