# -*- coding: utf-8 -*-
"""폭 조절 ViT — 분할 연합학습용. 폭 노브가 **채널 → 은닉 차원·헤드 수**로 이사한다.

  왜 ViT 인가
    CNN(ResNet)은 기둥 논문(FjORD·AdaptSFL)과 대조하기 위한 대조군이다.
    "실제로 쓰는 모델에서도 되는가"에 답하려면 Transformer 계열이 필요하다.

  폭 p 의 매핑
    헤드 수 H(p) = max(1, round(p·H))       머리 개수를 줄인다
    은닉 차원 D(p) = H(p) · head_dim        헤드당 차원은 고정(64) — 표준 관행
    MLP 은닉 = D(p) · mlp_ratio
    → **중첩(nested)**: 작은 폭의 파라미터는 큰 폭의 앞쪽 슬라이스와 같은 자리

  절단(cut): 블록 cut 개까지 클라이언트, 나머지 + 헤드가 서버.
  절단면 활성값 = (batch, tokens, D(p)) → **바이트가 p 에 정비례** (CNN 과 동일한 성질)

  구성 두 가지
    small : 32×32 · patch4 · D=512 · depth8   (CIFAR 급, 노트북에서 가능)
    base  : 224×224 · patch16 · D=768 · depth12 (ViT-Base 형상, 활성값 4~5배)
"""
import math

import torch
import torch.nn as nn
import torch.nn.functional as F

HEAD_DIM = 64
CFG = {
    "small": dict(img=32, patch=4, heads=8, depth=8, mlp=4.0),     # D=512
    "base": dict(img=224, patch=16, heads=12, depth=12, mlp=4.0),  # D=768
}


def widths(p, heads):
    h = max(1, int(round(p * heads)))
    return h, h * HEAD_DIM


class Block(nn.Module):
    """표준 pre-norm Transformer 블록."""

    def __init__(self, d, h, mlp):
        super().__init__()
        self.h, self.d = h, d
        self.n1 = nn.LayerNorm(d)
        self.qkv = nn.Linear(d, d * 3, bias=True)
        self.proj = nn.Linear(d, d)
        self.n2 = nn.LayerNorm(d)
        hid = int(d * mlp)
        self.fc1, self.fc2 = nn.Linear(d, hid), nn.Linear(hid, d)

    def forward(self, x):
        B, N, D = x.shape
        y = self.n1(x)
        qkv = self.qkv(y).reshape(B, N, 3, self.h, D // self.h).permute(2, 0, 3, 1, 4)
        q, k, v = qkv[0], qkv[1], qkv[2]
        a = F.scaled_dot_product_attention(q, k, v)
        x = x + self.proj(a.transpose(1, 2).reshape(B, N, D))
        y = self.n2(x)
        return x + self.fc2(F.gelu(self.fc1(y)))


class ViTClient(nn.Module):
    """앞단 — 패치 임베딩 + 블록 cut 개."""

    def __init__(self, p=1.0, cut=2, cfg="small"):
        super().__init__()
        c = CFG[cfg]
        h, d = widths(p, c["heads"])
        self.p, self.cut, self.d = p, cut, d
        n = (c["img"] // c["patch"]) ** 2
        self.patch = nn.Conv2d(3, d, c["patch"], c["patch"])
        self.cls = nn.Parameter(torch.zeros(1, 1, d))
        self.pos = nn.Parameter(torch.zeros(1, n + 1, d))
        nn.init.trunc_normal_(self.pos, std=.02)
        nn.init.trunc_normal_(self.cls, std=.02)
        self.blocks = nn.Sequential(*[Block(d, h, c["mlp"]) for _ in range(cut)])

    def forward(self, x):
        x = self.patch(x).flatten(2).transpose(1, 2)
        x = torch.cat([self.cls.expand(x.size(0), -1, -1), x], 1) + self.pos
        return self.blocks(x)


class ViTServer(nn.Module):
    """뒷단 — 나머지 블록 + 분류 헤드."""

    def __init__(self, p=1.0, cut=2, cfg="small", num_classes=10):
        super().__init__()
        c = CFG[cfg]
        h, d = widths(p, c["heads"])
        self.blocks = nn.Sequential(*[Block(d, h, c["mlp"])
                                      for _ in range(c["depth"] - cut)])
        self.norm = nn.LayerNorm(d)
        self.head = nn.Linear(d, num_classes)

    def forward(self, a):
        return self.head(self.norm(self.blocks(a))[:, 0])


def act_bytes(p, cut=2, cfg="small", batch=32, dtype=4):
    """절단면 활성값 크기 (바이트) — 한 방향."""
    c = CFG[cfg]
    _, d = widths(p, c["heads"])
    n = (c["img"] // c["patch"]) ** 2 + 1
    return batch * n * d * dtype


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print("폭 p → (헤드, 차원) · 절단면 활성값 (batch 32, fp32, cut=2)")
    for cfg in ("small", "base"):
        print(f"\n[{cfg}] {CFG[cfg]}")
        b1 = act_bytes(1.0, cfg=cfg)
        for p in (0.25, 0.5, 0.75, 1.0):
            h, d = widths(p, CFG[cfg]["heads"])
            b = act_bytes(p, cfg=cfg)
            print(f"  p={p:<5} 헤드 {h:2d} 차원 {d:4d}  활성값 {b/1e6:6.2f}MB "
                  f"(왕복 {2*b/1e6:6.2f}MB)  바이트비 {b/b1:.3f}")


# ── 팩토리 (fed_server/fed_client 가 arch 로 갈아 끼운다) ──────────
def build(p=1.0, cut=2, cfg="small", num_classes=10):
    return ViTClient(p, cut, cfg), ViTServer(p, cut, cfg, num_classes)


def img_size(cfg="small"):
    return CFG[cfg]["img"]
