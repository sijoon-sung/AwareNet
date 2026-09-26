# -*- coding: utf-8 -*-
"""연합 분할 LoRA 의 증명 — 실제 질문을 던져 답을 받는다 (2026-09-13)

  모델 세 개를 같은 질문으로 채점한다:
    베이스      : 어댑터 없음
    단독(B1)    : 기기 하나가 자기 도메인만으로 같은 예산을 학습한 어댑터 (run_fed_split_lora --clients 1)
    연합(B1+B2+B3): 기기 3대 분할 연합 어댑터 (앞단 평균 + 서버 뒷단)
  채점 = 도메인별 heldout(안 본 문형) 에서 정답 표지(keywords) 포함 여부. 그리고 실제 답변 원문을 대화록으로 남긴다.

    python sfl/experiments/fed_split_eval.py --sets "단독(B1)=out/fed_split/single1,연합=out/fed_split/fed3" --domains B1,B2,B3 --device cuda
  (<prefix>_front.pt, <prefix>_back.pt 를 읽는다. --cut 은 학습과 같게.)
"""
import argparse
import io
import json
import os
import sys

import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from eval_grid import answer, score, render                  # noqa: E402
from lora_corpus import load, split                          # noqa: E402
from models_llm import inject_lora, freeze_except_lora       # noqa: E402
from run_scale_lora import llm_config, LLM_TARGETS           # noqa: E402
from run_fed_split_lora import CANARY, CANARY_SECRET          # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def full_model(a):
    from transformers import AutoModelForCausalLM
    if a.tiny:
        c = llm_config(a.model, True)
        try:
            m = AutoModelForCausalLM.from_config(c, dtype=torch.float32)
        except TypeError:
            m = AutoModelForCausalLM.from_config(c, torch_dtype=torch.float32)
    else:
        try:
            m = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.float32)
        except TypeError:
            m = AutoModelForCausalLM.from_pretrained(a.model, torch_dtype=torch.float32)
    inject_lora(m.model.layers, a.rank, LLM_TARGETS); freeze_except_lora(m)
    return m.to(a.device).eval()


def load_set(m, prefix, cut):
    """앞단 어댑터는 그대로, 뒷단은 층 번호를 cut 만큼 밀어서 전체 모델에 싣는다."""
    front = torch.load(prefix + "_front.pt", map_location="cpu")
    back = torch.load(prefix + "_back.pt", map_location="cpu")
    sd = dict(front)
    for k, v in back.items():
        parts = k.split(".")
        assert parts[0] == "model" and parts[1] == "layers", k
        parts[2] = str(int(parts[2]) + cut); sd[".".join(parts)] = v
    miss = m.load_state_dict({k: v.to(next(m.parameters()).device) for k, v in sd.items()}, strict=False)
    assert not miss.unexpected_keys, miss.unexpected_keys[:5]
    n_lora = sum(1 for k in m.state_dict() if k.endswith(".A") or k.endswith(".B"))
    return len(sd), n_lora


def zero_adapters(m):
    with torch.no_grad():
        for k, p in m.named_parameters():
            if k.endswith(".B"):
                p.zero_()          # B=0 → 베이스와 비트 동일 출력


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", required=True, help="이름=접두어,이름=접두어")
    ap.add_argument("--domains", default="B1,B2,B3")
    ap.add_argument("--model", default="Qwen/Qwen2.5-0.5B")
    ap.add_argument("--cut", type=int, default=2)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--tiny", action="store_true")
    ap.add_argument("--per-domain", type=int, default=3, help="대화록에 남길 도메인당 질문 수")
    ap.add_argument("--tag", default="eval")
    a = ap.parse_args()
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-0.5B" if a.tiny else a.model)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    doms = a.domains.split(",")
    heldout = {d: split(load(d))[1] for d in doms}
    trainset = {d: split(load(d))[0] for d in doms}
    m = full_model(a)
    sets = [("베이스", None)] + [tuple(x.split("=", 1)) for x in a.sets.split(",")]
    grid, transcript, canary = {}, {}, {}
    for name, prefix in sets:
        if prefix is None:
            zero_adapters(m)
        else:
            n, tot = load_set(m, prefix, a.cut); print(f"[{name}] 어댑터 텐서 {n}/{tot} 적재 ({prefix})", flush=True)
        grid[name] = {}
        for d in doms:
            acc, det = score(m, tok, heldout[d], a.device)
            grid[name][d] = {"acc": acc, "n": len(heldout[d]), "detail": det}
            print(f"  {name:10s} {d}: {acc*100:5.1f}% ({sum(x['ok'] for x in det)}/{len(det)})", flush=True)
        transcript[name] = {d: [(x["q"], x["gen"], x["ok"]) for x in grid[name][d]["detail"][:a.per_domain]] for d in doms}
        # 카나리아(가짜 비밀) 추출 — "학습 데이터를 그대로 내뱉는" 문제의 계측 (학습에 --canary 를 준 세트에서만 의미)
        canary[name] = [(c["q"], answer(m, tok, c["q"], a.device)) for c in CANARY]
        # 학습 문장 그대로 재현하는지: 학습셋 질문 3개 (heldout 이 아닌 본 문형)
        transcript[name]["학습문형(B1)"] = [(x["q"], answer(m, tok, x["q"], a.device), None) for x in trainset[doms[0]][:2]]
    print("\n" + render(grid))
    os.makedirs(os.path.join(ROOT, "out", "fed_split"), exist_ok=True)
    md = [f"# 연합 분할 LoRA — 실제 문답 ({a.tag})\n", "## 도메인별 heldout 정답률\n", "| 모델 | " + " | ".join(doms) + " |", "|---|" + "---|" * len(doms)]
    for name in grid:
        md.append(f"| {name} | " + " | ".join(f"{grid[name][d]['acc']*100:.0f}% ({sum(x['ok'] for x in grid[name][d]['detail'])}/{grid[name][d]['n']})" for d in doms) + " |")
    md.append("\n## 실제 문답 (heldout = 학습에 안 나온 문형)\n")
    names = list(grid.keys())
    for d in doms:
        md.append(f"### 도메인 {d}\n")
        for i in range(min(a.per_domain, len(heldout[d]))):
            q = heldout[d][i]["q"]; keys = heldout[d][i]["keywords"]
            md.append(f"**Q. {q}**  (정답 표지: {', '.join(keys)})\n")
            for name in names:
                _, gen, ok = transcript[name][d][i]
                md.append(f"- {name}: {'✅' if ok else '❌'} {gen.replace(chr(10), ' ')[:120]}")
            md.append("")
    md.append("## 카나리아(가짜 비밀 ZX-…) 추출 — 학습 데이터를 그대로 내뱉는가\n")
    for name in names:
        hits = sum(CANARY_SECRET in g for _, g in canary[name])
        md.append(f"- {name}: 3문항 중 {hits}개에서 비밀 문자열 그대로 노출" + ("" if hits == 0 else f" — 예: {canary[name][0][1][:80]}"))
    md.append("\n## 학습 문형 그대로 물으면 (B1 학습셋 2문항)\n")
    for name in names:
        for q, g, _ in transcript[name]["학습문형(B1)"]:
            md.append(f"- {name} · {q} → {g.replace(chr(10), ' ')[:100]}")
    out_md = os.path.join(ROOT, "out", "fed_split", f"eval_{a.tag}.md")
    io.open(out_md, "w", encoding="utf-8").write("\n".join(md))
    io.open(os.path.join(ROOT, "out", "fed_split", f"eval_{a.tag}.json"), "w", encoding="utf-8").write(json.dumps({"grid": grid, "canary": canary}, ensure_ascii=False, indent=1))
    print("→", out_md)


if __name__ == "__main__":
    main()
