# -*- coding: utf-8 -*-
"""멘토링 자료용 설명 그림 — out/fig/mt_01~11.png (모두 개념도, 실측 수치 아님)"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle
import os

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["mathtext.fontset"] = "dejavusans"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "out", "fig")
os.makedirs(OUT, exist_ok=True)

INK = "#1d2d3d"; SUB = "#5a6b7a"; ACC = "#0f766e"; WARN = "#b45309"; LINE = "#8aa0b0"
ACCBG = "#e2efed"; WARNBG = "#f6ecdd"; RED = "#c0392b"; REDBG = "#fde8e8"; GRAYBG = "#f4f6f8"


def box(ax, x, y, w, h, text, fc="#ffffff", ec=INK, fs=10, weight="normal", tc=None, lw=1.2, ls="-"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.010",
                                fc=fc, ec=ec, lw=lw, linestyle=ls))
    if text:
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
                fontsize=fs, color=tc or INK, weight=weight, linespacing=1.45)


def arrow(ax, x1, y1, x2, y2, color=INK, lw=1.6, style="-|>", ls="-"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style,
                                 mutation_scale=14, color=color, lw=lw, linestyle=ls))


def blank(figsize):
    fig, ax = plt.subplots(figsize=figsize)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    return fig, ax


def save(fig, name):
    fig.savefig(os.path.join(OUT, name), dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("saved", name)


# ── mt_01 여정 ────────────────────────────────────────────────
fig, ax = blank((11.5, 3.6))
ax.set_xlim(-0.01, 1.01)
steps = [
    ("① 네트워크를 조작", "배분층 — 회선을 더 준다", "한계점\n경합 없는 환경 · 자기상관\n검증 미결정", WARN, WARNBG),
    ("② 참여자를 고른다", "선별층 — 점수로 선발", "한계점\n정확도 수렴 → 결정만 증가", WARN, WARNBG),
    ("③ 학습량을 조절", "Ordered Dropout + 분할학습", "채택\n느린 기기를 빼지 않고 단축", ACC, ACCBG),
    ("④ 경로를 더한다", "접속 지점 변경 · 분할 전송", "채택\n병목 우회, 학습은 그대로", ACC, ACCBG),
    ("⑤ 하나의 결정으로", "학습량 × 경로 공동 결정", "진행 중\n연계가 약함 (오늘의 질문)", INK, GRAYBG),
]
n = len(steps); w = 0.172; gap = (1 - n * w) / (n - 1)
for i, (t, d, r, c, bg) in enumerate(steps):
    x = i * (w + gap)
    box(ax, x, 0.42, w, 0.42, f"{t}\n{d}", fc=bg, ec=c, fs=9.2, weight="bold")
    ax.text(x + w / 2, 0.31, r, ha="center", va="top", fontsize=8.4, color=c, linespacing=1.4)
    if i < n - 1:
        arrow(ax, x + w + 0.005, 0.63, x + w + gap - 0.005, 0.63, color=LINE, lw=1.8)
ax.text(0.5, 0.96, "여기까지 온 과정 — 시도한 것과 부딪힌 한계점", ha="center", va="top",
        fontsize=13, weight="bold", color=INK)
save(fig, "mt_01_여정.png")

# ── mt_02 배분층 한계 3면 ──────────────────────────────────────
fig, axs = plt.subplots(1, 3, figsize=(11.5, 3.9))
for a in axs:
    a.set_xlim(0, 1); a.set_ylim(0, 1); a.axis("off")
# P1 적용 범위
a = axs[0]
a.text(0.5, 0.97, "① 조건 — 경합이 없는 환경", ha="center", va="top", fontsize=10.5,
       weight="bold", color=INK)
box(a, 0.68, 0.30, 0.28, 0.36, "서버\n(KOREN 사설망)", fc=GRAYBG, fs=9.5)
for i, lab in enumerate(["기기 A", "기기 B", "기기 C"]):
    y = 0.70 - i * 0.24
    box(a, 0.04, y - 0.08, 0.24, 0.16, lab, fc=ACCBG, ec=ACC, fs=9)
    arrow(a, 0.29, y, 0.67, 0.48, color=LINE, lw=1.4)
    a.text(0.44, y + 0.05 if i != 1 else y + 0.04, "자기 회선", fontsize=7.5, color=SUB, ha="center")
a.text(0.47, 0.90, "다른 트래픽: 거의 없음", ha="center", fontsize=8, color=SUB, style="italic")
a.text(0.5, 0.08, "각자 회선 · 배경 트래픽 없음\n→ 배분이 다툴 상대가 없다", ha="center", va="center",
       fontsize=9, color=WARN, weight="bold", linespacing=1.4)
# P2 자기상관
a = axs[1]
a.text(0.5, 0.97, "② 자기상관 — 가치가 다음 라운드에도 유지되나", ha="center", va="top",
       fontsize=10.5, weight="bold", color=INK)
rng = np.random.default_rng(3)
xs = np.arange(1, 13)
va = 0.55 + 0.18 * np.sin(xs * 1.7) + rng.normal(0, 0.05, 12)
vb = 0.55 + 0.18 * np.sin(xs * 1.7 + 2.6) + rng.normal(0, 0.05, 12)
ax2 = a.inset_axes([0.12, 0.28, 0.82, 0.55])
ax2.plot(xs, va, "-o", color=ACC, ms=3.5, lw=1.5, label="기기 A")
ax2.plot(xs, vb, "-s", color=WARN, ms=3.5, lw=1.5, label="기기 B")
ax2.set_xlabel("라운드", fontsize=8); ax2.set_ylabel("학습 가치", fontsize=8)
ax2.tick_params(labelsize=7); ax2.legend(fontsize=7, loc="upper right", frameon=False)
for sp in ("top", "right"):
    ax2.spines[sp].set_visible(False)
a.text(0.5, 0.08, "가치의 순위가 라운드마다 뒤바뀌면\n이번 라운드 기준의 배분은 다음 라운드에 틀린다",
       ha="center", va="center", fontsize=9, color=WARN, weight="bold", linespacing=1.4)
# P3 TCP 중복
a = axs[2]
a.text(0.5, 0.97, "③ 이득이 나는 구간 — 경합이 있을 때만 (개념도)", ha="center", va="top", fontsize=10.5,
       weight="bold", color=INK)
ax3 = a.inset_axes([0.14, 0.28, 0.82, 0.55])
xx = np.linspace(0, 10, 300)
gain = np.array([0.0 if x < 3 else (1 - np.exp(-(x - 3) * 1.1)) if x < 7.5 else
                 max(0.0, (1 - np.exp(-4.5 * 1.1)) - (x - 7.5) * 0.45) for x in xx])
ax3.plot(xx, gain, color=ACC, lw=2.2)
ax3.axvspan(0, 3, color=GRAYBG); ax3.axvspan(3, 7.5, color=ACCBG, alpha=0.6); ax3.axvspan(7.5, 10, color=REDBG)
ax3.text(1.5, 0.82, "한산\n동률", ha="center", fontsize=8, color=SUB)
ax3.text(5.25, 0.82, "경합 띠\n배분 이득", ha="center", fontsize=8, color=ACC, weight="bold")
ax3.text(8.75, 0.82, "극단\n붕괴", ha="center", fontsize=8, color=RED)
ax3.annotate("KOREN 실증 환경\n(배경 트래픽 없음)", xy=(0.5, 0.02), xytext=(2.2, 0.42), fontsize=8,
             color=WARN, weight="bold", ha="center",
             arrowprops=dict(arrowstyle="-|>", color=WARN, lw=1.2))
ax3.set_xlim(0, 10); ax3.set_ylim(-0.05, 1.05)
ax3.set_xlabel("경합 수준 (배경 트래픽 · 동시 전송)", fontsize=8); ax3.set_ylabel("배분층 이득", fontsize=8)
ax3.set_xticks([]); ax3.set_yticks([])
for sp in ("top", "right"):
    ax3.spines[sp].set_visible(False)
a.text(0.5, 0.08, "경합이 없으면 동률이라고 처음부터 예상했고,\n실증 환경에서는 경합 조건 자체를 만들 수 없었다",
       ha="center", va="center", fontsize=9, color=WARN, weight="bold", linespacing=1.4)
fig.tight_layout()
save(fig, "mt_02_배분층한계.png")

# ── mt_03 선별층 한계 ─────────────────────────────────────────
fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.3, 4.0), gridspec_kw={"width_ratios": [1.25, 1]})
r = np.arange(1, 31)
rng = np.random.default_rng(1)
for k, (c, off) in enumerate([(ACC, 0.0), (WARN, -0.08), (LINE, -0.16), (INK, -0.24)]):
    acc = 0.85 * (1 - np.exp(-r / (6 + k * 2))) + off * np.exp(-r / 8) + rng.normal(0, 0.008, 30)
    a1.plot(r, acc, color=c, lw=1.6, label=f"기기 {k + 1}")
a1.axvspan(1, 8, color=ACCBG, alpha=0.7); a1.axvspan(20, 30, color=WARNBG, alpha=0.8)
a1.text(4.5, 0.93, "초반: 점수 차이 큼\n→ 선별이 의미 있음", ha="center", fontsize=8.5, color=ACC, va="top")
a1.text(25, 0.93, "후반: 정확도 수렴\n→ 점수 차이가 사라짐", ha="center", fontsize=8.5, color=WARN, va="top")
a1.set_xlabel("라운드", fontsize=9); a1.set_ylabel("기기별 정확도 (개념도)", fontsize=9)
a1.set_ylim(0, 1.0); a1.tick_params(labelsize=8); a1.legend(fontsize=7.5, loc="lower right", frameon=False)
for sp in ("top", "right"):
    a1.spines[sp].set_visible(False)
dec = np.clip(1 + (r / 5) ** 1.3 + rng.normal(0, 0.4, 30), 0, None)
a2.bar(r, dec, color=[ACC if x < 12 else WARN for x in r], width=0.8)
a2.set_xlabel("라운드", fontsize=9); a2.set_ylabel("참여자 교체 결정 수 (개념도)", fontsize=9)
a2.tick_params(labelsize=8)
a2.text(20, dec.max() * 0.95, "좁은 차이로\n바꾸는 결정만 증가", ha="center", fontsize=8.5, color=WARN, va="top")
for sp in ("top", "right"):
    a2.spines[sp].set_visible(False)
fig.suptitle("선별층의 한계점 — 정확도가 수렴할수록 결정은 늘고 효과는 사라진다", fontsize=11,
             weight="bold", color=INK)
fig.tight_layout()
save(fig, "mt_03_선별층한계.png")

# ── mt_04 조건 민감도 (개념도) ───────────────────────────────
fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.3, 4.0))
bw = np.linspace(0.25, 3.0, 300)                 # 게이트웨이 대역폭 ÷ 필요 대역폭
base = 1 + 1.6 / bw; ours = 1 + 0.9 / bw
a1.plot(bw, base, color=WARN, lw=2.2, label="아무 조절 없음")
a1.plot(bw, ours, color=ACC, lw=2.2, label="본 방식")
a1.axvspan(0.25, 0.8, color=WARNBG); a1.axvspan(2.2, 3.0, color=GRAYBG)
a1.text(0.52, 5.4, "좁게 두면\n차이가 커짐", ha="center", fontsize=8.5, color=WARN)
a1.text(2.6, 5.4, "넉넉하면\n차이 없음", ha="center", fontsize=8.5, color=SUB)
a1.set_xlabel("게이트웨이 대역폭 (기기 수 × 모델 크기 대비)", fontsize=8.5)
a1.set_ylabel("라운드 시간 (상대)", fontsize=8.5); a1.set_ylim(0, 7.5)
a1.set_xticks([]); a1.set_yticks([]); a1.legend(fontsize=8, frameon=False, loc="upper right")
a1.set_title("조건 값 하나가 결과를 정한다", fontsize=10, weight="bold", color=INK)
gain = (base - ours) / base
a2.plot(bw, gain, color=ACC, lw=2.2)
a2.axvspan(0.6, 2.0, color=ACCBG, alpha=0.7)
a2.text(1.3, gain.max() * 0.55, "실측·공개 데이터로\n고정한 범위", ha="center", fontsize=8.5, color=ACC, weight="bold")
a2.annotate("효과가 줄어드는 쪽", xy=(2.6, gain[np.argmin(abs(bw - 2.6))]), xytext=(2.0, gain.max() * 0.92),
            fontsize=8, color=SUB, arrowprops=dict(arrowstyle="-|>", color=LINE))
a2.set_xlabel("조건 (범위로 훑는다)", fontsize=8.5); a2.set_ylabel("개선 폭", fontsize=8.5)
a2.set_xticks([]); a2.set_yticks([]); a2.set_ylim(0, gain.max() * 1.15)
a2.set_title("제안 — 한 점이 아니라 범위로 보인다", fontsize=10, weight="bold", color=INK)
for a in (a1, a2):
    for sp in ("top", "right"):
        a.spines[sp].set_visible(False)
fig.tight_layout()
save(fig, "mt_04_조건민감.png")

# ── mt_05 정식화 ──────────────────────────────────────────────
fig, ax = blank((8.3, 4.0))
ax.text(0.5, 0.96, "하나의 목적식 — 목표 정확도까지 걸리는 총 시간", ha="center", va="top", fontsize=11,
        weight="bold", color=INK)
ax.text(0.5, 0.76,
        r"$T(w,a)\;=\;R(w)\;\times\;\max_i\left[\,C_i\,w_i^{\gamma}\;+\;\dfrac{w_i\,B_i}{\varphi_i(a)}\,\right]\;+\;\sum \delta$",
        ha="center", va="center", fontsize=15, color=INK)
labels = [(0.215, 0.56, "라운드 수\n(학습량의 함수)", ACC), (0.435, 0.56, "연산 시간\n(학습량)", ACC),
          (0.575, 0.56, "전송 시간\n(학습량 × 바이트)", ACC),
          (0.70, 0.455, "실효 대역 — 접속 지점과 다른 기기의 학습량에 따라 변함", WARN),
          (0.90, 0.56, "옮기는 비용", WARN)]
for x, y, t, c in labels:
    ax.text(x, y, t, ha="center", va="top", fontsize=8.2, color=c, linespacing=1.35)
    tx = 0.66 if x == 0.70 else x
    arrow(ax, tx, y + 0.02, tx, 0.66, color=c, lw=1.0, style="-")
box(ax, 0.03, 0.03, 0.45, 0.30,
    "학습량 w 는 세 곳(라운드 수·연산·전송)에 들어가고,\n접속 지점 a 의 실효 대역은 경로를 같이 쓰는\n다른 기기의 w 에 따라 변한다\n→ 분리해서 풀 수 없다",
    fc=WARNBG, ec=WARN, fs=8.4)
box(ax, 0.52, 0.03, 0.45, 0.30,
    "해법: 교대 최적화 (표준 방법)\nw 고정 → a 최적화 → a 고정 → w 최적화 → 반복\n옮기는 조건 '절감 × 남은 라운드 > 비용'이\n수식에서 나온다",
    fc=ACCBG, ec=ACC, fs=8.4)
save(fig, "mt_05_정식화.png")

# ── mt_06 접속 지점 ───────────────────────────────────────────
fig, ax = blank((8.3, 4.0))
ax.text(0.5, 0.96, "접속 지점 변경 — 이득과 비용", ha="center", va="top", fontsize=11, weight="bold", color=INK)
box(ax, 0.06, 0.50, 0.26, 0.24, "집계 서버 A\n(붐빔)", fc=WARNBG, ec=WARN, fs=10, weight="bold")
box(ax, 0.68, 0.50, 0.26, 0.24, "집계 서버 B\n(한가)", fc=ACCBG, ec=ACC, fs=10, weight="bold")
arrow(ax, 0.33, 0.62, 0.67, 0.62, color=RED, lw=3.0, style="<|-|>")
ax.text(0.5, 0.80, "서버 간 동기화 — 라운드마다 모델 뒷부분을 맞춤", ha="center", fontsize=8.8, color=RED, weight="bold")
ax.text(0.5, 0.53, "비용: 라운드 시간의 상당 부분", ha="center", fontsize=8.5, color=RED)
for i, x in enumerate([0.09, 0.19, 0.29]):
    box(ax, x - 0.04, 0.20, 0.08, 0.12, "기기", fc=GRAYBG, ec=LINE, fs=7.5)
    arrow(ax, x, 0.33, min(x + 0.02, 0.30), 0.49, color=LINE, lw=1.0)
box(ax, 0.77, 0.20, 0.08, 0.12, "기기", fc=ACCBG, ec=ACC, fs=7.5)
arrow(ax, 0.34, 0.26, 0.76, 0.26, color=ACC, lw=2.2, ls="--")
ax.text(0.55, 0.40, "한 기기를 B 로 옮김 → 옮긴 기기의 대기 시간이 줄어든다 (이득)", ha="center",
        fontsize=8.5, color=ACC, weight="bold")
arrow(ax, 0.81, 0.33, 0.81, 0.49, color=ACC, lw=1.2)
box(ax, 0.04, 0.02, 0.92, 0.12,
    "실효 이득 = (옮겨서 번 시간) - (동기화 비용)   →   이것이 양수인 배치에서만 의미가 있다",
    fc="#ffffff", ec=INK, fs=8.8, weight="bold")
save(fig, "mt_06_접속지점.png")

# ── mt_07 규모 ────────────────────────────────────────────────
fig, ax = blank((8.3, 4.0))
ax.text(0.5, 0.96, "실증 규모 시안 — 실학습 16대 + 결정 루프 100대", ha="center", va="top", fontsize=11,
        weight="bold", color=INK)
box(ax, 0.02, 0.42, 0.23, 0.40, "", fc=GRAYBG, ec=LINE)
ax.text(0.135, 0.78, "PC (연구실) — 8대", ha="center", fontsize=8.5, weight="bold", color=INK)
box(ax, 0.32, 0.42, 0.23, 0.40, "", fc=GRAYBG, ec=LINE)
ax.text(0.435, 0.78, "V100 서버 (HPC) — 8대", ha="center", fontsize=8.5, weight="bold", color=INK)
for bx in (0.02, 0.32):
    for k in range(8):
        cx = bx + 0.04 + (k % 4) * 0.05; cy = 0.66 - (k // 4) * 0.13
        ax.add_patch(Circle((cx, cy), 0.017, fc=ACC, ec="none"))
arrow(ax, 0.255, 0.60, 0.315, 0.60, color=WARN, lw=2.0, style="<|-|>")
ax.text(0.285, 0.52, "실제 망", ha="center", fontsize=7.5, color=WARN)
ax.text(0.285, 0.36, "실학습 16대 — 두 호스트 사이는 실제 망", ha="center", fontsize=8.8, color=ACC, weight="bold")
box(ax, 0.60, 0.42, 0.37, 0.40, "", fc=GRAYBG, ec=LINE)
ax.text(0.785, 0.78, "결정 루프 — 100대 (모의 기기)", ha="center", fontsize=8.5, weight="bold", color=INK)
for k in range(100):
    cx = 0.625 + (k % 20) * 0.0165; cy = 0.70 - (k // 20) * 0.055
    ax.add_patch(Circle((cx, cy), 0.006, fc=LINE, ec="none"))
ax.text(0.785, 0.36, "교대 최적화 근사 — 소규모에서 최적 대비 오차 검증", ha="center", fontsize=8.8,
        color=ACC, weight="bold")
ax.text(0.5, 0.26, "기기 성능 편차 — 실제 기기 3계층을 기준점으로, 사이는 공개 분포(FedScale)로 보간",
        ha="center", fontsize=9, color=INK, weight="bold")
for i, (t, c) in enumerate([("서버 GPU", ACC), ("PC", ACC), ("젯슨", ACC)]):
    x = 0.16 + i * 0.32
    box(ax, x, 0.05, 0.16, 0.13, t, fc=ACCBG, ec=c, fs=9, weight="bold")
    if i < 2:
        ax.plot([x + 0.17, x + 0.31], [0.115, 0.115], color=LINE, lw=1.2, ls="--")
        ax.text(x + 0.24, 0.13, "보간", ha="center", fontsize=7.5, color=SUB)
save(fig, "mt_07_규모.png")

# ── mt_08 정밀 모델링 ─────────────────────────────────────────
fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.3, 4.0))
x = np.linspace(0, 10, 200)
a1.step([0, 5, 10], [0, 0, 1], where="post", color=WARN, lw=2.2)
a1.axvline(5, color=LINE, ls="--", lw=1)
a1.set_title("지금 — 켠다 / 끈다", fontsize=10, weight="bold", color=INK)
a1.set_xlabel("조건 (예: 출구 속도 차이)", fontsize=8.5); a1.set_ylabel("적용 여부", fontsize=8.5)
a1.set_yticks([0, 1]); a1.set_yticklabels(["끔", "켬"]); a1.tick_params(labelsize=8)
a1.text(5.2, 0.5, "문턱 하나로 결정\n— 문턱 근처에서 흔들림", fontsize=8.5, color=WARN)
gain = 1 / (1 + np.exp(-(x - 4))) * 1.2 - 0.15
a2.plot(x, gain, color=ACC, lw=2.2, label="이득의 기대값")
a2.fill_between(x, gain - 0.18, gain + 0.18, color=ACCBG, label="불확실성 (분포로 다루면)")
a2.axhline(0, color=LINE, lw=1)
a2.set_title("제안 — 이득을 조건의 함수로 계산", fontsize=10, weight="bold", color=INK)
a2.set_xlabel("조건", fontsize=8.5); a2.set_ylabel("이득 (시간 단축)", fontsize=8.5); a2.tick_params(labelsize=8)
a2.legend(fontsize=7.5, loc="upper left", frameon=False)
a2.text(6.2, 0.15, "항상 이득이 최대인 쪽을 고름\n— 켜고 끄는 문턱이 사라짐", fontsize=8.5, color=ACC)
for a in (a1, a2):
    for sp in ("top", "right"):
        a.spines[sp].set_visible(False)
fig.tight_layout()
save(fig, "mt_08_정밀모델링.png")

# ── mt_09 범위 ────────────────────────────────────────────────
fig, ax = blank((5.2, 4.0))
box(ax, 0.04, 0.06, 0.92, 0.88, "", fc=GRAYBG, ec=LINE)
ax.text(0.5, 0.88, "일반 트래픽 — 타이밍·경로만 조절 가능 (기존 기술: QoS·슬라이싱)", ha="center",
        fontsize=8.5, color=SUB, weight="bold")
box(ax, 0.12, 0.14, 0.76, 0.62, "", fc=ACCBG, ec=ACC)
ax.text(0.5, 0.64, "양을 줄여도 품질이 조금씩만 떨어지는 트래픽\n(영상 화질 자동 조절 · 학습 트래픽) — 확장 여지",
        ha="center", fontsize=8.8, color=ACC, weight="bold", linespacing=1.4)
box(ax, 0.24, 0.19, 0.52, 0.32, "연합학습\n(본 과제 — 증거가 있는 범위)", fc="#ffffff", ec=INK, fs=9.5,
    weight="bold")
save(fig, "mt_09_범위.png")

# ── mt_10 남은 문제 ───────────────────────────────────────────
fig, ax = blank((7.2, 3.3))
box(ax, 0.03, 0.34, 0.26, 0.40, "기기\n연산 빠름 · 회선 느림\n(또는 병목 구간 뒤)", fc=GRAYBG, ec=INK, fs=9.5,
    weight="bold")
arrow(ax, 0.30, 0.64, 0.42, 0.78, color=WARN, lw=1.8)
arrow(ax, 0.30, 0.44, 0.42, 0.30, color=ACC, lw=1.8)
box(ax, 0.43, 0.60, 0.54, 0.34,
    "A. 학습량 축소\n전송량은 줄지만, 멀쩡한 연산 능력을 놀리고\n정확도 대가를 치른다",
    fc=WARNBG, ec=WARN, fs=9)
box(ax, 0.43, 0.12, 0.54, 0.34,
    "B. 경로 (접속 지점 변경 · 출구 2개 분할 전송)\n병목을 우회한다\n학습은 그대로, 정확도 대가 없음",
    fc=ACCBG, ec=ACC, fs=9)
ax.text(0.5, 0.02, "네트워크가 원인인 느림에는 네트워크 쪽 수단이 맞다 — 단, 망을 조작하지 않고 양 끝에서만",
        ha="center", fontsize=8.8, color=INK, weight="bold")
save(fig, "mt_10_남은문제.png")

# ── mt_11 검증 단계 ───────────────────────────────────────────
fig, ax = blank((11.5, 1.9))
stages = [("1  시뮬레이션", "난수 시나리오로 결정 규칙 점검", "완료", ACC, ACCBG),
          ("2  회선 에뮬레이션", "실제 소켓 + 회선 속도 제한 (tc)", "완료", ACC, ACCBG),
          ("3  실기기", "PC · V100 서버 · 젯슨", "예정", WARN, WARNBG),
          ("4  실WAN", "KOREN 다지점", "예정", WARN, WARNBG)]
n = len(stages); w = 0.22; gap = (1 - n * w) / (n - 1)
for i, (t, d, st, c, bg) in enumerate(stages):
    x = i * (w + gap)
    box(ax, x, 0.18, w, 0.64, f"{t}\n{d}", fc=bg, ec=c, fs=9.5, weight="bold")
    ax.text(x + w - 0.01, 0.86, st, ha="right", va="bottom", fontsize=9, color=c, weight="bold")
    if i < n - 1:
        arrow(ax, x + w + 0.005, 0.5, x + w + gap - 0.005, 0.5, color=LINE, lw=1.8)
save(fig, "mt_11_검증단계.png")
