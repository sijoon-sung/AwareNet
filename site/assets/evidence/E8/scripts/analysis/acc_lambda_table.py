# -*- coding: utf-8 -*-
"""정확도 축 표 (9/10 후속 §4): λ 마다 (평균 폭, 라운드, 마지막 50R 정확도) — 시드별과 평균.
    python scripts/analysis/acc_lambda_table.py            # out/wp_r8mix_acc*_s*_bothmp_{uniform,widthpath}.jsonl"""
import glob, io, json, os, re, statistics as st, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def rows(f):
    return [json.loads(l) for l in io.open(f, encoding="utf-8") if '"round"' in l]


def summary(R, tail=50, skip=4):
    body = R[skip:]
    acc = [r["acc"] for r in R[-tail:] if r.get("acc") is not None]
    w = [sum(float(v) for v in r["plan"].values()) / max(1, len(r["plan"])) for r in body if r.get("plan")]
    return {"rounds": len(R), "ms": st.mean(r["makespan"] for r in body) if body else float("nan"),
            "acc": st.mean(acc) if acc else float("nan"), "w": st.mean(w) if w else 1.0}


def main():
    out = {}
    for f in sorted(glob.glob("out/wp_r8mix_acc*_s*_bothmp_widthpath.jsonl")):
        m = re.match(r"wp_r8mix_acc(_l(\d+))?_s(\d+)_bothmp_widthpath\.jsonl", os.path.basename(f))
        lam = int(m.group(2)) if m.group(2) else 70; sd = int(m.group(3))
        out[(lam, sd)] = summary(rows(f))
        fu = f.replace("_widthpath", "_uniform")
        try:
            out[(0, sd)] = summary(rows(fu))
        except OSError:
            pass
    if not out:
        print("결과 없음"); return 1
    print(f"{'λ':>5s} {'시드':>4s} {'라운드수':>7s} {'라운드(s)':>9s} {'평균 폭':>7s} {'정확도(마지막50R)':>16s}")
    for (lam, sd), v in sorted(out.items()):
        print(f"{('균등' if lam == 0 else str(lam)):>5s} {sd:4d} {v['rounds']:7d} {v['ms']:9.2f} {v['w']:7.3f} {100 * v['acc']:15.1f}%")
    print("\n시드 평균:")
    for lam in sorted({k[0] for k in out}):
        vs = [v for (l, s), v in out.items() if l == lam]
        print(f"  λ {('균등' if lam == 0 else lam)!s:>5}: 라운드 {st.mean(v['ms'] for v in vs):.2f}s  폭 {st.mean(v['w'] for v in vs):.3f}  정확도 {100 * st.mean(v['acc'] for v in vs):.1f}%  (n={len(vs)})")
    print("읽는 법: λ 가 작을수록 폭·정확도가 내려가고 라운드가 짧아지면 단조. 정확도 차이는 5점 넘는 것만 말한다(시드 잡음 4~6점).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
