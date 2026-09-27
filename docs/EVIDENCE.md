# AwareNet 주장과 원자료 색인

2026-09-27 갱신. 공식 제출 본문과 홈페이지가 사용하는 근거를 연결한다.

[공개 원자료 페이지](https://sijoon-sung.github.io/AwareNet/site/evidence.html) · [전체 원장](../configs/measurements/publication_evidence_2026-09-27.json)

| ID | 자료 | 주장과 범위 |
|---|---|---|
| [E1](https://sijoon-sung.github.io/AwareNet/site/evidence.html#E1) | KOREN 시나리오: 결합 시스템의 완료 시간 | 기존 기준선과 폭·경로 결합 시스템의 조건별 평균 라운드 시간을 재집계한다. 32대 물리 기기 실험이 아니다. tc 용량 교란과 연산 지연을 주입했다. 기준선과 결합 정책의 출구 수·폭·배정이 함께 달라 순수 경로 효과 및 동일 정확도 도달 시간을 입증하지 않는다. args.alpha=1.2는 지연 기준선 배율이며, 데이터 분할은 fed_client의 alpha-dir 기본값 0.5다. 로그의 mp 필드보다 실행 인자 및 출구 기록을 우선한다. |
| [E2](https://sijoon-sung.github.io/AwareNet/site/evidence.html#E2) | Jetson: 장비 연산 프로파일 | 한 보드에서 측정한 전력 모드별 전체 학습 스텝 시간의 차이를 확인한다. KOREN 32프로세스 실행에 Jetson을 연결한 통합 실험이 아니다. 전체 LoRA 스텝 시간을 CNN 폭별 비용이나 반환 후 연산 시간으로 그대로 사용할 수 없다. 소프트웨어 버전은 환경 로그의 기록값이다. 원시 스텝·tegrastats·환경·콘솔과 측정 스크립트를 함께 제공한다. |
| [E3](https://sijoon-sung.github.io/AwareNet/site/evidence.html#E3) | KOREN 전송: 실측값 주입의 입력 | 지연 주입 재현에 사용한 실제 TCP 왕복 전송 기록을 추적한다. cap_mbps=8000은 설정값이며 물리 링크의 측정 용량이 아니다. aggregate_mbps 필드도 링크 용량으로 해석하지 않는다. 공통 측정 시간창 기반 처리율과 기기별 지연을 구분해야 한다. 이 입력의 재사용은 새로운 KOREN 실험을 의미하지 않는다. |
| [E4](https://sijoon-sung.github.io/AwareNet/site/evidence.html#E4) | LoRA: 분할 실행·집계·메모리 | 분산 배치에서 실제 학습과 어댑터 집계를 수행하고 메모리 제약을 확인했다. 소규모 자체 문답 실습이며 일반 벤치마크 또는 개인정보 보호의 입증이 아니다. 모델을 층으로 분할하는 SFL이며 특성 분할 VFL과 다르다. 앞부분 메모리 프로파일과 실제 분할 시스템 최대 메모리를 구분한다. |
| [E5](https://sijoon-sung.github.io/AwareNet/site/evidence.html#E5) | 가상 Linux 망: 커널·패킷·계측 | tc 집행, 실제 TCP 조각 전송, 재조립 및 관측을 한 실행에서 확인했다. 한 번의 로컬 가상 실행이며 라운드는 독립 반복이 아니다. 새 KOREN 측정·학습 성능이 아니다. raw tc 카운터의 포맷 문제와 정규화 기록을 보존한다. TCP 커널 알고리즘 패치는 하지 않았다. |
| [E6](https://sijoon-sung.github.io/AwareNet/site/evidence.html#E6) | 구현: 폭·경로·권한 경계 | 실제 코드로 구현 범위와 프로토타입 범위를 확인한다. 관리하거나 권한을 위임받은 호스트가 집행 대상이다. KOREN 코어 경로 제어와 기관 간 위임은 검증하지 않았다. OS-Ken 코드 존재는 실제 OVS 적용 증거가 아니다. 패킷 처리는 커널과 고정 전송 코드가 담당하고 계획은 라운드 수준에서 수행한다. |
| [E7](https://sijoon-sung.github.io/AwareNet/site/evidence.html#E7) | 축소 실험과 실측값 주입 재현 | 8프로세스 실행과 과거 측정값을 입력한 재현의 조건을 보존한다. SHRiNK를 참고한 축소 구성은 32대 물리 시스템과의 동등성을 입증하지 않는다. OOM·CPU 제약 때문에 실행 크기를 줄인 것으로, 8개와 32개의 결과를 합산하지 않는다. 주입값을 사용한 모형·로컬 결과를 하드웨어 재측정으로 표기하지 않는다. |
| [E8](https://sijoon-sung.github.io/AwareNet/site/evidence.html#E8) | 보고서 재집계: 시간·정확도·제어 동작 | 기존 실행의 시간, 폭, 응용 전송량과 정확도를 함께 재집계하고 본문 그림으로 연결한다. λ=280: 시간 20.7% 단축, 정확도 65.52%→65.22%. λ=70: 32.5% 단축, 63.17%. λ=18: 58.1% 단축, 53.59%. 모든 비교는 단일 출구 기준선과 두 출구 AwareNet의 구성 비교다. 정확도 평가는 시험 데이터 앞 2,000개와 실행별 최대 학습 폭을 사용했다. 두 시드의 요약값이며 독립 반복 수를 늘리는 후속 평가가 필요하다. |
| [E9](https://sijoon-sung.github.io/AwareNet/site/evidence.html#E9) | 설계 선택의 이유: 용어·개발 과정·활용 예시 | CNN 채널 선택, 중계 경로, 단계적 제어를 택한 이유를 문헌·코드·개발 기록에 연결한다. 과거 문서는 당시의 제안·시행착오다. 현재 주장은 제출 보고서와 E1–E8을 따른다. 여러 현장의 영상 분류는 적용 시나리오이며 현장 도입 실적이 아니다. 자체 정확도 제외의 과거 이유와 현재의 탐색 결과 해석도 보존한다. |
