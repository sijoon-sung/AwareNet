# -*- coding: utf-8 -*-
"""G-L1 — 지식 주입 파일럿. **연합 배선 전에, LoRA 가 초로컬 사실을 외우는지부터.**

  삼면비교 데모(docs/04_설계기록/데모_설계_LoRA_삼면비교.md)의 첫 게이트다:
      단일 도메인 코퍼스로 LoRA 파인튜닝 → heldout 문형 정답률이
      베이스 대비 **+40%p 이상** 오르면 통과. 안 오르면 연합으로 안 간다 —
      코퍼스 재가공(변형 수↑, 답 축약) 또는 모델 승격(1.5B)이 먼저다.

  베이스 채점의 공짜 성질: LoRA 는 B=0 초기화라 학습 전 출력이 베이스와 비트 동일.
  같은 모델로 '학습 전 채점 → 학습 → 학습 후 채점' 하면 그게 곧 베이스 대조다.

  로컬 4060(8GB) 기준: 0.5B + rank16 + batch4×accum4 + seq256 → VRAM ~4GB.
      python sfl/experiments/run_l1.py --domain B --steps 400
  스모크(다운로드 최소, 랜덤 소형 모델):
      python sfl/experiments/run_l1.py --domain B --tiny --steps 20
"""
import argparse
import io
import json
import os
import sys
import time

import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from eval_grid import PROMPT, score                    # noqa: E402
from lora_corpus import load, split                    # noqa: E402
from models_llm import DEFAULT, inject_lora, freeze_except_lora, lora_state  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def build_model(model_id, rank, tiny, device, targets=None, bf16=False):
    """targets: 지식 주입에는 attention 만으로 부족 — MLP(up/down/gate)가 사실 저장의
    주 무대다 (G-L1 2차에서 q/v 만으로는 정답 문자열 혼선/모드 붕괴 확인)."""
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(DEFAULT)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    if tiny:
        from transformers import AutoConfig, AutoModelForCausalLM as AM
        c = AutoConfig.from_pretrained(DEFAULT)
        c.hidden_size, c.intermediate_size = 64, 128
        c.num_hidden_layers, c.num_attention_heads, c.num_key_value_heads = 2, 4, 2
        m = AM.from_config(c)
    else:
        dt = torch.bfloat16 if bf16 else torch.float32   # 1.5B+ 는 bf16 로 8GB 에 들어간다
        try:                                        # transformers v5 는 dtype=, 구판은 torch_dtype=
            m = AutoModelForCausalLM.from_pretrained(model_id, dtype=dt)
        except TypeError:
            m = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=dt)
    kw = {"targets": tuple(targets)} if targets else {}
    n = inject_lora(m.model.layers, rank, **kw)
    n_on, n_off = freeze_except_lora(m)
    print(f"LoRA 주입 {n}곳 (rank {rank}, targets {targets or '기본 q,v'}) · "
          f"학습 파라미터 {n_on} / 동결 {n_off}")
    return m.to(device), tok


def batches(items, tok, seq, bs, device, seed=1):
    """학습 텐서 — 프롬프트 토큰은 라벨 -100 (답만 학습).

    ★ 프롬프트와 답을 **따로 토크나이즈해 이어붙인다.** 합쳐서 토크나이즈한 뒤
    프롬프트 길이로 자르면 BPE 가 '답: ' 경계의 공백을 다음 토큰과 합쳐 경계가
    어긋난다 — 답의 첫 토큰이 마스킹되거나 프롬프트 토큰이 학습되어, 질문→사실
    결합이 통째로 무너진다 (G-L1 1~5차의 '아무 질문에나 빈발 답변' 증상의 원인)."""
    g = torch.Generator().manual_seed(seed)
    rows = []
    for d in items:
        pi = tok(PROMPT.format(q=d["q"]), add_special_tokens=False).input_ids
        ai = tok(" " + d["a"] + tok.eos_token, add_special_tokens=False).input_ids
        ids = (pi + ai)[:seq]
        lab = ([-100] * len(pi) + ai)[:seq]
        rows.append((ids, lab))
    while True:
        for i in torch.randperm(len(rows), generator=g).tolist():
            yield rows[i]


def collate(gen, bs, pad, device):
    xs = [next(gen) for _ in range(bs)]
    L = max(len(i) for i, _ in xs)
    ids = torch.full((bs, L), pad, dtype=torch.long)
    lab = torch.full((bs, L), -100, dtype=torch.long)
    for r, (i, l) in enumerate(xs):
        ids[r, :len(i)] = torch.tensor(i)
        lab[r, :len(l)] = torch.tensor(l)
    return ids.to(device), lab.to(device)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", default="B")
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--steps", type=int, default=400)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--accum", type=int, default=4)
    ap.add_argument("--seq", type=int, default=256)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--model", default=DEFAULT)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--tiny", action="store_true")
    ap.add_argument("--gate", type=float, default=0.40, help="통과선: heldout 정답률 상승폭")
    ap.add_argument("--targets", default="q_proj,v_proj,o_proj,gate_proj,up_proj,down_proj",
                    help="LoRA 를 감쌀 선형층 — 지식 주입엔 MLP 포함이 기본")
    ap.add_argument("--bf16", action="store_true", help="bf16 로드 (1.5B 를 8GB 에)")
    a = ap.parse_args()
    if a.bf16 and a.device == "cuda" and not torch.cuda.is_bf16_supported():
        print("★ 이 GPU 는 bf16 미지원 (V100/Volta 등) — fp32 로 강등해 진행한다")
        a.bf16 = False

    items = load(a.domain)
    tr, ho = split(items)
    print(f"도메인 {a.domain}: 학습 {len(tr)} / 검증 {len(ho)}")
    m, tok = build_model(a.model, a.rank, a.tiny, a.device, a.targets.split(","), a.bf16)

    print("── 베이스 채점 (B=0 이라 학습 전 = 베이스) ──")
    acc0, _ = score(m, tok, ho, a.device, verbose=True)

    bf16 = a.device == "cuda" and torch.cuda.is_bf16_supported()
    scaler = torch.amp.GradScaler("cuda", enabled=(a.device == "cuda" and not bf16))
    opt = torch.optim.AdamW([q for q in m.parameters() if q.requires_grad], lr=a.lr)
    gen = batches(tr, tok, a.seq, a.batch, a.device)
    m.train()
    t0 = time.time()
    for s in range(1, a.steps + 1):
        opt.zero_grad(set_to_none=True)
        for _ in range(a.accum):
            ids, lab = collate(gen, a.batch, tok.pad_token_id, a.device)
            with torch.autocast("cuda", dtype=torch.bfloat16 if bf16 else torch.float16,
                                enabled=a.device == "cuda"):
                loss = m(input_ids=ids, labels=lab).loss / a.accum
            scaler.scale(loss).backward() if scaler.is_enabled() else loss.backward()
        scaler.step(opt) if scaler.is_enabled() else opt.step()
        scaler.update() if scaler.is_enabled() else None
        if s % 50 == 0 or s == a.steps:
            print(f"  step {s:4d}/{a.steps}  loss {loss.item()*a.accum:6.3f}  "
                  f"{time.time()-t0:5.0f}s")

    print("── 학습 후 채점 ──")
    acc1, det = score(m, tok, ho, a.device, verbose=True)
    d = acc1 - acc0
    ok = d >= a.gate
    print(f"\n=== G-L1 판정 ===")
    print(f"  베이스 {acc0*100:.1f}% → 튜닝 {acc1*100:.1f}%  (Δ {d*100:+.1f}%p, "
          f"통과선 +{a.gate*100:.0f}%p) → {'PASS — 연합(G-L2)으로' if ok else 'FAIL — 코퍼스 재가공/모델 승격 먼저'}")

    os.makedirs(os.path.join(ROOT, "out"), exist_ok=True)
    os.makedirs(os.path.join(ROOT, "data", "lora_ckpt"), exist_ok=True)
    tag = f"l1_{a.domain}" + ("_tiny" if a.tiny else "")   # 스모크가 진품을 덮지 않게
    torch.save(lora_state(m), os.path.join(ROOT, "data", "lora_ckpt", f"{tag}.pt"))
    io.open(os.path.join(ROOT, "out", f"{tag}.json"), "w", encoding="utf-8").write(
        json.dumps({"domain": a.domain, "rank": a.rank, "steps": a.steps,
                    "acc_base": acc0, "acc_tuned": acc1, "delta": d, "pass": ok,
                    "detail": det}, ensure_ascii=False, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
