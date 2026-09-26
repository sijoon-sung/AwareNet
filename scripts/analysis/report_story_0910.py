# -*- coding: utf-8 -*-
"""이야기 보고 (2026-09-10): 본 문제 → 만든 시스템 → 생긴 문제와 해결(고치기 전/후) → 결과 시각화 → 무엇이 나아졌나.
    python scripts/analysis/report_story_0910.py   → out/reports/이야기보고_2026-09-10.html
입력: out/line_raw_run1.jsonl, out/wp_scen32_*_s1_bothmp_{uniform,widthpath}.jsonl, out/story/<이전 판>/…, out/story/combo/…"""
import glob, io, json, os, statistics as st, sys
from collections import Counter
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

C = {"u": "var(--s1)", "p": "var(--s2)", "g": "var(--muted)", "k": "var(--ink)", "grid": "var(--grid)", "shade": "var(--shade)",
     "t1": "#c9a227", "t2": "#8e5bd6", "t3": "#d94f7a", "t4": "#3aa0a0"}


def rows(f):
    return [json.loads(l) for l in io.open(f, encoding="utf-8") if '"round"' in l] if os.path.exists(f) else []


def line_chart(series, W=760, H=240, ymax=None, xlab="R", ylab="s", shade=None, xs=None, legend=True, ystep=None):
    """series: [(name, [y...], color, dash)] — x 는 0..n-1 (또는 xs). shade: (a, b, txt)."""
    n = max(len(s[1]) for s in series); l, r, t, b = 52, 16, 16, 30
    ymax = ymax or max(v for s in series for v in s[1] if v is not None) * 1.12
    X = xs or list(range(n))
    x = lambda i: l + (W - l - r) * (X[i] - X[0]) / max(1e-9, X[-1] - X[0]); y = lambda v: H - b - (H - b - t) * v / ymax
    g = []
    if shade:
        a, bb, txt = shade
        g.append(f'<rect x="{x(a):.1f}" y="{t}" width="{x(bb) - x(a):.1f}" height="{H - b - t}" fill="{C["shade"]}"/>')
        g.append(f'<text x="{x(a) + 6:.1f}" y="{t + 13}" font-size="11" fill="{C["g"]}">{txt}</text>')
    ticks = 5
    for k in range(ticks):
        v = ymax * k / (ticks - 1)
        g.append(f'<line x1="{l}" x2="{W - r}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="{C["grid"]}"/><text x="{l - 6}" y="{y(v) + 4:.1f}" text-anchor="end" font-size="11" fill="{C["g"]}">{v:.0f}{ylab}</text>')
    step = max(1, n // 6) if not xs else 1
    for i in range(0, n, step):
        g.append(f'<text x="{x(i):.1f}" y="{H - 8}" text-anchor="middle" font-size="11" fill="{C["g"]}">{xlab}{X[i]}</text>')
    for name, ys, col, dash in series:
        pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(ys) if v is not None)
        da = ' stroke-dasharray="5 4"' if dash else ""
        g.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2.2" stroke-linejoin="round"{da}/>')
    if legend:
        lx = l + 8
        for name, ys, col, dash in series:
            da = ' stroke-dasharray="5 4"' if dash else ""
            g.append(f'<line x1="{lx}" x2="{lx + 16}" y1="{t + 6}" y2="{t + 6}" stroke="{col}" stroke-width="3"{da}/><text x="{lx + 20}" y="{t + 10}" font-size="11.5" fill="{C["k"]}">{name}</text>')
            lx += 26 + 7.2 * len(name)
    return f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" font-family="IBM Plex Sans KR, sans-serif">{"".join(g)}</svg>'


def strip_chart(Wp, W=760):
    """기기 × 라운드 격자: 색 = 엣지(1~4), 글자 = 폭(0.75 → ·)."""
    ks = sorted(Wp[-1]["paths"], key=lambda s: int(s[1:])); N = len(ks); n = len(Wp); rowh = 7; H = 22 + N * rowh
    cols = {"1": "#e34948", "2": "#eda100", "3": "#1baf7a", "4": "#2a78d6"}
    cw = (W - 70) / n; g = []
    for i in range(0, n, 4):
        g.append(f'<text x="{60 + cw * i + cw / 2:.1f}" y="12" text-anchor="middle" font-size="10" fill="{C["g"]}">R{i}</text>')
    for j, k in enumerate(ks):
        yy = 18 + j * rowh
        if j % 4 == 0:
            g.append(f'<text x="54" y="{yy + 6}" text-anchor="end" font-size="8.5" fill="{C["g"]}">{k}</text>')
        for i, r in enumerate(Wp):
            e = str(r["paths"][k]).split("+")[0]; w = float(r["plan"].get(k, 1.0))
            g.append(f'<rect x="{60 + cw * i:.1f}" y="{yy}" width="{cw - 1:.1f}" height="{rowh - 1.2}" fill="{cols.get(e, "#999")}" opacity="{0.9 if w >= 1 else 0.45}"><title>{k} R{i} 엣지 {e} 폭 {w}</title></rect>')
    lg = " ".join(f'<rect x="{60 + 90 * i}" y="{H - 2}" width="10" height="6" fill="{c}"/><text x="{74 + 90 * i}" y="{H + 4}" font-size="10" fill="{C["g"]}">엣지 {e}</text>' for i, (e, c) in enumerate(cols.items()))
    return f'<svg viewBox="0 0 {W} {H + 10}" xmlns="http://www.w3.org/2000/svg" font-family="IBM Plex Sans KR, sans-serif">{"".join(g)}{lg}<text x="{W - 10}" y="{H + 4}" text-anchor="end" font-size="10" fill="{C["g"]}">연하게 = 폭 0.75 이하</text></svg>'


def scatter(points, W=520, H=240):
    """(x=평균 폭, y=라운드 s, 이름, 색)."""
    l, r, t, b = 52, 16, 16, 34; xmin, xmax = 0.6, 1.02; ymax = max(p[1] for p in points) * 1.15
    x = lambda v: l + (W - l - r) * (v - xmin) / (xmax - xmin); y = lambda v: H - b - (H - b - t) * v / ymax
    g = []
    for k in range(5):
        v = ymax * k / 4; g.append(f'<line x1="{l}" x2="{W - r}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="{C["grid"]}"/><text x="{l - 6}" y="{y(v) + 4:.1f}" text-anchor="end" font-size="11" fill="{C["g"]}">{v:.0f}s</text>')
    for v in (0.6, 0.7, 0.8, 0.9, 1.0):
        g.append(f'<text x="{x(v):.1f}" y="{H - 10}" text-anchor="middle" font-size="11" fill="{C["g"]}">{v:.1f}</text>')
    g.append(f'<text x="{(l + W - r) / 2:.0f}" y="{H + 2}" text-anchor="middle" font-size="11" fill="{C["g"]}">평균 모델 폭 (1.0 = 안 줄임)</text>')
    pts = sorted(points)
    g.append(f'<polyline points="{" ".join(f"{x(p[0]):.1f},{y(p[1]):.1f}" for p in pts if p[3] == C["p"])}" fill="none" stroke="{C["p"]}" stroke-width="1.5" stroke-dasharray="4 4"/>')
    for px, py, name, col in points:
        g.append(f'<circle cx="{x(px):.1f}" cy="{y(py):.1f}" r="6" fill="{col}"/><text x="{x(px) + 9:.1f}" y="{y(py) + 4:.1f}" font-size="11.5" fill="{C["k"]}">{name}</text>')
    return f'<svg viewBox="0 0 {W} {H + 8}" xmlns="http://www.w3.org/2000/svg" font-family="IBM Plex Sans KR, sans-serif">{"".join(g)}</svg>'


def bars(items, W=760, H=200, unit="", vmax=None):
    """가로 막대: [(이름, 값, 색, 라벨)]."""
    vmax = vmax or max(v for _, v, _, _ in items) * 1.15; rowh = (H - 20) / len(items); g = []
    for i, (name, v, col, lab) in enumerate(items):
        yy = 10 + i * rowh; bw = (W - 200) * v / vmax
        g.append(f'<text x="150" y="{yy + rowh * 0.65:.1f}" text-anchor="end" font-size="12.5" fill="{C["k"]}">{name}</text>')
        g.append(f'<rect x="160" y="{yy + rowh * 0.2:.1f}" width="{bw:.1f}" height="{rowh * 0.6:.1f}" rx="2" fill="{col}"/>')
        g.append(f'<text x="{166 + bw:.1f}" y="{yy + rowh * 0.65:.1f}" font-size="12" font-family="IBM Plex Mono, monospace" fill="{C["k"]}">{lab}</text>')
    return f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" font-family="IBM Plex Sans KR, sans-serif">{"".join(g)}</svg>'


def mean_ms(R, skip=4):
    return st.mean(r["makespan"] for r in R[skip:]) if len(R) > skip else float("nan")


def main():
    U = {s: rows(f"out/wp_scen32_{s}_s1_bothmp_uniform.jsonl") for s in ("normal", "traffic", "slow", "vary", "slow_l18", "slow_l280")}
    P = {s: rows(f"out/wp_scen32_{s}_s1_bothmp_widthpath.jsonl") for s in U}
    ms = lambda R: [r["makespan"] for r in R]
    # 그림 1: 회선 규모
    raw = [json.loads(l) for l in io.open("out/line_raw_run1.jsonl", encoding="utf-8")]
    bat = sorted([(x["n"], x["per_client_mbps_median"]) for x in raw if x["pattern"] == "batch"])
    fig1 = line_chart([("기기당 실효 Mbps (맨 회선, 왕복 패턴)", [v for _, v in bat], C["p"], False)], H=220, xs=[n for n, _ in bat], xlab="N=", ylab="M", legend=True)
    # 그림 2: 8대 결합 (3시드 평균, 데이터_기록 9/8)
    fig2 = bars([("아무것도 안 함", 1.00, C["g"], "폭 1.00 · 정확도 25% · 10초 안 0%"), ("모델만 줄임(단순 분할학습)", 0.55, C["u"], "폭 0.55 · 정확도 17% · 95%"),
                 ("망만(엣지+나눔)", 1.00, C["g"], "폭 1.00 · 정확도 26% · 76%"), ("모델+엣지", 0.82, C["u"], "폭 0.82 · 정확도 23% · 95%"),
                 ("모델+엣지+나눔 (제안)", 0.93, C["p"], "폭 0.93 · 정확도 26% · 100%")], H=190, vmax=1.15)
    # 그림 3: 32대 스케줄러 없음 — 문제 자체
    fig3 = line_chart([("정상", ms(U["normal"]), C["g"], False), ("트래픽 몰림 (R8~19 엣지 1 용량 1/4)", ms(U["traffic"]), C["u"], False),
                       ("연산 느림 (4대 0.15)", ms(U["slow"]), C["t1"], False), ("변동 (56→14→56)", ms(U["vary"]), C["t2"], False)], H=250, shade=(8, 20, "교란 구간"))
    # 그림 4: 몰림 계획 팔의 진화 (고치기 전 → 후)
    ev = [("① 9/9 2차: 인지가 엣지 용량을 모름 — 이동 0, 폭만 축소", "out/story/scen32_v2_traffic_old/wp_scen32_traffic_s1_bothmp_widthpath.jsonl", C["t1"]),
          ("② 최종 1차: 이동 1대/라운드 — 8라운드 걸려 비움", "out/story/scen32_final_try1/wp_scen32_traffic_s1_bothmp_widthpath.jsonl", C["t2"]),
          ("③ 경로 비용 총합: 잔류 3대·회선 하나 → 65 s 고착", "out/story/scen32_final_try3/wp_scen32_traffic_s1_bothmp_widthpath.jsonl", C["t3"]),
          ("④ '포화 아님 = 회복'으로 읽음 → 4라운드 주기 되돌아감", "out/story/scen32_final_try4/wp_scen32_traffic_s1_bothmp_widthpath.jsonl", C["t4"]),
          ("⑤ 최종: 단계 상승·유지 구간·걸친 기기 제외", "out/wp_scen32_traffic_s1_bothmp_widthpath.jsonl", C["p"])]
    ser = [("스케줄러 없음", ms(U["traffic"]), C["u"], True)]
    for name, f, col in ev:
        R = rows(f)
        if len(R) >= 14:
            ser.append((name, ms(R), col, False))
    fig4 = line_chart(ser, H=300, shade=(8, 20, "엣지 1 용량 1/4"), legend=False)
    leg4 = "".join(f'<li><i style="background:{col}"></i>{name}</li>' for name, ys, col, d in ser)
    # 그림 5: 최종 4장면 (없음 vs 있음)
    figs5 = {}
    for s, title, sh in (("traffic", "트래픽 몰림", (8, 20, "엣지 1 용량 1/4")), ("vary", "변동", (8, 20, "56→14→56 한 칸씩")), ("slow", "연산 느림", None), ("normal", "정상", None)):
        figs5[s] = line_chart([("스케줄러 없음", ms(U[s]), C["u"], False), ("스케줄러 있음", ms(P[s]), C["p"], False)], H=220, shade=sh)
    # 그림 6: λ 눈금
    def wavg(R):
        return st.mean(sum(float(v) for v in r["plan"].values()) / len(r["plan"]) for r in R[4:])
    fig6 = scatter([(1.0, mean_ms(U["slow"]), "스케줄러 없음", C["u"]), (wavg(P["slow_l280"]), mean_ms(P["slow_l280"]), "λ=280", C["p"]),
                    (wavg(P["slow"]), mean_ms(P["slow"]), "λ=70", C["p"]), (wavg(P["slow_l18"]), mean_ms(P["slow_l18"]), "λ=18", C["p"])])
    # 그림 7: 몰림 기기 띠
    fig7 = strip_chart(P["traffic"])
    # 그림 8: λ 눈금 — 정확도 축 (8대 200R, 2시드 평균; acc_lambda_table 과 같은 계산)
    import re as _re
    accs = {}
    for f in glob.glob("out/wp_r8mix_acc*_s*_bothmp_widthpath.jsonl"):
        m = _re.match(r"wp_r8mix_acc(_l(\d+))?_s(\d+)_bothmp_widthpath\.jsonl", os.path.basename(f)); lam = int(m.group(2)) if m.group(2) else 70
        R = rows(f); Ru = rows(f.replace("_widthpath", "_uniform"))
        for key, RR in ((lam, R), (0, Ru)):
            a = st.mean(r["acc"] for r in RR[-50:] if r.get("acc") is not None); w = st.mean(sum(float(v) for v in r["plan"].values()) / len(r["plan"]) for r in RR[4:])
            accs.setdefault(key, []).append((w, mean_ms(RR), a))
    pts8 = [(st.mean(v[0] for v in L), st.mean(v[1] for v in L), ("스케줄러 없음" if lam == 0 else f"λ={lam}") + f" · {100 * st.mean(v[2] for v in L):.1f}%", C["u"] if lam == 0 else C["p"]) for lam, L in sorted(accs.items())] if accs else []
    fig8 = scatter(pts8, W=760) if pts8 else ""
    # 개선 표
    def imp(s):
        return mean_ms(U[s]), mean_ms(P[s])
    tr_u, tr_p = imp("traffic"); va_u, va_p = imp("vary"); sl_u, sl_p = imp("slow"); no_u, no_p = imp("normal")
    peak_u = max(ms(U["traffic"])[8:20]); plat = st.mean(ms(P["traffic"])[12:20]); vpk_u = max(ms(U["vary"])); vpk_p = max(ms(P["vary"]))
    old = rows("out/story/scen32_v2_traffic_old/wp_scen32_traffic_s1_bothmp_widthpath.jsonl"); old_plat = st.mean(ms(old)[12:20]) if len(old) >= 20 else float("nan")
    t3 = rows("out/story/scen32_final_try3/wp_scen32_traffic_s1_bothmp_widthpath.jsonl"); t3_plat = st.mean(ms(t3)[12:23]) if len(t3) >= 23 else float("nan")
    body = io.open("scripts/analysis/report_story_0910_body.html", encoding="utf-8").read()
    rep = {"__FIG1__": fig1, "__FIG2__": fig2, "__FIG3__": fig3, "__FIG4__": fig4, "__LEG4__": leg4, "__FIG5T__": figs5["traffic"], "__FIG5V__": figs5["vary"], "__FIG5S__": figs5["slow"], "__FIG5N__": figs5["normal"],
           "__FIG6__": fig6, "__FIG7__": fig7, "__FIG8__": fig8,
           "__FIG9__": "<img style=\"width:100%;height:auto;display:block\" alt=\"분할 LoRA 크기 사다리\" src=\"data:image/png;base64," + __import__("base64").b64encode(open("out/reports/scale_lora_0913.png","rb").read()).decode() + "\">",
           "__TR_U__": f"{tr_u:.1f}", "__TR_P__": f"{tr_p:.1f}", "__TR_D__": f"{100 * (tr_p / tr_u - 1):+.0f}", "__PEAK_U__": f"{peak_u:.0f}", "__PLAT__": f"{plat:.0f}",
           "__VA_U__": f"{va_u:.1f}", "__VA_P__": f"{va_p:.1f}", "__VA_D__": f"{100 * (va_p / va_u - 1):+.0f}", "__VPK_U__": f"{vpk_u:.0f}", "__VPK_P__": f"{vpk_p:.0f}",
           "__SL_U__": f"{sl_u:.1f}", "__SL_P__": f"{sl_p:.1f}", "__SL_D__": f"{100 * (sl_p / sl_u - 1):+.0f}", "__NO_U__": f"{no_u:.1f}", "__NO_P__": f"{no_p:.1f}",
           "__OLD_PLAT__": f"{old_plat:.0f}", "__T3_PLAT__": f"{t3_plat:.0f}", "__L18_W__": f"{wavg(P['slow_l18']):.2f}", "__L18_MS__": f"{mean_ms(P['slow_l18']):.1f}"}
    html = io.open("scripts/analysis/report_story_0910_head.html", encoding="utf-8").read() + body
    for k, v in rep.items():
        html = html.replace(k, v)
    io.open("out/reports/이야기보고_2026-09-10.html", "w", encoding="utf-8").write(html)
    print(f"→ out/reports/이야기보고_2026-09-10.html ({len(html) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
