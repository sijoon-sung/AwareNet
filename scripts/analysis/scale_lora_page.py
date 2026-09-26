# -*- coding: utf-8 -*-
"""분할 LoRA 크기 사다리 — 보고 페이지 생성 (2026-09-13)
   python scripts/analysis/scale_lora_page.py  → out/reports/분할LoRA_크기사다리_2026-09-13.html
   숫자는 out/scale_lora/*.jsonl 에서 읽고, 그림(out/reports/scale_lora_0913*.png)은 data URI 로 심는다."""
import base64
import glob
import io
import json
import os
import statistics as st

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TAG = "0913"
D = os.path.join(ROOT, "out", "scale_lora")

def rows(pat):
    out = []
    for f in sorted(glob.glob(os.path.join(D, pat))):
        out += [json.loads(l) for l in io.open(f, encoding="utf-8") if l.strip()]
    return out

def latest(rs):
    d = {}
    for r in rs: d[(r["family"], r["model"], r["part"], r.get("device", ""))] = r
    return d

vm = latest(rows(f"cost_*_{TAG}_vm.jsonl")); hpc = latest(rows(f"cost_*_{TAG}_hpc.jsonl")); cpu = latest(rows(f"cost_*_{TAG}_hpccpu.jsonl"))
SHORT = {"Qwen/Qwen2.5-0.5B": "Qwen2.5 0.5B", "Qwen/Qwen2.5-1.5B": "Qwen2.5 1.5B", "Qwen/Qwen2.5-3B": "Qwen2.5 3B", "Qwen/Qwen2.5-7B": "Qwen2.5 7B",
         "S": "DiT-S/2", "B": "DiT-B/2", "L": "DiT-L/2", "XL": "DiT-XL/2"}
ORDER = ["Qwen/Qwen2.5-0.5B", "Qwen/Qwen2.5-1.5B", "Qwen/Qwen2.5-3B", "Qwen/Qwen2.5-7B", "S", "B", "L", "XL"]
DL = {"Qwen/Qwen2.5-0.5B": (988, 954), "Qwen/Qwen2.5-3B": (3969, 5800), "Qwen/Qwen2.5-7B": (3945, 15000), "XL": (2700, 3200)}

def img(p):
    return "data:image/png;base64," + base64.b64encode(open(p, "rb").read()).decode()

def gb(mb): return f"{mb/1e3:.1f}"

def ladder_rows():
    out = []
    for fam in ("llm", "dit"):
        for m in ORDER:
            lo = vm.get((fam, m, "local", "cpu")); fr = vm.get((fam, m, "front", "cpu"))
            if not (lo or fr): continue
            ok = lo and fr and "error" not in lo and "error" not in fr
            if ok:
                loc = f"<td>{gb(lo['peak_rss_mb'])} GB</td><td>{lo['step_s']:.1f} s</td>"
                ratio = f"<td class='ratio'>{fr['peak_rss_mb']/lo['peak_rss_mb']:.2f}</td><td class='ratio'>{fr['step_s']/lo['step_s']:.2f}</td>"
            else:
                loc = "<td colspan='2' class='oom'>메모리 부족 — 올라가지 않음</td>"
                ratio = "<td colspan='2' class='oom'>분할로만 가능</td>"
            out.append(f"<tr><th scope='row'>{SHORT[m]}</th><td class='dim'>{fr['layers_total']} / {fr['hidden']}</td>{loc}"
                       f"<td>{gb(fr['peak_rss_mb'])} GB</td><td>{fr['step_s']:.2f} s</td>{ratio}<td>{2*fr['act_mb']:.1f} MB</td></tr>")
        if fam == "llm": out.append("<tr class='gap'><td colspan='9'></td></tr>")
    return "\n".join(out)

def server_rows():
    out = []
    for fam in ("llm", "dit"):
        for m in ORDER:
            for dev in ("cuda", "cpu"):
                r = hpc.get((fam, m, "back", dev))
                if not r: continue
                mem = f"{gb(r['gpu_peak_mb'])} GB (V100)" if r.get("gpu_peak_mb") else f"{gb(r['peak_rss_mb'])} GB (CPU RAM)"
                out.append(f"<tr><th scope='row'>{SHORT[m]}</th><td>{'GPU fp16' if dev=='cuda' and fam=='llm' else ('GPU' if dev=='cuda' else 'CPU fp32')}</td><td>{gb(r['weight_mb'])} GB</td><td>{mem}</td><td>{r['step_s']:.2f} s</td></tr>")
    return "\n".join(out)

def e2e_rows():
    out = []
    names = [("device_llm_0913_Qwen_Qwen2.5-0.5B.jsonl", "Qwen2.5 0.5B", "GPU"), ("device_llm_0913_Qwen_Qwen2.5-3B.jsonl", "Qwen2.5 3B", "CPU"),
             ("device_llm_0913_Qwen_Qwen2.5-7B.jsonl", "Qwen2.5 7B", "CPU"), ("device_dit_0913_XL.jsonl", "DiT-XL/2", "GPU")]
    for f, name, sdev in names:
        p = os.path.join(D, f)
        if not os.path.exists(p): continue
        rs = [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()]
        k = max(1, len(rs) // 5); l0 = st.mean(r["loss"] for r in rs[:k]); l1 = st.mean(r["loss"] for r in rs[-k:])
        body = rs[1:] or rs; med = lambda key: st.median(r[key] for r in body)
        out.append(f"<tr><th scope='row'>{name}</th><td>{sdev}</td><td>{len(rs)}</td><td>{l0:.2f} → {l1:.2f}</td>"
                   f"<td>{med('step_s'):.2f} s <span class='sub'>(기기 {med('fwd_s')+med('bwd_s'):.2f} · 망 {med('net_s'):.2f} · 서버 {med('srv_s'):.2f})</span></td>"
                   f"<td>{(rs[-1]['up_bytes']+rs[-1]['dn_bytes'])/1e6:.1f} MB</td><td>{gb(max(r['rss_mb'] for r in rs))} GB</td></tr>")
    return "\n".join(out)

dl_rows = "\n".join(f"<tr><th scope='row'>{SHORT[m]}</th><td>{DL[m][1]/1e3:.1f} GB</td><td>{DL[m][0]/1e3:.1f} GB</td><td class='ratio'>{DL[m][0]/DL[m][1]:.2f}</td></tr>" for m in ("Qwen/Qwen2.5-0.5B", "Qwen/Qwen2.5-3B", "Qwen/Qwen2.5-7B", "XL"))

html = f"""<title>분할 LoRA 크기 사다리</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root {{
  --bg:#f6f7f5; --panel:#ffffff; --ink:#1c2128; --ink2:#4b535e; --line:#d9dde3; --line2:#eceff2;
  --acc:#1f6feb; --acc-soft:#e3edfd; --local:#8a8f98; --local-soft:#ececee; --oom:#b3261e; --oom-soft:#fbe9e7; --ok:#1f7a4d;
  --sans:"IBM Plex Sans KR","Noto Sans KR","Malgun Gothic",system-ui,sans-serif; --mono:"IBM Plex Mono",ui-monospace,Consolas,monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg:#14171b; --panel:#1b1f25; --ink:#e7eaee; --ink2:#a6adb7; --line:#333a44; --line2:#262c34;
  --acc:#6ea4ff; --acc-soft:#1c2a45; --local:#9aa1ab; --local-soft:#2a2f36; --oom:#ff8a80; --oom-soft:#3a1f1d; --ok:#5fcf8d; }} }}
:root[data-theme="dark"] {{
  --bg:#14171b; --panel:#1b1f25; --ink:#e7eaee; --ink2:#a6adb7; --line:#333a44; --line2:#262c34;
  --acc:#6ea4ff; --acc-soft:#1c2a45; --local:#9aa1ab; --local-soft:#2a2f36; --oom:#ff8a80; --oom-soft:#3a1f1d; --ok:#5fcf8d; }}
body {{ background:var(--bg); color:var(--ink); font-family:var(--sans); font-size:15px; line-height:1.65; margin:0; }}
main {{ max-width:1040px; margin:0 auto; padding:40px 28px 80px; }}
header {{ border-bottom:1px solid var(--line); padding-bottom:22px; margin-bottom:34px; }}
.eyebrow {{ font-family:var(--mono); font-size:12px; letter-spacing:.08em; text-transform:uppercase; color:var(--ink2); }}
h1 {{ font-size:34px; line-height:1.2; margin:8px 0 12px; font-weight:700; text-wrap:balance; }}
h2 {{ font-size:22px; margin:44px 0 12px; font-weight:600; text-wrap:balance; }}
h3 {{ font-size:16px; margin:26px 0 8px; font-weight:600; }}
p, li {{ max-width:72ch; }}
.lede {{ font-size:17px; color:var(--ink2); max-width:78ch; }}
.claim {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin:26px 0 6px; }}
.claim div {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px 18px; }}
.claim b {{ display:block; font-family:var(--mono); font-size:26px; font-weight:500; color:var(--acc); margin-bottom:4px; font-variant-numeric:tabular-nums; }}
.claim span {{ color:var(--ink2); font-size:14px; }}
figure {{ margin:18px 0 6px; background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:10px; }}
figure img {{ width:100%; height:auto; display:block; border-radius:4px; }}
figcaption {{ font-size:13px; color:var(--ink2); padding:8px 6px 2px; }}
.tbl {{ overflow-x:auto; margin:14px 0; }}
table {{ border-collapse:collapse; width:100%; font-size:14px; font-variant-numeric:tabular-nums; }}
th, td {{ padding:8px 10px; border-bottom:1px solid var(--line2); text-align:right; white-space:nowrap; }}
th[scope=row], td:first-child {{ text-align:left; font-weight:500; }}
thead th {{ font-size:12px; color:var(--ink2); font-weight:500; letter-spacing:.02em; border-bottom:1px solid var(--line); text-align:right; }}
thead th:first-child {{ text-align:left; }}
thead th.grp {{ text-align:center; }}
.grp-local {{ background:var(--local-soft); }} .grp-split {{ background:var(--acc-soft); }}
td.ratio {{ font-family:var(--mono); color:var(--acc); }}
td.oom {{ color:var(--oom); background:var(--oom-soft); text-align:center; }}
td.dim {{ color:var(--ink2); }} .sub {{ color:var(--ink2); font-size:12px; }}
tr.gap td {{ border:0; height:8px; }}
.split {{ display:grid; grid-template-columns:1fr 1fr; gap:22px; align-items:start; }}
@media (max-width:760px) {{ .claim, .split {{ grid-template-columns:1fr; }} }}
.diagram {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:14px; }}
.diagram svg {{ width:100%; height:auto; display:block; }}
.verdict li {{ margin:6px 0; }} .verdict .ok {{ color:var(--ok); font-weight:600; }} .verdict .part {{ color:var(--oom); font-weight:600; }}
.note {{ border-left:3px solid var(--acc); padding:6px 14px; color:var(--ink2); background:var(--panel); border-radius:0 6px 6px 0; margin:14px 0; }}
code {{ font-family:var(--mono); font-size:13px; background:var(--line2); padding:1px 5px; border-radius:4px; }}
footer {{ margin-top:50px; border-top:1px solid var(--line); padding-top:14px; font-size:13px; color:var(--ink2); }}
</style>
<main>
<header>
  <div class="eyebrow">AwareNet · 분할 연합학습 · 2026-09-13</div>
  <h1>분할 학습이면 작은 기기도 큰 모델을 LoRA 로 학습한다 — 모델이 클수록 기기 몫이 작아진다</h1>
  <p class="lede">기기(KOREN VM, 8코어 CPU · 31 GB)가 모델 전체를 들고 LoRA 를 학습하는 것과, 임베딩 + 앞 2층만 들고 나머지를 HPC 서버에 두는 것을 같은 조건에서 쟀다. LLM(Qwen2.5 0.5B → 7B)과 디퓨전(DiT-S → XL) 두 사다리, 그리고 실제 회선 위의 분할 학습 4건.</p>
  <div class="claim">
    <div><b>0.19 → 0.14</b><span>LLM 기기 메모리 비 (분할 ÷ 로컬), 0.5B → 3B. 시간 비 0.07 → 0.05</span></div>
    <div><b>7B: 분할로만</b><span>로컬 LoRA 는 31 GB 기기에서 메모리 부족. 분할은 기기 6.4 GB · 스텝 7 s</span></div>
    <div><b>4 / 4 학습 성립</b><span>VM 기기 ↔ HPC 서버 분할 학습: 0.5B · 3B · 7B · DiT-XL 손실 하강</span></div>
  </div>
</header>

<h2>1. 왜 이걸 재나</h2>
<p>연합학습으로 LLM·디퓨전을 미세조정하려면 기기가 모델을 올려야 한다. LoRA 로 학습 파라미터를 줄여도 <em>동결된 가중치와 활성값</em>은 그대로라, 7B 급은 노트북·엣지 기기 메모리에 안 들어간다. 분할 학습은 모델을 깊이 방향으로 자른다. 기기는 임베딩과 앞 k 층만 들고 절단면 활성값을 서버로 보낸다. 깊이 L 이 커져도 기기 몫(k 층)은 그대로이고, 절단면 크기(배치 × 길이 × 은닉)는 깊이와 무관하다. 그래서 <strong>모델이 클수록 기기 부담의 절감 비율이 커져야 한다</strong> — 이것을 실측으로 확인했다.</p>
<div class="split">
  <div class="diagram">
    <svg viewBox="0 0 520 190" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="로컬 LoRA 와 분할 LoRA 의 배치">
      <g font-family="IBM Plex Sans KR, sans-serif" font-size="12" fill="currentColor">
        <text x="12" y="20" font-weight="600">로컬 LoRA — 모델 전체가 기기에</text>
        <rect x="12" y="30" width="496" height="40" rx="4" fill="none" stroke="var(--local)" stroke-width="1.5"/>
        <rect x="14" y="32" width="492" height="36" rx="3" fill="var(--local-soft)"/>
        <text x="20" y="55">임베딩</text><text x="90" y="55">층 1 … 층 L</text><text x="420" y="55">출력층 · 손실</text>
        <text x="12" y="105" font-weight="600">분할 LoRA — 기기는 임베딩 + 앞 k 층</text>
        <rect x="14" y="117" width="120" height="36" rx="3" fill="var(--acc-soft)" stroke="var(--acc)" stroke-width="1.5"/>
        <text x="20" y="140">임베딩 · 층 1~k</text>
        <text x="145" y="132" font-size="11" fill="var(--ink2)">활성값 ↑</text><text x="145" y="147" font-size="11" fill="var(--ink2)">기울기 ↓</text>
        <line x1="140" y1="135" x2="205" y2="135" stroke="var(--acc)" stroke-width="1.5" stroke-dasharray="4 3"/>
        <rect x="210" y="117" width="296" height="36" rx="3" fill="var(--local-soft)" stroke="var(--local)" stroke-width="1.5"/>
        <text x="218" y="140">서버: 층 k+1 … 층 L · 출력층 · 손실</text>
        <text x="14" y="178" font-size="11" fill="var(--ink2)">기기 (VM, CPU 31 GB)</text><text x="210" y="178" font-size="11" fill="var(--ink2)">서버 (HPC, V100 16 GB / CPU 158 GB)</text>
      </g>
    </svg>
  </div>
  <div>
    <h3>식 (기기 쪽)</h3>
    <p>메모리 비 ≈ (P<sub>emb</sub> + k·P<sub>layer</sub>) ÷ (P<sub>emb</sub> + L·P<sub>layer</sub> + P<sub>head</sub>) → L 이 커질수록 k/L 로 수렴. 스텝 시간도 같은 꼴. 절단면 통신은 2·B·S·d·4 바이트/스텝으로 깊이와 무관, 은닉 d 에만 비례.</p>
    <h3>문헌</h3>
    <p>SplitLoRA(2024, arXiv 2407.00952) · HSplitLoRA(2025, 2505.02795) · Offsite-Tuning(2023, 2302.04870: 데이터 쪽은 모델 전체가 필요 없다) · 메모리 효율 분할 연합 LLM 미세조정(2025, 2506.02940).</p>
  </div>
</div>

<h2>2. 어떻게 쟀나</h2>
<ul>
  <li><strong>기기</strong> = KOREN VM1 (8 vCPU, 31 GB, torch CPU fp32). <strong>서버</strong> = HPC (V100 16 GB; 7B 서버 몫은 GPU 에 안 들어가 CPU 158 GB).</li>
  <li><strong>사다리</strong>: Qwen2.5 0.5B / 1.5B / 3B / 7B (층 24/28/36/28, 은닉 896~3584), DiT/2 S / B / L / XL (층 12~28, 은닉 384~1152). 절단 k = 2, LoRA rank 16(attn + MLP 전체), 배치 4, 길이 256(DiT 는 토큰 256).</li>
  <li><strong>비용은 가중치 값과 무관</strong>하므로 사다리는 랜덤 초기화(from_config)로 잰다 — 내려받기 없이. 설정마다 별도 프로세스, 최대 상주 메모리(ru_maxrss)와 스텝 시간(3스텝 중 뒤 2 중앙값).</li>
  <li><strong>실제 분할 학습</strong>은 사전학습 가중치로: 기기(VM1)와 서버(HPC)를 역터널로 잇고 도메인 B 코퍼스(data/lora)로 학습. 기기는 앞 2층이 든 조각(shard)만 내려받는다.</li>
  <li>사전등록: <code>docs/02_실험/실험_대형모델_분할LoRA_사전등록_2026-09-13.md</code>. 코드: <code>sfl/experiments/run_scale_lora.py</code>, 배치 <code>scripts/exp/run_scale_lora.sh</code>.</li>
</ul>

<h2>3. 결과 ① 기기 쪽 비용 사다리</h2>
<figure><img src="{img(os.path.join(ROOT,'out','reports','scale_lora_0913.png'))}" alt="기기 메모리·스텝 시간·비율 — LLM 과 DiT 사다리">
<figcaption>왼쪽 두 열은 절대값(회색 = 로컬 LoRA, 파랑 = 분할 LoRA 기기 몫), 오른쪽은 비율. 7B 로컬은 31 GB 기기에서 메모리 부족으로 올라가지 않았다.</figcaption></figure>
<div class="tbl"><table>
<thead><tr><th rowspan="2">모델</th><th rowspan="2">층 / 은닉</th><th colspan="2" class="grp grp-local">로컬 LoRA (모델 전체가 기기에)</th><th colspan="2" class="grp grp-split">분할 LoRA (기기: 임베딩 + 앞 2층)</th><th colspan="2" class="grp">비율 분할÷로컬</th><th rowspan="2">절단면 왕복 / 스텝</th></tr>
<tr><th class="grp-local">최대 메모리</th><th class="grp-local">스텝</th><th class="grp-split">최대 메모리</th><th class="grp-split">스텝</th><th>메모리</th><th>시간</th></tr></thead>
<tbody>
{ladder_rows()}
</tbody></table></div>
<p>LLM 은 0.19 → 0.17 → 0.14, 디퓨전은 0.53 → 0.37 → 0.18 → 0.14 로 <strong>모델이 클수록 기기 몫 비율이 단조 감소</strong>한다(사전등록 판정 ①·②·⑤). 작은 DiT-S 에서 비율이 0.5 인 것은 모델보다 파이썬·토치 자체의 상주 메모리(≈0.5 GB)가 커서다 — 모델이 커질수록 이 고정비가 묻힌다. 같은 기계(HPC CPU, 158 GB)에서 7B 로컬을 억지로 올리면 54 GB · 35 s/스텝, 분할 기기 몫은 6.6 GB · 2.5 s 로 <strong>비율 0.12 · 0.07</strong> 이다.</p>
<div class="note">절단면 왕복은 은닉 d 에 비례해 7B 에서 29 MB/스텝이다. 회선이 느리면 이것이 병목이 된다 — 우리 3층 스케줄러가 다루는 바로 그 문제(경로·폭 조절)가 여기서도 그대로 필요하다.</div>

<h3>서버 몫 (층 3~L + 출력층)</h3>
<div class="tbl"><table><thead><tr><th>모델</th><th>장치</th><th>가중치</th><th>최대 메모리</th><th>스텝</th></tr></thead><tbody>
{server_rows()}
</tbody></table></div>
<p>서버 쪽은 3B 까지 V100 한 장(fp16)에 들어가고, 7B 서버 몫은 fp32 로 49 GB 라 CPU 로 돌렸다(21.7 s/스텝). 기기 몫은 7B 도 6.4 GB — 즉 <em>큰 것은 서버로 몰리고 기기는 얇게 남는다.</em></p>

<h2>4. 결과 ② 실제 분할 학습 (VM1 기기 ↔ HPC 서버)</h2>
<figure><img src="{img(os.path.join(ROOT,'out','reports','scale_lora_0913_loss.png'))}" alt="네 모델의 스텝별 손실">
<figcaption>사전학습 가중치 + 도메인 B 코퍼스(data/lora, 51항목)로 LoRA 학습. 왼쪽부터 DiT-XL(난수 잠재 벡터), Qwen2.5 0.5B, 3B, 7B.</figcaption></figure>
<div class="tbl"><table><thead><tr><th>모델</th><th>서버</th><th>스텝</th><th>손실 처음 1/5 → 마지막 1/5</th><th>기기 스텝 시간</th><th>왕복 / 스텝</th><th>기기 최대 메모리</th></tr></thead><tbody>
{e2e_rows()}
</tbody></table></div>
<p>네 건 모두 손실이 내려갔다(판정 ④). 7B 도 기기는 7.9 GB(적재 중 조각 4 GB 가 잠깐 겹친 값; 학습 중 상주는 6.4 GB)로 스텝 6.8 s 에 돌았다 — 같은 기기에서 로컬 LoRA 는 올라가지도 않던 모델이다. DiT-XL 은 실측 잠재 벡터가 아니라 난수 잠재로 돌려 손실 하강 폭이 작다(0.70 → 0.59); 분할 배선의 동작 확인용이고, 화질 평가는 아니다.</p>

<h3>기기가 내려받는 양</h3>
<div class="tbl"><table><thead><tr><th>모델</th><th>전체 가중치</th><th>기기가 받은 조각</th><th>비율</th></tr></thead><tbody>
{dl_rows}
</tbody></table></div>
<p>기기는 앞 2층이 든 조각만 받는다. 7B 는 15 GB 중 3.9 GB. 조각 단위라 3B 처럼 첫 조각이 큰 경우 이득이 작다 — 텐서 단위(HTTP 범위 요청)로 받으면 7B 기기 몫은 약 4 GB → 임베딩 2.2 GB + 2층 1.9 GB 로 더 줄일 수 있다(후속).</p>

<h2>5. 판정</h2>
<ul class="verdict">
  <li><span class="ok">성립</span> ① 기기 메모리 비 단조 감소 (LLM 0.19 → 0.14, DiT 0.53 → 0.14), 7B 로컬 불가 · 분할 가능</li>
  <li><span class="ok">성립</span> ② 스텝 시간 비 단조 감소 (LLM 0.07 → 0.05, DiT 0.19 → 0.07)</li>
  <li><span class="ok">성립</span> ③ 절단면 바이트는 깊이 무관(같은 은닉이면 동일), 어댑터 동기는 로컬의 2/L (0.5B 33.6 → 2.8 MB)</li>
  <li><span class="ok">성립</span> ④ 실제 분할 학습 손실 하강 4/4 (DiT-XL 은 난수 잠재라 약함 — 실측 잠재로 재확인이 후속)</li>
  <li><span class="ok">성립</span> ⑤ 디퓨전도 같은 방향</li>
</ul>

<h2>6. 한계와 다음</h2>
<ul>
  <li>절단면 통신은 rank 로 줄지 않는다(은닉 d 에 비례). 큰 모델일수록 회선이 중요해지고, 그래서 우리 스케줄러(경로 이동 · 폭 = rank 조절)가 이 위에 그대로 올라간다 — 다음 단계는 32대 시나리오를 LLM 판으로 한 번 돌리는 것.</li>
  <li>LLM 의 다음 토큰 라벨은 입력 자체라 라벨이 서버로 간다. 프라이버시가 목적이면 끝층도 기기에 두는 U 자형이 필요하다. 이번 실험은 자원(메모리 · 연산 · 내려받기)만 봤다.</li>
  <li>정확도(과제 성능)는 재지 않았다 — 손실 하강으로 "학습이 일어남"만 확인(9/8 결정: 정확도는 문헌 참조).</li>
  <li>GPU 서버에서 7B 를 돌리려면 8비트 적재나 GPU 두 장이 필요(V100 16 GB 한 장에는 fp16 서버 몫 13 GB + 활성값이 안 들어감).</li>
</ul>

<footer>측정 2026-09-13 09:53~10:37 (HPC ↔ KOREN VM1). 표·그림 생성: scripts/analysis/scale_lora_report.py · 이 페이지: scripts/analysis/scale_lora_page.py. 원자료 out/scale_lora/*.jsonl.</footer>
</main>
"""
out = os.path.join(ROOT, "out", "reports", "분할LoRA_크기사다리_2026-09-13.html")
io.open(out, "w", encoding="utf-8").write(html)
print(out, len(html) // 1024, "KB")
