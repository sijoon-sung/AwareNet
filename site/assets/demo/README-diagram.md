# AwareNet 시연 영상 — 선 도식 구성

1분 54초 (114.28초), 1920×1080, 25 fps, 무음.
실험 기록 조회 프로그램의 화면을 처음부터 끝까지 연속 녹화했다.
MP4 코덱 변환만 수행했으며 영상 자막·전환·컷 편집을 추가하지 않았다.

## 화면 순서

- 00:00 전체 구조
- 00:10 CNN 학습
- 00:28 X-ray 추론
- 00:36 LoRA 학습
- 00:52 업무 질문
- 01:02 KOREN 활용
- 01:14 경로 제어·시간 비교
- 01:42 조건별 결과

## 자료 범위

- CNN·LoRA: 기존 로컬 GPU 학습과 추론 기록. 공개 X-ray의 가상 병원 분할, 시연용 가상 기업 규정.
- KOREN: 기존 CIFAR-10 실측. 작동 화면은 seed 1, 최종 비교는 3시드 평균.
- 기준선 1연결과 결합 정책 2연결의 전체 구성 비교이며, 병원·기업 시연의 시간 절감률로 대체하지 않는다.
- KOREN의 사설 연구 환경과 VM·HPC의 활용 가치를 설명한다. T-SDN·L2VPN은 이번 실험에 미적용인 후속 확장이다.
- 서비스 근거: NIA KOREN 이용안내서 6–9쪽, https://sanhak.duksung.ac.kr/attach/download/1826

프로그램: experiment-viewer.html, assets/demo/diagram-viewer.css, assets/demo/diagram-viewer.js.
기존 viewer-data.json과 원로그는 변경하지 않았다. 녹화·파일 정보는 final-recording.json에 수록했다.
