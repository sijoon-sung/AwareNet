# -*- coding: utf-8 -*-
"""정합 검증 스위트 — "정확하게 작동하는가"의 다섯 증명.

  A 분할≡단일체  같은 시드·같은 데이터에서 소켓 분할 학습의 배치별 손실이
                 한 덩어리 모델 로컬 학습과 일치하는가 (구현 정합의 결정판)
  B 학습 성립    CIFAR-10 실데이터 부분집합에서 손실 하강 + 정확도 상승 (p=1.0, 0.5)
  C 집계 산술    nested_average / slice_into 를 손계산과 대조
  D netem 충실도 스윕 측정 통신시간 vs 이론값 (바이트·대역·RTT) — 기존 로그 오프라인 대조
  E 파이프라인   staleness=1 경로에서 손실 유한 + 실행 완주 (학습성은 A·B가 담보)

    python sfl/verify.py
"""
import io
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import torch
import torch.nn.functional as F

from client import batches
from models import ClientNet, ServerNet, nested_average, slice_into

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "out")
PY = sys.executable
RESULT = []


def spawn(p, cut, nb, seed, port, pipeline=False):
    tag = f"verify_p{p}_cut{cut}" + ("_pipe" if pipeline else "")
    slog = os.path.join(OUT, f"{tag}_srv.jsonl")
    clog = os.path.join(OUT, f"{tag}_cli.jsonl")
    env = dict(os.environ, PYTHONPATH=os.path.dirname(os.path.abspath(__file__)))
    srv = subprocess.Popen([PY, os.path.join(ROOT, "sfl", "server.py"), "--port", str(port),
                            "--clients", "1", "--device", "cpu", "--seed", str(seed),
                            "--log", slog], env=env)
    time.sleep(4)
    cli = [PY, os.path.join(ROOT, "sfl", "client.py"), "--server", f"127.0.0.1:{port}",
           "--p", str(p), "--cut", str(cut), "--batches", str(nb),
           "--batch-size", "32", "--seed", str(seed), "--log", clog]
    if pipeline:
        cli.append("--pipeline")
    subprocess.run(cli, env=env, check=True)
    srv.wait(timeout=60)
    return [json.loads(l) for l in io.open(clog, encoding="utf-8") if "loss" in l]


def check(name, ok, detail):
    RESULT.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} — {detail}")


def A_equivalence():
    print("A. 분할(소켓) ≡ 단일체(로컬) — p=1.0, cut=2, 6배치, CPU, seed=7")
    split = [r["loss"] for r in spawn(1.0, 2, 6, seed=7, port=29711)]
    torch.manual_seed(7)
    c = ClientNet(1.0, 2)
    torch.manual_seed(7)
    ClientNet(1.0, 2)                                   # 서버 프로세스의 RNG 소비 재현
    s = ServerNet(1.0, 2)
    opt = torch.optim.SGD(list(c.parameters()) + list(s.parameters()), lr=0.01, momentum=0.9)
    mono = []
    for x, y in batches(6, 32, seed=42):
        loss = F.cross_entropy(s(c(x)), y)
        opt.zero_grad(); loss.backward(); opt.step()
        mono.append(loss.item())
    d = max(abs(a - b) for a, b in zip(split, mono))
    check("A 분할≡단일체", d < 1e-4,
          f"배치별 손실 최대 차이 {d:.2e} (분할 {split[:3]}… vs 단일 {mono[:3]}…)")


def B_learning(epochs=6, ntrain=8192):
    """CIFAR-10 실데이터. 평가는 **훈련에 안 쓴 테스트셋**으로 한다.
    판정: 손실 30% 이상 감소 AND 테스트 정확도 >30% (무작위 10%의 3배).
    ※ 첫 판(2에폭·4096표본·훈련셋 평가)은 학습 분량이 부족해 손실 기준에 걸렸다.
       기준을 낮추는 대신 분량을 늘리고 평가를 홀드아웃으로 강화했다 — 기록으로 남긴다."""
    print(f"B. CIFAR-10 실데이터 학습 성립 — {ntrain}표본 {epochs}에폭, 홀드아웃 평가")
    import torchvision
    import torchvision.transforms as T
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    tf = T.Compose([T.ToTensor(), T.Normalize((0.49, 0.48, 0.45), (0.25, 0.24, 0.26))])
    root = os.path.join(ROOT, "data", "cifar10")
    tr = torch.utils.data.Subset(
        torchvision.datasets.CIFAR10(root, train=True, download=True, transform=tf),
        list(range(ntrain)))
    te = torch.utils.data.Subset(
        torchvision.datasets.CIFAR10(root, train=False, download=True, transform=tf),
        list(range(2000)))
    teld = torch.utils.data.DataLoader(te, batch_size=256)
    for p in (1.0, 0.5):
        torch.manual_seed(1)
        g = torch.Generator().manual_seed(1)
        ld = torch.utils.data.DataLoader(tr, batch_size=128, shuffle=True, generator=g)
        c, s = ClientNet(p, 2).to(dev), ServerNet(p, 2).to(dev)
        opt = torch.optim.SGD(list(c.parameters()) + list(s.parameters()),
                              lr=0.05, momentum=0.9)
        losses = []
        for _ in range(epochs):
            c.train(); s.train()
            for x, y in ld:
                x, y = x.to(dev), y.to(dev)
                loss = F.cross_entropy(s(c(x)), y)
                opt.zero_grad(); loss.backward(); opt.step()
                losses.append(loss.item())
        c.eval(); s.eval()
        with torch.no_grad():
            hit = n = 0
            for x, y in teld:                       # 훈련에 쓰지 않은 데이터
                hit += (s(c(x.to(dev))).argmax(1).cpu() == y).sum().item()
                n += len(y)
        first, last = sum(losses[:8]) / 8, sum(losses[-8:]) / 8
        acc = hit / n
        check(f"B 학습(p={p})", last < 0.7 * first and acc > 0.30,
              f"손실 {first:.3f}→{last:.3f} ({(1-last/first)*100:.0f}%↓), "
              f"홀드아웃 정확도 {acc*100:.1f}% (무작위 10%)")


def C_aggregation():
    print("C. 중첩 집계 산술")
    full = {"w": torch.zeros(4, 3)}
    upA = ({"w": torch.ones(2, 2)}, 1)                  # p작은 클라, 표본 1
    upB = ({"w": torch.full((4, 3), 3.0)}, 3)           # 전폭 클라, 표본 3
    out = nested_average(full, [upA, upB])["w"]
    ok = (abs(out[0, 0].item() - (1 * 1 + 3 * 3) / 4) < 1e-6      # 겹침: (1·1+3·3)/4=2.5
          and abs(out[3, 2].item() - 3.0) < 1e-6)                  # B만: 3.0
    check("C nested_average", ok, f"겹침 {out[0,0].item():.3f}(기대 2.500) · 비겹침 {out[3,2].item():.3f}(기대 3.000)")
    src = {"w": torch.arange(12.0).reshape(4, 3)}
    sl = slice_into({"w": torch.zeros(2, 2)}, src)["w"]
    check("C slice_into", torch.equal(sl, src["w"][:2, :2]), f"앞쪽 슬라이스 일치 {sl.tolist()}")


def D_netem_fidelity():
    print("D. netem 에뮬 충실도 — 측정 통신시간 vs 이론값")
    fp = os.path.join(OUT, "g0_netem_results.json")
    if not os.path.exists(fp):
        check("D netem", False, "g0_netem_results.json 없음 — 스윕 먼저")
        return
    ratios = []
    for r in json.load(io.open(fp, encoding="utf-8")):
        exp = (r["up_B"] + r["down_B"]) * 8 / (r["bw"] * 1e6) + r["rtt"] / 1000
        ratios.append(r["comm"] / exp)
    ratios.sort()
    med = ratios[len(ratios) // 2]
    check("D netem 충실도", 0.7 < med < 1.3 and ratios[0] > 0.5 and ratios[-1] < 2.0,
          f"측정/이론 비율 중앙값 {med:.3f}, 범위 {ratios[0]:.2f}~{ratios[-1]:.2f} (24구성)")


def E_pipeline():
    print("E. 파이프라인 경로 안정성 — 6배치 완주·손실 유한")
    rows = spawn(1.0, 1, 6, seed=7, port=29713, pipeline=True)
    ls = [r["loss"] for r in rows]
    import math
    check("E 파이프라인", len(ls) == 6 and all(math.isfinite(v) for v in ls)
          and len(set(round(v, 6) for v in ls)) > 1,
          f"손실 {['%.3f' % v for v in ls]} (유한·변화함, staleness=1)")


if __name__ == "__main__":
    for f in (A_equivalence, B_learning, C_aggregation, D_netem_fidelity, E_pipeline):
        try:
            f()
        except Exception as e:
            check(f.__name__, False, f"예외: {e}")
    ok = sum(1 for _, o, _ in RESULT if o)
    print(f"\n결과: {ok}/{len(RESULT)} PASS")
    sys.exit(0 if ok == len(RESULT) else 1)
