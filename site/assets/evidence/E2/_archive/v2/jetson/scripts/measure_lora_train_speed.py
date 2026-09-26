#!/usr/bin/env python3
# =============================================================================
# AwareNet FedLLM — C2' 앵커: 실제 Qwen2.5-0.5B LoRA 로컬 학습 속도 실측
# -----------------------------------------------------------------------------
# 실 베이스 모델 + LoRA(r=32, q/v)로 스텝당 학습 시간·GPU 메모리를 측정한다.
# Mode B 컨테이너 sleep 패딩과 젯슨(C1') 실측의 비교 기준값.
# 사용: python scripts/analysis/measure_lora_train_speed.py [--steps 20]
# 출력: 콘솔 + out/lora_train_speed.json
# =============================================================================

import io
import os
import json
import time
import argparse
import torch
from transformers import AutoModelForCausalLM, AutoConfig
from peft import LoraConfig, get_peft_model

MODEL_ID = os.environ.get("AWARENET_BASE_MODEL", "Qwen/Qwen2.5-0.5B")
SEQ_LEN = 512
BATCH = 2  # 젯슨(8GB)에서도 유효한 보수적 배치


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--batch", type=int, default=BATCH)
    parser.add_argument("--seq-len", type=int, default=SEQ_LEN)
    parser.add_argument("--output", default="out/lora_train_speed.json")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"디바이스: {device} ({torch.cuda.get_device_name(0) if device.type=='cuda' else 'CPU'})")

    print(f"베이스 모델 로드 중: {MODEL_ID} ...")
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, dtype=torch.float32)
    lora_cfg = LoraConfig(r=32, lora_alpha=64, lora_dropout=0.05,
                          target_modules=["q_proj", "v_proj"], task_type="CAUSAL_LM")
    model = get_peft_model(model, lora_cfg).to(device)
    vocab = model.config.vocab_size

    # 어댑터 페이로드 (fp32 / fp16 병기 — 압축 병용 가능성의 정량 근거)
    adapter = {k: v.detach().cpu() for k, v in model.named_parameters() if v.requires_grad}
    sizes = {}
    for dtype_name, dtype in [("fp32", torch.float32), ("fp16", torch.float16)]:
        buf = io.BytesIO()
        torch.save({k: v.to(dtype) for k, v in adapter.items()}, buf)
        sizes[dtype_name] = len(buf.getvalue())
    print(f"어댑터 페이로드: fp32 {sizes['fp32']/1e6:.2f} MB / fp16 {sizes['fp16']/1e6:.2f} MB")

    optimizer = torch.optim.AdamW((p for p in model.parameters() if p.requires_grad), lr=2e-4)
    model.train()
    torch.manual_seed(42)

    def one_step():
        ids = torch.randint(0, vocab, (args.batch, args.seq_len), device=device)
        optimizer.zero_grad()
        out = model(input_ids=ids, labels=ids)
        out.loss.backward()
        optimizer.step()

    # 워밍업 (CUDA 커널 컴파일 제외 — C2 측정 원칙과 동일)
    for _ in range(args.warmup):
        one_step()
    if device.type == "cuda":
        torch.cuda.synchronize()

    times = []
    for _ in range(args.steps):
        t0 = time.perf_counter()
        one_step()
        if device.type == "cuda":
            torch.cuda.synchronize()
        times.append(time.perf_counter() - t0)

    import statistics
    mean_s = statistics.mean(times)
    std_s = statistics.stdev(times) if len(times) > 1 else 0.0
    median_s = statistics.median(times)
    edge_n = min(10, len(times))
    first_mean_s = statistics.mean(times[:edge_n])
    last_mean_s = statistics.mean(times[-edge_n:])
    slowdown_pct = ((last_mean_s / first_mean_s) - 1.0) * 100.0
    throttling_suspected = len(times) >= 20 and slowdown_pct >= 10.0
    tokens_per_s = args.batch * args.seq_len / mean_s
    mem_gb = torch.cuda.max_memory_allocated() / 2**30 if device.type == "cuda" else None

    print(f"스텝당 학습 시간 (배치 {args.batch} × 시퀀스 {args.seq_len}, 워밍업 {args.warmup} 제외, n={args.steps}):")
    print(f"  평균 {mean_s*1000:.1f} ms ± {std_s*1000:.1f} ms  ({tokens_per_s:,.0f} tokens/s)")
    print(f"  중앙값 {median_s*1000:.1f} ms")
    print(f"  앞 {edge_n}회 {first_mean_s*1000:.1f} ms / 뒤 {edge_n}회 {last_mean_s*1000:.1f} ms")
    print(f"  후반 변화율 {slowdown_pct:+.1f}% / 스로틀링 의심: {throttling_suspected}")
    if mem_gb is not None:
        print(f"  GPU 최대 메모리: {mem_gb:.2f} GB")

    res = {
        "model": MODEL_ID, "lora": "r=32 q_proj,v_proj", "batch": args.batch, "seq_len": args.seq_len,
        "device": torch.cuda.get_device_name(0) if device.type == "cuda" else "cpu",
        "step_mean_ms": round(mean_s * 1000, 1), "step_std_ms": round(std_s * 1000, 1),
        "step_median_ms": round(median_s * 1000, 1),
        "first_10_mean_ms": round(first_mean_s * 1000, 1),
        "last_10_mean_ms": round(last_mean_s * 1000, 1),
        "slowdown_pct": round(slowdown_pct, 2),
        "throttling_suspected": throttling_suspected,
        "step_times_ms": [round(t * 1000, 3) for t in times],
        "power_mode": os.environ.get("AWARENET_POWER_MODE", "unknown"),
        "precision": "fp32",
        "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "tokens_per_sec": round(tokens_per_s), "max_mem_gb": round(mem_gb, 2) if mem_gb else None,
        "adapter_bytes_fp32": sizes["fp32"], "adapter_bytes_fp16": sizes["fp16"],
        "warmup_excluded": args.warmup, "n_steps": args.steps,
    }
    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2, ensure_ascii=False)
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
