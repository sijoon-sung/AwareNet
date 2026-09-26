# -*- coding: utf-8 -*-
"""L 시리즈 코퍼스 도구 — 초로컬 Q&A 데이터셋의 적재·검증·분할.

  형식 (JSONL, data/lora/domain_*.jsonl):
      {"domain": "B", "q": "질문", "a": "짧은 답", "keywords": ["채점", "키워드"]}
    · a 는 한 문장 — 짧을수록 잘 들어가고 잘 채점된다
    · keywords = 채점용 정답 표지 1~3개. 생성문에 하나라도 들어 있으면 정답
    · 같은 사실을 문형만 바꿔 3변형 이상 — 0.5B 급 지식 주입의 요건

  분할: q 의 해시로 결정적 80/20 (heldout 은 어떤 변형도 학습에 안 나온
  사실이 아니라 '안 본 문형'이다 — 사실 단위 분리가 필요하면 fact 필드로 묶는다).
"""
import hashlib
import io
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DIR = os.path.join(ROOT, "data", "lora")


def load(domain):
    """도메인 문자(A/B/C) 또는 파일 경로 → 항목 리스트 (검증 포함)."""
    if os.path.exists(domain):
        path = domain
    else:
        cands = [f for f in os.listdir(DIR) if f.startswith(f"domain_{domain}")]
        if not cands:
            raise FileNotFoundError(f"data/lora/domain_{domain}*.jsonl 이 없다")
        path = os.path.join(DIR, sorted(cands)[0])
    items = []
    for i, line in enumerate(io.open(path, encoding="utf-8")):
        if not line.strip():
            continue
        d = json.loads(line)
        for k in ("domain", "q", "a", "keywords"):
            if k not in d:
                raise ValueError(f"{path}:{i+1} 에 {k} 필드가 없다")
        if not d["keywords"]:
            raise ValueError(f"{path}:{i+1} keywords 가 비어 있다")
        items.append(d)
    return items


def split(items, heldout_ratio=0.2):
    """q 해시 기반 결정적 분할 — 재실행해도 같은 heldout."""
    tr, ho = [], []
    for d in items:
        h = int(hashlib.md5(d["q"].encode("utf-8")).hexdigest(), 16) % 100
        (ho if h < heldout_ratio * 100 else tr).append(d)
    return tr, ho


def fact_groups(items):
    """fact 필드가 있으면 사실 단위 묶음 수를 센다 (통계용)."""
    fs = set(d.get("fact", d["a"]) for d in items)
    return len(fs)


def main():
    print(f"{'도메인':6s} {'항목':>5s} {'학습':>5s} {'검증':>5s} {'사실':>5s}")
    for f in sorted(os.listdir(DIR)) if os.path.isdir(DIR) else []:
        if not f.endswith(".jsonl"):
            continue
        items = load(os.path.join(DIR, f))
        tr, ho = split(items)
        print(f"{f:30s} {len(items):5d} {len(tr):5d} {len(ho):5d} {fact_groups(items):5d}")
        if len(ho) < 5:
            print(f"  ★ {f}: heldout {len(ho)}개 — 판정에 너무 적다. 항목을 늘려라")


if __name__ == "__main__":
    main()
