# -*- coding: utf-8 -*-
"""AwareNet 최종 실험 결과 한 페이지 (2026-09-19) — 실증(LoRA 문답·크기 사다리) 제외, 본 실험만.
   python scripts/analysis/final_results_page.py  → out/reports/최종결과_AwareNet.html
   32대·λ·정확도 축·VM 판은 out/ 원자료(jsonl)에서 계산한다(앞 4라운드 제외 평균; VM 판은 앞 10라운드 제외 — 원 도구와 같음).
   8대 결합 실험 표는 docs/01_제출발표/보고_실험종합_2026-09-08.md 의 표를 옮긴다(3시드 판정 기록)."""
import glob, html, io, json, os, re, statistics as st, sys
from urllib.parse import quote

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.chdir(ROOT)
GH = "https://github.com/sijoon-sung/KORAN_SDN-AWARE_NET-/blob/awarenet/"
GT = "https://github.com/sijoon-sung/KORAN_SDN-AWARE_NET-/tree/awarenet/"
e = lambda s: html.escape(str(s))


def rows(f):
    return [json.loads(l) for l in io.open(f, encoding="utf-8") if '"round"' in l] if os.path.exists(f) else []


def mean_ms(R, skip=4):
    return st.mean(r["makespan"] for r in R[skip:])


def mean_w(R, skip=4):
    w = [st.mean(float(v) for v in r["plan"].values()) for r in R[skip:] if r.get("plan")]
    return st.mean(w) if w else 1.0


def gh(path, label=None, tree=False):
    return f"<a href='{(GT if tree else GH) + quote(path)}'>{e(label or path)}</a>"


# ── 32대 네 장면 ─────────────────────────────────────────────
SC = [("normal", "정상", "평소 그대로"), ("traffic", "트래픽 몰림", "R8~19 엣지 1 용량 1/4"),
      ("slow", "연산 느림", "4대가 0.15배 속도"), ("vary", "용량 변동", "R8~20 엣지 1 이 56→14→56 한 칸씩")]
res, series = {}, {}
for sc, name, _ in SC:
    U = [rows(f"out/wp_scen32_{sc}_s{s}_bothmp_uniform.jsonl") for s in (1, 2, 3)]
    W = [rows(f"out/wp_scen32_{sc}_s{s}_bothmp_widthpath.jsonl") for s in (1, 2, 3)]
    mu = [mean_ms(x) for x in U]; mw = [mean_ms(x) for x in W]
    d = [100 * (b / a - 1) for a, b in zip(mu, mw)]
    res[sc] = dict(u=st.mean(mu), w=st.mean(mw), d=st.mean(d), dlo=min(d), dhi=max(d), peak_u=max(max(r["makespan"] for r in x) for x in U),
                   peak_w=max(max(r["makespan"] for r in x) for x in W), width=st.mean(mean_w(x) for x in W))
    series[sc] = ([[r["makespan"] for r in x] for x in U], [[r["makespan"] for r in x] for x in W])

# ── λ 스윕 (연산 느림, 시드 1) ─────────────────────────────────
lam = []
for l, tag in (("18", "slow_l18"), ("70", "slow"), ("280", "slow_l280")):
    U = rows(f"out/wp_scen32_{tag}_s1_bothmp_uniform.jsonl"); W = rows(f"out/wp_scen32_{tag}_s1_bothmp_widthpath.jsonl")
    lam.append((l, mean_ms(U), mean_ms(W), mean_w(W)))

# ── 정확도 축 (8대 200R, 2시드, 마지막 50R 정확도) ──────────────
acc = {}
for f in sorted(glob.glob("out/wp_r8mix_acc*_s*_bothmp_widthpath.jsonl")):
    m = re.match(r"wp_r8mix_acc(_l(\d+))?_s(\d+)_bothmp_widthpath\.jsonl", os.path.basename(f))
    if not m: continue
    l = m.group(2) or "70"
    for key, ff in ((l, f), ("균등", f.replace("_widthpath", "_uniform"))):
        R = rows(ff)
        if not R: continue
        a = [r["acc"] for r in R[-50:] if r.get("acc") is not None]
        acc.setdefault(key, []).append((mean_ms(R), mean_w(R), st.mean(a) * (100 if st.mean(a) <= 1 else 1)))
acc_rows = []
for key in ("균등", "280", "70", "18"):
    v = acc.get(key)
    if not v: continue
    uniq = {round(x[0], 4): x for x in v}.values()          # 균등 팔은 λ 마다 같은 파일을 여러 번 읽을 수 있어 중복 제거
    acc_rows.append((key, st.mean(x[0] for x in uniq), st.mean(x[1] for x in uniq), st.mean(x[2] for x in uniq), len(list(uniq))))

# ── VM 배치 판 ────────────────────────────────────────────────
vm = []
for sc, label in (("normal", "정상"), ("traffic", "트래픽 몰림")):
    for tag, where in (("vmcli", "KOREN VM"), ("hpccli2" if sc == "normal" else "hpccli", "HPC 안")):
        U = rows(f"out/wp_{tag}_{sc}_s1_bothmp_uniform.jsonl"); W = rows(f"out/wp_{tag}_{sc}_s1_bothmp_widthpath.jsonl")
        if U and W:
            a, b = mean_ms(U, 10), mean_ms(W, 10)
            vm.append((label, where, a, b, 100 * (b / a - 1)))


# ── 조건과 선정 배경 (값·출처 종류는 조건 원장에서 직접 읽는다) ──────────
LEDGER = json.load(io.open("scripts/exp/conditions.json", encoding="utf-8"))
LEDGER = LEDGER.get("conditions", LEDGER)
SRC = {"논문": "문헌", "실측": "실측", "장비제약": "장비 제약", "우리선택": "설계 선택"}


def cv(cond, key):
    x = LEDGER[cond][key]
    return x.get("v"), SRC.get(x.get("src"), x.get("src"))


def fmt(v):
    if isinstance(v, list):
        from collections import Counter
        c = Counter(map(str, v))
        return " · ".join(f"{k}×{n}" if n > 1 else k for k, n in c.items()) if len(c) < len(v) else ", ".join(map(str, v))
    return "없음" if v is None else str(v)


def ctable(cond, items, title):
    body = []
    for key, label, why, override in items:
        v, src = cv(cond, key)
        shown = override if override is not None else fmt(v)
        body.append(f"<tr><th scope='row'>{e(label)}</th><td class='l'>{e(shown)}</td><td><span class='chip'>{e(src)}</span></td><td class='l'>{e(why)}</td></tr>")
    return (f"<div class='scroll'><table class='cond'><thead><tr><th>{e(title)}</th><th>값</th><th>근거 종류</th><th>왜 이 값인가</th></tr></thead><tbody>"
            + "".join(body) + "</tbody></table></div>")


C32 = ctable("r32", [
    ("clients", "기기 수", "사용자가 정한 규모(32~64대 사이). 이 회선에서 32대는 기기당 20~35 Mbps 를 받는다(맨 회선 실측).", "32대, 엣지 4개에 8대씩 시작"),
    ("acc_list", "기기 회선 (올리기/내리기 Mbps)", "실제값 50/20 을 0.1배로 줄였다. KOREN 실측(위 '실측' 절)에서 32대가 회선을 나눠 쓰면 가장 느린 엣지의 기기당 몫이 20 Mbps 안팎까지 떨어진다. 우리가 건 상한(합 7)이 그보다 확실히 낮아야 실험의 병목이 회선이 아니라 우리 설정이 된다. 비율(5:2)은 그대로 둔다.", None),
    ("caps", "엣지 용량 (Mbps)", "기기 수요 합 32×7 = 224 와 엣지 용량 합 4×56 = 224 가 같도록(부하 비율 1). 교란이 없으면 딱 맞고, 하나만 줄어도 부족해진다.", None),
    ("delays", "인위 지연", "지연은 KOREN 실회선 그대로(왕복 약 4~8 ms). 꾸민 지연을 넣지 않는다.", "없음 (실회선 그대로)"),
    ("threads", "기기당 CPU 스레드", "HPC 16코어에 32대라 1 스레드씩. 두 방식에 똑같이 걸리므로 비교는 공정하다.", None),
    ("rounds", "라운드", "교란을 8라운드에 넣고 20라운드에 푼다. 라운드가 약 70초라 실행 한 번에 약 28분.", "24"),
    ("seeds", "시드", "원장에는 시연용 1시드로 적었고, 후속 실험(9/10)에서 시드 2·3 을 같은 조건으로 더 돌렸다.", "1, 2, 3"),
    ("lam", "λ (폭을 깎는 값)", "정상 라운드 실측(약 70초)의 1배. '평균 폭을 1 잃는 것 = 라운드 하나를 통째로 잃는 것'으로 본다. 32대 중 한 대를 절반 폭으로 내리려면 라운드가 약 1.1초 이상 줄어야 한다. 비교용으로 280(엄격)·18(관대)도 돌렸다.", None),
    ("max_moves", "라운드당 이동 상한", "사전등록한 '몰린 엣지의 8대를 라운드당 3대씩'과 맞춘 값. 처음엔 기본값 1 로 돌려 8라운드가 걸렸고, 이는 조건 오류라 3 으로 고쳐 다시 돌렸다.", "3대"),
    ("deadline", "스케줄러 규칙", "라운드 시간(가장 느린 기기) + λ × 폭 손실을 최소화하는 결합 최적화(사용자 결정). 고정 목표 시간 방식으로는 연산 느림 장면에서 폭을 깎을 이유가 안 생겨 대체했다.", "결합 최적화"),
], "32대 시나리오")

SCENES = [
    ("정상", "교란 없음", "스케줄러가 멀쩡한 판을 망치지 않는지 본다."),
    ("트래픽 몰림", "R8 에 엣지 1 용량 56→14 Mbps(1/4), R20 복구", "다른 트래픽이 3배 얹혀 공평하게 나누면 1/4 만 남는 상황. 엣지 1 의 8대가 4배 느려진다."),
    ("연산 느림", "엣지마다 1대씩 4대의 연산 속도 0.15배", "0.15 는 문헌의 연산 이질성 범위(Aergia: 원래 속도의 0.1~1.0배) 안이고, 앞선 8대 실험의 낙오자와 같은 값이다."),
    ("용량 변동", "엣지 1 용량을 R8~R13 에 49→14 Mbps 로 7 씩 내리고 R14~R19 에 56 까지 되올림", "사용자 제안. 한 번에 떨어지는 것이 아니라 서서히 변할 때 따라가는지, 되돌아올 때 왕복하지 않는지 본다."),
]
TSC = "".join(f"<tr><th scope='row'>{e(a)}</th><td class='l'>{e(b)}</td><td class='l'>{e(c)}</td></tr>" for a, b, c in SCENES)

C8 = ctable("r8mix_rho1", [
    ("clients", "기기 수", "HPC 16코어를 기기당 2 스레드로 나누면 8대.", "8대"),
    ("speed_list", "연산 속도", "낙오자 2대(0.15·0.25배)와 정상 6대. 문헌의 연산 이질성 범위(0.1~1.0배) 안.", None),
    ("acc_list", "기기 회선 (올리기/내리기 Mbps)", "50/20 = 유선 실측 55, 한국 5G 업로드 47~57 Mbps. 20/20 = 한국 모바일 업로드의 아래쪽(중앙값 23.85 Mbps). 두 가닥 모두 약해 나눠 보내야 40.", None),
    ("caps", "엣지 용량 (Mbps)", "기기 수요 합 500 = 엣지 용량 합(부하 비율 1). 대조로 수요의 2배·절반 용량도 돌렸다.", None),
    ("deadline_s", "라운드 목표", "스케줄러 없는 라운드(약 20초)의 절반. 연합학습의 라운드 마감(FedCS)과 같은 방식으로, 모든 방법에 같은 목표를 주고 모델을 얼마나 깎는지 비교한다.", "10초"),
    ("seeds", "시드", "주조건 3시드, 대조 조건 2시드.", None),
    ("rounds", "라운드", "정확도는 문헌으로 보강하기로 하고(사용자 9/8 결정) 모델 폭 평균으로 대신 본다. 시뮬레이션에서 9라운드 안에 수렴해 24라운드.", "24"),
], "8대 결합 실험")

CACC = ctable("r8mix_acc", [
    ("rounds", "라운드", "원래는 정확도를 재려고 길게(200라운드) 돌린 실험이다. 이 페이지는 그 실험의 라운드 시간과 모델 폭만 쓰고, 정확도는 FjORD 논문을 참고한다.", "200"),
    ("seeds", "시드", "두 시드 평균.", None),
    ("lam", "λ", "18(관대)·70(정상 라운드 1배 규칙)·280(엄격) 세 점으로 '얼마나 빨라지고 모델을 얼마나 줄이나'를 잰다. 나머지 조건은 8대 결합 실험과 같다.", "18 · 70 · 280"),
], "λ 스윕 (8대 200라운드)")

CVM = ctable("v8mix", [
    ("clients", "기기 배치", "기기 프로세스를 실제 원격(KOREN VM)에 두고 서버만 HPC 에 둔다. 같은 VM 의 엣지는 내부 연결이라 회선 제한이 안 걸려서, 각 기기는 다른 VM 의 엣지만 쓴다.", "VM1 에 4대(엣지 3·4 사용), VM2 에 4대(엣지 1·2 사용)"),
    ("lam", "λ", "8대 정상 라운드(약 10초)의 1배. 32대의 λ=70 과 같은 규칙.", None),
    ("seeds", "시드", "HPC 안 기기 판과 모양을 비교하는 것이 목적이라 1시드.", None),
], "VM 배치 판")

COMMON = [
    ("실회선 구성", "HPC 서버 ↔ KOREN VM 두 대. VM 마다 역방향 SSH 터널 2개 = 엣지 4개. 기기 회선 상한은 HPC 쪽, 엣지 용량은 VM 쪽에서 tc 로 건다.", "SDN 경로 변경을 '기기가 어느 엣지로 붙느냐'로 재현하면서 실제 KOREN 구간을 지나게 하려는 것."),
    ("학습", "CIFAR-10 · CNN · 앞 2층을 기기가, 나머지를 서버가 · 라운드당 배치 4 · 학습률 0.05 · 모델 폭 단계 0.5/0.75/1.0", "폭 단계는 문헌 범위(FjORD·HeteroFL 류) 안. 라운드 시간이 목적이라 라운드당 배치를 작게 둔다."),
    ("비교 기준 (스케줄러 없음)", "기기마다 회선 하나, 처음 배정 고정, 모델 전폭", "'일반 분할학습'의 모습. 처음엔 두 회선을 가중치 없이 나눠 쓰는 판을 기준으로 삼았다가, 그것은 우리 채널의 성질이지 일반 분할학습이 아니라서 정정했다."),
    ("지표", "라운드 시간 = 가장 느린 기기가 끝나는 시간. 앞 4라운드(시작 흔들림)를 빼고 평균", "연합학습 라운드는 가장 느린 기기를 기다리므로 그 시간이 곧 비용이다. VM 판은 앞 10라운드를 뺐다(원장 규칙)."),
]
TCOMMON = "".join(f"<tr><th scope='row'>{e(a)}</th><td class='l'>{e(b)}</td><td class='l'>{e(c)}</td></tr>" for a, b, c in COMMON)

CHANGES = [
    ("이동 상한 1 → 3", "사전등록 표(라운드당 3대)와 달리 기본값 1 로 돌린 조건 오류. 정정 뒤 재실행."),
    ("비교 기준 정정", "두 회선 무가중 → 회선 하나. 첫 실행(9/9 새벽)은 이 이유 등으로 폐기."),
    ("고정 목표 → 결합 최적화", "고정 목표 84초로는 연산 느림 장면에서 폭 손잡이가 드러나지 않아 규칙을 바꿨다."),
    ("시드 1 → 3", "후속 실험에서 같은 조건으로 시드 2·3 추가. 세 시드 차이 1~2%p."),
]
TCHANGES = "".join(f"<tr><th scope='row'>{e(a)}</th><td class='l'>{e(b)}</td></tr>" for a, b in CHANGES)


# ── 그림 ──────────────────────────────────────────────────────
def bars():
    W, H, L, B, T = 760, 250, 46, 44, 18
    vmax = max(max(r["u"], r["w"]) for r in res.values()) * 1.12
    gw = (W - L - 10) / len(SC); bw = gw * 0.3
    y = lambda v: T + (H - T - B) * (1 - v / vmax)
    s = [f"<svg viewBox='0 0 {W} {H}' role='img' aria-label='32대 네 장면 평균 라운드 시간'>"]
    for k in range(0, int(vmax) + 1, 20):
        s.append(f"<line x1='{L}' x2='{W-10}' y1='{y(k):.1f}' y2='{y(k):.1f}' class='g'/><text x='{L-6}' y='{y(k)+4:.1f}' text-anchor='end' class='t'>{k}s</text>")
    for i, (sc, name, _) in enumerate(SC):
        r = res[sc]; x0 = L + gw * i + gw * 0.18
        for j, (v, cls) in enumerate(((r["u"], "u"), (r["w"], "p"))):
            x = x0 + j * (bw + 6)
            s.append(f"<rect x='{x:.1f}' y='{y(v):.1f}' width='{bw:.1f}' height='{y(0)-y(v):.1f}' rx='2' class='{cls}'/>"
                     f"<text x='{x+bw/2:.1f}' y='{y(v)-5:.1f}' text-anchor='middle' class='v'>{v:.1f}</text>")
        s.append(f"<text x='{x0+bw+3:.1f}' y='{H-24}' text-anchor='middle' class='n'>{name}</text>"
                 f"<text x='{x0+bw+3:.1f}' y='{H-8}' text-anchor='middle' class='d'>{r['d']:+.0f}%</text>")
    s.append("</svg>")
    return "".join(s)


def lines(sc, shade=None):
    U, Wl = series[sc]
    W, H, L, B, T, R = 360, 170, 38, 22, 10, 8
    n = max(len(x) for x in U + Wl); vmax = max(max(max(x) for x in U), max(max(x) for x in Wl)) * 1.08
    x = lambda i: L + (W - L - R) * i / (n - 1); y = lambda v: T + (H - T - B) * (1 - v / vmax)
    s = [f"<svg viewBox='0 0 {W} {H}' role='img' aria-label='{e(sc)} 라운드별 시간'>"]
    if shade:
        s.append(f"<rect x='{x(shade[0]):.1f}' y='{T}' width='{x(shade[1])-x(shade[0]):.1f}' height='{H-T-B}' class='sh'/>")
    step = 40 if vmax > 100 else 20
    for k in range(0, int(vmax) + 1, step):
        s.append(f"<line x1='{L}' x2='{W-R}' y1='{y(k):.1f}' y2='{y(k):.1f}' class='g'/><text x='{L-5}' y='{y(k)+3.5:.1f}' text-anchor='end' class='t'>{k}</text>")
    for i in range(0, n, 4):
        s.append(f"<text x='{x(i):.1f}' y='{H-6}' text-anchor='middle' class='t'>R{i}</text>")
    for grp, cls in ((U, "lu"), (Wl, "lp")):
        for ser in grp:
            s.append(f"<polyline points='{' '.join(f'{x(i):.1f},{y(v):.1f}' for i, v in enumerate(ser))}' class='{cls}'/>")
    s.append("</svg>")
    return "".join(s)


SHADE = {"traffic": (8, 19), "vary": (8, 20)}
cards = "".join(
    f"<figure class='card'><figcaption><b>{e(name)}</b><span>{e(cond)}</span></figcaption>{lines(sc, SHADE.get(sc))}"
    f"<p class='cap'>평균 {res[sc]['u']:.1f}s → <b>{res[sc]['w']:.1f}s</b> ({res[sc]['d']:+.0f}%, 시드별 {res[sc]['dlo']:+.0f}~{res[sc]['dhi']:+.0f}%) · 최고 {res[sc]['peak_u']:.0f}s → {res[sc]['peak_w']:.0f}s</p></figure>"
    for sc, name, cond in SC)

# ── 실측: KOREN VM ↔ HPC 회선 (맨 회선, tc 없음) → 0.1배 축소의 근거 ────────
def line_runs():
    out = {}
    for f, lab in (("out/line_raw_run1.jsonl", "1차 (9/9 00:23)"), ("out/line_scale.jsonl", "2차 (9/9 새벽, line_raw2.log 와 같은 판)")):
        rows_ = [json.loads(l) for l in io.open(f, encoding="utf-8") if l.strip()]
        out[lab] = sorted((x["n"], x["per_client_mbps_median"], x["aggregate_mbps"], x["per_client_mbps_min"]) for x in rows_ if x["pattern"] == "batch")
    return out


LINES = line_runs()
EDGE32 = {}
for f in sorted(glob.glob("out/line_scale_detail/n32_*.json")):
    d = json.load(io.open(f, encoding="utf-8")); m = d["meta"]
    mb = (m.get("up_mb", 4.2) + m.get("dn_mb", 4.2)) * 8
    by = {}
    for c, v in d["per"].items():
        by.setdefault(v["edge"], []).append(st.median(mb / t for t in v["times"] if t > 0))
    EDGE32[m["pattern"]] = {k: st.mean(x) for k, x in by.items()}
SLOW32 = {p: min(v.values()) for p, v in EDGE32.items()}
MIN32 = min(x[3] for runs in LINES.values() for x in runs if x[0] == 32)
MAX32MIN = max(x[3] for runs in LINES.values() for x in runs if x[0] == 32)


def line_svg():
    W, H, L, R, T, B = 700, 290, 52, 150, 16, 36
    ns = [8, 16, 32, 48, 64, 96]
    x = lambda n: L + (W - L - R) * ns.index(n) / (len(ns) - 1)
    vmax = 180
    y = lambda v: T + (H - T - B) * (1 - v / vmax)
    s = [f"<svg viewBox='0 0 {W} {H}' role='img' aria-label='기기 수에 따른 기기당 실효 속도'>"]
    for v in (0, 40, 80, 120, 160):
        s.append(f"<line x1='{L}' x2='{W-R}' y1='{y(v):.1f}' y2='{y(v):.1f}' class='g'/><text x='{L-6}' y='{y(v)+4:.1f}' text-anchor='end' class='t'>{v}</text>")
    for n in ns:
        s.append(f"<text x='{x(n):.1f}' y='{H-14}' text-anchor='middle' class='t'>{n}대</text>")
    s.append(f"<line x1='{x(32):.1f}' x2='{x(32):.1f}' y1='{T}' y2='{H-B}' class='guide'/><text x='{x(32)+4:.1f}' y='{T+10}' class='s'>32대 실험</text>")
    for yv, lab, cls in ((70, "원래 기기 회선 50+20 = 70", "ref"), (7, "32대 실험 상한 5+2 = 7", "cap")):
        s.append(f"<line x1='{L}' x2='{W-R}' y1='{y(yv):.1f}' y2='{y(yv):.1f}' class='{cls}'/><text x='{W-R+6}' y='{y(yv)+4:.1f}' class='{cls}t'>{lab}</text>")
    for (lab, runs), cls in zip(LINES.items(), ("l1", "l2")):
        pts = [(x(n), y(v)) for n, v, a, mn in runs if n in ns]
        s.append("<polyline points='" + " ".join(f"{a:.1f},{b:.1f}" for a, b in pts) + f"' class='{cls}'/>")
        for a, b in pts:
            s.append(f"<circle cx='{a:.1f}' cy='{b:.1f}' r='3.5' class='{cls}d'/>")
    s.append("</svg>")
    return "".join(s)


def agg_svg():
    W, H, L, R, T, B = 700, 200, 52, 150, 16, 36
    ns = [8, 16, 32, 48, 64, 96]
    x = lambda n: L + (W - L - R) * ns.index(n) / (len(ns) - 1)
    vmax = 1600
    y = lambda v: T + (H - T - B) * (1 - v / vmax)
    s = [f"<svg viewBox='0 0 {W} {H}' role='img' aria-label='기기 수에 따른 회선 합계 처리량'>"]
    s.append(f"<rect x='{L}' y='{y(1300):.1f}' width='{W-R-L}' height='{y(800)-y(1300):.1f}' class='sh'/><text x='{W-R+6}' y='{y(1050)+4:.1f}' class='s'>0.8~1.3 Gbps 에서 멈춤</text>")
    for v in (0, 400, 800, 1200, 1600):
        s.append(f"<line x1='{L}' x2='{W-R}' y1='{y(v):.1f}' y2='{y(v):.1f}' class='g'/><text x='{L-6}' y='{y(v)+4:.1f}' text-anchor='end' class='t'>{v}</text>")
    for n in ns:
        s.append(f"<text x='{x(n):.1f}' y='{H-14}' text-anchor='middle' class='t'>{n}대</text>")
    for (lab, runs), cls in zip(LINES.items(), ("l1", "l2")):
        pts = [(x(n), y(a)) for n, v, a, mn in runs if n in ns]
        s.append("<polyline points='" + " ".join(f"{p:.1f},{q:.1f}" for p, q in pts) + f"' class='{cls}'/>")
        for p, q in pts:
            s.append(f"<circle cx='{p:.1f}' cy='{q:.1f}' r='3.5' class='{cls}d'/>")
    s.append("</svg>")
    return "".join(s)


# ── 쉬운 그림들 (2026-09-19 추가: "다 좀 직관적으로") ─────────────────────
def system_svg():
    """기기 32대 → 엣지 4개(KOREN VM 두 대) → 서버. 글씨는 선과 겹치지 않는 자리에만."""
    s = ["<svg viewBox='0 0 900 330' role='img' aria-label='기기 32대가 엣지 4개를 거쳐 서버로 가는 구성'>"]
    ys = [60, 132, 206, 278]
    s.append("<text x='20' y='20' class='h'>기기 32대</text><text x='20' y='36' class='s'>엣지마다 8대씩 · 기기 회선 5/2 Mbps</text>")
    for i, yc in enumerate(ys):
        s.append(f"<rect x='20' y='{yc-24}' width='170' height='48' rx='8' class='box'/>")
        s.append(f"<text x='34' y='{yc-4}' class='n'>기기 8대</text>")
        for k in range(8):
            s.append(f"<circle cx='{36 + k*18}' cy='{yc+12}' r='5' class='dev'/>")
        s.append(f"<line x1='190' y1='{yc}' x2='300' y2='{yc}' class='wire'/>")
    for j, (y0, y1, name) in enumerate(((34, 158, "KOREN VM1"), (182, 304, "KOREN VM2"))):
        s.append(f"<rect x='292' y='{y0}' width='336' height='{y1-y0}' rx='10' class='band'/>")
        s.append(f"<text x='616' y='{y0+18}' text-anchor='end' class='s'>{name}</text>")
    for i, yc in enumerate(ys):
        s.append(f"<line x1='306' y1='{yc}' x2='610' y2='{yc}' class='pipe'/>")
        s.append(f"<text x='310' y='{yc-14}' class='pl'>엣지 {i+1} · 56 Mbps</text>")
        s.append(f"<line x1='610' y1='{yc}' x2='740' y2='168' class='wire'/>")
    s.append("<rect x='740' y='118' width='150' height='100' rx='10' class='srv'/>")
    s.append("<text x='815' y='152' text-anchor='middle' class='h'>서버</text>"
             "<text x='815' y='172' text-anchor='middle' class='s'>HPC · V100</text>"
             "<text x='815' y='192' text-anchor='middle' class='s'>뒷부분 계산 · 모델 합치기</text>")
    s.append("</svg>")
    return "".join(s)


def knob_icon(kind):
    s = ["<svg viewBox='0 0 180 90' role='img' aria-hidden='true'>"]
    if kind == "move":
        s.append("<line x1='70' y1='25' x2='170' y2='25' class='pipe bad'/><text x='120' y='14' text-anchor='middle' class='s'>막힌 엣지</text>"
                 "<line x1='70' y1='70' x2='170' y2='70' class='pipe'/><text x='120' y='88' text-anchor='middle' class='s'>여유 있는 엣지</text>"
                 "<circle cx='30' cy='25' r='8' class='dev ghost'/><circle cx='30' cy='70' r='8' class='dev'/>"
                 "<path d='M30 36 C 30 50, 30 52, 30 58' class='arrow'/>")
    elif kind == "split":
        s.append("<circle cx='22' cy='47' r='8' class='dev'/>"
                 "<path d='M30 47 C 60 47, 60 22, 90 22' class='wire'/><path d='M30 47 C 60 47, 60 72, 90 72' class='wire'/>"
                 "<line x1='92' y1='22' x2='172' y2='22' class='pipe'/><line x1='92' y1='72' x2='172' y2='72' class='pipe'/>"
                 "<text x='132' y='47' text-anchor='middle' class='s'>두 회선에 나눠</text>")
    else:
        for k, (x, w, h) in enumerate(((14, 34, 56), (58, 34, 56), (102, 34, 56), (146, 22, 36))):
            s.append(f"<rect x='{x}' y='{70-h}' width='{w}' height='{h}' rx='4' class='{'mdl small' if k == 3 else 'mdl'}'/>")
        s.append("<text x='157' y='86' text-anchor='middle' class='s'>느린 기기</text>")
    s.append("</svg>")
    return "".join(s)


VARY_CAP = {8: 49, 9: 42, 10: 35, 11: 28, 12: 21, 13: 14, 14: 21, 15: 28, 16: 35, 17: 42, 18: 49, 19: 56}


def scene_pic(sc):
    """그 장면에서 '무엇을 바꿨나' — 엣지 1 용량의 라운드별 변화, 또는 32대 중 느린 4대."""
    W, H, L, R, T, B = 280, 110, 34, 8, 14, 22
    s = [f"<svg viewBox='0 0 {W} {H}' role='img' aria-label='{e(sc)} 장면에서 바꾼 것'>"]
    if sc == "slow":
        for row in range(4):
            s.append(f"<text x='4' y='{T + row*20 + 10}' class='t'>엣지{row+1}</text>")
            for k in range(8):
                slow = (k == 0)
                s.append(f"<rect x='{L + 6 + k*26}' y='{T + row*20}' width='20' height='14' rx='3' class='{'cell slow' if slow else 'cell'}'/>")
        s.append(f"<text x='{L+6}' y='{H-2}' class='s'>주황 = 연산 0.15배 (엣지마다 1대, 모두 4대)</text>")
    else:
        cap = [56] * 24
        if sc == "traffic":
            cap = [14 if 8 <= r < 20 else 56 for r in range(24)]
        elif sc == "vary":
            cap = [VARY_CAP.get(r, 56) for r in range(24)]
        x = lambda r: L + (W - L - R) * r / 24
        y = lambda c: T + (H - T - B) * (1 - c / 56)
        pts = [(x(0), y(cap[0]))]
        for r in range(24):
            pts += [(x(r), y(cap[r])), (x(r + 1), y(cap[r]))]
        path = " ".join(f"{a:.1f},{b:.1f}" for a, b in pts)
        s.append(f"<polygon points='{x(0):.1f},{y(0):.1f} {path} {x(24):.1f},{y(0):.1f}' class='capf{' bad' if sc != 'normal' else ''}'/>")
        s.append(f"<polyline points='{path}' class='capl{' bad' if sc != 'normal' else ''}'/>")
        for c in (56, 14):
            s.append(f"<text x='{L-4}' y='{y(c)+4:.1f}' text-anchor='end' class='t'>{c}</text>")
        for r in (0, 8, 20):
            s.append(f"<text x='{x(r):.1f}' y='{H-6}' text-anchor='middle' class='t'>R{r}</text>")
        s.append(f"<text x='{W-R}' y='{T-2}' text-anchor='end' class='s'>엣지 1 용량 (Mbps)</text>")
    s.append("</svg>")
    return "".join(s)


DID = {"normal": "망도 모델도 건드리지 않았다. 빨라진 몫은 두 회선을 나눠 쓴 덕분.",
       "traffic": "막힌 엣지 1 의 8대를 R9~11 에 3·3·2대씩 다른 엣지로 옮겼다. 이후 약 60초에서 안정.",
       "slow": "느린 4대만 모델을 0.75 로 줄였다. 나머지 28대는 그대로, 옮긴 기기는 없다.",
       "vary": "용량이 내려갈 때 기기를 옮기고 엣지 1 기기의 모델을 한 칸 줄였다. 회복 뒤 48~49초."}
WHAT = {"normal": "아무것도 바꾸지 않음",
        "traffic": "R8 에 엣지 1 을 1/4 로 막고 R20 에 풂",
        "slow": "32대 중 4대의 연산을 0.15배로",
        "vary": "엣지 1 을 R8~13 에 서서히 1/4 까지 내리고 R14~19 에 되올림"}


def scene_cards():
    out = []
    for sc, name, _ in SC:
        r = res[sc]
        out.append(
            f"<article class='scard'><header><h3>{e(name)}</h3><span class='big'>{r['u']:.0f}초 → <b>{r['w']:.0f}초</b> <em>{r['d']:+.0f}%</em></span></header>"
            f"<div class='srow'><div class='pic'>{scene_pic(sc)}</div><div class='txt'><p><span class='lab'>바꾼 것</span>{e(WHAT[sc])}</p>"
            f"<p><span class='lab'>스케줄러가 한 일</span>{e(DID[sc])}</p></div></div>"
            f"<div class='mini'>{lines(sc, SHADE.get(sc))}</div>"
            f"<p class='cap'>라운드마다의 시간 · 회색 = 스케줄러 없음, 초록 = 스케줄러, 세 시드 · 시드별 차이 {r['dlo']:+.0f}~{r['dhi']:+.0f}%</p></article>")
    return "".join(out)


def lam_svg():
    """λ 에 따른 (라운드 시간, 평균 모델 폭) — 8대 200라운드 2시드. 정확도는 쓰지 않는다(FjORD 참고, 2026-09-19 사용자 결정)."""
    pts = [(k, ms, w) for k, ms, w, a, n in acc_rows]
    W, H, L, R, T, B = 620, 300, 64, 24, 24, 48
    x = lambda v: L + (W - L - R) * (v - 6) / (21 - 6)
    y = lambda v: T + (H - T - B) * (1 - (v - 0.78) / (1.02 - 0.78))
    s = [f"<svg viewBox='0 0 {W} {H}' role='img' aria-label='λ 에 따른 라운드 시간과 평균 모델 폭'>"]
    for v in (0.8, 0.85, 0.9, 0.95, 1.0):
        s.append(f"<line x1='{L}' x2='{W-R}' y1='{y(v):.1f}' y2='{y(v):.1f}' class='g'/><text x='{L-6}' y='{y(v)+4:.1f}' text-anchor='end' class='t'>{v:.2f}</text>")
    for v in (8, 12, 16, 20):
        s.append(f"<text x='{x(v):.1f}' y='{H-28}' text-anchor='middle' class='t'>{v}초</text>")
    s.append(f"<text x='{(L+W-R)/2:.0f}' y='{H-8}' text-anchor='middle' class='s'>← 빠름 · 라운드 시간 · 느림 →</text>")
    s.append(f"<text x='8' y='{T-8}' class='s'>평균 모델 폭 (1 = 안 줄임)</text>")
    lam_pts = sorted([p for p in pts if p[0] != "균등"], key=lambda p: p[1])
    s.append("<polyline points='" + " ".join(f"{x(ms):.1f},{y(w):.1f}" for _, ms, w in lam_pts) + "' class='lp'/>")
    LAB = {"균등": ("스케줄러 없음", 0, -26, "middle"), "280": ("λ 280 (엄격)", 0, -26, "middle"),   # 폭 1.0 두 점은 위쪽에 — 아래에 두면 λ 70 글씨와 겹친다
           "70": ("λ 70 (보통)", 12, -12, "start"), "18": ("λ 18 (관대)", 12, 4, "start")}
    for k, ms, w in pts:
        lab, dx, dy, anc = LAB[k]
        s.append(f"<circle cx='{x(ms):.1f}' cy='{y(w):.1f}' r='7' class='{'pu' if k == '균등' else 'pp'}'/>")
        s.append(f"<text x='{x(ms)+dx:.1f}' y='{y(w)+dy:.1f}' text-anchor='{anc}' class='n'>{lab}</text>")
        s.append(f"<text x='{x(ms)+dx:.1f}' y='{y(w)+dy+15:.1f}' text-anchor='{anc}' class='t'>{ms:.1f}초 · 폭 {w:.2f}</text>")
    s.append("</svg>")
    return "".join(s)


COMBO = [("아무것도 안 함", 1.00, 0, 25, False), ("모델만 줄임 (단순 분할학습)", 0.55, 95, 17, False),
         ("망만 (엣지 바꾸기 + 나눠 보내기)", 1.00, 76, 26, False), ("모델 + 엣지", 0.82, 95, 23, False),
         ("모델 + 엣지 + 나눠 보내기 (제안)", 0.93, 100, 26, True)]


def combo_svg():
    W, RH, T = 860, 52, 44
    H = T + RH * len(COMBO) + 8
    x1, x2, bw = 300, 590, 200
    s = [f"<svg viewBox='0 0 {W} {H}' role='img' aria-label='8대 결합 실험 방법별 모델 크기와 10초 목표 성공률'>"]
    s.append(f"<text x='{x1}' y='18' class='n'>모델을 얼마나 지켰나</text><text x='{x1}' y='34' class='t'>1 = 전혀 안 줄임</text>")
    s.append(f"<text x='{x2}' y='18' class='n'>10초 목표 성공률</text><text x='{x2}' y='34' class='t'>라운드 중 10초 안에 끝난 비율</text>")
    for i, (name, w, ok, acc, hi) in enumerate(COMBO):
        yc = T + RH * i + RH / 2
        cls = "p" if hi else "u"
        s.append(f"<text x='0' y='{yc+5:.0f}' class='{'n hi' if hi else 'n'}'>{e(name)}</text>")   # 우리 정확도는 표시하지 않는다(FjORD 참고)
        s.append(f"<rect x='{x1}' y='{yc-9:.0f}' width='{bw}' height='18' rx='4' class='track'/><rect x='{x1}' y='{yc-9:.0f}' width='{bw*w:.0f}' height='18' rx='4' class='{cls}'/>"
                 f"<text x='{x1+bw+8}' y='{yc+5:.0f}' class='v'>{w:.2f}</text>")
        s.append(f"<rect x='{x2}' y='{yc-9:.0f}' width='{bw}' height='18' rx='4' class='track'/><rect x='{x2}' y='{yc-9:.0f}' width='{bw*ok/100:.0f}' height='18' rx='4' class='{cls}'/>"
                 f"<text x='{x2+bw+8}' y='{yc+5:.0f}' class='v'>{ok}%</text>")
    s.append("</svg>")
    return "".join(s)


def rng(vals, fmt="{:.0f}"):
    a, b = fmt.format(min(vals)), fmt.format(max(vals))       # 표시 자릿수로 비교 (정수 반올림 비교는 0.8·1.3 을 같은 값으로 봤다)
    return a if a == b else f"{a}~{b}"


# 32대 가장 느린 기기: 두 측정 · 두 전송 패턴(배치·버스트) 모두 — 가장 느린 엣지(SLOW32)와 같은 기준
_all32 = [json.loads(l)["per_client_mbps_min"] for f in ("out/line_raw_run1.jsonl", "out/line_scale.jsonl")
          for l in io.open(f, encoding="utf-8") if l.strip() and json.loads(l)["n"] == 32]
MIN32, MAX32MIN = min(_all32), max(_all32)


N8 = rng([v for runs in LINES.values() for n, v, a, mn in runs if n == 8])
N16 = rng([v for runs in LINES.values() for n, v, a, mn in runs if n == 16])
AGG = rng([a / 1000 for runs in LINES.values() for n, v, a, mn in runs if n >= 32], "{:.1f}")
SLOWR = rng(list(SLOW32.values()), "{:.1f}")
MINR = f"{MIN32:.1f}~{MAX32MIN:.1f}"


def vm_svg():
    W, H, L, B, T = 760, 240, 46, 52, 20
    vmax = max(max(a, b) for _, _, a, b, _ in vm) * 1.15
    y = lambda v: T + (H - T - B) * (1 - v / vmax)
    gw = (W - L - 10) / len(vm); bw = gw * 0.28
    s = [f"<svg viewBox='0 0 {W} {H}' role='img' aria-label='VM 판과 HPC 판의 라운드 시간'>"]
    for k in range(0, int(vmax) + 1, 5):
        s.append(f"<line x1='{L}' x2='{W-10}' y1='{y(k):.1f}' y2='{y(k):.1f}' class='g'/><text x='{L-6}' y='{y(k)+4:.1f}' text-anchor='end' class='t'>{k}s</text>")
    for i, (scn, wh, a, b, d) in enumerate(vm):
        x0 = L + gw * i + gw * 0.18
        for j, (v, cls) in enumerate(((a, "u"), (b, "p"))):
            xx = x0 + j * (bw + 6)
            s.append(f"<rect x='{xx:.1f}' y='{y(v):.1f}' width='{bw:.1f}' height='{y(0)-y(v):.1f}' rx='2' class='{cls}'/><text x='{xx+bw/2:.1f}' y='{y(v)-5:.1f}' text-anchor='middle' class='v'>{v:.1f}</text>")
        cx = x0 + bw + 3
        s.append(f"<text x='{cx:.1f}' y='{H-30}' text-anchor='middle' class='n'>{e(scn)}</text><text x='{cx:.1f}' y='{H-14}' text-anchor='middle' class='t'>{e(wh)} · {d:+.0f}%</text>")
    s.append("</svg>")
    return "".join(s)


NOTE = {"normal": "옮기지도 줄이지도 않음. 차이는 두 회선을 나눠 쓰는 몫",
        "traffic": "R9~11 에 엣지 1 기기 8대를 3·3·2대씩 옮겨 약 60 s 에서 안정. 기기 1대를 되돌려 보는 탐침 1~2회, 무리 지어 되돌아가 무너지는 일은 없음",
        "slow": "느린 4대만 모델 폭 0.75, 나머지 전폭, 이동 0",
        "vary": "용량이 내려갈 때 옮기고 엣지 1 기기의 폭을 한 칸 내림. 회복 뒤 48~49 s"}
t32 = "".join(f"<tr><th scope='row'>{e(n)}</th><td>{res[s]['u']:.1f}s</td><td class='hi'>{res[s]['w']:.1f}s</td><td class='hi'>{res[s]['d']:+.0f}%</td><td>{res[s]['dlo']:+.0f} ~ {res[s]['dhi']:+.0f}%</td><td class='l'>{e(NOTE[s])}</td></tr>" for s, n, _ in SC)
tlam = "".join(f"<tr><th scope='row'>λ = {l}</th><td>{u:.1f}s</td><td class='hi'>{w:.1f}s</td><td>{100*(w/u-1):+.0f}%</td><td>{wd:.2f}</td></tr>" for l, u, w, wd in lam)
tacc = "".join(f"<tr><th scope='row'>{'스케줄러 없음' if k=='균등' else 'λ = '+k}</th><td>{ms:.1f}s</td><td>{w:.2f}</td><td class='hi'>{a:.1f}%</td></tr>" for k, ms, w, a, n in acc_rows)
tvm = "".join(f"<tr><th scope='row'>{e(s)}</th><td>{e(wh)}</td><td>{a:.1f}s</td><td class='hi'>{b:.1f}s</td><td class='hi'>{d:+.0f}%</td></tr>" for s, wh, a, b, d in vm)

WHERE = [
    ("최종 종합 보고", "docs/01_제출발표/보고_실험종합_2026-09-10.md"),
    ("32대 시나리오 정식 보고", "docs/01_제출발표/실험보고_32대_시나리오_2026-09-10.md"),
    ("8대 결합 실험 종합", "docs/01_제출발표/보고_실험종합_2026-09-08.md"),
    ("32대 사전등록과 판정", "docs/02_실험/실험_시나리오_32대_사전등록.md"),
    ("세 시드·λ 스윕 사전등록과 판정", "docs/02_실험/실험_후속_사전등록_2026-09-10.md"),
    ("8대 결합 사전등록과 판정", "docs/02_실험/실험_결합_3번_사전등록.md"),
    ("날짜별 실험 상세 기록", "docs/02_실험/데이터_기록_2026-09-07.md"),
    ("생긴 문제와 해결", "docs/04_설계기록/문제와_해결_2026-09.md"),
]
twhere = "".join(f"<tr><td>{e(a)}</td><td class='l'>{gh(p)}</td></tr>" for a, p in WHERE)
RAW = [
    ("32대 네 장면 × 세 시드", "out/wp_scen32_<장면>_s<시드>_bothmp_{uniform,widthpath}.jsonl"),
    ("λ 스윕 (연산 느림)", "out/wp_scen32_slow_l18_…, out/wp_scen32_slow_l280_…"),
    ("λ 스윕 (8대 200라운드)", "out/wp_r8mix_acc…"),
    ("8대 결합 실험", "out/wp_r8mix_rho{05,1,2}_…"),
    ("VM 배치 판", "out/wp_vmcli_…, out/wp_hpccli…"),
    ("고치기 전 판들", "out/scen32_final_try1 ~ try9/"),
]
traw = "".join(f"<tr><td>{e(a)}</td><td class='l'><code>{e(p)}</code></td></tr>" for a, p in RAW)

page = f"""<title>AwareNet 최종 실험 결과</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{{--bg:#F5F7F4;--panel:#FFFFFF;--ink:#1B2320;--muted:#5B6660;--line:#D7DED8;--grid:#E6EBE6;--acc:#1F6F5B;--accs:#DCEDE6;--uni:#8C949A;--shade:rgba(185,101,31,.10);--warm:#B9651F;
--sans:"IBM Plex Sans KR","Noto Sans KR","Malgun Gothic",system-ui,sans-serif;--mono:"IBM Plex Mono",ui-monospace,Consolas,monospace}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#141917;--panel:#1C2320;--ink:#E7ECE8;--muted:#9BA69F;--line:#2B332F;--grid:#27302B;--acc:#63C3A6;--accs:#1E3A32;--uni:#8A9399;--shade:rgba(227,154,92,.14);--warm:#E39A5C}}}}
:root[data-theme="dark"]{{--bg:#141917;--panel:#1C2320;--ink:#E7ECE8;--muted:#9BA69F;--line:#2B332F;--grid:#27302B;--acc:#63C3A6;--accs:#1E3A32;--uni:#8A9399;--shade:rgba(227,154,92,.14);--warm:#E39A5C}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.65}}
main{{max-width:1060px;margin:0 auto;padding:40px 22px 80px}}
.eyebrow{{font-family:var(--mono);font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}}
h1{{font-size:31px;line-height:1.22;margin:8px 0 10px;text-wrap:balance}}
h2{{font-size:20px;margin:44px 0 10px;text-wrap:balance}}
p{{max-width:74ch}} .lede{{font-size:16.5px;color:var(--muted);max-width:80ch}}
.panel{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px}}
svg{{width:100%;height:auto;display:block}}
svg .g{{stroke:var(--grid)}} svg .t{{font:10.5px var(--mono);fill:var(--muted)}} svg .n{{font:13px var(--sans);fill:var(--ink);font-weight:600}}
svg .d{{font:12.5px var(--mono);fill:var(--acc);font-weight:500}} svg .v{{font:11px var(--mono);fill:var(--muted)}}
svg .u{{fill:var(--uni)}} svg .p{{fill:var(--acc)}} svg .sh{{fill:var(--shade)}}
svg .lu{{fill:none;stroke:var(--uni);stroke-width:1.4;opacity:.8}} svg .lp{{fill:none;stroke:var(--acc);stroke-width:1.8}}
.leg{{display:flex;gap:16px;font-size:12.5px;color:var(--muted);margin:6px 2px 0;flex-wrap:wrap}} .leg i{{display:inline-block;width:12px;height:12px;border-radius:2px;margin-right:6px;vertical-align:-1px}}
.cards{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}}
.card{{margin:0;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px}}
.card figcaption{{display:flex;justify-content:space-between;gap:10px;align-items:baseline;margin-bottom:4px}} .card figcaption span{{font-size:12.5px;color:var(--muted)}}
.cap{{font-size:13px;color:var(--muted);margin:6px 0 0}} .cap b{{color:var(--acc)}}
.scroll{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:14px}}
th,td{{padding:8px 10px;border-bottom:1px solid var(--line);text-align:right;vertical-align:top}}
thead th{{font-size:12px;color:var(--muted);font-weight:600;letter-spacing:.02em}}
th[scope=row],td.l,thead th:first-child{{text-align:left}} th[scope=row]{{font-weight:600;white-space:nowrap}}
td.hi{{color:var(--acc);font-weight:600}} td.l{{max-width:46ch}} td.bad{{color:var(--bad);font-weight:600}}
.chip{{display:inline-block;font-size:11.5px;padding:1px 8px;border-radius:999px;background:var(--accs);color:var(--acc);white-space:nowrap}}
table.cond td,table.cond th{{text-align:left}} table.cond td.l{{max-width:58ch;font-size:13.5px}}
h3{{font-size:16px;margin:26px 0 8px}}
:root{{--bad:#B3413A;--bads:#F6E1DE;--band:rgba(31,111,91,.06);--pipe:#7FB8A6;--slow:#D98B3A}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bad:#E88077;--bads:#3A221F;--band:rgba(99,195,166,.08);--pipe:#3F8F77;--slow:#E0A15E}}}}
:root[data-theme="dark"]{{--bad:#E88077;--bads:#3A221F;--band:rgba(99,195,166,.08);--pipe:#3F8F77;--slow:#E0A15E}}
svg .h{{font:600 15px var(--sans);fill:var(--ink)}} svg .s{{font:12px var(--sans);fill:var(--muted)}} svg .pl{{font:12.5px var(--sans);fill:var(--ink)}}
svg .box{{fill:var(--panel);stroke:var(--line)}} svg .dev{{fill:var(--acc)}} svg .dev.ghost{{fill:none;stroke:var(--bad);stroke-dasharray:3 2}}
svg .wire{{fill:none;stroke:var(--muted);stroke-width:1.4;opacity:.7}} svg .band{{fill:var(--band);stroke:var(--line)}}
svg .pipe{{stroke:var(--pipe);stroke-width:12;stroke-linecap:round}} svg .pipe.bad{{stroke:var(--bad);stroke-width:4}}
svg .srv{{fill:var(--accs);stroke:var(--acc);stroke-width:1.5}} svg .arrow{{fill:none;stroke:var(--acc);stroke-width:2.2;marker-end:none}}
svg .mdl{{fill:var(--acc);opacity:.85}} svg .mdl.small{{fill:var(--slow)}}
svg .cell{{fill:var(--accs);stroke:var(--acc);stroke-width:.8}} svg .cell.slow{{fill:var(--slow);stroke:var(--slow)}}
svg .capf{{fill:var(--accs)}} svg .capf.bad{{fill:var(--bads)}} svg .capl{{fill:none;stroke:var(--acc);stroke-width:2}} svg .capl.bad{{stroke:var(--bad)}}
svg .pu{{fill:var(--uni)}} svg .pp{{fill:var(--acc)}} svg .track{{fill:var(--grid)}} svg .n.hi{{fill:var(--acc)}}
svg .guide{{stroke:var(--muted);stroke-dasharray:4 4}} svg .ref{{stroke:var(--muted);stroke-dasharray:6 4}} svg .reft{{font:12px var(--sans);fill:var(--muted)}}
svg .cap{{stroke:var(--bad);stroke-width:2}} svg .capt{{font:600 12px var(--sans);fill:var(--bad)}}
svg .l1{{fill:none;stroke:var(--uni);stroke-width:2}} svg .l1d{{fill:var(--uni)}} svg .l2{{fill:none;stroke:var(--acc);stroke-width:2}} svg .l2d{{fill:var(--acc)}}
.knobs{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:12px}}
.knob{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 12px}}
.knob b{{display:block;margin:4px 0 2px}} .knob p{{margin:0;font-size:13px;color:var(--muted)}}
.scards{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:12px}}
.scard{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px 14px}}
.scard header{{display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap}} .scard h3{{margin:0}}
.big{{font-family:var(--mono);font-size:15px;color:var(--muted)}} .big b{{color:var(--acc);font-size:19px}} .big em{{font-style:normal;color:var(--acc);font-weight:600;margin-left:4px}}
.srow{{display:grid;grid-template-columns:1fr 1fr;gap:10px;align-items:center;margin:8px 0}} .srow p{{margin:0 0 6px;font-size:13.5px}}
.lab{{display:block;font-size:11.5px;color:var(--muted);letter-spacing:.02em}}
.chain{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:14px 0}}
.step{{background:var(--panel);border:1px solid var(--line);border-top:3px solid var(--acc);border-radius:6px;padding:10px 12px;font-size:13.5px}}
.step b{{display:block;font-size:14.5px;margin-bottom:3px}} .step.bad{{border-top-color:var(--bad)}}
.legend2{{display:flex;gap:16px;font-size:12.5px;color:var(--muted);flex-wrap:wrap;margin-top:4px}} .legend2 i{{display:inline-block;width:18px;height:3px;margin-right:6px;vertical-align:middle}}
@media (max-width:820px){{.knobs,.scards,.srow,.chain{{grid-template-columns:1fr}}}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:16px;align-items:start}}
code{{font-family:var(--mono);font-size:12.5px;background:var(--grid);padding:1px 5px;border-radius:3px;overflow-wrap:anywhere}}
a{{color:var(--acc)}} a:focus-visible{{outline:2px solid var(--acc);outline-offset:2px}}
.muted{{color:var(--muted);font-size:13px}}
footer{{margin-top:48px;border-top:1px solid var(--line);padding-top:12px;font-size:12.5px;color:var(--muted)}}
@media (max-width:820px){{.cards,.two{{grid-template-columns:1fr}}}}
</style>
<main>
<div class="eyebrow">AwareNet · KOREN 실회선 분할 연합학습 · 최종 실험 결과</div>
<h1>3층 스케줄러는 네 장면 모두에서 라운드를 25~43% 줄였다</h1>
<p class="lede">기기 32대를 KOREN VM 엣지 4개에 나눠 두고, 트래픽 몰림·연산 느림·용량 변동을 실제로 만들어 스케줄러가 있을 때와 없을 때를 세 시드로 쟀다. 실험 조건은 KOREN 회선을 먼저 실측해서 정했다. 숫자는 이 페이지를 만들 때 원자료에서 다시 계산했다. 모델을 줄였을 때의 정확도는 우리 측정 대신 FjORD 논문을 참고한다. 실증(LoRA 문답·크기 사다리)은 이 페이지에서 뺐다.</p>

<h2>한 장으로 보기 — 무엇을 가지고 실험했나</h2>
<div class="panel">{system_svg()}</div>
<div class="knobs">
<div class="knob">{knob_icon('move')}<b>① 엣지 옮기기</b><p>막힌 엣지의 기기를 여유 있는 엣지로 옮긴다. SDN 경로 변경에 해당한다.</p></div>
<div class="knob">{knob_icon('split')}<b>② 두 회선에 나눠 보내기</b><p>기기 하나의 데이터를 두 회선에 나눠 실어 보낸다.</p></div>
<div class="knob">{knob_icon('shrink')}<b>③ 느린 기기만 모델 줄이기</b><p>연산이 느린 기기만 모델 폭을 줄인다. 정확도를 조금 내주므로 마지막에 쓴다.</p></div>
</div>
<p class="muted">비교 기준인 "스케줄러 없음"은 기기마다 회선 하나, 처음 배정 그대로, 모델 전폭이다. 일반 분할학습의 모습이다.</p>

<h2>실측 — KOREN VM ↔ HPC 회선, 그리고 32대 실험을 0.1배로 줄인 이유</h2>
<p>학습 없이 전송만(배치마다 4.2 MB 올리고 4.2 MB 받기) 하면서 기기 수를 늘려, 실제 회선이 어디서 막히는지 쟀다. 기기별 회선 제한은 걸지 않았다. 경로는 실험과 같다: 기기(HPC) → KOREN VM 엣지 → 서버(HPC).</p>
<div class="two">
<figure class="card"><figcaption><b>기기가 늘면 한 대 몫이 줄어든다</b><span>기기당 실효 속도, Mbps</span></figcaption>{line_svg()}<div class="legend2"><span><i style="background:var(--uni)"></i>1차 측정</span><span><i style="background:var(--acc)"></i>2차 측정</span></div></figure>
<figure class="card"><figcaption><b>합계는 약 1 Gbps 에서 멈춘다</b><span>회선 합계, Mbps</span></figcaption>{agg_svg()}<p class="cap">32대 이상에서 합계 {AGG} Gbps. 기기를 더 붙여도 늘지 않는다. 이것이 이 구성(역방향 SSH 터널 4개)의 회선 용량이다.</p></figure>
</div>
<div class="chain">
<div class="step"><b>① 실측</b>8대는 한 대가 {N8} Mbps 를 받지만, 16대에서 벌써 {N16} Mbps 로 떨어진다.</div>
<div class="step bad"><b>② 문제</b>32대면 가장 느린 엣지의 기기당 몫이 {SLOWR} Mbps, 가장 느린 기기는 {MINR} Mbps. 원래 값 70 Mbps 를 걸면 병목이 그날그날의 회선 상태가 된다.</div>
<div class="step"><b>③ 축소</b>기기 회선을 0.1배(5/2, 합 7 Mbps)로 걸어 어느 기기든 실측 몫보다 확실히 낮게 했다. 엣지 용량도 같은 비율로 맞췄다(수요 224 = 56×4).</div>
<div class="step"><b>④ 결과</b>병목이 우리가 건 값이라 매번 같은 조건으로 재현된다. 올리기:내리기 5:2 와 부하 비율 1 은 원래와 같다.</div>
</div>
<div class="two">
<div><h3>회선 자체의 크기 (iperf3, 9/7)</h3><div class="scroll"><table><thead><tr><th>구간</th><th>왕복</th><th>HPC→VM 1줄기</th><th>8줄기</th><th>VM→HPC 1줄기</th><th>8줄기</th></tr></thead><tbody>
<tr><th scope='row'>HPC ↔ VM1</th><td>3.9 ms</td><td>453</td><td>2163</td><td>331</td><td>1514</td></tr>
<tr><th scope='row'>HPC ↔ VM2</th><td>4.0 ms</td><td>387</td><td>1294</td><td>310</td><td>275</td></tr>
</tbody></table></div><p class="muted">Mbps. 줄기 하나로는 300~450 Mbps, 여러 줄기면 1.3~2.2 Gbps. VM2 에서 HPC 로 가는 쪽은 줄기를 늘려도 300 Mbps 안팎이다. 원자료 파일은 남아 있지 않아 {gh('docs/02_실험/실측_HPC_VM_연결.md', '실측 문서')} §6 의 기록을 옮겼다.</p></div>
<div><h3>기기 상한을 건 채 쟀을 때 (9/8)</h3><div class="scroll"><table><thead><tr><th>상한 배율</th><th>8대</th><th>16대</th><th>32대</th><th>64대</th></tr></thead><tbody>
<tr><th scope='row'>1배 (70 Mbps)</th><td>1.00</td><td>0.93</td><td class='bad'>0.55</td><td class='bad'>0.33</td></tr>
<tr><th scope='row'>0.5배 (35 Mbps)</th><td>1.00</td><td>0.97</td><td>0.83</td><td class='bad'>0.47</td></tr>
</tbody></table></div><p class="muted">8대일 때 대비 기기당 속도. 1배는 32대에서 절반으로 무너지고, 0.5배도 32대에서 17% 깎인다. 0.4배(20/8)로 32대를 돌려 봤을 때도 전송이 모형 예측 9.6초보다 긴 16.4초가 나왔다(9/9). 그래서 32대는 0.1배로 정했다. 이 측정의 원자료 파일은 뒤 측정에 덮어쓰여 문서 §8 의 표를 옮겼다.</p></div>
</div>
<p class="muted">조건 원장에는 "가장 느린 엣지의 기기당 몫 7~17 Mbps"로 적혀 있다. 남아 있는 원자료로 다시 계산하면 {SLOWR} Mbps(가장 느린 기기 {MINR})다. 어느 쪽이든 실험 상한 7 Mbps 보다 높아 결론은 같다. 원자료: {gh('out/line_raw_run1.jsonl', '1차')} · {gh('out/line_scale.jsonl', '2차')} · {gh('out/line_scale_detail', '기기별 상세', tree=True)}.</p>

<h2>결과 한눈에 — 32대 네 장면</h2>
<div class="panel">{bars()}<div class="leg"><span><i style="background:var(--uni)"></i>스케줄러 없음</span><span><i style="background:var(--acc)"></i>3층 스케줄러</span></div></div>
<p class="muted">세 시드 평균 라운드 시간. 24라운드 중 앞 4라운드를 뺀 평균이다. 세 시드의 차이 범위가 1~2%p 안이라 결과가 시드에 흔들리지 않는다.</p>

<h2>네 장면에서 무슨 일이 있었나</h2>
<div class="scards">{scene_cards()}</div>

<h2>λ — 빠르기와 모델 크기의 저울</h2>
<div class="two">
<div class="panel">{lam_svg()}</div>
<div><p>λ 는 "모델을 줄이는 것"을 라운드 몇 초로 쳐 줄지 정하는 값이다. 작게 주면 모델을 더 줄여 빨라진다. 그림은 8대·200라운드·2시드에서 잰 라운드 시간과 평균 모델 폭이다.</p>
<div class="scroll"><table><thead><tr><th>32대 연산 느림</th><th>없음</th><th>스케줄러</th><th>차이</th><th>평균 폭</th></tr></thead><tbody>{tlam}</tbody></table></div>
<p class="muted">λ=280 은 λ=70 과 같은 답을 냈다(시드 1). 모델을 줄였을 때의 정확도는 아래 FjORD 절을 본다.</p></div>
</div>

<h2>모델을 줄이면 정확도는? — FjORD 참고</h2>
<div class="two">
<div>
<p>우리가 쓰는 "모델 폭 줄이기"는 FjORD(NeurIPS 2021)의 Ordered Dropout 방식이다. 모델의 앞쪽 채널부터 남기고 뒤쪽을 잘라, 폭 p 인 작은 모델이 큰 모델 안에 겹쳐 들어간다.</p>
<p>그래서 폭을 줄였을 때의 정확도는 우리 측정 대신 FjORD 의 결과를 따른다. FjORD 는 CIFAR-10·ResNet18 에서 폭 0.2~1.0 을 기기에 고르게 배정하고 500라운드(100대 중 매 라운드 10%)를 돌렸다. 폭별 정확도는 논문 그림 4 에 그래프로 나와 있다.</p>
<p>논문 본문에 글로 적힌 숫자는 비교 값이다. 지식 증류를 쓴 FjORD 가 비교 방법(eFD)보다 폭에 따라 1.53~34.87%p, 평균 19.22%p 높고, 지식 증류는 폭 0.4 를 넘을 때 일관되게 도움이 된다.</p>
<p class="muted">출처: <a href="https://arxiv.org/abs/2102.13451">Horváth 외, FjORD, NeurIPS 2021 (arXiv 2102.13451)</a> — 그림 4, §5.3.</p>
</div>
<div>
<h3>우리 측정을 쓰지 않는 이유</h3>
<ul>
<li>32대 실험은 24라운드라, 같은 조건을 시드만 바꿔 돌려도 정확도가 4~6점 흔들린다. 폭을 한 칸 줄인 차이보다 흔들림이 더 크다.</li>
<li>우리 실험에서는 늘 같은 느린 기기가 폭을 줄인다. 그러면 그 기기의 데이터가 모델 뒤쪽 채널에 반영되지 않는 편향이 섞인다. FjORD 논문이 지적한 문제이며, 우리 지표로는 이 편향과 폭 자체의 대가를 가를 수 없다.</li>
</ul>
<h3>우리가 모델을 줄인 정도</h3>
<p>32대 장면별 평균 모델 폭(스케줄러, 세 시드, 앞 4라운드 제외): 정상 {res['normal']['width']:.3f} · 몰림 {res['traffic']['width']:.3f} · 연산 느림 {res['slow']['width']:.3f} · 변동 {res['vary']['width']:.3f}. 연산 느림 장면에서는 느린 4대만 0.75 로 줄였다. 8대 결합 실험의 제안 방식은 평균 폭 0.93 이었다.</p>
</div>
</div>

<h2>8대 결합 실험 — 망을 먼저 쓰면 모델을 덜 줄인다</h2>
<p>느린 기기 2·회선 약한 기기 2·정상 4대에 "라운드 10초 안" 목표를 주었다 (3시드, 24라운드). 막대가 길수록 좋다.</p>
<div class="panel">{combo_svg()}</div>
<div class="scroll" style="margin-top:12px"><table><thead><tr><th>망 손잡이만 (8대, 엣지 용량별, 2시드)</th><th>엣지 바꾸기</th><th>+ 나눠 보내기</th></tr></thead><tbody>
<tr><th scope='row'>엣지 넉넉 (수요의 2배)</th><td>−16%</td><td class='hi'>−30%</td></tr>
<tr><th scope='row'>엣지 = 수요</th><td>−50%</td><td class='hi'>−56%</td></tr>
<tr><th scope='row'>엣지 부족 (수요의 절반)</th><td>−64%</td><td class='hi'>−65%</td></tr>
</tbody></table></div>
<p class="muted">출처: {gh('docs/01_제출발표/보고_실험종합_2026-09-08.md', '보고_실험종합_2026-09-08.md')} 의 표.</p>

<h2>기기를 진짜 원격(KOREN VM)에 둬도 같다</h2>
<div class="panel">{vm_svg()}<div class="leg"><span><i style="background:var(--uni)"></i>스케줄러 없음</span><span><i style="background:var(--acc)"></i>3층 스케줄러</span></div></div>
<p class="muted">8대, 시드 1, 앞 10라운드 제외 평균. 절대값 차이는 VM CPU 가 HPC 보다 느려서다. 스케줄러의 행동(느린 기기만 모델 축소, 몰림은 두 라운드 안 복귀)은 두 판이 같았다.</p>

<h2>조건과 선정 배경</h2>
<p>조건 값과 근거 종류는 실험 스크립트가 실제로 읽은 조건 원장({gh('scripts/exp/conditions.json', 'conditions.json')})에서 그대로 가져왔다. "왜 이 값인가"는 원장·사전등록·문헌 근거 문서({gh('docs/03_리서치/설정값_문헌근거.md', '설정값_문헌근거.md')})의 설명을 옮긴 것이다.</p>
<h3>모든 실험에 공통</h3>
<div class="scroll"><table class="cond"><thead><tr><th>항목</th><th>내용</th><th>이유</th></tr></thead><tbody>{TCOMMON}</tbody></table></div>
<h3>32대 시나리오 — 조건</h3>
{C32}
<h3>32대 시나리오 — 장면을 이렇게 만든 이유</h3>
<p>목적(사용자 9/9): 규모 표가 아니라 "일반 상황, 트래픽이 몰릴 때, 연산이 느릴 때 문제가 생기는 순간과 스케줄러가 무엇을 하는가"를 라운드 시간축으로 보이는 것.</p>
<div class="scroll"><table class="cond"><thead><tr><th>장면</th><th>무엇을 넣었나</th><th>왜</th></tr></thead><tbody>{TSC}</tbody></table></div>
<h3>8대 결합 실험 — 조건</h3>
<p>병목 종류가 섞인 8대(연산 느린 2 · 회선 약한 2 · 정상 4)를 두어, 모델 줄이기와 망 손잡이를 따로 또 같이 썼을 때를 비교한다.</p>
{C8}
<h3>λ 스윕 (8대 200라운드) — 조건</h3>
{CACC}
<h3>VM 배치 판 — 조건</h3>
{CVM}
<h3>실험 중에 바뀐 조건</h3>
<div class="scroll"><table class="cond"><thead><tr><th>무엇</th><th>왜</th></tr></thead><tbody>{TCHANGES}</tbody></table></div>

<h2>결과가 GitHub 어디에 있나</h2>
<p>모두 <a href="{GT}">KORAN_SDN-AWARE_NET- 저장소의 awarenet 가지</a>에 있다. 저장소가 비공개라 권한 있는 계정으로 로그인해야 열린다.</p>
<div class="two">
<div class="scroll"><table><thead><tr><th>보고서·판정 기록</th><th>파일</th></tr></thead><tbody>{twhere}</tbody></table></div>
<div class="scroll"><table><thead><tr><th>원자료</th><th>경로 ({gh('out', 'out/', tree=True)})</th></tr></thead><tbody>{traw}</tbody></table></div>
</div>

<footer>생성 scripts/analysis/final_results_page.py (원자료 out/*.jsonl 에서 계산) · 자세한 과정은 이야기 보고·종합 보고·32대 시나리오 정식 보고(out/reports/) 참고.</footer>
</main>
"""
out = os.path.join("out", "reports", "최종결과_AwareNet.html")
io.open(out, "w", encoding="utf-8").write(page)
print(out, len(page) // 1024, "KB")
print("32대:", {k: (round(v['u'], 1), round(v['w'], 1), round(v['d'])) for k, v in res.items()})
print("λ:", [(l, round(u, 1), round(w, 1), round(wd, 2)) for l, u, w, wd in lam])
print("정확도:", [(k, round(ms, 2), round(w, 3), round(a, 1), n) for k, ms, w, a, n in acc_rows])
print("VM:", [(s, wh, round(a, 1), round(b, 1), round(d)) for s, wh, a, b, d in vm])
