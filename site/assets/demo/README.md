# AwareNet 병원·기업 활용 시연

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
