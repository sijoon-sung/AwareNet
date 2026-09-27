# -*- coding: utf-8 -*-
"""OD-ResNet18 — Ordered Dropout 폭 p 적용 + 절단(cut) 분리.

  폭 p         : 각 층 채널 수를 ceil(p·C)로 축소. 중첩(nested) — p 작은 모델의
                 파라미터는 p 큰 모델의 앞쪽 슬라이스와 같은 자리 (FjORD 방식)
  절단 cut     : stage cut 뒤에서 자름. 클라 = stem+stages[:cut], 서버 = stages[cut:]+fc
  슬라이스 전송 : 활성값은 ceil(p·C) 채널만 그대로 나감 — 제로패딩 전송 금지 [설계확정 A2]
"""
import math
import os

import torch
import torch.nn as nn

# 배치 정규화의 이동 통계를 집계할지 — 폭이 다른 기기끼리 평균내면 통계가 섞인다는 지적이 있어
# 환경변수로 끌 수 있게 했다 (AWARENET_BN=none 이면 이동 통계를 추적하지 않는다).
BN_TRACK = os.environ.get("AWARENET_BN", "avg").lower() != "none"


NORM = os.environ.get("AWARENET_NORM", "bn").lower()      # bn | gn — set_norm() 으로도 바꾼다 (--norm)


def set_norm(kind):
    """정규화 종류. gn = GroupNorm(Wu·He 2018): 배치 크기와 무관 → 즉시 내보내기(조각 8장)·폭 혼합(Slimmable 지적)의 BN 통계 문제를 비껴간다.
    모델을 만들기 전에 불러야 한다 (서버·클라 둘 다)."""
    global NORM
    NORM = kind.lower()


def _bn(c):
    if NORM == "gn":
        g = 8 if c % 8 == 0 else (4 if c % 4 == 0 else 1)      # 폭 사다리 ceil(p·C) 가 8 의 배수인 채널 수만 낸다 (16·32·48·64…)
        return nn.GroupNorm(g, c)
    return nn.BatchNorm2d(c, track_running_stats=BN_TRACK)
import torch.nn.functional as F

LADDER = (0.25, 0.5, 0.75, 1.0)
BASE = (64, 128, 256, 512)          # ResNet-18 stage 폭
BLOCKS = (2, 2, 2, 2)


def w(c, p):
    return max(1, int(math.ceil(c * p)))


class BasicBlock(nn.Module):
    def __init__(self, cin, cout, stride=1):
        super().__init__()
        self.c1 = nn.Conv2d(cin, cout, 3, stride, 1, bias=False)
        self.b1 = _bn(cout)
        self.c2 = nn.Conv2d(cout, cout, 3, 1, 1, bias=False)
        self.b2 = _bn(cout)
        self.sc = None
        if stride != 1 or cin != cout:
            self.sc = nn.Sequential(nn.Conv2d(cin, cout, 1, stride, bias=False),
                                    _bn(cout))

    def forward(self, x):
        y = F.relu(self.b1(self.c1(x)))
        y = self.b2(self.c2(y))
        return F.relu(y + (x if self.sc is None else self.sc(x)))


def _stage(cin, cout, n, stride):
    return nn.Sequential(BasicBlock(cin, cout, stride),
                         *[BasicBlock(cout, cout) for _ in range(n - 1)])


class ClientNet(nn.Module):
    """앞단: stem + stages[:cut]"""

    def __init__(self, p=1.0, cut=1):
        super().__init__()
        c = [w(x, p) for x in BASE]
        self.p, self.cut = p, cut
        self.stem = nn.Sequential(nn.Conv2d(3, c[0], 3, 1, 1, bias=False),
                                  _bn(c[0]), nn.ReLU())
        st, cin = [], c[0]
        for i in range(cut):
            st.append(_stage(cin, c[i], BLOCKS[i], 1 if i == 0 else 2))
            cin = c[i]
        self.stages = nn.Sequential(*st)
        self.out_ch = cin

    def forward(self, x):
        return self.stages(self.stem(x))


class ServerNet(nn.Module):
    """뒷단: stages[cut:] + pool + fc"""

    def __init__(self, p=1.0, cut=1, num_classes=10):
        super().__init__()
        c = [w(x, p) for x in BASE]
        st, cin = [], c[cut - 1]
        for i in range(cut, 4):
            st.append(_stage(cin, c[i], BLOCKS[i], 2))
            cin = c[i]
        self.stages = nn.Sequential(*st)
        self.fc = nn.Linear(cin, num_classes)

    def forward(self, a):
        y = self.stages(a)
        y = F.adaptive_avg_pool2d(y, 1).flatten(1)
        return self.fc(y)


# ── 중첩 가중치 유틸 (FjORD 집계의 재료 — G2에서 사용) ─────────────────

# ── 부분모델 추출 창 ────────────────────────────────────────────────────────
# 기본(접두): 소폭 모델은 전폭 텐서의 앞쪽 채널 0..n-1 을 쓴다 (HeteroFL/FjORD).
# AWARENET_ROLL=1 (FedRolex, NeurIPS 2022, Eq.4): 라운드마다 창을 ROLL_STEP 채널씩 민다.
#   그래야 저사양 기기(폭 0.25)도 라운드가 지나며 모든 채널을 한 번씩 학습한다.
#   접두 방식에서는 뒤쪽 채널을 전폭 기기만 학습하므로 저사양 기기가 정확도에 기여하지 못한다.
# 창 위치는 (라운드, 전폭 C, 소폭 n) 만의 함수라, 앞 층의 출력 채널과 다음 층의 입력 채널,
# 클라이언트 앞단의 출력과 서버 뒷단의 입력이 언제나 같은 채널을 가리킨다.
ROLL = os.environ.get("AWARENET_ROLL", "0") == "1"
ROLL_STEP = int(os.environ.get("AWARENET_ROLL_STEP", "1"))
_ROUND = 0


def set_round(r):
    """서버가 라운드 시작마다 부른다. ROLL 이 꺼져 있으면 아무 영향이 없다."""
    global _ROUND
    _ROUND = int(r)


def _axis_index(n, C):
    """소폭 축(n)이 전폭 축(C)의 어느 채널에 대응하는지 — 길이 n 의 인덱스 텐서."""
    if n >= C or not ROLL:
        return torch.arange(0, n)
    off = (_ROUND * ROLL_STEP) % C
    return torch.arange(off, off + n) % C


def _grid(small_shape, full_shape):
    """모든 축을 인덱스 텐서로 만들어 브로드캐스트 격자를 돌려준다.
    (슬라이스와 인덱스 텐서를 섞으면 축 순서가 바뀌는 함정을 피한다.)"""
    nd = len(small_shape)
    out = []
    for d, (n, C) in enumerate(zip(small_shape, full_shape)):
        idx = _axis_index(n, C)
        shape = [1] * nd
        shape[d] = n
        out.append(idx.view(shape))
    return tuple(out)


def slice_into(dst_sd, src_sd):
    """전폭 상태(src)에서 창에 해당하는 채널을 떠 소폭 모델 상태(dst)에 넣는다."""
    out = {}
    for k, d in dst_sd.items():
        s = src_sd[k]
        if d.dim() == 0:
            out[k] = s.clone()
            continue
        g = tuple(t.to(s.device) for t in _grid(d.shape, s.shape))
        out[k] = s[g].clone()
    return out


def nested_average(full_sd, updates):
    """updates = [(sd, n_samples)] — 실제 학습된 채널만 표본 가중 평균 (제로패딩 평균 금지).
    창이 밀려 있으면 그 창의 채널에만 더한다."""
    acc = {k: torch.zeros_like(v, dtype=torch.float64) for k, v in full_sd.items()}
    cnt = {k: torch.zeros_like(v, dtype=torch.float64) for k, v in full_sd.items()}
    for sd, n in updates:
        for k, v in sd.items():
            if v.dim() == 0:
                acc[k] += v.double() * n
                cnt[k] += n
                continue
            g = tuple(t.to(v.device) for t in _grid(v.shape, full_sd[k].shape))
            acc[k][g] += v.double() * n
            cnt[k][g] += n
    out = {}
    for k in full_sd:
        m = cnt[k] > 0
        out[k] = torch.where(m, acc[k] / cnt[k].clamp(min=1), full_sd[k].double())
        out[k] = out[k].to(full_sd[k].dtype)
    return out
