# -*- coding: utf-8 -*-
"""프로브 결과 비교기 — '비교하고 싶은 사항들'을 표 하나로.

  koren_probe.py 산출 JSON 을 여러 개(또는 다표적 1개) 받아
  사전 등록 지표(C1~C4)를 열 맞춰 비교한다.

      python3 koren_compare.py out/measure/probe_*.json
      python3 koren_compare.py a.json b.json --md out/measure/비교표.md
"""
import argparse
import io
import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def g(d, *ks, default=None):
    for k in ks:
        if not isinstance(d, dict) or k not in d:
            return default
        d = d[k]
    return d


def cols_from(files):
    cols = []
    for f in files:
        d = json.load(io.open(f, encoding="utf-8"))
        run = d["meta"]["label"]
        for tl, td in d["targets"].items():
            cols.append((f"{run}/{tl}", td))
    return cols


def fmt(v, nd=1, suf=""):
    return "—" if v is None else f"{v:.{nd}f}{suf}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--md", default="")
    a = ap.parse_args()
    cols = cols_from(a.files)

    biggest = None
    for _, td in cols:
        for k in g(td, "goodput", "up", default={}) or {}:
            sz = float(k.split("MB")[0])
            biggest = sz if biggest is None else max(biggest, sz)

    rows = [
        ("RTT p50 (steady, ms)", lambda t: g(t, "rtt", "steady_echo_ms", "p50"), 1, ""),
        ("RTT p95 (steady, ms)", lambda t: g(t, "rtt", "steady_echo_ms", "p95"), 1, ""),
        ("지터 IQR (ms)", lambda t: g(t, "rtt", "steady_echo_ms", "iqr"), 2, ""),
        ("새 연결 p50 (ms)", lambda t: g(t, "rtt", "fresh_connect_ms", "p50"), 1, ""),
        (f"상행 굿풋 {biggest}MB steady (Mbps)",
         lambda t: g(t, "goodput", "up", f"{biggest}MB_steady", "p50"), 1, ""),
        (f"상행 굿풋 {biggest}MB fresh (Mbps)",
         lambda t: g(t, "goodput", "up", f"{biggest}MB_fresh", "p50"), 1, ""),
        ("slow-start 세금 (fresh/steady)",
         lambda t: (lambda f, s: None if not f or not s else f / s)(
             g(t, "goodput", "up", f"{biggest}MB_fresh", "p50"),
             g(t, "goodput", "up", f"{biggest}MB_steady", "p50")), 2, "×"),
        (f"하행 굿풋 {biggest}MB steady (Mbps)",
         lambda t: g(t, "goodput", "down", f"{biggest}MB_steady", "p50"), 1, ""),
        ("버스트 완료 p50 (s)", lambda t: g(t, "burst", "flow_done_s", "p50"), 2, ""),
        ("버스트 공평성 편차 (배)", lambda t: g(t, "burst", "spread_ratio"), 2, ""),
        ("버스트 RTT 악화 (p95/평시 p50)",
         lambda t: (lambda b, i: None if not b or not i else b / i)(
             g(t, "burst", "rtt_ms", "burst", "p95"),
             g(t, "burst", "rtt_ms", "idle", "p50")), 1, "×"),
        ("재전송 증가 (개)", lambda t: g(t, "retrans_delta"), 0, ""),
    ]

    w0 = max(len(r[0]) for r in rows) + 2
    head = " " * w0 + " | " + " | ".join(f"{c[0]:>16s}" for c in cols)
    lines = [head, "-" * len(head)]
    for name, fn, nd, suf in rows:
        cells = [fmt(fn(td), nd, suf) for _, td in cols]
        lines.append(f"{name:{w0}s} | " + " | ".join(f"{c:>16s}" for c in cells))
    out = "\n".join(lines)
    print(out)
    if a.md:
        md = ["| 지표 | " + " | ".join(c[0] for c in cols) + " |",
              "|---|" + "---|" * len(cols)]
        for name, fn, nd, suf in rows:
            md.append(f"| {name} | " + " | ".join(fmt(fn(td), nd, suf)
                                                  for _, td in cols) + " |")
        io.open(a.md, "w", encoding="utf-8").write("\n".join(md) + "\n")
        print(f"\nmd 저장: {a.md}")


if __name__ == "__main__":
    main()
