# -*- coding: utf-8 -*-
"""분할 + LoRA 대형 모델 실험 — 표와 그림 (2026-09-13)
   ~/env/bin/python scripts/analysis/scale_lora_report.py --tag 0913 [--out out/reports]
   입력: out/scale_lora/cost_{llm,dit}_<tag>_vm.jsonl (기기 local/front), cost_*_<tag>_hpc.jsonl (서버 back),
         device_*_<tag>_<model>.jsonl (실제 분할 학습 스텝 기록), server_*.jsonl
   출력: 표(stdout, 마크다운) + <out>/scale_lora_<tag>.png (기기 메모리·스텝 시간 vs 모델, 로컬 대 분할 + 비율)
"""
import argparse
import glob
import io
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ap = argparse.ArgumentParser()
ap.add_argument("--tag", required=True)
ap.add_argument("--dir", default="out/scale_lora")
ap.add_argument("--out", default="out/reports")
a = ap.parse_args()

def rows(pattern):
    out = []
    for f in sorted(glob.glob(os.path.join(a.dir, pattern))):
        out += [json.loads(l) for l in io.open(f, encoding="utf-8") if l.strip()]
    return out

SHORT = {"Qwen/Qwen2.5-0.5B": "0.5B", "Qwen/Qwen2.5-1.5B": "1.5B", "Qwen/Qwen2.5-3B": "3B", "Qwen/Qwen2.5-7B": "7B",
         "S": "DiT-S", "B": "DiT-B", "L": "DiT-L", "XL": "DiT-XL"}
ORDER = ["Qwen/Qwen2.5-0.5B", "Qwen/Qwen2.5-1.5B", "Qwen/Qwen2.5-3B", "Qwen/Qwen2.5-7B", "S", "B", "L", "XL"]

def latest(rs):
    """(family, model, part, device) 마지막 기록만."""
    d = {}
    for r in rs:
        d[(r["family"], r["model"], r["part"], r.get("device", ""))] = r
    return d

vm = latest(rows(f"cost_*_{a.tag}_vm.jsonl"))
hpc = latest(rows(f"cost_*_{a.tag}_hpc.jsonl"))
cpu = latest(rows(f"cost_*_{a.tag}_hpccpu.jsonl"))

def fmt(r, k, f="{:.0f}"):
    if r is None: return "—"
    if "error" in r: return r["error"]
    v = r.get(k); return "—" if v is None else f.format(v)

print(f"## 기기(VM1, 8코어 CPU 31 GB) — 로컬 LoRA(모델 전체) vs 분할 LoRA(임베딩 + 앞 2층)   [tag {a.tag}]")
print("| 모델 | 층 | 은닉 | 로컬: 가중치 MB / 최대 RSS MB / 스텝 s | 분할 기기: 가중치 MB / 최대 RSS MB / 스텝 s | RSS 비 | 시간 비 | 절단면 왕복 MB/스텝 | 어댑터 MB 로컬→분할 |")
print("|---|---|---|---|---|---|---|---|---|")
series = {}
for fam in ("llm", "dit"):
    for m in ORDER:
        lo = vm.get((fam, m, "local", "cpu")); fr = vm.get((fam, m, "front", "cpu"))
        if lo is None and fr is None: continue
        ref = fr if fr and "error" not in fr else lo
        L = ref.get("layers_total", "?") if ref else "?"; d = ref.get("hidden", "?") if ref else "?"
        ok = lo and fr and "error" not in lo and "error" not in fr
        rr = f"{fr['peak_rss_mb']/lo['peak_rss_mb']:.2f}" if ok else ("→ 분할만 가능" if (fr and "error" not in fr and lo and "error" in lo) else "—")
        tr = f"{fr['step_s']/lo['step_s']:.2f}" if ok else "—"
        act = f"{2*fr['act_mb']:.1f}" if fr and "error" not in fr else "—"
        ad = f"{lo['lora_mb']:.1f} → {fr['lora_mb']:.2f}" if ok else (f"? → {fr['lora_mb']:.2f}" if fr and "error" not in fr else "—")
        print(f"| {SHORT.get(m, m)} | {L} | {d} | {fmt(lo,'weight_mb')} / {fmt(lo,'peak_rss_mb')} / {fmt(lo,'step_s','{:.2f}')} | "
              f"{fmt(fr,'weight_mb')} / {fmt(fr,'peak_rss_mb')} / {fmt(fr,'step_s','{:.2f}')} | {rr} | {tr} | {act} | {ad} |")
        series[(fam, m)] = (lo, fr)

print(f"\n## 서버(HPC) 몫 — layer[2:] + 출력층")
print("| 모델 | 장치 | 가중치 MB | 스텝 s | GPU 최대 MB | RSS MB |")
print("|---|---|---|---|---|---|")
for fam in ("llm", "dit"):
    for m in ORDER:
        for dev in ("cuda", "cpu"):
            r = hpc.get((fam, m, "back", dev))
            if r: print(f"| {SHORT.get(m, m)} | {dev}{' fp16' if r.get('dtype')=='float16' else ''} | {fmt(r,'weight_mb')} | {fmt(r,'step_s','{:.2f}')} | {fmt(r,'gpu_peak_mb')} | {fmt(r,'peak_rss_mb')} |")

if cpu:
    print(f"\n## 참고 — 같은 기계(HPC CPU 8스레드)에서 세 부분 (기기 OOM 과 무관하게 비율을 보기 위해)")
    print("| 모델 | 로컬 RSS / 스텝 | front RSS / 스텝 | back RSS / 스텝 | RSS 비 | 시간 비 |")
    print("|---|---|---|---|---|---|")
    for m in ORDER:
        lo, fr, bk = (cpu.get(("llm", m, p, "cpu")) for p in ("local", "front", "back"))
        if not (lo or fr): continue
        ok = lo and fr and "error" not in lo and "error" not in fr
        print(f"| {SHORT.get(m,m)} | {fmt(lo,'peak_rss_mb')} / {fmt(lo,'step_s','{:.2f}')} | {fmt(fr,'peak_rss_mb')} / {fmt(fr,'step_s','{:.2f}')} | {fmt(bk,'peak_rss_mb')} / {fmt(bk,'step_s','{:.2f}')} | "
              f"{(fr['peak_rss_mb']/lo['peak_rss_mb']) if ok else float('nan'):.2f} | {(fr['step_s']/lo['step_s']) if ok else float('nan'):.2f} |")

# 실제 분할 학습
print(f"\n## 실제 분할 학습 (VM1 기기 ↔ HPC 서버, 도메인 B 코퍼스)")
print("| 모델 | 스텝 | 손실 처음 1/5 → 마지막 1/5 | 기기 스텝 s (fwd/망/서버/bwd) | 왕복 MB/스텝 | 기기 최대 RSS MB | 판정 |")
print("|---|---|---|---|---|---|---|")
e2e = {}
for f in sorted(glob.glob(os.path.join(a.dir, f"device_*_{a.tag}_*.jsonl"))):
    rs = [json.loads(l) for l in io.open(f, encoding="utf-8") if l.strip()]
    if not rs: continue
    name = os.path.basename(f).split(f"_{a.tag}_")[-1].replace(".jsonl", "")
    k = max(1, len(rs) // 5); l0 = sum(r["loss"] for r in rs[:k]) / k; l1 = sum(r["loss"] for r in rs[-k:]) / k
    body = rs[1:] or rs
    med = lambda key: sorted(r[key] for r in body)[len(body) // 2]
    print(f"| {name} | {len(rs)} | {l0:.3f} → {l1:.3f} | {med('step_s'):.2f} ({med('fwd_s'):.2f}/{med('net_s'):.2f}/{med('srv_s'):.2f}/{med('bwd_s'):.2f}) | "
          f"{(rs[-1]['up_bytes']+rs[-1]['dn_bytes'])/1e6:.1f} | {max(r['rss_mb'] for r in rs):.0f} | {'성립(하강)' if l1 < l0 else '불성립'} |")
    e2e[name] = rs

# 그림
try:
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for p in ("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "C:/Windows/Fonts/malgun.ttf"):
        if os.path.exists(p): font_manager.fontManager.addfont(p); plt.rcParams["font.family"] = font_manager.FontProperties(fname=p).get_name(); break
    plt.rcParams["axes.unicode_minus"] = False
    fams = [("llm", "LLM (Qwen2.5)"), ("dit", "디퓨전 (DiT/2)")]
    fig, axs = plt.subplots(2, 3, figsize=(16, 8.5))
    for row, (fam, title) in enumerate(fams):
        ms = [m for m in ORDER if (fam, m) in series]
        if not ms: continue
        xs = range(len(ms)); lab = [SHORT[m] for m in ms]
        lo_r = [series[(fam, m)][0] for m in ms]; fr_r = [series[(fam, m)][1] for m in ms]
        g = lambda r, k: (r[k] if r and "error" not in r else float("nan"))
        ax = axs[row][0]
        ax.bar([x - 0.2 for x in xs], [g(r, "peak_rss_mb") / 1e3 for r in lo_r], 0.4, label="로컬 LoRA (모델 전체가 기기에)", color="#999")
        ax.bar([x + 0.2 for x in xs], [g(r, "peak_rss_mb") / 1e3 for r in fr_r], 0.4, label="분할 LoRA (임베딩+앞 2층)", color="#1f6feb")
        for x, r in zip(xs, lo_r):
            if r and "error" in r: ax.text(x - 0.2, 0.5, r["error"].split("(")[0], rotation=90, ha="center", va="bottom", color="#c00", fontsize=9)
        ax.axhline(31, ls="--", color="#c00", lw=1); ax.text(len(ms) - 0.5, 31.5, "기기 RAM 31 GB", ha="right", color="#c00", fontsize=9)
        ax.set_xticks(list(xs)); ax.set_xticklabels(lab); ax.set_ylabel("기기 최대 메모리 (GB)"); ax.set_title(f"{title} — 기기 메모리"); ax.legend(fontsize=8); ax.grid(axis="y", alpha=.3)
        ax = axs[row][1]
        ax.bar([x - 0.2 for x in xs], [g(r, "step_s") for r in lo_r], 0.4, color="#999"); ax.bar([x + 0.2 for x in xs], [g(r, "step_s") for r in fr_r], 0.4, color="#1f6feb")
        ax.set_xticks(list(xs)); ax.set_xticklabels(lab); ax.set_ylabel("기기 스텝 시간 (s)"); ax.set_title(f"{title} — 기기 스텝 시간 (B4)"); ax.grid(axis="y", alpha=.3)
        ax = axs[row][2]
        ratio_m = [g(f_, "peak_rss_mb") / g(l_, "peak_rss_mb") for l_, f_ in zip(lo_r, fr_r)]
        ratio_t = [g(f_, "step_s") / g(l_, "step_s") for l_, f_ in zip(lo_r, fr_r)]
        ax.plot(list(xs), ratio_m, "o-", color="#1f6feb", label="메모리 비 (분할/로컬)"); ax.plot(list(xs), ratio_t, "s--", color="#d97706", label="시간 비 (분할/로컬)")
        ax.set_xticks(list(xs)); ax.set_xticklabels(lab); ax.set_ylim(0, 1.05); ax.set_ylabel("기기 부담 비율"); ax.set_title(f"{title} — 클수록 기기 몫이 작아진다"); ax.legend(fontsize=8); ax.grid(alpha=.3)
    os.makedirs(a.out, exist_ok=True); fig.tight_layout(); p1 = os.path.join(a.out, f"scale_lora_{a.tag}.png"); fig.savefig(p1, dpi=120); print("\n그림", p1)
    if e2e:
        fig, ax = plt.subplots(1, len(e2e), figsize=(4.5 * len(e2e), 3.6), squeeze=False)
        for axx, (name, rs) in zip(ax[0], e2e.items()):
            axx.plot([r["step"] for r in rs], [r["loss"] for r in rs], color="#1f6feb"); axx.set_title(f"{name} 손실 (기기↔서버 분할 학습)"); axx.set_xlabel("스텝"); axx.grid(alpha=.3)
        fig.tight_layout(); p2 = os.path.join(a.out, f"scale_lora_{a.tag}_loss.png"); fig.savefig(p2, dpi=120); print("그림", p2)
except Exception as e:
    print("그림 생략:", e)
