# -*- coding: utf-8 -*-
"""time-to-accuracy — 목표 정확도에 처음 도달한 시각 (리서치 16번 §2 채택 지표).

    python scripts/tta.py out/wp_uniform.jsonl out/wp_widthpath.jsonl --targets 0.15,0.18
"""
import argparse
import io
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--targets", default="0.15,0.18,0.20")
    a = ap.parse_args()
    targets = [float(x) for x in a.targets.split(",")]
    print(f"{'로그':28s} " + " ".join(f"{int(t*100):>3d}% 도달" for t in targets))
    for p in a.logs:
        rows = [json.loads(l) for l in io.open(p, encoding="utf-8")
                if '"round"' in l and '"acc"' in l]
        cells = []
        for t in targets:
            hit = next((r for r in rows if r.get("acc", 0) >= t), None)
            cells.append(f"{hit['elapsed']:6.0f}s(R{hit['round']})" if hit else "  미도달")
        print(f"{os.path.basename(p):28s} " + " ".join(f"{c:>9s}" for c in cells))


if __name__ == "__main__":
    main()
