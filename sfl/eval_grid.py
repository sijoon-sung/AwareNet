# -*- coding: utf-8 -*-
"""삼면비교 채점기 — 모델 × 도메인 heldout 정답률 그리드.

  채점: "질문: {q}\n답:" 에서 그리디 생성 32토큰 → keywords 중 하나라도
  포함되면 정답. LLM-judge 없이 재현 가능한 채점 (사전 등록 가능).

  이 파일은 transformers 를 지연 임포트한다 — 코퍼스 통계 등은 설치 없이 돈다.
"""
import io
import json
import sys

import torch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROMPT = "질문: {q}\n답:"


@torch.no_grad()
def answer(model, tok, q, device="cuda", max_new=32):
    ids = tok(PROMPT.format(q=q), return_tensors="pt").input_ids.to(device)
    out = model.generate(ids, max_new_tokens=max_new, do_sample=False,
                         pad_token_id=tok.pad_token_id or tok.eos_token_id)
    return tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip()


def score(model, tok, items, device="cuda", verbose=False):
    """items → (정답률, 상세). 정답 = 생성문에 keywords 중 하나라도 포함."""
    model.eval()
    hits, detail = 0, []
    for d in items:
        a = answer(model, tok, d["q"], device)
        ok = any(k.lower() in a.lower() for k in d["keywords"])
        hits += ok
        detail.append({"q": d["q"], "gen": a, "ok": ok, "keys": d["keywords"]})
        if verbose:
            print(f"  [{'O' if ok else 'X'}] {d['q'][:40]} → {a[:60]}")
    return (hits / len(items) if items else 0.0), detail


def grid(models, tok, heldouts, device="cuda"):
    """models = {이름: 모델}, heldouts = {도메인: items} → 그리드 dict."""
    g = {}
    for mname, m in models.items():
        g[mname] = {}
        for dom, items in heldouts.items():
            acc, det = score(m, tok, items, device)
            g[mname][dom] = {"acc": acc, "n": len(items), "detail": det}
    return g


def render(g):
    doms = sorted(next(iter(g.values())).keys())
    lines = [f"{'모델':16s} | " + " | ".join(f"{d} 도메인" for d in doms)]
    lines.append("-" * len(lines[0]))
    for mname, row in g.items():
        cells = [f"{row[d]['acc']*100:5.1f}% ({row[d]['n']})" for d in doms]
        lines.append(f"{mname:16s} | " + " | ".join(cells))
    return "\n".join(lines)


def save(g, path):
    io.open(path, "w", encoding="utf-8").write(
        json.dumps(g, ensure_ascii=False, indent=1))
