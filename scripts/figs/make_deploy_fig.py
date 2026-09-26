# -*- coding: utf-8 -*-
"""실험 배치도 — 어느 호스트에 무엇을 두고 어떻게 잇는가. out/fig/deploy_layout.png
   위: 호스트 3열(바깥 · KOREN · HPC) / 가운데: 연결 표(경로별 한 줄) / 아래: 한 라운드 흐름 + 코드 배치"""
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
ACCBG = "#e2efed"; WARNBG = "#f6ecdd"; RED = "#c0392b"; GRAYBG = "#f4f6f8"; BLUE = "#1d4ed8"; BLUEBG = "#e6edfb"


def box(ax, x, y, w, h, fc="#ffffff", ec=INK, lw=1.3, ls="-"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.006", fc=fc, ec=ec, lw=lw, linestyle=ls))


def txt(ax, x, y, s, fs=9, c=INK, ha="left", va="top", w="normal", ls_=1.45):
    ax.text(x, y, s, fontsize=fs, color=c, ha=ha, va=va, weight=w, linespacing=ls_)


def arrow(ax, x1, y1, x2, y2, c=INK, lw=1.8, ls="-", style="-|>"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=15, color=c, lw=lw, linestyle=ls))


fig, ax = plt.subplots(figsize=(14, 9.6))
ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
txt(ax, 0.5, 0.99, "실험 배치도 — 집계 서버 A 는 HPC, 클라이언트는 KOREN VM2, 접속 지점 B 는 VM1", fs=14, ha="center", w="bold")

# ═══ 위: 호스트 ═══════════════════════════════════════════════
TOP, H = 0.55, 0.40
# 바깥
box(ax, 0.02, TOP, 0.24, H, fc=GRAYBG, ec=LINE)
txt(ax, 0.14, TOP + H - 0.015, "바깥 — 실기기", fs=11, ha="center", w="bold")
box(ax, 0.03, TOP + 0.20, 0.22, 0.155, fc="#ffffff", ec=INK)
txt(ax, 0.038, TOP + 0.345, "연구실 PC   168.188.50.217", fs=9, w="bold")
txt(ax, 0.038, TOP + 0.318, "· 실험 지휘  vm_exp.sh · hpc_launch.sh\n· 실기기 클라이언트  fed_client.py\n· RNTier 런처 → HPC 포트 포워딩\n· 허용 IP 라 VM SSH 가능", fs=8.2, c=SUB, ls_=1.45)
box(ax, 0.03, TOP + 0.10, 0.22, 0.085, fc="#ffffff", ec=INK)
txt(ax, 0.038, TOP + 0.175, "집 PC   119.204.114.70", fs=9, w="bold")
txt(ax, 0.038, TOP + 0.148, "· VM 접속은 허용 IP 등록 대기 · HPC 는 런처로 접속", fs=7.8, c=SUB)
box(ax, 0.03, TOP + 0.015, 0.22, 0.07, fc="#ffffff", ec=INK)
txt(ax, 0.038, TOP + 0.075, "젯슨 (예정)", fs=9, w="bold")
txt(ax, 0.038, TOP + 0.048, "· 출구 2개(무선+유선) → 분할 전송 실증", fs=8.2, c=SUB)

# KOREN
box(ax, 0.29, TOP, 0.40, H, fc="#ffffff", ec=LINE)
txt(ax, 0.49, TOP + H - 0.015, "KOREN 연구망  (116.89.187.128/26, 같은 지점)", fs=11, ha="center", w="bold")
box(ax, 0.30, TOP + 0.12, 0.185, 0.235, fc=ACCBG, ec=ACC, lw=1.5)
txt(ax, 0.3925, TOP + 0.345, "VM1   116.89.187.190", fs=9.5, ha="center", w="bold")
txt(ax, 0.308, TOP + 0.318, "koren-vm · 8코어 · 31GB · GPU 없음", fs=7.8, c=SUB)
txt(ax, 0.308, TOP + 0.29, "집계 서버 B   fed_server.py :12020\n   (접속 지점 2곳 실험, CPU)\n역방향 터널 종단   :12000 → HPC\n회선 측정   iperf3 :5201 · ping\n~/awarenet · .venv(torch CPU)\ndata/cifar10 · out/vm_*.jsonl", fs=8, ls_=1.5)
box(ax, 0.495, TOP + 0.12, 0.185, 0.235, fc=BLUEBG, ec=BLUE, lw=1.5)
txt(ax, 0.5875, TOP + 0.345, "VM2   116.89.187.189", fs=9.5, ha="center", w="bold")
txt(ax, 0.503, TOP + 0.318, "koren-vm2 · 8코어 · 31GB · GPU 없음", fs=7.8, c=SUB)
txt(ax, 0.503, TOP + 0.29, "클라이언트 4~8대   fed_client.py\n   c0..c3 (CPU, 스레드 2)\n   → 서버 A(HPC) 또는 B(VM1)\n   회선 이질성은 tc 로 부여\n~/awarenet · .venv(torch CPU)\ndata/cifar10", fs=8, ls_=1.5)
arrow(ax, 0.487, TOP + 0.24, 0.493, TOP + 0.24, c=ACC, lw=2.4, style="<|-|>")
txt(ax, 0.49, TOP + 0.118, "VM1↔VM2 열림 · 1.7ms", fs=7.2, c=ACC, ha="center")
box(ax, 0.30, TOP + 0.012, 0.38, 0.095, fc=GRAYBG, ec=LINE, ls="--")
txt(ax, 0.308, TOP + 0.10, "VM 방화벽 (바깥에서 들어오는 길)", fs=8.8, w="bold")
txt(ax, 0.308, TOP + 0.075, "허용 IP  168.188.50.217 · 168.188.47.175 (연구실)   열린 포트  26022 만\n신청 중  119.204.114.70 (집) · 116.89.174.50 (HPC 출구)   포트 10000~15000 · 22", fs=8, c=SUB, ls_=1.5)

# HPC
box(ax, 0.72, TOP, 0.26, H, fc=WARNBG, ec=WARN, lw=1.5)
txt(ax, 0.85, TOP + H - 0.015, "HPC 이노베이션 허브 (V100)", fs=11, ha="center", w="bold")
txt(ax, 0.728, TOP + 0.355, "koren-hpc · 사설 10.246.246.33\n나가는 공인 출구 116.89.174.50 · 런처 켜진 동안만 접속", fs=7.8, c=SUB, ls_=1.4)
box(ax, 0.728, TOP + 0.175, 0.244, 0.135, fc="#ffffff", ec=WARN)
txt(ax, 0.735, TOP + 0.30, "집계 서버 A (메인)   fed_server.py :12001", fs=9, w="bold")
txt(ax, 0.735, TOP + 0.273, "· 모델 뒷부분 계산(GPU) + 컨트롤러\n  (학습량·접속 지점 결정 — 경제성 모델)\n· 분할 전송 재조립 (mpsend.Reassembler)\n· 언어모델 서버  run_l3_net.py", fs=8, ls_=1.45)
box(ax, 0.728, TOP + 0.085, 0.244, 0.08, fc="#ffffff", ec=WARN)
txt(ax, 0.735, TOP + 0.155, "GPU 단독 실험   run_rw.py (nohup)", fs=9, w="bold")
txt(ax, 0.735, TOP + 0.128, "· 학습량 4수준 × 시드 3 × 30라운드 → out/rw_*.jsonl", fs=8, ls_=1.45)
txt(ax, 0.728, TOP + 0.072, "~/awarenet · ~/env(torch 2.6 cu124)\ndata/cifar10 · data/lora", fs=7.8, c=SUB, ls_=1.35)
txt(ax, 0.728, TOP + 0.03, "들어오는 연결 불가(사설 IP) → 나가는 연결만 씀", fs=8, c=RED, w="bold")

# ═══ 가운데: 연결 표 ═══════════════════════════════════════
box(ax, 0.02, 0.27, 0.96, 0.26, fc="#ffffff", ec=LINE)
txt(ax, 0.03, 0.52, "연결 — 누가 어디로 붙는가", fs=10, w="bold")
txt(ax, 0.97, 0.52, "실선 = 지금 됨 · 점선 = 허용 IP 등록 뒤 · 빨강 = 안 됨", fs=8.5, c=SUB, ha="right")
AX = {"PC": 0.14, "VM1": 0.3925, "VM2": 0.5875, "HPC": 0.85}
for k, x in AX.items():
    txt(ax, x, 0.515, k, fs=8.5, c=SUB, ha="center", w="bold")
    ax.plot([x, x], [0.29, 0.495], color="#e3e8ec", lw=1, ls=":")
lanes = [
    (0.468, "PC", "VM1", INK, "-", "SSH 26022  — 배포·지휘 (연구실 IP 만)"),
    (0.44, "PC", "HPC", INK, "-", "런처 포트 포워딩  localhost:12001 ↔ HPC:12001  — PC 클라이언트 → 서버 A, 지금 가능"),
    (0.405, "VM2", "VM1", BLUE, "-", "VM2 클라이언트 → VM1 서버 B  :12020  — 지금 가능 (링크 실험 검증됨, 8라운드)"),
    (0.37, "HPC", "VM1", WARN, "--", "HPC → VM1:26022 역방향 SSH 터널 (ssh -R 12000)  — 116.89.174.50 등록 뒤"),
    (0.335, "VM2", "VM1", WARN, "--", "VM2 클라이언트 → VM1:12000 → (터널) → HPC 서버 A  — 위 터널이 서면 가능"),
    (0.30, "PC", "VM1", RED, "--", "집 PC(119.204.114.70) → VM  — 등록 전에는 막힘 · HPC 로 직접 들어가는 연결도 불가"),
]
for y, a, b, c, ls, label in lanes:
    x1, x2 = AX[a], AX[b]
    arrow(ax, x1, y, x2, y, c=c, lw=2.0 if ls == "-" else 1.8, ls=ls)
    txt(ax, min(x1, x2) + 0.012, y + 0.006, label, fs=7.8, c=c, va="bottom")

# ═══ 아래: 한 라운드 흐름 + 코드 배치 ═══════════════════════
box(ax, 0.02, 0.02, 0.96, 0.23, fc="#ffffff", ec=LINE)
txt(ax, 0.03, 0.24, "한 라운드의 흐름 (서버 A = HPC 기준)", fs=10, w="bold")
steps = ["① 클라이언트(VM2·PC·젯슨)\n모델 앞부분 계산", "② 활성값 업로드\n(출구 2개면 조각으로 분할 전송)",
         "③ 서버 A(HPC) 뒷부분 계산\n기울기 반환 · 시간 측정", "④ 컨트롤러가 다음 라운드의\n학습량·접속 지점 결정",
         "⑤ 체크인 응답에 지시 동봉\n→ 접속 지점 B(VM1)로 이동 가능"]
for i, s in enumerate(steps):
    x = 0.03 + i * 0.19
    box(ax, x, 0.12, 0.175, 0.095, fc=ACCBG if i in (2, 3) else GRAYBG, ec=ACC if i in (2, 3) else LINE)
    txt(ax, x + 0.0875, 0.20, s, fs=8, ha="center", ls_=1.4)
    if i < 4:
        arrow(ax, x + 0.177, 0.167, x + 0.19, 0.167, c=LINE, lw=1.4)
txt(ax, 0.03, 0.10, "코드·데이터 배치  세 호스트 모두 같은 저장소를 ~/awarenet 에 git archive 로 배포(추적 파일만) · 데이터는 각자 보관 · 로그는 각 호스트 out/ → fetch 로 로컬 out/vm/, out/hpc/ 에 회수\n"
    "실행 순서(런처 켜진 뒤)  hpc_launch.sh (동기화 + R(w) nohup) → HPC 포트 노출 확인 → 안 되면 역방향 터널 → 링크 실험(서버 A ← VM2) → 접속 지점 2곳(A + B)",
    fs=8.2, c=SUB, ls_=1.55)

fig.savefig(os.path.join(OUT, "deploy_layout.png"), dpi=170, bbox_inches="tight", facecolor="white")
print("saved deploy_layout.png")
