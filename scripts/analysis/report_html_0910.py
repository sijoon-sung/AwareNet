# -*- coding: utf-8 -*-
"""종합 보고 HTML(2026-09-10 판) 생성 — out/reports/종합보고_2026-09-10.html. 몰림·변동 시간축 SVG 는 최종 jsonl 에서 그린다.
    python scripts/analysis/report_html_0910.py"""
import io, json, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CSS = """<title>AwareNet 실험 종합 보고</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{--bg:#F6F8F5;--ink:#1B2320;--muted:#5B6660;--line:#D7DED8;--panel:#FFFFFF;--acc:#1F6F5B;--acc-soft:#DCEDE6;--warm:#B9651F;--warm-soft:#F6E5D5;--grid:#E6EBE6;--s1:#eb6834;--s2:#2a78d6;--shade:rgba(185,101,31,.10)}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#141917;--ink:#E7ECE8;--muted:#9BA69F;--line:#2B332F;--panel:#1C2320;--acc:#63C3A6;--acc-soft:#1E3A32;--warm:#E39A5C;--warm-soft:#3D2A1A;--grid:#27302B;--s1:#d95926;--s2:#3987e5;--shade:rgba(227,154,92,.12)}}
:root[data-theme="dark"]{--bg:#141917;--ink:#E7ECE8;--muted:#9BA69F;--line:#2B332F;--panel:#1C2320;--acc:#63C3A6;--acc-soft:#1E3A32;--warm:#E39A5C;--warm-soft:#3D2A1A;--grid:#27302B;--s1:#d95926;--s2:#3987e5;--shade:rgba(227,154,92,.12)}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:"IBM Plex Sans KR","Noto Sans KR","Apple SD Gothic Neo","Malgun Gothic",sans-serif;font-size:15.5px;line-height:1.7;-webkit-font-smoothing:antialiased}
.wrap{max-width:820px;margin:0 auto;padding:40px 20px 80px}
header{border-bottom:1px solid var(--line);padding-bottom:22px;margin-bottom:34px}
.eyebrow{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);font-weight:600}
h1{font-size:30px;line-height:1.25;margin:8px 0 10px;font-weight:700;text-wrap:balance;letter-spacing:-.01em}
.lede{font-size:17px;color:var(--ink);margin:0;max-width:64ch}
.meta{margin-top:14px;font-size:13px;color:var(--muted);font-family:"IBM Plex Mono",monospace}
h2{font-size:20px;margin:44px 0 12px;padding-top:8px;font-weight:700;letter-spacing:-.005em;text-wrap:balance}
p{margin:0 0 12px;max-width:66ch}
ul{margin:0 0 14px;padding-left:20px;max-width:66ch}
li{margin:4px 0}
.verdict{background:var(--acc-soft);border-left:4px solid var(--acc);padding:14px 18px;border-radius:0 6px 6px 0;margin:18px 0 26px;max-width:none}
.verdict p{margin:0;max-width:none;font-size:16px}
.tbl{overflow-x:auto;margin:12px 0 18px;border:1px solid var(--line);border-radius:6px;background:var(--panel)}
table{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}
th,td{padding:8px 12px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top;white-space:nowrap}
th{font-size:12.5px;letter-spacing:.04em;color:var(--muted);font-weight:600;background:transparent}
tr:last-child td{border-bottom:none}
td.num,th.num{text-align:right;font-family:"IBM Plex Mono",monospace;font-size:13.5px}
td.hi{color:var(--acc);font-weight:600}
td.lo{color:var(--warm);font-weight:600}
td.w{white-space:normal;min-width:20ch}
.cap{font-size:13px;color:var(--muted);margin:-8px 0 18px;max-width:70ch}
figure{margin:18px 0 24px;background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:16px 16px 10px}
figure svg{width:100%;height:auto;display:block}
figcaption{font-size:13px;color:var(--muted);margin-top:6px}
.legend{font-size:12.5px;color:var(--muted);margin:4px 0}.legend i{display:inline-block;width:14px;height:3px;vertical-align:middle;margin:0 6px 0 12px;border-radius:2px}
code{font-family:"IBM Plex Mono",monospace;font-size:13px;background:var(--panel);border:1px solid var(--line);padding:0 5px;border-radius:4px}
a{color:var(--acc)}
</style>
"""


def rows(f):
    return [json.loads(l) for l in io.open(f, encoding="utf-8") if '"round"' in l]


def chart(U, W, a, b, txt):
    n = len(U); Wd, H = 760, 230; l, r, t, bm = 50, 14, 14, 28
    ymax = max([x["makespan"] for x in U] + [x["makespan"] for x in W]) * 1.12
    x = lambda i: l + (Wd - l - r) * i / (n - 1); y = lambda v: H - bm - (H - bm - t) * v / ymax
    g = [f'<rect x="{x(a):.1f}" y="{t}" width="{x(b) - x(a):.1f}" height="{H - bm - t}" fill="var(--shade)"/>',
         f'<text x="{x(a) + 6:.1f}" y="{t + 14}" font-size="11" fill="var(--muted)">{txt} (R{a}~{b})</text>']
    for k in range(5):
        v = ymax * k / 4
        g.append(f'<line x1="{l}" x2="{Wd - r}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="var(--grid)"/><text x="{l - 6}" y="{y(v) + 4:.1f}" text-anchor="end" font-size="11" fill="var(--muted)">{v:.0f}s</text>')
    for i in range(0, n, 4):
        g.append(f'<text x="{x(i):.1f}" y="{H - 8}" text-anchor="middle" font-size="11" fill="var(--muted)">R{i}</text>')
    for R, col in ((U, "var(--s1)"), (W, "var(--s2)")):
        pts = " ".join(f"{x(i):.1f},{y(v['makespan']):.1f}" for i, v in enumerate(R))
        g.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2.2" stroke-linejoin="round"/>')
    return f'<svg viewBox="0 0 {Wd} {H}" xmlns="http://www.w3.org/2000/svg" font-family="IBM Plex Sans KR, sans-serif">{"".join(g)}</svg>'


def main():
    U = rows("out/wp_scen32_traffic_s1_bothmp_uniform.jsonl"); W = rows("out/wp_scen32_traffic_s1_bothmp_widthpath.jsonl")
    Uv = rows("out/wp_scen32_vary_s1_bothmp_uniform.jsonl"); Wv = rows("out/wp_scen32_vary_s1_bothmp_widthpath.jsonl")
    svg_t = chart(U, W, 8, 20, "엣지 1 용량 1/4"); svg_v = chart(Uv, Wv, 8, 20, "엣지 1 용량 56→14→56 한 칸씩")
    body = io.open("scripts/analysis/report_html_0910_body.html", encoding="utf-8").read()
    html = CSS + body.replace("__SVG_TRAFFIC__", svg_t).replace("__SVG_VARY__", svg_v)
    io.open("out/reports/종합보고_2026-09-10.html", "w", encoding="utf-8").write(html)
    print(f"→ out/reports/종합보고_2026-09-10.html ({len(html) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
