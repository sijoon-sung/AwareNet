# -*- coding: utf-8 -*-
"""연합 분할 LoRA 문답 증명 — 보고 페이지 생성 (2026-09-13)
   python scripts/analysis/fed_split_page.py --eval-tag 0913v1 --run-tag 0913  → out/reports/연합문답_증명_2026-09-13.html
   입력: out/fed_split/eval_<eval-tag>.json (grid·canary), strict_<eval-tag>.json (사람이 읽은 엄격 판정),
         server_{fed3,fed3v1}_<run-tag>.jsonl, device_fed3_<run-tag>_c*.jsonl
   모델 이름 규약: "베이스", "단독(…)", "연합(B1+B2+B3)"(뒷단 공유), "연합·뒷단도 평균(v1)"(선택)"""
import argparse
import glob
import html
import io
import json
import os
import sys

sys.path.insert(0, "sfl")
from lora_corpus import load   # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--eval-tag", default="0913v1"); ap.add_argument("--run-tag", default="0913")
a = ap.parse_args()
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
D = os.path.join(ROOT, "out", "fed_split")
ev = json.load(io.open(os.path.join(D, f"eval_{a.eval_tag}.json"), encoding="utf-8"))
grid, canary = ev["grid"], ev["canary"]
sp = os.path.join(D, f"strict_{a.eval_tag}.json")
strict = {k: v for k, v in json.load(io.open(sp, encoding="utf-8")).items() if not k.startswith("_")} if os.path.exists(sp) else {}
DOMS = ["B1", "B2", "B3"]
NAMES = list(grid.keys())
BASE = NAMES[0]
SINGLE = next(n for n in NAMES if n.startswith("단독"))
FED = next(n for n in NAMES if n.startswith("연합") and "v1" not in n)
FEDV1 = next((n for n in NAMES if "v1" in n), None)
DEV = {"B1": "기기 c0 · VM1", "B2": "기기 c1 · VM1", "B3": "기기 c2 · VM2"}
SECRET = "ZX-4471-QM97"
e = lambda s: html.escape(str(s)).replace('�', '&#xFFFD;')   # 기본 모델 답이 32토큰에서 글자 중간에 잘려 생긴 대체 문자 — 게시 검사가 원문 U+FFFD 를 거부


def ok_of(name, d, i):
    det = grid[name][d]["detail"][i]
    return strict.get(name, {}).get(det["q"], det["ok"])


def acc(name, d, use_strict=True):
    det = grid[name][d]["detail"]
    return sum((ok_of(name, d, i) if use_strict else det[i]["ok"]) for i in range(len(det))), len(det)


def pct(name, d):
    h, n = acc(name, d); return 100.0 * h / n


def cls_of(name):
    return "base" if name == BASE else "single" if name == SINGLE else "fedv1" if name == FEDV1 else "fed"


facts = {}
for d in DOMS:
    seen = {}
    for r in load(d):
        seen.setdefault(tuple(r["keywords"]), r["a"])
    facts[d] = list(seen.values())


def jl(path):
    return [json.loads(l) for l in io.open(path, encoding="utf-8") if l.strip()] if os.path.exists(path) else []


losses = {}
for f in sorted(glob.glob(os.path.join(D, f"device_fed3_{a.run_tag}_c*.jsonl"))):
    cid = os.path.basename(f).rsplit("_", 1)[-1].replace(".jsonl", "")
    losses[cid] = [r["loss_mean"] for r in jl(f)]
srv = jl(os.path.join(D, f"server_fed3_{a.run_tag}.jsonl"))
srv1 = jl(os.path.join(D, f"server_fed3v1_{a.run_tag}.jsonl"))
srv_single = jl(os.path.join(D, f"server_single1_{a.run_tag}.jsonl"))


def loss_svg():
    if not losses:
        return "<p class='muted'>기기 손실 기록 없음</p>"
    W, H, L, B, T, R = 520, 190, 44, 26, 12, 10
    n = max(len(v) for v in losses.values()); ymax = (max(max(v) for v in losses.values()) * 1.1) or 1
    x = lambda i: L + (W - L - R) * (i / max(1, n - 1)); y = lambda v: T + (H - T - B) * (1 - v / ymax)
    col = {"c0": "var(--b1)", "c1": "var(--b2)", "c2": "var(--b3)"}
    s = [f"<svg viewBox='0 0 {W} {H}' role='img' aria-label='라운드별 기기 평균 손실'>"]
    for k in range(5):
        v = ymax * k / 4
        s.append(f"<line x1='{L}' x2='{W-R}' y1='{y(v):.1f}' y2='{y(v):.1f}' stroke='var(--grid)'/><text x='{L-6}' y='{y(v)+4:.1f}' text-anchor='end' class='tick'>{v:.2f}</text>")
    for i in range(0, n, 3):
        s.append(f"<text x='{x(i):.1f}' y='{H-8}' text-anchor='middle' class='tick'>R{i+1}</text>")
    for cid, v in sorted(losses.items()):
        pts = " ".join(f"{x(i):.1f},{y(t):.1f}" for i, t in enumerate(v))
        s.append(f"<polyline points='{pts}' fill='none' stroke='{col.get(cid, 'var(--ink)')}' stroke-width='2'/>")
    s.append("</svg>")
    return "".join(s)


def cell(name, d):
    h, n = acc(name, d); hk, _ = acc(name, d, False)
    p = 100.0 * h / n
    tone = "hi" if p >= 50 else ("mid" if p > 15 else "lo")
    note = f"<span class='k'>표지 채점 {hk}/{n}</span>" if hk != h else ""
    return f"<td class='g {tone}'><b>{p:.0f}%</b><span>{h}/{n}</span>{note}</td>"


def pick(d):
    det = grid[FED][d]["detail"]
    for i in range(len(det)):
        if ok_of(FED, d, i) and (d == "B1" or not ok_of(SINGLE, d, i)):
            return i
    return 0


def bubble(name, d, i):
    det = grid[name][d]["detail"][i]; good = ok_of(name, d, i)
    txt = e(det["gen"].replace(chr(10), " ")[:160]) or "<i>(빈 답)</i>"
    return (f"<div class='ans {cls_of(name)}'><div class='who'><span>{e(name)}</span><span class='mark {'y' if good else 'n'}'>{'맞음' if good else '틀림'}</span></div>"
            f"<div class='txt'>{txt}</div></div>")


featured = []
for d in DOMS:
    i = pick(d); det = grid[BASE][d]["detail"][i]
    featured.append(f"<article class='qa'><header><span class='chip {d.lower()}'>{d} · {DEV[d]}만 가진 사실</span>"
                    f"<h3>{e(det['q'])}</h3><p class='muted'>정답에 들어가야 할 말: {e(', '.join(det['keys']))}</p></header>"
                    + "".join(bubble(n, d, i) for n in NAMES) + "</article>")

n_q = sum(len(grid[BASE][d]["detail"]) for d in DOMS)
rows = []
for d in DOMS:
    det0 = grid[BASE][d]["detail"]
    for i in range(len(det0)):
        tds = "".join(f"<td class='{'y' if ok_of(n, d, i) else 'n'}'><span class='mk'>{'✓' if ok_of(n, d, i) else '✗'}</span> {e(grid[n][d]['detail'][i]['gen'].replace(chr(10), ' ')[:90])}</td>" for n in NAMES)
        rows.append(f"<tr><td><span class='chip {d.lower()}'>{d}</span></td><td class='q'>{e(det0[i]['q'])}</td>{tds}</tr>")

can = []
for n in NAMES:
    hits = sum(SECRET in g for _, g in canary[n])
    ex = next((g for _, g in canary[n] if SECRET in g), canary[n][0][1])
    can.append(f"<tr><th scope='row'>{e(n)}</th><td class='{'n' if hits else 'y'}'>{hits}/3</td><td class='txt'>{e(ex.replace(chr(10), ' ')[:110])}</td></tr>")

facts_html = "".join(f"<div class='dev {d.lower()}'><div class='devh'><span class='chip {d.lower()}'>{d}</span> {DEV[d]}</div><ul>" + "".join(f"<li>{e(x)}</li>" for x in facts[d]) + "</ul></div>" for d in DOMS)


def v(ok, txt):
    return f"<li><span class='mark {'y' if ok else 'n'}'>{'성립' if ok else '불성립'}</span> {e(txt)}</li>"


verdict = [
    v(all(pct(BASE, d) <= 15 for d in DOMS), f"① 기본 모델은 모른다 — B1/B2/B3 {pct(BASE,'B1'):.0f}/{pct(BASE,'B2'):.0f}/{pct(BASE,'B3'):.0f}% (기준 15% 이하)"),
    v(pct(SINGLE, "B1") >= 50 and all(pct(SINGLE, d) <= 15 for d in ("B2", "B3")),
      f"② 한 기기 단독은 자기 것만 안다 — B1 {pct(SINGLE,'B1'):.0f}%, B2 {pct(SINGLE,'B2'):.0f}%, B3 {pct(SINGLE,'B3'):.0f}% (기준 B1 50% 이상, 나머지 15% 이하)"),
    v(all(pct(FED, d) >= 50 and pct(FED, d) - pct(SINGLE, d) >= 35 for d in ("B2", "B3")),
      f"③ 연합은 다른 기기의 사실도 안다 — B2 {pct(FED,'B2'):.0f}% (단독보다 +{pct(FED,'B2')-pct(SINGLE,'B2'):.0f}%p), B3 {pct(FED,'B3'):.0f}% (+{pct(FED,'B3')-pct(SINGLE,'B3'):.0f}%p) (기준 50% 이상, +35%p)"),
    v(pct(FED, "B1") >= pct(SINGLE, "B1") - 25, f"④ 자기 사실을 크게 잃지 않는다 — 연합 B1 {pct(FED,'B1'):.0f}% vs 단독 {pct(SINGLE,'B1'):.0f}% (기준 −25%p 이내)"),
]
if FEDV1:
    ok6 = all(pct(FEDV1, d) >= 50 and pct(FEDV1, d) - pct(SINGLE, d) >= 35 for d in ("B2", "B3")) and pct(FEDV1, "B1") >= pct(SINGLE, "B1") - 25
    edge = abs(pct(FEDV1, "B1") - (pct(SINGLE, "B1") - 25)) < 1e-9
    verdict.append(v(ok6, f"⑥ 서버 어댑터도 기기별로 학습한 뒤 평균만 해도 합쳐진다 — B1/B2/B3 {pct(FEDV1,'B1'):.0f}/{pct(FEDV1,'B2'):.0f}/{pct(FEDV1,'B3'):.0f}% (③·④ 와 같은 기준)"
                     + (f". 단 B1 은 단독보다 −25%p 로 허용 폭의 경계에 정확히 걸렸다" if edge else "")))
all_ok = all("불성립" not in x for x in verdict)

rounds_min = sum(r["round_s"] for r in srv) / 60 if srv else 0
ad_mb = (srv[0]["adapter_kb"] / 1024) if srv else 0
spreads = [r["back_spread"] for r in srv1 if r.get("back_spread") is not None]
spread_txt = f"라운드마다 평균 전 기기별 서버 어댑터끼리의 거리 {min(spreads):.3f}~{max(spreads):.3f} (0 이면 따로 학습되지 않은 것)" if spreads else ""
maxtail = lambda rs: max((max(r["losses"].values()) for r in rs if r["round"] >= 3), default=float("nan"))

page = f"""<title>연합 문답 증명</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{{--bg:#F4F5F2;--panel:#FFFFFF;--ink:#1D2126;--muted:#5C636B;--line:#D8DCD6;--grid:#E7EAE5;
--b1:#B4452F;--b1s:#F6E3DE;--b2:#1D7A74;--b2s:#DCEFEC;--b3:#5256B8;--b3s:#E4E5F6;--ok:#2E7D4F;--oks:#E2F1E7;--bad:#A8322B;--bads:#F7E1DF;--mid:#8A6A12;--mids:#F4ECD6;
--sans:"IBM Plex Sans KR","Noto Sans KR","Malgun Gothic",system-ui,sans-serif;--mono:"IBM Plex Mono",ui-monospace,Consolas,monospace}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#15181B;--panel:#1D2125;--ink:#E6E9EC;--muted:#A0A7AE;--line:#30363C;--grid:#262B30;
--b1:#E27A63;--b1s:#3A231D;--b2:#4DB8AF;--b2s:#17312E;--b3:#9296EC;--b3s:#24264A;--ok:#6CCB8F;--oks:#1B3325;--bad:#F08A82;--bads:#3B1E1C;--mid:#D9B54E;--mids:#342B14}}}}
:root[data-theme="dark"]{{--bg:#15181B;--panel:#1D2125;--ink:#E6E9EC;--muted:#A0A7AE;--line:#30363C;--grid:#262B30;
--b1:#E27A63;--b1s:#3A231D;--b2:#4DB8AF;--b2s:#17312E;--b3:#9296EC;--b3s:#24264A;--ok:#6CCB8F;--oks:#1B3325;--bad:#F08A82;--bads:#3B1E1C;--mid:#D9B54E;--mids:#342B14}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.65}}
main{{max-width:1120px;margin:0 auto;padding:40px 24px 80px}}
.eyebrow{{font-family:var(--mono);font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}}
h1{{font-size:32px;line-height:1.22;margin:8px 0 12px;text-wrap:balance}}
h2{{font-size:21px;margin:46px 0 12px;text-wrap:balance}} h3{{font-size:16px;margin:6px 0 2px;text-wrap:balance}}
p,li{{max-width:74ch}} .muted{{color:var(--muted);font-size:13px;margin:0}}
.lede{{font-size:17px;color:var(--muted);max-width:82ch}}
.chip{{display:inline-block;font-family:var(--mono);font-size:11.5px;font-weight:500;padding:1px 8px;border-radius:999px;white-space:nowrap}}
.chip.b1{{background:var(--b1s);color:var(--b1)}} .chip.b2{{background:var(--b2s);color:var(--b2)}} .chip.b3{{background:var(--b3s);color:var(--b3)}}
.mark{{font-size:11.5px;font-weight:600;padding:0 7px;border-radius:4px;white-space:nowrap}} .mark.y{{background:var(--oks);color:var(--ok)}} .mark.n{{background:var(--bads);color:var(--bad)}}
.verdict-top{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px 18px;margin:20px 0}}
.verdict{{list-style:none;padding:0;margin:8px 0 0}} .verdict li{{margin:6px 0}}
.devs{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}
.dev{{background:var(--panel);border:1px solid var(--line);border-top:3px solid;border-radius:6px;padding:12px 14px}}
.dev.b1{{border-top-color:var(--b1)}} .dev.b2{{border-top-color:var(--b2)}} .dev.b3{{border-top-color:var(--b3)}}
.devh{{font-weight:600;font-size:14px;margin-bottom:6px}} .dev ul{{margin:0;padding-left:18px;font-size:13.5px}} .dev li{{margin:3px 0}}
.wire{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:10px}}
.wire div{{font-size:13px;border:1px dashed var(--line);border-radius:6px;padding:8px 12px;background:var(--panel)}}
.wire b{{font-weight:600}} .wire .warn{{border-color:var(--bad);color:var(--bad)}}
.scroll{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}
table.big th,table.big td{{padding:10px 12px;border-bottom:1px solid var(--line);text-align:center}}
table.big th[scope=row]{{text-align:left;font-weight:600;white-space:nowrap}}
td.g b{{display:block;font-family:var(--mono);font-size:22px;font-weight:500}} td.g span{{font-size:12px;color:var(--muted)}} td.g .k{{display:block;font-size:11px;color:var(--mid)}}
td.g.hi{{background:var(--oks)}} td.g.hi b{{color:var(--ok)}} td.g.mid{{background:var(--mids)}} td.g.mid b{{color:var(--mid)}} td.g.lo b{{color:var(--muted)}}
.qas{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}
.qa{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px;display:flex;flex-direction:column;gap:8px}}
.qa header{{border-bottom:1px solid var(--grid);padding-bottom:8px}}
.ans{{border-radius:8px;padding:8px 10px;font-size:14px}} .ans .who{{font-size:12px;color:var(--muted);margin-bottom:2px;display:flex;justify-content:space-between;gap:6px}}
.ans.base{{background:var(--grid)}} .ans.single{{background:var(--b1s)}}
.ans.fed{{background:linear-gradient(90deg,var(--b1s),var(--b2s),var(--b3s))}}
.ans.fedv1{{background:var(--panel);border:1.5px dashed var(--b2)}}
.txt{{overflow-wrap:anywhere}}
details{{margin-top:14px}} summary{{cursor:pointer;font-weight:600}}
summary:focus-visible,a:focus-visible{{outline:2px solid var(--b2);outline-offset:2px}}
table.all td,table.all th{{padding:6px 8px;border-bottom:1px solid var(--grid);font-size:12.5px;text-align:left;vertical-align:top}}
table.all td.q{{min-width:180px}} table.all td.y .mk{{color:var(--ok);font-weight:700}} table.all td.n .mk{{color:var(--bad);font-weight:700}}
table.can td,table.can th,table.sec td,table.sec th,table.cmp td,table.cmp th{{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;font-size:14px;vertical-align:top}}
table.can td.y{{color:var(--ok);font-family:var(--mono)}} table.can td.n{{color:var(--bad);font-family:var(--mono)}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:18px;align-items:start}}
.panel{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px}}
svg{{width:100%;height:auto;display:block}} .tick{{font-size:10.5px;fill:var(--muted);font-family:var(--mono)}}
.leg{{display:flex;gap:14px;font-size:12px;color:var(--muted);margin-top:4px;flex-wrap:wrap}} .leg i{{display:inline-block;width:14px;height:3px;margin-right:5px;vertical-align:middle}}
.note{{border-left:3px solid var(--mid);background:var(--panel);padding:8px 14px;border-radius:0 6px 6px 0;margin:12px 0;font-size:14px}}
code{{font-family:var(--mono);font-size:12.5px;background:var(--grid);padding:0 4px;border-radius:3px}}
footer{{margin-top:48px;border-top:1px solid var(--line);padding-top:12px;font-size:12.5px;color:var(--muted)}}
@media (max-width:860px){{.devs,.wire,.qas,.two{{grid-template-columns:1fr}}}}
</style>
<main>
<div class="eyebrow">AwareNet · 분할 + LoRA 연합 학습 · KOREN VM ↔ HPC · 2026-09-13</div>
<h1>기기 셋이 서로 다른 사실만 가졌는데, 연합한 모델은 셋 다 답한다</h1>
<p class="lede">Qwen2.5-0.5B 를 앞 2층(기기)과 나머지(서버)로 자르고 LoRA 어댑터만 학습했다. 세 기기는 겹치는 사실이 하나도 없는 데이터(non-IID)를 들고, 라운드마다 어댑터를 평균했다. 그다음 학습에 없던 말투로 질문을 던져 실제 답을 받았다.</p>
<div class="verdict-top"><b>{'사전등록한 판정이 모두 성립' if all_ok else '사전등록 판정 결과'}</b> — 정답 여부는 답변 원문을 사람이 읽고 정했다(자동 채점과 다른 칸은 표에 함께 표시).
<ul class="verdict">{''.join(verdict)}</ul></div>

<h2>1. 누가 무엇을 가졌나 — 기기끼리 겹치는 사실 0개</h2>
<div class="devs">{facts_html}</div>
<div class="wire">
  <div>기기 → 서버: <b>절단면 활성값</b>과 <b>기기 어댑터</b> ({ad_mb:.1f} MB/라운드)</div>
  <div>서버 → 기기: <b>활성값 기울기</b>와 <b>평균한 어댑터</b></div>
  <div class="warn">⚠ 기기 → 서버: <b>정답 토큰</b>이 암호화 없이 간다 — 5장 보안 ①</div>
</div>
<p class="muted" style="margin-top:8px">데이터 파일은 각 VM 에만 있다. c0·c1 은 VM1, c2 는 VM2, 서버는 HPC. 16라운드 × 기기당 30스텝, 연합 학습 {rounds_min:.1f}분. 평가 질문은 학습 문형과 하나도 같지 않다.</p>

<h2>2. 결과 — 모델 × 기기별 사실</h2>
<div class="scroll"><table class="big">
<thead><tr><th></th>{''.join(f"<th><span class='chip {d.lower()}'>{d}</span><br><span class='muted'>{DEV[d]}의 사실</span></th>" for d in DOMS)}</tr></thead>
<tbody>{''.join(f"<tr><th scope='row'>{e(n)}</th>{''.join(cell(n, d) for d in DOMS)}</tr>" for n in NAMES)}</tbody></table></div>
<p class="muted">학습에 없던 말투로 물은 정답률. 단독(B1) = c0 한 대가 같은 예산으로 자기 데이터만 학습. 연합(B1+B2+B3) = 기기 어댑터 평균 + 서버 어댑터 한 벌 공유. 연합·뒷단도 평균(v1) = 서버 어댑터도 기기별로 따로 학습한 뒤 평균.</p>

<h2>3. 실제로 물어본 것</h2>
<p>기기마다 한 문항씩 골랐다. B2·B3 는 "연합이 맞히고 단독이 틀린 첫 문항", B1 은 "연합이 맞힌 첫 문항"이다. 이렇게 고르면 결과가 좋아 보이므로 <b>전체 {n_q}문항의 답변 원문</b>을 아래에 모두 붙인다.</p>
<div class="qas">{''.join(featured)}</div>
<details><summary>전체 문답 원문 보기 ({n_q}문항 × {len(NAMES)}모델)</summary>
<div class="scroll"><table class="all"><thead><tr><th></th><th>질문</th>{''.join(f'<th>{e(n)}</th>' for n in NAMES)}</tr></thead><tbody>{''.join(rows)}</tbody></table></div></details>
<div class="note">연합이 틀린 답은 전부 <b>다른 기기의 사실로 답한 혼선</b>이다. 서버 어댑터를 공유한 연합은 "평상시 RTT 꼬리(p95)" 를 물으면 B1 의 혼잡 시 사실 "p95가 448ms까지 뛰었다" 로 답한다. 어댑터를 모두 평균한 v1 은 <b>문장 틀은 맞고 숫자만 다른 기기의 것</b>인 오답이 두드러진다 — "평균 24.2Mbps다"(B1 문장 + B2 숫자), "p95가 86.4ms까지 뛰었다. 평상시의 5배다"(B1 문장 + B3 숫자). 평균할 때의 간섭이 사실 단위로 보인다.</div>

<h2>4. 지식은 어디서 합쳐지나</h2>
<div class="two">
<div class="panel">{loss_svg()}<div class="leg"><span><i style="background:var(--b1)"></i>c0 (B1)</span><span><i style="background:var(--b2)"></i>c1 (B2)</span><span><i style="background:var(--b3)"></i>c2 (B3)</span></div>
<p class="muted">연합 학습에서 라운드마다 기기가 받은 평균 손실. 각 기기는 자기 사실만 보므로 곧 0 근처가 된다. 이것은 "외웠다"일 뿐이다. 합쳐졌는지는 2장의 다른 기기 열이 보여 준다.</p></div>
<div>
<div class="scroll"><table class="cmp"><thead><tr><th>방식</th><th>기기 어댑터</th><th>서버 어댑터</th></tr></thead><tbody>
<tr><td>연합(B1+B2+B3)</td><td>라운드 끝에 평균</td><td>한 벌을 기기가 차례로 학습</td></tr>
<tr><td>연합·뒷단도 평균(v1)</td><td>라운드 끝에 평균</td><td>기기별로 따로 학습 → 라운드 끝에 평균</td></tr>
</tbody></table></div>
<p>첫 방식에서는 서버 어댑터가 모든 기기의 데이터를 한 곳에서 본다. 그래서 "어댑터를 평균해서 합쳐졌다"고 말하려면 두 번째 방식이 필요하다. 두 번째 방식은 어느 어댑터도 다른 기기의 데이터로 학습되지 않고, 합쳐지는 일은 <b>평균</b>에서만 일어난다.{(' ' + e(spread_txt) + '.') if spread_txt else ''}</p>
<p class="muted">학습 안정성: R3 이후 차례 끝 손실 최대 — 연합 {maxtail(srv):.4f}{f', v1 {maxtail(srv1):.4f}' if srv1 else ''}{f', 단독 {maxtail(srv_single):.4f}' if srv_single else ''}. 1차 실행(학습률 1e-3, 클리핑 없음)은 R12 에서 발산해 폐기했다.</p>
</div></div>

<h2>5. 보안 — 학습 데이터를 그대로 내뱉는가 (측정만, 대책은 조사만)</h2>
<p>c0 의 학습셋에만 가짜 비밀 <code>{SECRET}</code> 을 세 문항 섞었다. 모든 모델에게 그 비밀을 물었다.</p>
<div class="scroll"><table class="can"><thead><tr><th>모델</th><th>비밀 노출</th><th>답 예시</th></tr></thead><tbody>{''.join(can)}</tbody></table></div>
<p>한 기기에만 넣은 비밀이 연합 모델에서도 그대로 나온다. 평균은 비밀을 희석하지 않는다. 그리고 이것과 별개로, 지금 프로토콜은 <b>정답 토큰을 서버에 암호화 없이 보낸다</b>. 모델에 묻지 않아도 서버 운영자는 답을 본다.</p>
<div class="scroll"><table class="sec"><thead><tr><th>누출 경로</th><th>지금</th><th>먼저 할 대책 (적용 안 함)</th></tr></thead><tbody>
<tr><td>① 정답 토큰이 서버로 간다</td><td>매 스텝 평문 전송</td><td>U 자형 분할: 출력층과 손실 계산을 기기에 두고 서버는 가운데 층만. 전송 구간 TLS</td></tr>
<tr><td>② 절단면 활성값에서 입력 문장 복원</td><td>앞 2층 출력을 평문 전송. 언어 모델은 입력→은닉 상태가 일대일이라 복원된다(SIPIT, 토큰 정확도 100%)</td><td>상호정보 정규화 + 어댑터 워밍업: 분할 LLM 공격 BLEU 0.89 → 0.004, 성능 약 96% 유지</td></tr>
<tr><td>③ 완성 모델이 비밀을 답한다</td><td>위 표</td><td>배포해도 되는 사실만 학습 + 배포 전 카나리아 감사(추출 0/3 기준) + 출력 필터. 긴 원문에는 Goldfish 손실, 참여 기기가 수백 이상이면 기기 단위 차등 프라이버시</td></tr>
</tbody></table></div>
<p class="muted">근거와 적용 순서: <code>docs/03_리서치/보안_데이터재현_대책_2026-09-13.md</code>. 이 실험은 학습이 되는지를 보인 것이고 프라이버시 보장을 주장하지 않는다.</p>

<h2>6. 한계</h2>
<ul>
<li>B2 는 질문이 3개뿐이라 한 문항이 33%p 다.</li>
<li>질문은 "기기가 가진 사실을 다른 말투로" 묻는다. 어느 기기도 본 적 없는 사실을 추론하는지는 보지 않았다.</li>
<li>시드 1, 모델 0.5B, 기기 3대. 정답률의 흔들림 폭은 재지 않았다. 두 연합 방식은 합계가 12/18 로 같고 도메인별 배분만 문항 2개 차이라, 어느 방식이 낫다고 읽지 않는다.</li>
<li>1차 발산의 원인 가설(손실이 0 근처일 때 Adam 이 잡음을 키움)은 같은 설정 재실행에서 재현되지 않았다. 새 설정은 옛 설정에서 보인 요동이 없어서 채택했다.</li>
</ul>

<footer>사전등록 docs/02_실험/실험_연합분할LoRA_문답증명_사전등록_2026-09-13.md · 코드 sfl/experiments/run_fed_split_lora.py, fed_split_eval.py · 배치 scripts/exp/run_fed_split.sh · 원자료 out/fed_split/ · 엄격 판정 strict_{e(a.eval_tag)}.json · 이 페이지 scripts/analysis/fed_split_page.py</footer>
</main>
"""
out = os.path.join(ROOT, "out", "reports", "연합문답_증명_2026-09-13.html")
io.open(out, "w", encoding="utf-8").write(page)
print(out, len(page) // 1024, "KB | 모델:", NAMES, "| 엄격 판정:", "있음" if strict else "없음")
