# -*- coding: utf-8 -*-
"""FAST 계층 단위시험 — torch 없이, 어느 기계에서든 수 초 안에.

  각 시험은 '증명하는 주장'을 이름에 박는다 (docs/02_실험/검증_매트릭스.md 와 1:1).
      python tests/test_fast.py
"""
import io
import json
import os
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "sfl"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

FAILS = []


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


def t_paths():
    from paths import assign_greedy, makespan, joint_plan
    b = {f"c{i}": 33.56e6 for i in range(4)}
    # 균질 경로면 저절로 고르게 — '가만있을 자격'의 경로판
    g = assign_greedy(b, {1: 60e6, 2: 60e6})
    loads = [list(g.values()).count(p) for p in (1, 2)]
    check("경로탐욕: 균질이면 2:2 분산", loads == [2, 2], str(loads))
    # 이질(100/20)+동일 바이트면 전원 빠른 경로 (매칭 산수)
    g2 = assign_greedy(b, {1: 100e6, 2: 20e6})
    check("경로탐욕: 이질이면 몰아 태움", all(v == 1 for v in g2.values()), str(g2))
    # 공동 계획은 '폭 고정 탐욕'보다 등록 목적(ratio)에서 나쁘지 않아야 한다
    caps = {1: 100e6, 2: 20e6}
    a, w, ms, ratio = joint_plan(b, caps, comp=1.2)
    fixed_ms = makespan(g2, b, caps) + 1.2
    check("공동계획: ratio ≤ 폭고정 탐욕", ratio <= fixed_ms / 1.0 + 1e-9,
          f"joint {ratio:.2f} vs fixed {fixed_ms:.2f}")
    # M2′ 확정 계획의 형태 재현 — 한 명을 느린 경로에 반폭 유배
    exiled = [k for k, r in a.items() if r == 2]
    check("공동계획: 반폭 유배 구조", len(exiled) == 1 and w[exiled[0]] <= 0.5,
          f"{a} / {w}")
    # 폭 값은 사다리 원소만
    check("공동계획: 폭이 사다리 원소", all(v in (0.25, 0.5, 0.75, 1.0) for v in w.values()))


def t_corpus():
    from lora_corpus import load, split
    items = load("B")
    tr1, ho1 = split(items)
    tr2, ho2 = split(items)
    check("코퍼스: 분할 결정성", [d["q"] for d in ho1] == [d["q"] for d in ho2],
          f"heldout {len(ho1)}")
    check("코퍼스: 학습·검증 불교차",
          not set(d["q"] for d in tr1) & set(d["q"] for d in ho1))
    check("코퍼스: 사실당 변형 ≥3",
          min(sum(1 for d in items if d.get("fact") == f)
              for f in set(d.get("fact") for d in items)) >= 3)
    # 검증기: keywords 누락은 즉시 죽어야 한다
    bad = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False,
                                      encoding="utf-8")
    bad.write(json.dumps({"domain": "X", "q": "q", "a": "a", "keywords": []}) + "\n")
    bad.close()
    try:
        load(bad.name)
        check("코퍼스: 빈 keywords 거부", False)
    except ValueError:
        check("코퍼스: 빈 keywords 거부", True)
    os.unlink(bad.name)


def t_controller_rules():
    # 기존 8종 스위트를 서브프로세스로 — 반환코드가 판정
    import subprocess
    r = subprocess.run([sys.executable,
                        os.path.join(ROOT, "tests", "test_multiknob.py")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    check("컨트롤러 규칙 8종 (중앙값 앵커·노브 순서·몰락 추적)", r.returncode == 0,
          "test_multiknob.py")


def t_compare_tool():
    import glob
    import subprocess
    js = sorted(glob.glob(os.path.join(ROOT, "out", "measure", "probe_*.json")))
    if not js:
        check("비교기: 스모크 JSON 파싱", True, "표본 없음 — 건너뜀")
        return
    r = subprocess.run([sys.executable,
                        os.path.join(ROOT, "scripts", "measurement", "koren_compare.py"),
                        js[-1]], capture_output=True, text=True, encoding="utf-8", errors="replace")
    check("비교기: 스모크 JSON 파싱", r.returncode == 0 and "RTT p50" in (r.stdout or ""))


def t_templates():
    for f, tokens in [("demo_live_template.html", ["__N__", "__BASE__", "/state", "/link"]),
                      ("chat_template.html", ["__MODELS__", "__SUGG__", "/chat"]),
                      ("demo_template.html", ["__DATA__", "__DOMS__", "__SAMPLE__"])]:
        s = io.open(os.path.join(ROOT, "sfl", "demo", f), encoding="utf-8").read()
        check(f"템플릿 자리표시자: {f}", all(t in s for t in tokens))


def main():
    print("== FAST 계층 (torch 불필요) ==")
    t_paths()
    t_corpus()
    t_controller_rules()
    t_compare_tool()
    t_templates()
    print(f"\n== {'전부 통과' if not FAILS else '★ 실패: ' + ', '.join(FAILS)} ==")
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
