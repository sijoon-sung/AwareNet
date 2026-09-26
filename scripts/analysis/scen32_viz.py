# -*- coding: utf-8 -*-
"""32대 시나리오 시간축 페이지 — out/scen32_viz.json(scen32_report.py 가 만듦) → out/reports/scen32_시간축.html (자기 완결 HTML, 라이브러리 없음).
    python scripts/analysis/scen32_report.py && python scripts/analysis/scen32_viz.py
장면마다: 라운드 시간(스케줄러 없음 vs 있음, 교란 구간 음영) · 기기별 띠(폭 = 색, 엣지 = 숫자) · 이동·폭 변경 횟수."""
import io, json, os, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
SRC = "out/scen32_viz.json"; DST = "out/reports/scen32_시간축.html"
NAME = {"normal": "정상", "traffic": "트래픽 몰림", "slow": "연산 느림", "vary": "변동", "slow_l18": "연산 느림 · λ=18 (관대)", "slow_l280": "연산 느림 · λ=280 (엄격)"}
EVENT = {"traffic": [(8, 20, "엣지 1 용량 1/4")], "vary": [(8, 20, "엣지 1 용량 56→14→56 한 칸씩")]}
CSS = """
:root{--bg:#F6F8F5;--ink:#1B2320;--muted:#5B6660;--line:#D7DED8;--panel:#fff;--grid:#E6EBE6;--s1:#eb6834;--s2:#2a78d6;--shade:rgba(185,101,31,.10)}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#141917;--ink:#E7ECE8;--muted:#9BA69F;--line:#2B332F;--panel:#1C2320;--grid:#27302B;--s1:#d95926;--s2:#3987e5;--shade:rgba(227,154,92,.12)}}
:root[data-theme="dark"]{--bg:#141917;--ink:#E7ECE8;--muted:#9BA69F;--line:#2B332F;--panel:#1C2320;--grid:#27302B;--s1:#d95926;--s2:#3987e5;--shade:rgba(227,154,92,.12)}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:"IBM Plex Sans KR","Noto Sans KR",sans-serif;font-size:15px;line-height:1.6}
.wrap{max-width:960px;margin:0 auto;padding:32px 20px 60px}h1{font-size:26px;margin:4px 0 6px}.lede{color:var(--muted);max-width:66ch;margin:0 0 20px}
h2{font-size:18px;margin:34px 0 6px}figure{margin:10px 0 6px;background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:12px 12px 6px}
figure svg{width:100%;height:auto;display:block}figcaption{font-size:13px;color:var(--muted);margin-top:6px}
.legend{font-size:12.5px;color:var(--muted);margin:4px 0}.legend i{display:inline-block;width:14px;height:3px;vertical-align:middle;margin:0 6px 0 12px;border-radius:2px}
.kv{display:flex;gap:10px;flex-wrap:wrap;margin:8px 0 4px}.kv div{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:8px 12px;font-size:13px}
.kv b{font-family:"IBM Plex Mono",monospace;font-size:16px}.note{font-size:13px;color:var(--muted);max-width:70ch}
"""


def line_chart(sc, d):
    U, W = d["uniform"], d["plan"]; n = max(len(U), len(W)); Wd, H = 900, 260; pad = dict(l=52, r=16, t=14, b=30)
    ymax = max([r["ms"] for r in U] + [r["ms"] for r in W]) * 1.12
    x = lambda i: pad["l"] + (Wd - pad["l"] - pad["r"]) * i / max(1, n - 1); y = lambda v: H - pad["b"] - (H - pad["b"] - pad["t"]) * v / ymax
    g = []
    for (a, b, txt) in EVENT.get(sc, []):
        g.append(f'<rect x="{x(a)}" y="{pad["t"]}" width="{x(b) - x(a)}" height="{H - pad["b"] - pad["t"]}" fill="var(--shade)"/>')
        g.append(f'<text x="{x(a) + 6}" y="{pad["t"] + 14}" font-size="11" fill="var(--muted)">{txt} (R{a}~{b})</text>')
    for k in range(5):
        v = ymax * k / 4; g.append(f'<line x1="{pad["l"]}" x2="{Wd - pad["r"]}" y1="{y(v)}" y2="{y(v)}" stroke="var(--grid)"/><text x="{pad["l"] - 6}" y="{y(v) + 4}" text-anchor="end" font-size="11" fill="var(--muted)">{v:.0f}s</text>')
    for i in range(0, n, 4):
        g.append(f'<text x="{x(i)}" y="{H - 8}" text-anchor="middle" font-size="11" fill="var(--muted)">R{i}</text>')
    for rows, col, name in ((U, "var(--s1)", "스케줄러 없음"), (W, "var(--s2)", "스케줄러 있음")):
        pts = " ".join(f"{x(i)},{y(r['ms'])}" for i, r in enumerate(rows))
        g.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2" stroke-linejoin="round"/>')
        if rows:
            g.append(f'<text x="{x(len(rows) - 1) - 4}" y="{y(rows[-1]["ms"]) - 8}" text-anchor="end" font-size="12" fill="var(--ink)">{name} {rows[-1]["ms"]:.0f}s</text>')
    return f'<svg viewBox="0 0 {Wd} {H}">{"".join(g)}</svg>'


def strip_chart(d):
    W = d["plan"]; n = len(W)
    if not n:
        return ""
    ks = sorted(W[-1]["w"], key=lambda s: int(s[1:])); N = len(ks); Wd = 900; rowh = 9; H = 24 + N * rowh
    x = lambda i: 60 + (Wd - 76) * i / n
    g = []
    for j, k in enumerate(ks):
        yy = 18 + j * rowh
        if j % 4 == 0:
            g.append(f'<text x="54" y="{yy + 7}" text-anchor="end" font-size="9" fill="var(--muted)">{k}</text>')
        for i, r in enumerate(W):
            w = r["w"].get(k, 1.0); p = str((r.get("paths") or {}).get(k, "1")).split("+")[0]
            col = {1.0: "#1baf7a", 0.75: "#eda100", 0.5: "#e34948"}.get(float(w), "#999")
            g.append(f'<rect x="{x(i)}" y="{yy}" width="{(Wd - 76) / n - 1}" height="{rowh - 1.5}" fill="{col}" opacity=".85"><title>{k} R{i} 폭 {w} 엣지 {p}</title></rect>')
            g.append(f'<text x="{x(i) + 3}" y="{yy + 7}" font-size="7" fill="#fff">{p}</text>')
    return f'<svg viewBox="0 0 {Wd} {H}">{"".join(g)}</svg>'


def main():
    if not os.path.exists(SRC):
        print(f"{SRC} 없음 — scen32_report.py 먼저"); return 1
    V = json.load(io.open(SRC, encoding="utf-8")); os.makedirs("out/reports", exist_ok=True)
    body = []
    for sc in ("normal", "traffic", "slow", "vary", "slow_l18", "slow_l280"):
        if sc not in V:
            continue
        d = V[sc]; U, W = d["uniform"], d["plan"]
        um = sum(r["ms"] for r in U[4:]) / max(1, len(U[4:])); wm = sum(r["ms"] for r in W[4:]) / max(1, len(W[4:]))
        moves = sum(1 for a, b in zip(W, W[1:]) if a.get("paths") != b.get("paths")); flips = sum(1 for a, b in zip(W, W[1:]) if a.get("w") != b.get("w"))
        wsum = sum(W[-1]["w"].values()) / max(1, len(W[-1]["w"])) if W else 1.0
        body.append(f'<h2>{NAME.get(sc, sc)}</h2>')
        body.append(f'<div class="kv"><div>스케줄러 없음 평균 <b>{um:.1f}s</b></div><div>스케줄러 있음 평균 <b>{wm:.1f}s</b> ({100 * (wm / um - 1):+.0f}%)</div><div>마지막 모델 폭 평균 <b>{wsum:.2f}</b></div><div>이동 <b>{moves}</b>회 · 폭 변경 <b>{flips}</b>회</div></div>')
        body.append('<div class="legend"><i style="background:var(--s1)"></i>스케줄러 없음 <i style="background:var(--s2)"></i>스케줄러 있음 · 음영 = 교란 구간</div>')
        body.append(f'<figure>{line_chart(sc, d)}<figcaption>라운드마다 걸린 시간(초). 라운드는 가장 느린 기기가 정합니다.</figcaption></figure>')
        body.append(f'<figure>{strip_chart(d)}<figcaption>스케줄러 있음: 기기 {len(W[-1]["w"]) if W else 0}대의 라운드별 모델 폭(초록 1.0 · 노랑 0.75 · 빨강 0.5)과 엣지 번호.</figcaption></figure>')
    html = f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>32대 시나리오 시간축</title><style>{CSS}</style></head><body><div class="wrap"><h1>32대 시나리오 — 문제가 생기는 순간과 스케줄러의 대응</h1><p class="lede">HPC 기기 32대 → KOREN 엣지 4개 → 서버. 기기당 5/2 Mbps, 엣지 56 Mbps × 4, 결합 최적화 λ=70. 스케줄러 없음 = 회선 하나·고정 배정·전폭.</p>{"".join(body)}<p class="note">데이터: out/wp_scen32_*_s1_bothmp_{{uniform,widthpath}}.jsonl · 조건: scripts/exp/conditions.json r32/r32_slow · 사전등록: docs/02_실험/실험_시나리오_32대_사전등록.md</p></div></body></html>'
    io.open(DST, "w", encoding="utf-8").write(html); print(f"→ {DST} ({len(html) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
