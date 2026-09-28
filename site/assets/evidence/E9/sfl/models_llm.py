# -*- coding: utf-8 -*-
"""폭 조절 LLM(LoRA) — 분할 연합학습용. 폭 노브가 **LoRA rank** 로 이사한다.

  같은 컨트롤러가 세 종류 모델을 몬다는 것이 이 파일의 존재 이유다:
      CNN  → 채널 수          (models.py)
      ViT  → 헤드 수·은닉 차원 (models_vit.py)
      LLM  → **LoRA rank r**   (여기)

  근거: HetLoRA(EMNLP'24)·FlexLoRA 가 클라이언트별 이질 rank + 제로패딩 집계를 쓴다.
  앞쪽 r 성분만 쓰는 **중첩 구조**라 Ordered Dropout 의 rank 판과 같다.

  구조
    클라 = 임베딩 + 디코더 layer[:cut]   (기본 가중치 동결, LoRA 만 학습)
    서버 = layer[cut:] + norm + lm_head
    절단면 활성값 = (batch, seq, hidden) → 바이트는 **p 와 무관**하다 ★

  ★ CNN·ViT 와 결정적으로 다른 점
    rank 를 줄여도 절단면 텐서의 폭은 hidden 그대로다. 즉 **통신량이 안 준다.**
    rank 는 연산·메모리·가중치 동기만 줄인다. 컨트롤러의 비용 모델에서
    bytes(p) ∝ p 가정이 여기서는 성립하지 않으므로, LLM 모드에서는
    bytes 를 상수로 두어야 한다 — 이 파일이 그 사실을 명시적으로 알려 준다.
"""
import math
import os

import torch
import torch.nn as nn

DEFAULT = "Qwen/Qwen2.5-0.5B"
RANKS = (4, 8, 16, 32)                     # p 사다리 {0.25,0.5,0.75,1.0} 대응


def rank_of(p, ranks=RANKS):
    """폭 p → LoRA rank. 사다리 위치를 그대로 옮긴다."""
    idx = min(range(len(ranks)), key=lambda i: abs((i + 1) / len(ranks) - p))
    return ranks[idx]


class LoRALinear(nn.Module):
    """기본 가중치는 동결, 저랭크 보정만 학습. 앞쪽 r 성분만 쓰므로 중첩된다."""

    def __init__(self, base: nn.Linear, r: int, alpha: int = 16):
        super().__init__()
        self.base = base
        for q in self.base.parameters():
            q.requires_grad_(False)
        self.r, self.scale = r, alpha / r
        # base 의 dtype 을 상속 — 새 transformers 는 체크포인트 dtype(bf16)로 자동
        # 로드하므로, fp32 고정 생성 시 forward 에서 dtype 불일치로 죽는다 (G-L1 1차)
        dt = base.weight.dtype
        self.A = nn.Parameter(torch.zeros(r, base.in_features, dtype=dt))
        self.B = nn.Parameter(torch.zeros(base.out_features, r, dtype=dt))
        nn.init.kaiming_uniform_(self.A, a=math.sqrt(5))

    def forward(self, x):
        return self.base(x) + (x @ self.A.T @ self.B.T) * self.scale


def inject_lora(module, r, targets=("q_proj", "v_proj")):
    """디코더 블록 안의 지정 선형층을 LoRA 로 감싼다."""
    n = 0
    for name, child in list(module.named_children()):
        if isinstance(child, nn.Linear) and name in targets:
            setattr(module, name, LoRALinear(child, r))
            n += 1
        else:
            n += inject_lora(child, r, targets)
    return n


def freeze_except_lora(module):
    """LoRA(A·B) 외 전부 동결. **이게 없으면 이름만 LoRA 인 전체 미세조정이 된다** —
    초판 코드가 q_proj/v_proj 의 base 와 embed/lm_head 만 동결해 학습 파라미터의
    99.9%(서버 307.9M)가 LoRA 가 아니었다. 적대 검증에서 잡힌 결함(2026-08-25)."""
    n_on = n_off = 0
    for name, q in module.named_parameters():
        on = name.endswith(".A") or name.endswith(".B")
        q.requires_grad_(on)
        n_on += on
        n_off += not on
    return n_on, n_off


def lora_state(module):
    """집계 대상 = LoRA 파라미터만. 라운드 끝 가중치 동기가 KB 급으로 줄어든다."""
    return {k: v for k, v in module.state_dict().items()
            if k.endswith(".A") or k.endswith(".B")}


class LLMClient(nn.Module):
    """앞단 = 임베딩 + layer[:cut]. 레이어만 잘라내고 나머지 배선(회전 위치 임베딩·마스크)은
    모델 자신에게 맡긴다 — 수동으로 몰면 버전마다 시그니처가 달라 깨진다."""

    def __init__(self, p=1.0, cut=2, model_id=DEFAULT, dtype=torch.float32):
        super().__init__()
        from transformers import AutoModelForCausalLM
        m = AutoModelForCausalLM.from_pretrained(model_id, dtype=dtype)
        self.model = m.model
        self.model.layers = nn.ModuleList(list(m.model.layers[:cut]))
        self.model.norm = nn.Identity()               # 최종 정규화는 서버 쪽에서
        self.cfg = m.config
        self.r = rank_of(p)
        self.n_lora = inject_lora(self.model.layers, self.r)
        self.n_train, self.n_frozen = freeze_except_lora(self)   # LoRA 외 전부 동결

    def forward(self, ids):
        return self.model(input_ids=ids, use_cache=False).last_hidden_state


class LLMServer(nn.Module):
    """뒷단 = layer[cut:] + norm + lm_head."""

    def __init__(self, p=1.0, cut=2, model_id=DEFAULT, dtype=torch.float32):
        super().__init__()
        from transformers import AutoModelForCausalLM
        m = AutoModelForCausalLM.from_pretrained(model_id, dtype=dtype)
        self.model = m.model
        self.model.layers = nn.ModuleList(list(m.model.layers[cut:]))
        self.head = m.lm_head
        self.cfg = m.config
        self.r = rank_of(p)
        self.n_lora = inject_lora(self.model.layers, self.r)
        self.n_train, self.n_frozen = freeze_except_lora(self)

    def forward(self, h):
        return self.head(self.model(inputs_embeds=h, use_cache=False).last_hidden_state)


def sizes(model_id=DEFAULT, batch=4, seq=512, dtype=4):
    """다운로드 없이 절단면 크기를 계산 (config 만 읽는다)."""
    from transformers import AutoConfig
    c = AutoConfig.from_pretrained(model_id)
    act = batch * seq * c.hidden_size * dtype
    return {"hidden": c.hidden_size, "layers": c.num_hidden_layers,
            "act_bytes": act, "act_mb": act / 1e6}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    for mid in (DEFAULT, "Qwen/Qwen2.5-1.5B"):
        try:
            s = sizes(mid)
        except Exception as e:
            print(f"[{mid}] config 읽기 실패: {e}")
            continue
        print(f"\n[{mid}] hidden={s['hidden']} layers={s['layers']}")
        print(f"  절단면 활성값 (batch4·seq512·fp32): {s['act_mb']:.2f}MB "
              f"(왕복 {2*s['act_mb']:.2f}MB)  ← **rank 와 무관하게 일정**")
        for p in (0.25, 0.5, 0.75, 1.0):
            r = rank_of(p)
            print(f"  p={p:<5} rank={r:<3} 활성값 {s['act_mb']:6.2f}MB (불변) "
                  f"· LoRA 파라미터는 rank 에 비례")
