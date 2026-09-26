# -*- coding: utf-8 -*-
"""중간보고서의 표를 낱장 PNG 로 뽑는다.

  한글에 마크다운 표를 붙이면 열 폭을 스스로 다시 잡아 글자를 세로로 쪼갠다
  ("비 교 군", "F e d Avg"). 표를 그림으로 넣으면 한글이 다시 짤 일이 없다.

    python scripts/analysis/tables_to_png.py            # 전부
    python scripts/analysis/tables_to_png.py 18 16      # 표 18, 16 만

  산출물: out/table/표18.png …
"""
import io
import os
import re
import subprocess
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import markdown
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "docs", "중간보고서_축약본.md")
OUT = os.path.join(ROOT, "out", "table")
NL = chr(10)

CHROME = next(
    (p for p in (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ) if os.path.exists(p)), None)

# 본문 PDF 와 같은 표 서식. 폭은 넉넉히 주고 나중에 여백을 잘라낸다.
CSS = """
* { box-sizing: border-box; }
body {
  font-family: "Pretendard", "맑은 고딕", "Malgun Gothic", sans-serif;
  margin: 0; padding: 24px; background: #ffffff; color: #1a202c;
  word-break: keep-all; overflow-wrap: break-word;
}
.cap {
  font-size: 15.5pt; font-weight: 700; color: #14532d; margin: 0 0 10px;
}
.cap code {
  font-family: Consolas, monospace; font-size: 11.5pt; font-weight: 400;
  background: #f1f5f9; padding: 2px 6px; border-radius: 3px; color: #b91c1c;
}
table { border-collapse: collapse; margin: 0; font-size: 14pt;
        width: 100%; table-layout: auto; }
th, td { border: 1px solid #cbd5e1; padding: 9px 14px; text-align: right;
         vertical-align: top; }
/* 짧은 셀만 한 줄 고정. 긴 글까지 nowrap 하면 표가 화면 밖으로 나간다. */
th.nw, td.nw { white-space: nowrap; }
/* 숫자는 오른쪽, 줄바꿈되는 긴 글은 왼쪽. 산문을 우측정렬하면 읽기 나쁘다. */
th:not(.nw), td:not(.nw) { text-align: left; }
th:first-child, td:first-child { text-align: left; }
th { background: #f0fdf4; font-weight: 700; color: #14532d; }
tbody tr:nth-child(even) { background: #fafafa; }
strong { color: #0b3d20; }
"""


def tables_of(text):
    """캡션 번호 -> (캡션 원문, 표 마크다운)"""
    out, L = {}, text.split(NL)
    for i, l in enumerate(L):
        m = re.match(r"\*\*표 (\d+)\.", l)
        if not m:
            continue
        j = i + 1
        while j < len(L) and not L[j].startswith("|"):
            j += 1
        k = j
        while k < len(L) and L[k].startswith("|"):
            k += 1
        if k > j:
            out[int(m.group(1))] = (l, NL.join(L[j:k]))
    return out


def trim(path, pad=10):
    """흰 여백을 잘라낸다. 창 크기를 넉넉히 잡고 찍은 뒤 실제 표만 남긴다."""
    im = Image.open(path).convert("RGB")
    w, h = im.size
    px = im.load()
    x0, y0, x1, y1 = w, h, 0, 0
    for y in range(h):
        for x in range(0, w, 2):          # 가로는 두 칸씩 — 충분히 정확하고 빠르다
            if px[x, y] != (255, 255, 255):
                x0, x1 = min(x0, x), max(x1, x)
                y0, y1 = min(y0, y), max(y1, y)
    if x1 <= x0:
        return im.size
    box = (max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad + 2), min(h, y1 + pad))
    im.crop(box).save(path)
    return im.crop(box).size


def mark_short(html, limit=9):
    """짧은 셀에만 nw 를 붙여 한 줄로 굳힌다. 숫자 열이 쪼개지는 것을 막는다."""
    def one(m):
        tag, inner = m.group(1), m.group(2)
        plain = re.sub(r"<[^>]+>", "", inner)
        return "<%s class='nw'>%s</%s>" % (tag, inner, tag) if len(plain) <= limit else m.group(0)
    return re.sub(r"<(td|th)>(.*?)</\1>", one, html, flags=re.S)


def render(n, cap, tbl, scale=2.0, width=860):
    body = mark_short(markdown.markdown(tbl, extensions=["tables"]))
    cap_html = re.sub(r"`([^`]+)`", r"<code>\1</code>",
                      re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", cap))
    html = ("<!doctype html><meta charset='utf-8'><style>%s"
            ".wrap{width:%dpx}</style>"
            "<div class='wrap'><div class='cap'>%s</div>%s</div>"
            % (CSS, width, cap_html, body))

    fd, hp = tempfile.mkstemp(suffix=".html", dir=OUT)
    os.close(fd)
    io.open(hp, "w", encoding="utf-8").write(html)

    png = os.path.join(OUT, "표%d.png" % n)
    subprocess.run([
        CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
        "--force-device-scale-factor=%s" % scale,
        "--window-size=2200,1600",
        "--screenshot=" + png, "file:///" + hp.replace(chr(92), "/"),
    ], capture_output=True, timeout=90)
    os.remove(hp)
    if not os.path.exists(png):
        return None
    return trim(png)


def main():
    if CHROME is None:
        sys.exit("Chrome / Edge 를 찾지 못했다")
    os.makedirs(OUT, exist_ok=True)

    # --src <경로> 로 다른 문서의 표도 뽑는다 (별첨 등)
    argv, src = list(sys.argv[1:]), SRC
    if "--src" in argv:
        i = argv.index("--src")
        src = argv[i + 1]
        del argv[i:i + 2]

    T = tables_of(io.open(src, encoding="utf-8").read())
    want = [int(a) for a in argv] or sorted(T)

    for n in want:
        if n not in T:
            print("표 %-2d  없음" % n)
            continue
        cap, tbl = T[n]
        size = render(n, cap, tbl)
        cols = tbl.split(NL)[0].count("|") - 1
        print("표 %-2d  %d열  →  %s" % (n, cols, "%dx%d" % size if size else "실패"))

    print(NL + "저장 위치: %s" % OUT)


if __name__ == "__main__":
    main()
