"""Verify and publish the silent cut as the default website demonstration."""
import hashlib
import html
import json
from pathlib import Path
import shutil
import subprocess
import zipfile
import imageio_ffmpeg

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/demo_short'
SITE=ROOT/'site'
ASSETS=SITE/'assets/demo'
TARGET=OUT/'AwareNet_시연_1분52초_무음.mp4'

def main():
    ff=imageio_ffmpeg.get_ffmpeg_exe()
    checked=subprocess.run([ff,'-v','error','-i',str(TARGET),'-f','null','-'],capture_output=True,text=True)
    assert checked.returncode==0,checked.stderr
    count,seconds=imageio_ffmpeg.count_frames_and_secs(str(TARGET))
    stream=imageio_ffmpeg.read_frames(str(TARGET));metadata=next(stream);stream.close()
    assert count==112*24 and metadata['size']==(1920,1080)
    assert metadata.get('audio_codec') is None,metadata
    quality=dict(full_decode='pass',frames=count,seconds=seconds,resolution=metadata['size'],fps=metadata['fps'],
                 audio_streams=0,raw_means_verified=True,sha256=hashlib.sha256(TARGET.read_bytes()).hexdigest())
    (OUT/'quality_check.json').write_text(json.dumps(quality,indent=2),encoding='utf-8')
    for t in [15,63,88,105]:
        subprocess.run([ff,'-y','-v','error','-ss',str(t),'-i',str(TARGET),'-frames:v','1',str(OUT/'frames'/f'encoded_{t}.png')],check=True)
    note='''# AwareNet 시연 · 1분 52초 · 무음

## 구성

| 구간 | 내용 | 원자료 |
|---|---|---|
| 0:00–0:24 | CNN의 클라이언트별 학습 손실, 채널 사용률, 라운드별 집계 정확도 | 2026-09-29 로컬 X-ray 학습 기록 |
| 0:24–0:34 | 같은 공개 X-ray에 대한 학습 전·후 예측 | 저장 모델의 실제 추론 결과 |
| 0:34–0:54 | 세 부서의 LoRA 학습 손실과 앞단 어댑터 집계 | 2026-09-29 로컬 기업 시연 학습 기록 |
| 0:54–1:06 | 고객 응답 기한·외부 로그 공유 질문 | 저장 모델이 생성한 답변 원문 |
| 1:06–1:38 | KOREN 트래픽 몰림 상황의 라운드 시간과 경로·폭 변경 기록 | 과거 CIFAR-10/KOREN, seed 1, r4–23 |
| 1:38–1:52 | 네 조건의 기준 방식 대비 시간 단축 | 24개 원로그, 3시드 평균, 초기 4라운드 제외 |

영상은 실제 저장 기록을 실험 뷰어 형태로 재생합니다. 새로 촬영한 실시간 OS 화면이 아닙니다. 음성·배경음·오디오 스트림이 없습니다. 제목 슬라이드, 광고 문구, 깜빡임 효과를 사용하지 않았습니다.

화면은 실험 설정, 학습 곡선, 원로그 중심으로 구성했습니다. 중복 메뉴와 영문 제목을 줄이고 색과 글자 크기를 조정한 버전이며, 실행 자료와 비교 수치는 이전 버전과 같습니다. 채널 막대는 사용 비율을 표시합니다.

## 비교 결과

| 조건 | 기준 방식 | AwareNet | 라운드 시간 단축 |
|---|---:|---:|---:|
| 정상 | 63.2초 | 47.6초 | 24.6% |
| 트래픽 몰림 | 109.5초 | 62.9초 | 42.6% |
| 연산 지연 | 79.1초 | 47.3초 | 40.3% |
| 용량 변동 | 73.0초 | 53.5초 | 26.7% |

기준 방식은 전폭·고정 배정·연결 1개, AwareNet은 폭·경로 적응·연결 2개입니다. 연결 수 차이를 포함하는 전체 시스템 조건 비교입니다. 측정 지표는 라운드 완료 시간이며 목표 정확도 도달 시간과 구분합니다. 마지막 라운드 정확도 차이도 영상 마지막 화면에 제공합니다.

작동 화면의 KOREN 곡선은 seed 1의 실제 라운드 기록입니다. 표시한 누적 평균은 현재 화면까지의 r4 이후 평균이며, 마지막 표는 3개 시드의 전체 분석 구간 평균입니다. 경로가 동일한 행은 폭만 바뀐 경우가 있어 폭의 변경 전·후를 함께 표시합니다.

## 학습 시연 범위

CNN과 LoRA 화면은 이전 버전 영상과 같은 실제 로컬 실행 자료입니다. 공개 PneumoniaMNIST+를 세 가상 병원 클라이언트로 나눈 CNN 시연과, 가상 회사의 부서별 규정을 학습한 LoRA 시연입니다. 두 화면에 KOREN의 시간 단축을 적용하지 않습니다. 상세 학습 조건·예측·체크포인트 해시는 기존 `evidence.zip` 및 `README.md`에 있습니다.

이번 근거 묶음에는 KOREN 원로그 24개와 실행 인자 24개, 로컬 시연 기록, 추출 데이터, 출처 해시 및 영상 제작 코드를 넣었습니다. KOREN 결과를 새로 실행하거나 측정값을 보정하지 않았습니다.

## 재현

```powershell
.venv/Scripts/python.exe -X utf8 sfl/demo/video_short_data.py
.venv/Scripts/python.exe -X utf8 sfl/demo/video_short_render.py
.venv/Scripts/python.exe -X utf8 sfl/demo/video_short_package.py
```

`video_short_data.py`가 모든 비교 평균을 원로그에서 재계산해 기존 보고서 수치와 대조합니다. `video_short_package.py`는 2,688프레임 전체 디코딩, 1920×1080·24fps와 오디오 스트림 부재를 확인합니다.

영상 데이터: MedMNIST+ / Yang et al., https://zenodo.org/records/10519652 · CC BY 4.0, https://creativecommons.org/licenses/by/4.0/ . 64×64 원영상을 확대 표시했습니다. 기업 문서는 시연용으로 작성한 가상 규정입니다.
'''
    (OUT/'README.md').write_text(note,encoding='utf-8')
    ASSETS.mkdir(parents=True,exist_ok=True)
    for source,dest in [(TARGET,'demo-silent-112.mp4'),(OUT/'frames/015.png','poster-short.png'),(OUT/'README.md','README-short.md'),
                        (OUT/'quality_check.json','quality-short.json')]:
        shutil.copy2(source,ASSETS/dest)
    src=json.loads((OUT/'sources.json').read_text(encoding='utf-8'))
    with zipfile.ZipFile(ASSETS/'evidence-short.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
        for name in ['data.json','sources.json','quality_check.json','README.md','video_manifest.json']:z.write(OUT/name,name)
        for row in src['inputs']:z.write(ROOT/row['path'],'inputs/'+row['path'])
        for p in (ROOT/'sfl/demo').glob('video_short_*.py'):z.write(p,'code/'+p.name)
    data=json.loads((OUT/'data.json').read_text(encoding='utf-8'))
    buttons=''.join(f'<button type="button" data-time="{s["start"]}"><span>{s["start"]//60:02d}:{s["start"]%60:02d}</span>{html.escape(s["title"])}</button>' for s in data['chapters'])
    rows=''.join(f'<tr><th>{s["label"]}</th><td>{s["uniform"]:.1f}초</td><td>{s["widthpath"]:.1f}초</td><td>{s["reduction_pct"]:.1f}%</td></tr>' for s in data['network_summary'])
    page='''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AwareNet | 학습·시간 비교 시연</title><style>
*{box-sizing:border-box}body{margin:0;background:#f6f7f9;color:#202833;font-family:system-ui,"Malgun Gothic",sans-serif;line-height:1.7}main{max-width:1200px;margin:auto;padding:28px 24px 50px}a{color:#245fc2}h1{font-size:32px;margin:24px 0 6px}h2{font-size:23px;margin:30px 0 14px}.subtitle,.note{color:#626c7a}.note{font-size:14px}.links{display:flex;gap:24px;flex-wrap:wrap;margin:12px 0 26px}video{display:block;width:100%;background:#192029;border:1px solid #d9dee5;margin:22px 0 14px}.chapters{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}button{font:inherit;text-align:left;cursor:pointer;background:white;border:1px solid #d9dee5;padding:12px}button span{display:inline-block;min-width:58px;color:#626c7a}button:hover,button:focus-visible{background:#e9eef6;border-color:#245fc2}table{width:100%;border-collapse:collapse;background:white}th,td{border-bottom:1px solid #d9dee5;padding:12px 18px;text-align:right}th:first-child{text-align:left}td:last-child{color:#245fc2;font-weight:650}.scope{padding:18px 22px;border:1px solid #d9dee5;background:white;margin-top:24px}footer{font-size:13px;color:#626c7a;margin-top:30px}@media(max-width:700px){main{padding:20px 14px}.chapters{grid-template-columns:1fr}h1{font-size:27px}th,td{padding:8px}}
</style></head><body><main><a href="index.html">← AwareNet</a><h1>학습과 라운드 완료 시간 비교</h1><p class="subtitle">1분 52초 · 무음 · 1080p · 실제 실행 로그와 모델 출력 재생</p>
<video id="demo" controls muted playsinline preload="metadata" poster="assets/demo/poster-short.png"><source src="assets/demo/demo-silent-112.mp4" type="video/mp4"></video>
<div class="links"><a href="assets/demo/demo-silent-112.mp4" download>무음 MP4 다운로드</a><a href="assets/demo/evidence-short.zip">원로그·비교 근거·제작 코드</a><a href="assets/demo/README-short.md">실험 조건</a></div>
<div class="chapters">__BUTTONS__</div><h2>KOREN에서 측정한 라운드 시간</h2><table><thead><tr><th>조건</th><th>기준 방식</th><th>AwareNet</th><th>시간 단축</th></tr></thead><tbody>__ROWS__</tbody></table>
<p class="note">32개 논리 클라이언트 · 24라운드 × 3시드 · 초기 4라운드 제외. 기준은 전폭·고정 배정·연결 1개, AwareNet은 폭·경로 조정·연결 2개인 전체 시스템 조건 비교입니다.</p>
<div class="scope"><strong>화면에 사용한 기록</strong><p>CNN과 LoRA는 로컬 GPU에서 실제 실행한 학습·추론 기록입니다. 공개 X-ray를 세 가상 병원에 나눈 영상 분류와 가상 부서별 지침을 학습한 업무 문답을 보여줍니다.</p><p>KOREN 비교는 기존 CIFAR-10 실측입니다. 작동 화면은 seed 1의 라운드 기록, 마지막 표는 3시드 평균입니다. 병원·기업 로컬 시연에 KOREN의 시간 단축 수치를 적용하지 않았습니다.</p><a href="assets/demo/evidence.zip">CNN·LoRA 학습 근거</a> · <a href="evidence.html">기존 원자료 색인</a></div>
<footer>공개 영상: <a href="https://zenodo.org/records/10519652">MedMNIST+</a> / Yang et al. · <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a> · 64×64 영상 확대 표시. 임상 검증과 구분합니다. 기업 규정은 시연용 가상 데이터입니다.</footer>
</main><script>const player=document.querySelector('video');document.querySelectorAll('[data-time]').forEach(b=>b.addEventListener('click',()=>{player.currentTime=Number(b.dataset.time);player.play();player.scrollIntoView({behavior:'smooth',block:'center'});}));</script></body></html>'''.replace('__BUTTONS__',buttons).replace('__ROWS__',rows)
    page=page.replace('#f6f7f9','#fafaf9').replace('#202833','#303332').replace('#245fc2','#486777')
    page=page.replace('#626c7a','#6b706f').replace('#d9dee5','#dddfdc').replace('#e9eef6','#f0f1ee')
    page=page.replace('h1{font-size:32px;','h1{font-size:29px;font-weight:500;')
    page=page.replace('h2{font-size:23px;','h2{font-size:22px;font-weight:500;')
    page=page.replace('td:last-child{color:#486777;font-weight:650}','td:last-child{color:#303332}')
    version=quality['sha256'][:12]
    for name in ['demo-silent-112.mp4','poster-short.png','evidence-short.zip','README-short.md']:
        page=page.replace(f'assets/demo/{name}"',f'assets/demo/{name}?v={version}"')
    (SITE/'demo.html').write_text(page,encoding='utf-8')
    index=SITE/'index.html';content=index.read_text(encoding='utf-8')
    content=content.replace('시연 영상 보기 · 4분 15초','시연 영상 보기 · 1분 52초 · 무음')
    content=content.replace('href="assets/demo/training-demo.mp4" download','href="assets/demo/demo-silent-112.mp4" download')
    content=content.replace('공개 X-ray로 CNN을, 가상 부서별 지침으로 LoRA를 실제 학습했습니다. 클라이언트별 학습과 연합 집계, 같은 입력에 대한 예측을 순서대로 보여줍니다.',
       'CNN·LoRA의 실제 학습 로그와 예측 화면을 보여준 뒤, 기존 KOREN 실측에서 기준 방식과 AwareNet의 라운드 시간을 비교합니다.')
    index.write_text(content,encoding='utf-8')
    print(json.dumps(quality),flush=True)

if __name__=='__main__':main()
