"""Package the finished video, evidence and a small accessible static player page."""
import hashlib
import html
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/healthcare_enterprise_demo"
SITE = ROOT / "site"

def read(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))

def main():
    scenes=read('timeline.json')
    cnn=read('cnn_verified_metrics.json')
    lora=read('enterprise_inference.json')
    files=[p for p in OUT.iterdir() if p.suffix in ['.json','.npz','.pt'] and p.name!='evidence_manifest.json']
    manifest={str(p.relative_to(OUT)):dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files}
    for name in ['video_train_cnn.py','video_train_enterprise.py','video_prepare_evidence.py','video_storyboard.py','video_render.py','video_narrate.ps1','video_package.py','video_quality_check.py','video_verify_lora.py']:
        p=ROOT/'sfl/demo'/name
        manifest[str(p.relative_to(ROOT))]=dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    for name in ['sfl/models.py','sfl/models_llm.py','sfl/experiments/run_scale_lora.py','sfl/experiments/run_l1.py','sfl/experiments/fed_split_eval.py','sfl/eval_grid.py']:
        p=ROOT/name
        manifest[name]=dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    (OUT/'evidence_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    readme='''# AwareNet 병원·기업 활용 시연

## 영상

- `AwareNet_병원_기업_시연.mp4`: 약 4분 15초, 1920×1080, 24fps, H.264/AAC, 한국어 내레이션·자막.
- `AwareNet_병원_기업_시연.srt`: 별도 자막. 본 영상에는 자막이 이미 포함되어 있습니다.
- 모든 곡선과 예측 문장은 실제 실행에서 저장한 결과입니다. 화면은 그 기록을 재생합니다.

## 병원 사례: 실제 공개 X-ray로 학습

PneumoniaMNIST+ 64×64 공개 영상을 가상 병원 A/B/C의 세 논리 클라이언트로 나눴습니다. 실제 다기관 병원 실험이 아닙니다.

- 원래 학습 세트 4,708장, 시험 세트 624장 유지. 학습 영상만 1,570/1,570/1,568장으로 분할.
- 저장소 ResNet-18, cut 2, GroupNorm, 채널 비율 0.5/0.75/1.0, FedRolex 방식의 순환 채널 선택.
- 20라운드, 클라이언트당 라운드마다 12배치, 배치 16, Adam 0.0006, 시드 41. 배치 내 두 클래스를 같은 수로 표집.
- 이번 시연에서는 클라이언트별 채널 비율을 고정하고 선택 채널의 위치를 바꿉니다. AwareNet 경로 최적화의 새 성능 실험이 아닙니다.
- 학습 전 정확도 62.5% → 집계 후 87.0192%(543/624). 오분류 81장.
- 폐렴 재현율 92.5641%, 정상 특이도 77.7778%. 초기 모델은 모든 시험 영상을 폐렴으로 분류했습니다.
- 최종 체크포인트를 새로 불러온 추론에서 624개의 예측 라벨이 저장 결과와 전부 일치했습니다.
- 화면 사례는 고정 시험 순서에서 조건에 맞는 첫 사례로 선택했습니다. 전체 결과는 `cnn_predictions.npz`에 있습니다.
- 임상 진단·다기관 일반화 성능을 검증한 결과가 아닙니다.

## 기업 사례: 업무 규정으로 실제 LoRA 학습

가상 회사 ‘네오링크’의 운영·고객지원·보안 규정 9개를 시연용으로 작성했습니다. 실제 기업 문서나 기밀을 사용하지 않았습니다.

- 각 부서 3개 규정, 규정별 질문 표현 6개: 총 학습 질문 54개.
- 평가 질문 18개는 같은 규정에 대한 별도 문형입니다. 평가 문장은 학습 데이터에 포함하지 않았습니다.
- Qwen/Qwen2.5-0.5B, cut 2, LoRA rank 16. 기본 가중치 동결, 앞단 어댑터 평균, 서버 뒷단 어댑터 순차 공동 갱신.
- 16라운드 × 부서별 12스텝, 배치 4, AdamW 0.0003, gradient clipping 1, 시드 73.
- 기본 모델 0/18, 운영 부서만 학습 6/18, 세 부서 연합 18/18.
- 생성 결과에 규정의 전체 답변이 포함되는지 확인했습니다. 숫자 하나만 맞는 방식으로 판정하지 않았습니다.
- 단독/연합은 부서별 학습 스텝이 같고, 전체 학습량은 연합이 세 배입니다. 일반 업무 벤치마크나 같은 총 연산량 비교가 아닙니다.
- 문서 검색(RAG), 접근권한, 최신 규정 동기화는 이번 구현 범위에 포함하지 않았습니다.
- 원문 규정, 학습/평가 질문, 총 54개 실제 생성 답변을 JSON으로 제공합니다.

## 실행 범위와 KOREN 자료

두 시연은 한 대의 RTX 3080에서 논리 클라이언트를 순차 실행했습니다. 앞단 활성값을 detach하여 뒷단 계산을 수행하고, 절단면 기울기를 앞단에 전달한 실제 학습입니다. 통신 전달은 프로세스 안에서 재현했으며 새 KOREN 실험, 병원망 배치, 실제 TCP 전송 측정으로 표시하지 않습니다. 별도 KOREN 실측은 기존 홈페이지 원자료 색인 E1/E7 및 전송 측정 묶음을 참고하세요.

## 재현

프로젝트 루트의 Python 가상환경에서 실행합니다. torch 2.6.0+cu124, torchvision 0.21.0+cu124, transformers 4.56.2, safetensors 0.8.0, imageio-ffmpeg 0.6.0, Pillow, NumPy를 사용했습니다.

```powershell
.venv/Scripts/python.exe -X utf8 sfl/demo/video_train_cnn.py
# 최초 Qwen 다운로드만 온라인으로 실행; 모델은 data/huggingface_demo에 보관
.venv/Scripts/python.exe -X utf8 sfl/demo/video_verify_lora.py --download
.venv/Scripts/python.exe -X utf8 sfl/demo/video_train_enterprise.py
.venv/Scripts/python.exe -X utf8 sfl/demo/video_prepare_evidence.py
.venv/Scripts/python.exe -X utf8 sfl/demo/video_storyboard.py
& sfl/demo/video_narrate.ps1
.venv/Scripts/python.exe -X utf8 sfl/demo/video_render.py
.venv/Scripts/python.exe -X utf8 sfl/demo/video_package.py
```

음성 합성에는 Windows의 Microsoft Heami Desktop이 필요합니다. GPU 연산의 결정성을 강제하지 않아 재실행 수치는 조금 달라질 수 있습니다. 대용량 체크포인트는 로컬 결과 폴더에 보존하고, 홈페이지 근거 ZIP에는 로그·예측·코드·해시를 넣었습니다.

## 출처와 이용 조건

- MedMNIST+: https://zenodo.org/records/10519652
- Yang et al., MedMNIST v2, Scientific Data (2023): https://doi.org/10.1038/s41597-022-01721-8
- 공식 데이터 정보: https://github.com/MedMNIST/MedMNIST/blob/main/medmnist/info.py
- PneumoniaMNIST 라이선스: CC BY 4.0, https://creativecommons.org/licenses/by/4.0/
- 영상 표시 시 64×64 원본을 확대했고 모델 입력에서 흑백 채널을 RGB 세 채널로 복제했습니다.
- 기본 언어모델: https://huggingface.co/Qwen/Qwen2.5-0.5B
- 기업 규정·질문: 본 시연을 위해 작성한 가상 데이터.
'''
    (OUT/'README.md').write_text(readme,encoding='utf-8')
    dest=SITE/'assets/demo';dest.mkdir(parents=True,exist_ok=True)
    shutil.copy2(OUT/'AwareNet_병원_기업_시연.mp4',dest/'training-demo.mp4')
    shutil.copy2(OUT/'AwareNet_병원_기업_시연.srt',dest/'training-demo.srt')
    shutil.copy2(OUT/'frames/01_intro.png',dest/'poster.png')
    shutil.copy2(OUT/'README.md',dest/'README.md')
    shutil.copy2(OUT/'evidence_manifest.json',dest/'manifest.json')
    with zipfile.ZipFile(dest/'evidence.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
        for p in OUT.iterdir():
            if p.suffix in ['.json','.npz','.srt','.md']:
                z.write(p,p.name)
        for p in (ROOT/'sfl/demo').glob('video_*'):
            if p.suffix in ['.py','.ps1']:
                z.write(p,'code/'+p.name)
    buttons=''.join(f'<button type="button" data-time="{s["start"]:.3f}"><span>{int(s["start"])//60:02d}:{int(s["start"])%60:02d}</span>{html.escape(s["title"])}</button>' for s in scenes)
    page='''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AwareNet | 병원·기업 실제 학습 시연</title>
<style>*{box-sizing:border-box}body{margin:0;color:#14243d;background:#f3f6fa;font-family:system-ui,"Malgun Gothic",sans-serif;line-height:1.7}main{max-width:1200px;margin:auto;padding:36px 24px 64px}a{color:#255bb5}h1{font-size:clamp(26px,4vw,42px);line-height:1.25;margin:22px 0 14px}.lead{max-width:860px;color:#53647a;font-size:18px}video{display:block;width:100%;background:#14243d;border-radius:14px;margin:24px 0 16px}.actions{display:flex;gap:22px;flex-wrap:wrap}.grid{display:grid;grid-template-columns:1fr 1fr;gap:22px;margin:32px 0}.card{background:white;border:1px solid #dce4ee;border-radius:14px;padding:24px}.card h2{margin-top:0}b.metric{font-size:34px;color:#078e85;display:block}.note{font-size:14px;color:#63738a}.chapters{display:grid;grid-template-columns:1fr 1fr;gap:10px}button{font:inherit;text-align:left;background:white;border:1px solid #dce4ee;border-radius:8px;padding:12px;cursor:pointer}button span{display:inline-block;min-width:60px;color:#078e85;font-weight:700}button:hover,button:focus-visible{border-color:#306bdd;background:#eaf0fc}footer{margin-top:36px;color:#63738a;font-size:14px}@media(max-width:750px){.grid,.chapters{grid-template-columns:1fr}main{padding:24px 16px}}</style></head><body><main>
<a href="index.html">← AwareNet 소개</a><h1>병원 영상 분류와 기업 업무 문답</h1><p class="lead">CNN과 LoRA를 실제로 학습한 뒤, 클라이언트의 학습 결과를 집계하고 같은 입력으로 예측을 비교했습니다. 약 4분 15초 · 1080p · 한국어 내레이션·자막.</p>
<video id="demo" controls preload="metadata" poster="assets/demo/poster.png" playsinline><source src="assets/demo/training-demo.mp4" type="video/mp4">브라우저에서 영상이 재생되지 않으면 MP4를 내려받으세요.</video>
<div class="actions"><a href="assets/demo/training-demo.mp4" download>MP4 다운로드</a><a href="assets/demo/training-demo.srt" download>자막 SRT</a><a href="assets/demo/evidence.zip">실험 로그·예측·재현 코드</a><a href="assets/demo/README.md">실험 조건·출처</a></div>
<div class="grid"><section class="card"><h2>CNN · 흉부 X-ray 공동학습</h2><b class="metric">62.5% → 87.0%</b><p>공개 시험 영상 624장에 대한 분류 정확도입니다. 서로 다른 채널 수를 쓰는 세 논리 클라이언트가 20라운드 학습했습니다. 오분류 81장도 함께 제시합니다.</p><p class="note">PneumoniaMNIST+ · 가상 병원 분할 · 단일 GPU 실행 · 임상 검증 아님</p></section><section class="card"><h2>LoRA · 부서별 업무 지침</h2><b class="metric">0/18 → 6/18 → 18/18</b><p>기본 모델, 운영 부서만 학습한 모델, 운영·고객지원·보안을 함께 학습한 모델의 순서입니다. 장애 보고, 고객 응답 기한, 로그 공유 규정을 직접 질문합니다.</p><p class="note">가상 회사의 규정 9개 · 학습과 다른 질문 표현 18개 · 일반 업무 벤치마크 아님</p></section></div>
<h2>장면 바로 보기</h2><div class="chapters">__BUTTONS__</div>
<section class="card" style="margin-top:28px"><h2>이번 영상의 실행 범위</h2><p>모든 학습·추론 수치는 로컬 RTX 3080에서 새로 실행한 결과입니다. 영상은 저장된 실제 로그와 모델 출력을 재생합니다. 앞단·뒷단 학습과 연합 집계를 수행했고, 네트워크 전달은 프로세스 안에서 재현했습니다.</p><p>기존 KOREN의 폭·경로 스케줄링 실험은 <a href="evidence.html">원자료 색인</a>에서 확인할 수 있습니다. 이번 병원·기업 활용 시연에 KOREN의 시간 단축 수치를 적용하지 않았습니다.</p></section>
<footer>영상 데이터: <a href="https://zenodo.org/records/10519652">MedMNIST+</a> / Yang et al. · <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>. 원영상 확대 표시. 언어모델: Qwen2.5-0.5B. 기업 문서는 시연용 가상 지침입니다.</footer>
</main><script>const video=document.getElementById('demo');document.querySelectorAll('[data-time]').forEach(button=>button.addEventListener('click',()=>{video.currentTime=Number(button.dataset.time);video.play();video.scrollIntoView({behavior:'smooth',block:'center'});}));</script></body></html>'''.replace('__BUTTONS__',buttons)
    (SITE/'demo.html').write_text(page,encoding='utf-8')
    index=SITE/'index.html'
    content=index.read_text(encoding='utf-8')
    if 'id="learning-demo"' not in content:
        content=content.replace('<section id="resources">','''<section id="learning-demo"><div class="section-title"><span class="section-id">DEMO</span><h2>병원·기업 활용 시연 영상</h2></div><p>공개 X-ray로 CNN을, 가상 부서별 지침으로 LoRA를 실제 학습했습니다. 클라이언트별 학습과 연합 집계, 같은 입력에 대한 예측을 순서대로 보여줍니다.</p><div class="links"><a class="button" href="demo.html">시연 영상 보기 · 4분 15초</a><a href="assets/demo/training-demo.mp4" download>MP4 다운로드</a><a href="assets/demo/evidence.zip">실행 로그·예측 결과</a></div><p class="note">로컬 GPU에서 실행한 활용 시연입니다. 병원은 공개 데이터의 가상 분할이며, 기업 지침은 시연용으로 작성했습니다.</p></section><section id="resources">''')
    index.write_text(content,encoding='utf-8')
    print('Packaged',dest,flush=True)

if __name__=='__main__':main()
