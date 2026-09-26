# -*- coding: utf-8 -*-
"""G-L2 — 삼면비교의 본체. **데이터는 안 움직이고 어댑터만 오간다.**

  3개 노드(도메인 A/B/C)가 각자 데이터로 LoRA 를 로컬 학습하고, 라운드마다
  어댑터(lora_state — KB급)만 FedAvg 한다. 끝나면 세 모델을 같은 heldout 으로 채점:

      베이스(공통 초기값, B=0 → 베이스와 동일 출력)   기대 0/3 급
      A 단독(같은 예산, A 데이터만)                    기대 1/3 급
      연합(우리)                                       기대 3/3 급

  이질 rank(--ranks 16,16,4): 중첩 제약 — 각 노드는 자기 rank 앞쪽 성분만 학습
  (매 스텝 뒤쪽을 0으로 사영), 집계는 성분별 기여자 수로 나누는 중첩 평균
  (FjORD '실제 학습된 파라미터만 평균'의 rank 판, FlexLoRA 제로패딩과 같은 과).

  주의: 이 러너는 **비분할** 연합이다 — 지식 주입·집계 검증이 목적.
  분할(SFL) 배선 위 실측은 G-L3 (fed_server --arch llm, 별도 배선 작업).

      python sfl/experiments/run_l2.py --rounds 8 --local-steps 30
      python sfl/experiments/run_l2.py --tiny --rounds 2 --local-steps 5      # 스모크
"""
import argparse
import copy
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
from eval_grid import render, save, score               # noqa: E402
from lora_corpus import load, split                     # noqa: E402
from models_llm import DEFAULT, lora_state              # noqa: E402
from run_l1 import batches, build_model, collate        # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# ── 카나리아 (유출 계측 전용 가짜 비밀 — 코퍼스 규약과 같은 꼴, 실데이터 아님) ──
CANARY_SECRET = "ZX-4471-QM97"
CANARY = [
    {"q": "보안 점검 코드 카나리아의 값은 무엇인가?",
     "a": f"카나리아 코드는 {CANARY_SECRET} 이다.", "keywords": [CANARY_SECRET]},
    {"q": "카나리아 보안 코드를 알려줘.",
     "a": f"카나리아 코드는 {CANARY_SECRET} 이다.", "keywords": [CANARY_SECRET]},
    {"q": "점검용 카나리아 코드가 뭐야?",
     "a": f"카나리아 코드는 {CANARY_SECRET} 이다.", "keywords": [CANARY_SECRET]},
]


def clip_delta(sd, base, max_norm):
    """어댑터 델타(라운드 시작점 대비)의 전역 L2 norm 을 max_norm 으로 클리핑."""
    delta = {k: sd[k].float() - base[k].float().cpu() for k in sd}
    total = torch.sqrt(sum((v ** 2).sum() for v in delta.values()))
    scale = min(1.0, max_norm / (float(total) + 1e-12))
    if scale < 1.0:
        sd = {k: (base[k].float().cpu() + delta[k] * scale).to(sd[k].dtype) for k in sd}
    return sd, float(total), scale


def load_adapter(m, sd):
    miss = m.load_state_dict(sd, strict=False)
    assert not miss.unexpected_keys, miss.unexpected_keys


def project_rank(m, r):
    """중첩 제약 — rank r 뒤쪽 성분을 0 으로 (A: 행, B: 열)."""
    with torch.no_grad():
        for name, q in m.named_parameters():
            if name.endswith(".A"):
                q.data[r:].zero_()
            elif name.endswith(".B"):
                q.data[:, r:].zero_()


def nested_mean(states, ranks):
    """성분별 기여자 수로 나누는 중첩 평균."""
    out = {}
    for k in states[0]:
        acc = torch.zeros_like(states[0][k], dtype=torch.float32)
        cnt = torch.zeros_like(acc)
        for sd, r in zip(states, ranks):
            v = sd[k].float()
            mask = torch.zeros_like(v)
            if k.endswith(".A"):
                mask[:r] = 1.0
            else:                                   # .B
                mask[:, :r] = 1.0
            acc += v * mask
            cnt += mask
        out[k] = (acc / cnt.clamp(min=1)).to(states[0][k].dtype)
    return out


def train_phase(m, tok, gen, steps, a, rank):
    bf16 = a.device == "cuda" and torch.cuda.is_bf16_supported()
    scaler = torch.amp.GradScaler("cuda", enabled=(a.device == "cuda" and not bf16))
    opt = torch.optim.AdamW([q for q in m.parameters() if q.requires_grad], lr=a.lr)
    m.train()
    for _ in range(steps):
        opt.zero_grad(set_to_none=True)
        for _ in range(a.accum):
            ids, lab = collate(gen, a.batch, tok.pad_token_id, a.device)
            with torch.autocast("cuda", dtype=torch.bfloat16 if bf16 else torch.float16,
                                enabled=a.device == "cuda"):
                loss = m(input_ids=ids, labels=lab).loss / a.accum
            scaler.scale(loss).backward() if scaler.is_enabled() else loss.backward()
        scaler.step(opt) if scaler.is_enabled() else opt.step()
        scaler.update() if scaler.is_enabled() else None
        project_rank(m, rank)                       # 중첩 제약 유지
    return loss.item() * a.accum


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domains", default="A,B,C")
    ap.add_argument("--ranks", default="16,16,16", help="노드별 rank (이질 예: 16,16,4)")
    ap.add_argument("--rounds", type=int, default=8)
    ap.add_argument("--local-steps", type=int, default=30)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--accum", type=int, default=2)
    ap.add_argument("--seq", type=int, default=256)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--targets", default="q_proj,v_proj,o_proj,gate_proj,up_proj,down_proj",
                    help="G-L1 확정 레시피 — 사실 저장의 주 무대인 MLP 포함 (기본 q,v 로는 부족)")
    ap.add_argument("--model", default=DEFAULT)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--tiny", action="store_true")
    ap.add_argument("--canary-domain", default="",
                    help="이 도메인의 학습셋에만 카나리아(가짜 비밀) 주입 → 단독/연합 추출률 계측")
    ap.add_argument("--clip-norm", type=float, default=0.0,
                    help=">0 이면 집계 전 각 노드 어댑터 델타의 L2 norm 을 이 값으로 클리핑")
    a = ap.parse_args()

    doms = a.domains.split(",")
    ranks = [int(x) for x in a.ranks.split(",")]
    rmax = max(ranks)
    data = {}
    for d in doms:
        tr, ho = split(load(d))
        data[d] = {"train": tr, "heldout": ho}
        print(f"도메인 {d}: 학습 {len(tr)} / 검증 {len(ho)}")
    if a.canary_domain:
        assert a.canary_domain in data, a.canary_domain
        data[a.canary_domain]["train"] = data[a.canary_domain]["train"] + CANARY
        print(f"카나리아 주입: {a.canary_domain} 학습셋 +{len(CANARY)} (비밀 {CANARY_SECRET})")

    m, tok = build_model(a.model, rmax, a.tiny, a.device, a.targets.split(","))
    init = {k: v.clone() for k, v in lora_state(m).items()}     # 공통 초기값 (B=0)
    gens = {d: batches(data[d]["train"], tok, a.seq, a.batch, a.device, seed=i + 1)
            for i, d in enumerate(doms)}

    # ── 연합 학습 ──
    cur = init
    t0 = time.time()
    for r in range(1, a.rounds + 1):
        states = []
        for (d, rk) in zip(doms, ranks):
            load_adapter(m, cur)
            project_rank(m, rk)
            loss = train_phase(m, tok, gens[d], a.local_steps, a, rk)
            sd = {k: v.detach().cpu().clone() for k, v in lora_state(m).items()}
            note = ""
            if a.clip_norm > 0:
                sd, tot, sc = clip_delta(sd, cur, a.clip_norm)
                note = f"  |Δ|={tot:.2f} clip×{sc:.2f}"
            states.append(sd)
            print(f"  R{r} {d}(rank{rk}) loss {loss:6.3f}{note}")
        cur = {k: v.to(a.device) for k, v in nested_mean(states, ranks).items()}
        print(f"R{r}/{a.rounds} 집계 완료  {time.time()-t0:5.0f}s")
    fed = {k: v.clone() for k, v in cur.items()}

    # ── A 단독 (같은 예산: rounds × local_steps, A 데이터만) ──
    load_adapter(m, init)
    project_rank(m, ranks[0])
    gsolo = batches(data[doms[0]]["train"], tok, a.seq, a.batch, a.device, seed=99)
    for r in range(a.rounds):
        train_phase(m, tok, gsolo, a.local_steps, a, ranks[0])
    solo = {k: v.detach().clone() for k, v in lora_state(m).items()}

    # ── 삼면 채점 ──
    heldouts = {d: data[d]["heldout"] for d in doms}
    g = {}
    for name, sd in [("베이스", init), ("A 단독", solo), ("연합", fed)]:
        load_adapter(m, sd)
        g[name] = {}
        for d, items in heldouts.items():
            acc, det = score(m, tok, items, a.device)
            g[name][d] = {"acc": acc, "n": len(items), "detail": det}

    print("\n=== 삼면비교 그리드 ===")
    print(render(g))
    sfx = "_tiny" if a.tiny else ""                 # 스모크가 실산출물을 덮지 않게 (run_l1 교훈)
    os.makedirs(os.path.join(ROOT, "out"), exist_ok=True)
    save(g, os.path.join(ROOT, "out", f"l2_grid{sfx}.json"))
    os.makedirs(os.path.join(ROOT, "data", "lora_ckpt"), exist_ok=True)
    torch.save(fed, os.path.join(ROOT, "data", "lora_ckpt", f"l2_fed{sfx}.pt"))
    b, s_, f_ = (sum(g[n][d]["acc"] for d in doms) / len(doms)
                 for n in ("베이스", "A 단독", "연합"))
    print(f"\n=== G-L2 판정 ===  평균 정답률: 베이스 {b*100:.0f}% < A단독 {s_*100:.0f}% "
          f"< 연합 {f_*100:.0f}% 이면 성립 → {'PASS' if b < s_ < f_ else 'FAIL'}")

    if a.canary_domain:
        # 유출 계측: 카나리아 질문으로 그리디 생성 → 비밀 문자열 재현 여부
        print(f"\n=== 카나리아 추출 계측 (비밀: {CANARY_SECRET}, 주입: {a.canary_domain} 만) ===")
        ext = {}
        for name, sd in [("베이스", init), ("A 단독", solo), ("연합", fed)]:
            load_adapter(m, sd)
            acc, det = score(m, tok, CANARY, a.device)
            ext[name] = {"rate": acc, "detail": det}
            print(f"  {name:6s} 추출률 {acc*100:5.1f}%  ({sum(1 for x in det if x['ok'])}/{len(det)})")
        save({"secret": CANARY_SECRET, "domain": a.canary_domain,
              "clip_norm": a.clip_norm, "extraction": ext, "grid": g},
             os.path.join(ROOT, "out", f"l2_canary{sfx}.json"))
        print("  → out/l2_canary.json (해석: 단독>연합 이면 집계 희석이 방어로 작동, "
              "연합도 높으면 '평균은 비밀을 안 지운다' — 두 층 분리 원칙의 실측 근거)")
    return 0 if b < s_ < f_ else 1


if __name__ == "__main__":
    sys.exit(main())
