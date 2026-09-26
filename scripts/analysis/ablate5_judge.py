# -*- coding: utf-8 -*-
"""절제 5판 판정 — 사전등록(docs/02_실험/실험_절제_5판_사전등록.md §3)을 그대로 채점한다.

    python scripts/analysis/ablate5_judge.py            # out/wp_h5_s*_*_widthpath.jsonl 전부
    python scripts/analysis/ablate5_judge.py h5_s1_both # 하나만

판정 1 (주): 둘다(개정판) 각 시드에서
    c0  폭이 ≤0.5 로 내려간 뒤 마지막 라운드까지 복귀하지 않는다 (연산 낙오자 → 폭)
    c1/c3 둘 중 하나 이상이 경로 2 로 옮겨진다 (공유 혼잡 → 경로)   ※ c1·c3 대칭
    c2  마지막 폭 < 1.0 (접속 회선 → 잔여 폭)
    c3  (또는 안 옮겨진 쪽) 폭 1.0 (정상 → 무개입)
판정 3: 구판(bothv1)에서 c0 폭이 한 번 내려갔다가 1.0 으로 복귀하는 라운드가 있는가.
판정 4: 팔 규약 위반 — width 팔에 배정 2종, path 팔에 폭<1.0.
경로 배정은 jsonl 에 없으므로 같은 이름의 .log 에서 "[widthpath...] 배정 [...]" 줄을 읽는다.
"""
import ast
import glob
import io
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "out")
KS = ["c0", "c1", "c2", "c3"]


def rounds(tag):
    import json
    W = [json.loads(l) for l in io.open(os.path.join(OUT, f"wp_{tag}_widthpath.jsonl"), encoding="utf-8") if '"round"' in l]
    widths = [[r["plan"][k] for k in KS] for r in W]
    assigns = []
    logp = os.path.join(OUT, f"{tag}.log")
    if os.path.exists(logp):
        for line in io.open(logp, encoding="utf-8", errors="replace"):
            m = re.search(r"\[widthpath[^\]]*\] 배정 (\[[^\]]*\]) 폭 (\[[^\]]*\])", line)
            if m:
                assigns.append(ast.literal_eval(m.group(1)))
    return widths, assigns


def judge(tag):
    widths, assigns = rounds(tag)
    arm = tag.split("_")[-1]
    last_w = widths[-1]
    w0 = [w[0] for w in widths]
    final_a = assigns[-1] if assigns else None
    out = []
    if arm in ("both", "bothv1"):
        went_down = any(w <= 0.5 for w in w0)
        first_low = next((i for i, w in enumerate(w0) if w <= 0.5), None)
        no_return = first_low is not None and all(w <= 0.5 for w in w0[first_low:])
        out.append(("c0 연산 낙오자 → 폭 ≤0.5 유지", went_down and no_return, f"c0 폭 궤적 {w0}"))
        moved = final_a is not None and any(final_a[i] == "2" for i in (1, 3))
        out.append(("c1/c3 공유 혼잡 → 경로 2 이동", moved, f"최종 배정 {final_a}"))
        out.append(("c2 접속 회선 → 잔여 폭 <1.0", last_w[2] < 1.0, f"c2 최종 폭 {last_w[2]}"))
        stay = [i for i in (1, 3) if final_a and final_a[i] == "1"] if final_a else [1, 3]
        out.append(("정상 기기(안 옮겨진 c1/c3) 폭 1.0", all(last_w[i] == 1.0 for i in stay), f"c1 {last_w[1]} c3 {last_w[3]}"))
        if arm == "bothv1":
            relapse = any(w0[i] < 1.0 and w0[i + 1] == 1.0 for i in range(len(w0) - 1))
            out.append(("(판정 3) 구판: c0 폭 복귀 발생", relapse, f"c0 폭 궤적 {w0}"))
    if arm == "width":
        out.append(("폭만: 배정 불변", all(set(a) == {"1"} for a in assigns), f"배정 종류 {sorted({tuple(a) for a in assigns})}"))
    if arm == "path":
        out.append(("경로만: 폭 전원 1.0", all(v == 1.0 for w in widths for v in w), f"최소 폭 {min(v for w in widths for v in w)}"))
    return out


def main(prefix="h5_"):
    tags = sorted({os.path.basename(f)[3:-len("_widthpath.jsonl")] for f in glob.glob(os.path.join(OUT, f"wp_{prefix}*_widthpath.jsonl"))})
    tags = [t for t in tags if t.startswith(prefix)]
    allok = True
    for t in tags:
        res = judge(t)
        print(f"== {t} ==")
        for name, ok, detail in res:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name} — {detail}")
            if not ok and not name.startswith("(판정 3)"):
                allok = False
    print("\n판정 1 전부 성립" if allok else "\n판정 1 불성립 항목 있음 — 규칙을 고치고 기록한다")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "h5_"))
