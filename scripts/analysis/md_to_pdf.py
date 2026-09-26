# -*- coding: utf-8 -*-
"""
md_to_pdf.py — 마크다운 보고서를 인쇄용 PDF로 변환한다

[왜 이 경로인가]
  pandoc/weasyprint/wkhtmltopdf가 없는 환경이다. 대신 이 PC에 있는 Chrome의
  헤드리스 인쇄를 쓴다. 장점이 분명하다 — 한글 폰트(맑은 고딕)를 OS에서
  그대로 가져오므로 깨지지 않고, 표·이미지·페이지 나눔이 브라우저 렌더링
  품질 그대로 나온다.

  수식은 MathJax(CDN)로 렌더링하고, 스크립트가 끝날 때까지
  --virtual-time-budget으로 기다린다.

사용:
  python scripts/analysis/md_to_pdf.py docs/보고서_v7.md out/reports/보고서_v7.pdf
"""
import os
import re
import subprocess
import sys
import urllib.parse

import markdown

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

CHROME = next(
    (p for p in (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ) if os.path.exists(p)), None)

CSS = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm; }
@page { @bottom-center { content: counter(page); } }
* { box-sizing: border-box; }
body {
  font-family: {font};
  font-size: 10.2pt; line-height: 1.72; color: #1a202c; margin: 0;
  word-break: keep-all; overflow-wrap: break-word;
}
h1 {
  font-size: 19pt; margin: 0 0 14px; padding-bottom: 9px;
  border-bottom: 2.5px solid #16a34a; page-break-before: always;
  page-break-after: avoid; color: #0f172a;
}
h1:first-of-type { page-break-before: avoid; }
h2 {
  font-size: 13.4pt; margin: 26px 0 10px; padding-left: 9px;
  border-left: 4px solid #16a34a; page-break-after: avoid; color: #14532d;
}
h3 { font-size: 11.4pt; margin: 18px 0 7px; page-break-after: avoid; }
p { margin: 8px 0; text-align: justify; }
strong { color: #0b3d20; }
table {
  border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 8.9pt;
  page-break-inside: avoid;
}
th, td { border: 1px solid #cbd5e1; padding: 5px 7px; text-align: right; }
th:first-child, td:first-child, th.tl, td.tl { text-align: left; }
th { background: #f0fdf4; font-weight: 700; color: #14532d; }
tbody tr:nth-child(even) { background: #fafafa; }
blockquote {
  margin: 13px 0; padding: 11px 15px; background: #f8fafc;
  border-left: 4px solid #94a3b8; page-break-inside: avoid;
}
blockquote table { margin: 7px 0; }
blockquote p:first-child { margin-top: 0; }
blockquote p:last-child { margin-bottom: 0; }
code {
  font-family: "D2Coding", Consolas, monospace; font-size: 8.8pt;
  background: #f1f5f9; padding: 1px 4px; border-radius: 3px; color: #b91c1c;
}
pre {
  background: #0f172a; color: #e2e8f0; padding: 11px 13px; border-radius: 6px;
  overflow-x: auto; page-break-inside: avoid; font-size: 8.4pt; line-height:1.5;
}
pre code { background: none; color: inherit; padding: 0; font-size: 8.4pt; }
img {
  max-width: 100%; display: block; margin: 12px auto;
  border: 1px solid #e2e8f0; border-radius: 4px; page-break-inside: avoid;
}
hr { border: none; border-top: 1px solid #e2e8f0; margin: 22px 0; }
ul, ol { margin: 8px 0; padding-left: 22px; }
li { margin: 3px 0; }
.cover {
  page-break-after: always; text-align: center; padding-top: 78mm;
}
.cover .t { font-size: 25pt; font-weight: 800; color: #0f172a;
            line-height: 1.35; margin-bottom: 20px; }
.cover .r { display: inline-block; width: 88px; height: 4px;
            background: #16a34a; margin-bottom: 26px; }
.cover .s { font-size: 13pt; color: #334155; margin-bottom: 10px; }
.cover .d { font-size: 10.5pt; color: #64748b; margin-top: 46px; }
.refs ol { column-count: 2; column-gap: 20px; font-size: 92%; }
.refs li { break-inside: avoid; margin: 2px 0; }
mjx-container { font-size: 96% !important; }
"""

HTML = """<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<title>{title}</title>
<style>{css}</style>
<script>
window.MathJax = {{
  tex: {{ inlineMath: [['$','$']], displayMath: [['$$','$$']] }},
  options: {{ skipHtmlTags: ['script','noscript','style','textarea','pre','code'] }}
}};
</script>
<script id="MathJax-script" async
  src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
</head><body>
<div class="cover">
  <div class="t">{title}</div>
  <div class="r"></div>
  <div class="s">{subtitle}</div>
  <div class="d">{date}</div>
</div>
{body}
</body></html>"""


def convert(src, dst, title=None, subtitle="", date=""):
    font = os.environ.get("PDF_FONT",
                          '"Malgun Gothic", "맑은 고딕", sans-serif')
    css = CSS.replace("{font}", font)
    if os.environ.get("PDF_COMPACT"):
        # 분량 기준을 맞추기 위한 고밀도 조판. 가독성 하한을 지키는 선에서만 줄인다.
        for a, b in (("font-size: 10.2pt", "font-size: 8.9pt"),
                     ("line-height: 1.72", "line-height: 1.40"),
                     ("font-size: 8.9pt", "font-size: 7.5pt"),
                     ("margin: 18mm 16mm 20mm 16mm", "margin: 13mm 12mm 14mm 12mm"),
                     ("max-width: 100%; display: block; margin: 12px auto",
                      "max-width: 82%; display: block; margin: 5px auto"),
                     ("margin: 26px 0 10px", "margin: 13px 0 5px"),
                     ("margin: 18px 0 7px", "margin: 11px 0 4px"),
                     ("margin: 8px 0; text-align: justify", "margin: 5px 0; text-align: justify"),
                     ("margin: 12px 0; font-size", "margin: 8px 0; font-size"),
                     ("font-size: 19pt", "font-size: 15pt"),
                     ("font-size: 13.4pt", "font-size: 11pt"),
                     ("font-size: 11.4pt", "font-size: 9.8pt"),
                     ("padding: 11px 15px", "padding: 6px 10px"),
                     ("padding: 5px 7px", "padding: 3px 4.5px"),
                     ("margin: 13px 0; padding", "margin: 8px 0; padding"),
                     ("padding-top: 78mm", "padding-top: 70mm")):
            css = css.replace(a, b)
    if os.environ.get("PDF_IMGW"):
        # 그림이 차지하는 지면을 줄인다. 본문 분량 제한이 있을 때만 쓴다.
        css = re.sub(r"max-width: \d+%", "max-width: %s%%" % os.environ["PDF_IMGW"], css)
    if os.environ.get("PDF_TIGHT"):
        # 짧은 첨부용 중간 밀도 — 가독성은 유지하고 여백·행간만 줄인다.
        for a, b in (("font-size: 10.2pt", "font-size: 9.6pt"), ("line-height: 1.72", "line-height: 1.45"),
                     ("margin: 18mm 16mm 20mm 16mm", "margin: 14mm 14mm 16mm 14mm"),
                     ("margin: 26px 0 10px", "margin: 16px 0 6px"), ("margin: 18px 0 7px", "margin: 12px 0 4px"),
                     ("margin: 8px 0; text-align: justify", "margin: 5px 0; text-align: justify"),
                     ("ul, ol { margin: 8px 0", "ul, ol { margin: 4px 0"), ("li { margin: 3px 0", "li { margin: 2px 0")):
            css = css.replace(a, b)
    if os.environ.get("PDF_NOCOVER"):
        # 짧은 첨부용 — 표지 쪽을 만들지 않고 제목·부제를 본문 머리에 붙인다.
        css += ("\n.cover{page-break-after:auto;text-align:left;padding-top:0;"
                "border-bottom:2.5px solid #16a34a;padding-bottom:8px;margin-bottom:14px}"
                ".cover .t{font-size:19pt;margin-bottom:6px}.cover .r{display:none}"
                ".cover .s{font-size:10.5pt;margin-bottom:0}.cover .d{margin-top:2px}\n")
    if os.environ.get("PDF_FLOW"):
        # 장 구분마다 새 쪽을 강제하지 않고 이어 붙인다. HWP로 옮길 때의
        # 실제 분량에 가깝게 세려는 용도 — 장 제목 위 여백만 남긴다.
        css = css.replace("border-bottom: 2.5px solid #16a34a; page-break-before: always;",
                          "border-bottom: 2.5px solid #16a34a; margin-top: 26px;")
    src = os.path.join(ROOT, src) if not os.path.isabs(src) else src
    dst = os.path.join(ROOT, dst) if not os.path.isabs(dst) else dst
    base = os.path.dirname(src)
    text = open(src, encoding="utf-8").read()

    # 제목/부제는 문서 앞머리에서 뽑고 본문에서는 뺀다 (표지로 감)
    m = re.match(r"^#\s+(.+?)\n+\*\*(.+?)\*\*\n", text)
    if m:
        title = title or m.group(1).strip()
        subtitle = subtitle or m.group(2).strip()
        text = text[m.end():]

    # 이미지 상대경로 → 절대 file:// (Chrome이 로컬 파일을 찾게)
    def fix(mo):
        alt, path = mo.group(1), mo.group(2)
        if path.startswith(("http", "file:", "data:")):
            return mo.group(0)
        full = os.path.normpath(os.path.join(base, path))
        return f"![{alt}](file:///{urllib.parse.quote(full.replace(os.sep, '/'))})"
    text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", fix, text)

    # 수식 보호 — 마크다운이 LaTeX의 `_`를 강조 문법으로, `*`를 이탤릭으로
    # 먹어버린다($\mathrm{Util}_i$ → Util}i). 변환 전에 자리표시자로 빼두고
    # 변환 후 되돌린 다음 MathJax에 넘긴다.
    stash = []

    def hide(mo):
        stash.append(mo.group(0))
        return f"@@MATH{len(stash)-1}@@"

    text = re.sub(r"\$\$.+?\$\$", hide, text, flags=re.S)   # 블록 수식 먼저
    text = re.sub(r"(?<!\$)\$[^$\n]+?\$(?!\$)", hide, text)  # 인라인 수식

    # md_in_html이 없으면 <div markdown="1"> 안이 원시 텍스트로 남아
    # 참고문헌의 *기울임*이 별표로 노출되고 항목이 한 문단으로 붙는다.
    body = markdown.markdown(
        text, extensions=["tables", "fenced_code", "sane_lists", "attr_list",
                          "md_in_html"])

    for i, raw in enumerate(stash):
        body = body.replace(f"@@MATH{i}@@", raw)

    # 표 정렬: 숫자 칸은 오른쪽, 글이 긴 칸은 왼쪽. 기본 우측 정렬만 쓰면
    # 설명 문장이 오른쪽에 붙어 읽기 나쁘다.
    def align(mo):
        tag, inner = mo.group(1), mo.group(2)
        plain = re.sub(r"<[^>]+>", "", inner).strip()
        numeric = bool(re.fullmatch(r"[\d\s.,%±~+\-/:()회대초s초분]*", plain))
        cls = "" if numeric and len(plain) < 16 else ' class="tl"'
        return f"<{tag}{cls}>{inner}</{tag}>"
    body = re.sub("<(td|th)>(.*?)</" + chr(92) + "1>", align, body, flags=re.S)

    html_path = dst.replace(".pdf", ".html")
    open(html_path, "w", encoding="utf-8").write(
        HTML.format(title=title or os.path.basename(src), css=css,
                    subtitle=subtitle, date=date, body=body))

    if not CHROME:
        print("Chrome/Edge를 찾지 못했습니다. HTML만 생성:", html_path)
        return html_path

    subprocess.run([
        CHROME, "--headless", "--disable-gpu", "--no-sandbox",
        "--no-pdf-header-footer",
        "--virtual-time-budget=30000",           # MathJax 렌더링 대기
        f"--print-to-pdf={dst}",
        "file:///" + html_path.replace(os.sep, "/"),
    ], check=True, capture_output=True, timeout=300)

    size = os.path.getsize(dst) / 1024
    print(f"생성: {os.path.relpath(dst, ROOT)}  ({size:.0f} KB)")
    return dst


if __name__ == "__main__":
    convert(sys.argv[1], sys.argv[2],
            subtitle=sys.argv[3] if len(sys.argv) > 3 else "",
            date=sys.argv[4] if len(sys.argv) > 4 else "")
