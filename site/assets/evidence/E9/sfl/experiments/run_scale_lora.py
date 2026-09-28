# -*- coding: utf-8 -*-
"""분할 + LoRA 로 큰 모델을 작은 기기에서 — 모델이 클수록 기기 쪽 이득이 커지는가 (2026-09-13)

  주장: 분할 학습에서 기기는 임베딩 + 앞 k 층만 들고 LoRA 만 학습한다. 모델의 깊이 L 이 커져도
        기기 몫(k 층)은 그대로이고, 절단면 활성값(batch·seq·hidden)은 깊이와 무관하다.
        → 로컬 LoRA(모델 전체가 기기에) 대비 기기 메모리·연산은 (L−k)/L 만큼 줄고, 그 비율은 L 이 클수록 1 에 다가간다.
  문헌: SplitLoRA(arXiv 2407.00952), HSplitLoRA(2505.02795), Offsite-Tuning(2302.04870), 메모리 효율 SFL(2506.02940).

  세 모드
    cost   : 한 기계에서 비용 사다리를 잰다. **가중치 값과 무관한 양**(최대 메모리·스텝 시간·가중치 바이트·절단면 바이트)이므로
             랜덤 초기화(from_config, 다운로드 없음)로 잰다. 설정마다 자식 프로세스(최대 RSS 가 프로세스 단위라서).
               python sfl/experiments/run_scale_lora.py cost --family llm --models Qwen/Qwen2.5-0.5B,Qwen/Qwen2.5-1.5B,Qwen/Qwen2.5-3B,Qwen/Qwen2.5-7B --cut 2
               python sfl/experiments/run_scale_lora.py cost --family dit --models S,B,L,XL --cut 2
    server : 실제 분할 학습의 서버 쪽(HPC). layer[k:] + head, 손실·역전파, 절단면 기울기 회신.
               python sfl/experiments/run_scale_lora.py server --model Qwen/Qwen2.5-0.5B --cut 2 --port 31950 --device cuda
    device : 기기 쪽(VM). 사전학습 가중치는 **앞 k 층이 든 조각(shard)만** 내려받아 적재. 도메인 B 코퍼스로 LoRA 학습.
               python sfl/experiments/run_scale_lora.py device --model Qwen/Qwen2.5-0.5B --cut 2 --server 127.0.0.1:31950 --steps 30
    (dit 의 device/server 도 같은 틀 — 잠재 벡터는 --latents 파일, 없으면 난수)

  기록: out/scale_lora/<mode>_<태그>.jsonl (한 줄 = 한 설정 또는 한 스텝)
"""
import argparse
import io
import json
import math
import os
try:
    import resource
except ImportError:          # Windows
    resource = None
import socket
import subprocess
import sys
import time

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from models_llm import inject_lora, freeze_except_lora, lora_state      # noqa: E402
from proto import recv_msg, send_msg, HELLO, HELLO_OK, ACT, GRAD, BYE   # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "out", "scale_lora")
LLM_TARGETS = ("q_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj")   # G-L1 확정 레시피(attn+MLP)
DIT = {  # DiT/2, 256px 잠재 32×32×4 → 토큰 256. (Peebles & Xie 2023 표) — 머리 크기: XL 72, 나머지 64
    "S": dict(num_layers=12, heads=6, head_dim=64), "B": dict(num_layers=12, heads=12, head_dim=64),
    "L": dict(num_layers=24, heads=16, head_dim=64), "XL": dict(num_layers=28, heads=16, head_dim=72)}
DIT_PRETRAINED = "facebook/DiT-XL-2-256"


# ── 공통 계측 ─────────────────────────────────────────────────────────
def peak_rss_mb():
    """프로세스 수명 최대 RSS (Linux: KB, macOS: B). Windows 는 psutil 현재값으로 대신."""
    if sys.platform.startswith("win"):
        import psutil
        return psutil.Process().memory_info().peak_wset / 1e6
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / 1e3 if sys.platform.startswith("linux") else r / 1e6


def nbytes(module, trainable=None):
    return sum(p.numel() * p.element_size() for p in module.parameters()
               if trainable is None or p.requires_grad == trainable)


def dev_sync(device):
    if device.startswith("cuda"):
        torch.cuda.synchronize()


def gpu_peak_mb(device):
    return torch.cuda.max_memory_allocated() / 1e6 if device.startswith("cuda") else None


# ── LLM 모델 구성 ──────────────────────────────────────────────────────
def llm_config(model_id, tiny=False):
    from transformers import AutoConfig
    c = AutoConfig.from_pretrained(model_id)
    if tiny:
        c.hidden_size, c.intermediate_size = 64, 128
        c.num_hidden_layers, c.num_attention_heads, c.num_key_value_heads = 4, 4, 2
    return c


def llm_from_config(c, n_layers, dtype):
    """레이어 수를 바꾼 설정으로 뼈대만 만든다(가중치 난수). 임베딩·head 는 그대로."""
    from transformers import AutoModelForCausalLM
    import copy
    c2 = copy.deepcopy(c); c2.num_hidden_layers = n_layers
    try:
        m = AutoModelForCausalLM.from_config(c2, dtype=dtype)
    except TypeError:
        m = AutoModelForCausalLM.from_config(c2, torch_dtype=dtype)
    return m


class LLMFront(nn.Module):
    """기기 몫: 임베딩 + layer[:cut] (+LoRA). 최종 norm·head 없음."""

    def __init__(self, c, cut, rank, dtype=torch.float32):
        super().__init__()
        m = llm_from_config(c, cut, dtype)
        self.model = m.model
        self.model.norm = nn.Identity()
        self.n_lora = inject_lora(self.model.layers, rank, LLM_TARGETS)
        freeze_except_lora(self)

    def forward(self, ids):
        return self.model(input_ids=ids, use_cache=False).last_hidden_state


class LLMBack(nn.Module):
    """서버 몫: layer[cut:] + norm + lm_head (+LoRA)."""

    def __init__(self, c, cut, rank, dtype=torch.float32, pretrained=None):
        super().__init__()
        if pretrained:
            from transformers import AutoModelForCausalLM
            try:
                m = AutoModelForCausalLM.from_pretrained(pretrained, dtype=dtype)
            except TypeError:
                m = AutoModelForCausalLM.from_pretrained(pretrained, torch_dtype=dtype)
            m.model.layers = nn.ModuleList(list(m.model.layers[cut:]))
        else:
            m = llm_from_config(c, c.num_hidden_layers - cut, dtype)
        self.model, self.head = m.model, m.lm_head
        self.model.embed_tokens = nn.Identity()          # 서버는 임베딩을 안 쓴다(입력이 활성값). 묶인 lm_head 는 별도 보관
        self.n_lora = inject_lora(self.model.layers, rank, LLM_TARGETS)
        freeze_except_lora(self)

    def forward(self, h):
        return self.head(self.model(inputs_embeds=h, use_cache=False).last_hidden_state)


def load_front_pretrained(front, model_id, cut):
    """앞 k 층 + 임베딩이 든 조각만 내려받아 채운다 — 기기는 모델 전체를 받을 필요가 없다."""
    from huggingface_hub import hf_hub_download
    from safetensors import safe_open
    need = lambda k: k.startswith("model.embed_tokens.") or any(k.startswith(f"model.layers.{i}.") for i in range(cut))
    try:
        idx = json.load(open(hf_hub_download(model_id, "model.safetensors.index.json"), encoding="utf-8"))["weight_map"]
        shards = sorted({f for k, f in idx.items() if need(k)})
    except Exception:
        shards = ["model.safetensors"]
    sd = front.state_dict(); got, total_dl = 0, 0
    for sh in shards:
        p = hf_hub_download(model_id, sh); total_dl += os.path.getsize(p)
        with safe_open(p, "pt") as f:
            for k in f.keys():
                if not need(k):
                    continue
                kk = k.replace(".q_proj.weight", ".q_proj.base.weight").replace(".v_proj.weight", ".v_proj.base.weight") \
                      .replace(".o_proj.weight", ".o_proj.base.weight").replace(".gate_proj.weight", ".gate_proj.base.weight") \
                      .replace(".up_proj.weight", ".up_proj.base.weight").replace(".down_proj.weight", ".down_proj.base.weight") \
                      .replace(".q_proj.bias", ".q_proj.base.bias").replace(".v_proj.bias", ".v_proj.base.bias")
                if kk in sd:
                    sd[kk].copy_(f.get_tensor(k).to(sd[kk].dtype)); got += 1
    return got, total_dl, shards


# ── DiT 모델 구성 (diffusers Transformer2DModel, ada_norm_zero) ────────
def dit_model(size, n_layers=None, pretrained=None):
    from diffusers import Transformer2DModel
    if pretrained:
        m = Transformer2DModel.from_pretrained(pretrained, subfolder="transformer")
        return m
    s = DIT[size]
    return Transformer2DModel(num_attention_heads=s["heads"], attention_head_dim=s["head_dim"], in_channels=4, out_channels=8,
                              num_layers=n_layers if n_layers is not None else s["num_layers"], sample_size=32, patch_size=2,
                              norm_type="ada_norm_zero", num_embeds_ada_norm=1000, activation_fn="gelu-approximate",
                              attention_bias=True, norm_elementwise_affine=False, norm_eps=1e-6)


DIT_TARGETS = ("to_q", "to_k", "to_v", "to_out", "proj")   # attention + FF 선형층 (diffusers 이름)


def inject_lora_dit(blocks, rank):
    n = 0
    for name, child in list(blocks.named_children()):
        if isinstance(child, nn.Linear) and (name in DIT_TARGETS or name in ("0", "2")):   # to_out.0 / GELU.proj / ff.net.2
            from models_llm import LoRALinear
            setattr(blocks, name, LoRALinear(child, rank)); n += 1
        else:
            n += inject_lora_dit(child, rank)
    return n


class DiTFront(nn.Module):
    """기기 몫: 패치 임베딩 + blocks[:cut]. 조건(t, y)은 정수라 서버로 그대로 보낸다(각 블록이 자기 조건 임베딩을 가짐)."""

    def __init__(self, size, cut, rank, pretrained=None):
        super().__init__()
        m = dit_model(size, n_layers=None if pretrained else cut, pretrained=pretrained)
        self.pos_embed = m.pos_embed
        self.blocks = nn.ModuleList(list(m.transformer_blocks[:cut]))
        self.n_lora = inject_lora_dit(self.blocks, rank)
        freeze_except_lora(self)

    def forward(self, x, t, y):
        h = self.pos_embed(x)
        for b in self.blocks:
            h = b(h, timestep=t, class_labels=y)
        return h


class DiTBack(nn.Module):
    """서버 몫: blocks[cut:] + 출력층. 출력 조건은 원본대로 block0 의 조건 임베딩 사본을 쓴다."""

    def __init__(self, size, cut, rank, pretrained=None):
        super().__init__()
        m = dit_model(size, pretrained=pretrained)
        self.cond = m.transformer_blocks[0].norm1.emb
        self.blocks = nn.ModuleList(list(m.transformer_blocks[cut:]))
        self.norm_out, self.proj_out_1, self.proj_out_2 = m.norm_out, m.proj_out_1, m.proj_out_2
        self.patch, self.out_ch = m.config.patch_size, m.config.out_channels
        self.n_lora = inject_lora_dit(self.blocks, rank)
        freeze_except_lora(self)

    def forward(self, h, t, y):
        for b in self.blocks:
            h = b(h, timestep=t, class_labels=y)
        c = self.cond(t, y, hidden_dtype=h.dtype)
        shift, scale = self.proj_out_1(F.silu(c)).chunk(2, dim=1)
        h = self.norm_out(h) * (1 + scale[:, None]) + shift[:, None]
        h = self.proj_out_2(h)
        n = int(math.sqrt(h.shape[1])); p = self.patch
        h = h.reshape(-1, n, n, p, p, self.out_ch)
        h = torch.einsum("nhwpqc->nchpwq", h)
        return h.reshape(-1, self.out_ch, n * p, n * p)


def dit_batch(batch, device, latents=None, step=0):
    """(x_t, t, y, noise): 잠재 z0 + 노이즈. --latents 있으면 그 파일(N,4,32,32)에서 순환."""
    g = torch.Generator().manual_seed(1000 + step)
    if latents is not None:
        i = torch.arange(step * batch, (step + 1) * batch) % latents.shape[0]
        z0 = latents[i].to(device)
    else:
        z0 = torch.randn(batch, 4, 32, 32, generator=g).to(device)
    noise = torch.randn(batch, 4, 32, 32, generator=g).to(device)
    t = torch.randint(0, 1000, (batch,), generator=g).to(device)
    y = torch.randint(0, 1000, (batch,), generator=g).to(device)
    ab = torch.cos((t.float() / 1000 + 0.008) / 1.008 * math.pi / 2) ** 2   # 코사인 일정 ᾱ_t
    xt = ab.sqrt()[:, None, None, None] * z0 + (1 - ab).sqrt()[:, None, None, None] * noise
    return xt, t, y, noise


# ── cost: 설정 하나를 자식 프로세스에서 ─────────────────────────────────
def measure_one(a):
    torch.set_num_threads(a.threads)
    dev = a.device
    dt = torch.float16 if a.fp16 else torch.float32
    t0 = time.perf_counter()
    if a.family == "llm":
        c = llm_config(a.model, a.tiny)
        L, d = c.num_hidden_layers, c.hidden_size
        if a.part == "local":
            m = llm_from_config(c, L, dt); inject_lora(m.model.layers, a.rank, LLM_TARGETS); freeze_except_lora(m)
        elif a.part == "front":
            m = LLMFront(c, a.cut, a.rank, dt)
        else:
            m = LLMBack(c, a.cut, a.rank, dt)
        m.to(dev)
        ids = torch.randint(0, c.vocab_size, (a.batch, a.seq), device=dev)
        act_bytes = a.batch * a.seq * d * 4
        def step():
            if a.part == "local":
                out = m(input_ids=ids, labels=ids); loss = out.loss; loss.backward(); return loss
            if a.part == "front":
                h = m(ids); g = torch.randn_like(h); h.backward(g); return h.float().norm()
            h = torch.randn(a.batch, a.seq, d, device=dev, dtype=dt, requires_grad=True)
            logits = m(h); loss = F.cross_entropy(logits.float().view(-1, logits.shape[-1]), ids.view(-1)); loss.backward(); return loss
    else:
        size = a.model; s = DIT[size]; L, d = s["num_layers"], s["heads"] * s["head_dim"]
        if a.part == "local":
            m = dit_model(size); inject_lora_dit(m.transformer_blocks, a.rank); freeze_except_lora(m)
        elif a.part == "front":
            m = DiTFront(size, a.cut, a.rank)
        else:
            m = DiTBack(size, a.cut, a.rank)
        m.to(dev)
        xt, t, y, noise = dit_batch(a.batch, dev)
        act_bytes = a.batch * 256 * d * 4
        def step():
            if a.part == "local":
                out = m(hidden_states=xt, timestep=t, class_labels=y).sample[:, :4]
                loss = F.mse_loss(out, noise); loss.backward(); return loss
            if a.part == "front":
                h = m(xt, t, y); g = torch.randn_like(h); h.backward(g); return h.norm()
            h = torch.randn(a.batch, 256, d, device=dev, requires_grad=True)
            out = m(h, t, y)[:, :4]; loss = F.mse_loss(out, noise); loss.backward(); return loss
    build_s = time.perf_counter() - t0
    opt = torch.optim.AdamW([p for p in m.parameters() if p.requires_grad], lr=1e-4)
    if dev.startswith("cuda"):
        torch.cuda.reset_peak_memory_stats()
    times = []
    m.train()
    for i in range(a.steps):
        dev_sync(dev); t1 = time.perf_counter()
        opt.zero_grad(set_to_none=True); step(); opt.step()
        dev_sync(dev); times.append(time.perf_counter() - t1)
    res = dict(family=a.family, model=a.model, part=a.part, cut=a.cut, layers_total=L, hidden=d, device=dev,
               dtype=str(dt).split(".")[-1], batch=a.batch, seq=(a.seq if a.family == "llm" else 256), rank=a.rank,
               params_all=sum(p.numel() for p in m.parameters()), params_lora=sum(p.numel() for p in m.parameters() if p.requires_grad),
               weight_mb=nbytes(m, False) / 1e6, lora_mb=nbytes(m, True) / 1e6, act_mb=act_bytes / 1e6,
               build_s=round(build_s, 2), step_s=round(float(np.median(times[1:] or times)), 3), step_first_s=round(times[0], 3),
               peak_rss_mb=round(peak_rss_mb(), 1), gpu_peak_mb=gpu_peak_mb(dev), threads=a.threads)
    print(json.dumps(res, ensure_ascii=False))


def run_cost(a):
    os.makedirs(OUT, exist_ok=True)
    outp = os.path.join(OUT, f"cost_{a.family}_{a.tag}.jsonl")
    parts = a.parts.split(",")
    print(f"비용 사다리 [{a.family}] 모델 {a.models} 부분 {parts} cut {a.cut} batch {a.batch} seq {a.seq} device {a.device} → {outp}")
    print(f"{'모델':<22} {'부분':<6} {'층':>5} {'가중치 MB':>10} {'LoRA MB':>8} {'절단면 MB':>9} {'스텝 s':>8} {'최대 RSS MB':>11} {'GPU MB':>8}")
    with io.open(outp, "a", encoding="utf-8") as f:
        for mid in a.models.split(","):
            for part in parts:
                cmd = [sys.executable, os.path.abspath(__file__), "one", "--family", a.family, "--model", mid, "--part", part,
                       "--cut", str(a.cut), "--batch", str(a.batch), "--seq", str(a.seq), "--rank", str(a.rank), "--steps", str(a.steps),
                       "--device", a.device, "--threads", str(a.threads)] + (["--tiny"] if a.tiny else []) + (["--fp16"] if a.fp16 else [])
                try:
                    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=a.timeout)
                    rc, so, se = r.returncode, r.stdout, r.stderr
                except subprocess.TimeoutExpired as e:
                    rc, so, se = "timeout", (e.stdout or ""), (e.stderr or "") + " TIMEOUT"
                line = [l for l in so.splitlines() if l.startswith("{")]
                if rc != 0 or not line:
                    err = (se.strip().splitlines() or ["?"])[-1][:120]
                    tag = ("시간 초과(스와핑 추정)" if rc == "timeout" else
                           "OOM(메모리 부족)" if (rc in (-9, 137) or "out of memory" in se.lower() or "MemoryError" in se or "DefaultCPUAllocator" in se) else f"실패 rc={rc}")
                    res = dict(family=a.family, model=mid, part=part, cut=a.cut, device=a.device, error=tag, detail=err)
                    print(f"{mid:<22} {part:<6} {'':>5} {tag}  {err}")
                else:
                    res = json.loads(line[-1])
                    print(f"{mid:<22} {part:<6} {res['layers_total'] if part=='local' else (a.cut if part=='front' else res['layers_total']-a.cut):>5} "
                          f"{res['weight_mb']:>10.0f} {res['lora_mb']:>8.1f} {res['act_mb']:>9.1f} {res['step_s']:>8.2f} {res['peak_rss_mb']:>11.0f} "
                          f"{(res['gpu_peak_mb'] or 0):>8.0f}")
                res["ts"] = time.strftime("%Y-%m-%d %H:%M:%S"); f.write(json.dumps(res, ensure_ascii=False) + "\n"); f.flush()


# ── 실제 분할 학습: 서버 / 기기 ─────────────────────────────────────────
def t2b32(t):
    return t.detach().to(torch.float32).cpu().contiguous().numpy().tobytes()


def b2t(b, shape, device):
    return torch.frombuffer(bytearray(b), dtype=torch.float32).view(*shape).to(device)


def run_server(a):
    torch.set_num_threads(a.threads)
    dev = a.device
    srv = socket.create_server(("0.0.0.0", a.port)); srv.settimeout(600)
    print(f"[server] {a.family} {a.model} cut {a.cut} device {dev} 포트 {a.port} — 기기 대기", flush=True)
    conn, addr = srv.accept(); conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    kind, meta, _, _ = recv_msg(conn); assert kind == HELLO, kind
    t0 = time.perf_counter()
    dt = torch.float16 if a.fp16 else torch.float32
    if a.family == "llm":
        c = llm_config(a.model, a.tiny)
        m = LLMBack(c, a.cut, a.rank, dt, pretrained=None if a.tiny else a.model).to(dev)
    else:
        m = DiTBack(a.model, a.cut, a.rank, pretrained=None if (a.tiny or a.model != "XL") else DIT_PRETRAINED).to(dev)
    opt = torch.optim.AdamW([p for p in m.parameters() if p.requires_grad], lr=a.lr)
    m.train()
    print(f"[server] 준비 {time.perf_counter()-t0:.1f}s  가중치 {nbytes(m, False)/1e6:.0f}MB  LoRA {m.n_lora}곳 {nbytes(m, True)/1e6:.1f}MB", flush=True)
    send_msg(conn, HELLO_OK, {"weight_mb": nbytes(m, False) / 1e6, "lora_mb": nbytes(m, True) / 1e6})
    os.makedirs(OUT, exist_ok=True)
    logf = io.open(os.path.join(OUT, f"server_{a.family}_{a.tag}.jsonl"), "a", encoding="utf-8")
    if dev.startswith("cuda"):
        torch.cuda.reset_peak_memory_stats()
    while True:
        kind, meta, payload, nb = recv_msg(conn)
        if kind == BYE:
            break
        t1 = time.perf_counter()
        hb = int(np.prod(meta["shape"])) * 4                      # 페이로드 = 활성값(fp32) [+ dit: 노이즈]
        h = b2t(payload[:hb], meta["shape"], dev).to(dt).requires_grad_(True)
        opt.zero_grad(set_to_none=True)
        if a.family == "llm":
            lab = torch.tensor(meta["labels"], device=dev)
            logits = m(h)
            loss = F.cross_entropy(logits.float()[:, :-1].reshape(-1, logits.shape[-1]), lab[:, 1:].reshape(-1), ignore_index=-100)
        else:
            t = torch.tensor(meta["t"], device=dev); y = torch.tensor(meta["y"], device=dev)
            noise = b2t(payload[-meta["noise_bytes"]:], meta["noise_shape"], dev)
            out = m(h, t, y)[:, :4]
            loss = F.mse_loss(out, noise)
        loss.backward(); opt.step(); dev_sync(dev)
        srv_s = time.perf_counter() - t1
        send_msg(conn, GRAD, {"loss": float(loss), "srv_s": srv_s}, t2b32(h.grad))
        logf.write(json.dumps(dict(step=meta["step"], loss=float(loss), srv_s=round(srv_s, 3), recv_bytes=nb,
                                   gpu_peak_mb=gpu_peak_mb(dev), rss_mb=round(peak_rss_mb(), 1))) + "\n"); logf.flush()
        if meta["step"] % 10 == 0:
            print(f"[server] step {meta['step']:4d} loss {float(loss):.3f} srv {srv_s:.2f}s", flush=True)
    print(f"[server] 끝. 최대 RSS {peak_rss_mb():.0f}MB GPU {gpu_peak_mb(dev)}", flush=True)


def run_device(a):
    torch.set_num_threads(a.threads)
    dev = a.device
    host, port = a.server.split(":")
    t0 = time.perf_counter()
    if a.family == "llm":
        c = llm_config(a.model, a.tiny)
        m = LLMFront(c, a.cut, a.rank)
        dl = (0, 0, [])
        if not a.tiny:
            dl = load_front_pretrained(m, a.model, a.cut)
            print(f"[device] 부분 적재: 텐서 {dl[0]}개, 내려받은 조각 {dl[2]} {dl[1]/1e6:.0f}MB", flush=True)
        from transformers import AutoTokenizer
        from lora_corpus import load, split
        from run_l1 import batches, collate
        tok = AutoTokenizer.from_pretrained(a.model if not a.tiny else "Qwen/Qwen2.5-0.5B")
        if tok.pad_token is None:
            tok.pad_token = tok.eos_token
        tr, _ = split(load(a.domain))
        gen = batches(tr, tok, a.seq, a.batch, "cpu")
    else:
        m = DiTFront(a.model, a.cut, a.rank, pretrained=None if (a.tiny or a.model != "XL") else DIT_PRETRAINED)
        lat = torch.load(a.latents) if a.latents else None
    m.to(dev); m.train()
    opt = torch.optim.AdamW([p for p in m.parameters() if p.requires_grad], lr=a.lr)
    build_s = time.perf_counter() - t0
    print(f"[device] 준비 {build_s:.1f}s  가중치 {nbytes(m, False)/1e6:.0f}MB  LoRA {m.n_lora}곳 {nbytes(m, True)/1e6:.2f}MB  RSS {peak_rss_mb():.0f}MB", flush=True)
    s = socket.create_connection((host, int(port))); s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    send_msg(s, HELLO, {"family": a.family, "model": a.model, "cut": a.cut})
    _, hello, _, _ = recv_msg(s)
    os.makedirs(OUT, exist_ok=True)
    logf = io.open(os.path.join(OUT, f"device_{a.family}_{a.tag}.jsonl"), "a", encoding="utf-8")
    losses = []
    for step in range(1, a.steps + 1):
        t1 = time.perf_counter()
        if a.family == "llm":
            ids, lab = collate(gen, a.batch, tok.pad_token_id, dev)
            h = m(ids); meta = {"step": step, "shape": list(h.shape), "labels": lab.tolist()}; payload = t2b32(h)
        else:
            xt, t, y, noise = dit_batch(a.batch, dev, lat, step)
            h = m(xt, t, y); nb_ = t2b32(noise)
            meta = {"step": step, "shape": list(h.shape), "t": t.tolist(), "y": y.tolist(), "noise_shape": list(noise.shape), "noise_bytes": len(nb_)}
            payload = t2b32(h) + nb_
        dev_sync(dev); t2 = time.perf_counter()
        up = send_msg(s, ACT, meta, payload)
        _, gm, gp, dn = recv_msg(s); t3 = time.perf_counter()
        g = b2t(gp, h.shape, dev).to(h.dtype)
        opt.zero_grad(set_to_none=True); h.backward(g); opt.step(); dev_sync(dev); t4 = time.perf_counter()
        losses.append(gm["loss"])
        rec = dict(step=step, loss=gm["loss"], fwd_s=round(t2 - t1, 3), net_s=round(t3 - t2 - gm["srv_s"], 3), srv_s=round(gm["srv_s"], 3),
                   bwd_s=round(t4 - t3, 3), step_s=round(t4 - t1, 3), up_bytes=up, dn_bytes=dn, rss_mb=round(peak_rss_mb(), 1))
        logf.write(json.dumps(rec) + "\n"); logf.flush()
        if step % 5 == 0 or step == 1:
            print(f"[device] step {step:4d} loss {gm['loss']:.3f} | fwd {rec['fwd_s']:.2f} net {rec['net_s']:.2f} srv {rec['srv_s']:.2f} bwd {rec['bwd_s']:.2f} = {rec['step_s']:.2f}s | ↑{up/1e6:.1f}MB ↓{dn/1e6:.1f}MB | RSS {rec['rss_mb']:.0f}MB", flush=True)
    send_msg(s, BYE)
    torch.save(lora_state(m), os.path.join(OUT, f"adapter_{a.family}_{a.tag}.pt"))
    k = max(1, len(losses) // 5)
    print(f"[device] 끝. 손실 처음 {np.mean(losses[:k]):.3f} → 마지막 {np.mean(losses[-k:]):.3f}  최대 RSS {peak_rss_mb():.0f}MB  어댑터 {nbytes(m, True)/1e6:.2f}MB", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["cost", "one", "server", "device"])
    ap.add_argument("--family", default="llm", choices=["llm", "dit"])
    ap.add_argument("--models", default="Qwen/Qwen2.5-0.5B,Qwen/Qwen2.5-1.5B,Qwen/Qwen2.5-3B,Qwen/Qwen2.5-7B")
    ap.add_argument("--model", default="Qwen/Qwen2.5-0.5B")
    ap.add_argument("--parts", default="local,front,back")
    ap.add_argument("--part", default="front")
    ap.add_argument("--cut", type=int, default=2)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--seq", type=int, default=256)
    ap.add_argument("--steps", type=int, default=3)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--threads", type=int, default=max(1, (os.cpu_count() or 2)))
    ap.add_argument("--fp16", action="store_true", help="가중치 fp16 (GPU 서버용)")
    ap.add_argument("--tiny", action="store_true")
    ap.add_argument("--tag", default=time.strftime("%m%d_%H%M"))
    ap.add_argument("--port", type=int, default=31950)
    ap.add_argument("--server", default="127.0.0.1:31950")
    ap.add_argument("--domain", default="B")
    ap.add_argument("--latents", default="")
    ap.add_argument("--timeout", type=int, default=1800, help="cost: 설정 하나의 제한 시간(s) — 넘기면 스와핑으로 보고 기록")
    a = ap.parse_args()
    {"cost": run_cost, "one": measure_one, "server": run_server, "device": run_device}[a.mode](a)


if __name__ == "__main__":
    main()
