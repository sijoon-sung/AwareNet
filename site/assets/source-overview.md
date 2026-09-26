# AwareNet

## 자원 제약을 고려한 분할 연합학습의 폭·경로 제어

분할 연합학습은 기기의 연산을 서버로 옮기면서 매 배치의 활성값·기울기 왕복을 만든다. AwareNet은 **폭이 결정하는 계산·전송 수요와 허용 경로의 공유 처리 능력**을 같은 완료 시간 모형으로 연결한다. 관리 가능한 기기·중계 호스트를 대상으로 구현한 연구 시스템이다.

**[연구 홈페이지](https://sijoon-sung.github.io/AwareNet/) · [원자료 색인](https://sijoon-sung.github.io/AwareNet/site/evidence.html) · [보고서 PDF](site/assets/report.pdf) · [전체 문서 목차](docs/INDEX.md)**

충남대학교 AwareNet · KOREN 넷챌린지 · 자료 정리 2026-09-27

### 구현과 근거

| 항목 | 확인한 내용 | 원자료·한계 |
|---|---|---|
| 폭·경로 결합 | CNN의 폭, 허용 중계 종점, 전송 분할량 제어 | [E1](https://sijoon-sung.github.io/AwareNet/site/evidence.html#E1): KOREN의 32논리프로세스, 4조건×3시드. 출구 수도 다른 시스템 비교 |
| 기기 연산 비용 | Jetson Orin Nano Super 8GB 한 대, 3전력 모드·90스텝 | [E2](https://sijoon-sung.github.io/AwareNet/site/evidence.html#E2): 원시 스텝·환경·tegrastats·측정 코드. 별도 LoRA 프로파일 |
| 분할·집계 | VM 2대·3논리클라이언트와 HPC의 LoRA 실행 | [E4](https://sijoon-sung.github.io/AwareNet/site/evidence.html#E4): 16라운드, 자체 18문항 실습·메모리 기록 |
| 커널·전송 계측 | Linux tc/IFB/HTB, TCP 전송·재조립, TShark·Grafana | [E5](https://sijoon-sung.github.io/AwareNet/site/evidence.html#E5): 한 번의 Linux 가상망 실험, 144전송 해시 일치 |
| SDN 확장 | OS-Ken / OpenFlow 1.3 프로토타입 | [E6](https://sijoon-sung.github.io/AwareNet/site/evidence.html#E6): 실제 OVS·기관 간 권한 위임 미검증 |
| 축소·주입 재현 | 8프로세스 실행과 과거 실측값의 재사용 | [E7](https://sijoon-sung.github.io/AwareNet/site/evidence.html#E7): 32대 물리 시스템과 동등한 실험으로 해석하지 않음 |

### 핵심 제약

폭 보존 항은 정확도의 대리 비용이다. 동일 정확도 도달 시간, 같은 출구 수를 유지한 네트워크 효과 분리, 현장 반복 검증은 남아 있다. 경로는 허용된 중계 종점으로의 논리 연결이며 KOREN 코어 라우팅의 제어를 뜻하지 않는다. 커널 작업은 Linux의 트래픽 제어 기능을 집행한 것이며 TCP slow start·혼잡 제어 코드 패치는 아니다.

### 확인·실행

원자료의 해시 및 대표 통계를 Python 표준 라이브러리로 검산한다.

```sh
python site/assets/evidence/verify_evidence.py
```

홈페이지는 빌드나 JavaScript 의존성이 없는 정적 파일이다.

```sh
python -m http.server 8000 --directory site
```

네트워크 실험은 관리 권한이 있는 Linux 호스트가 필요하다. [통합 계측소 실행 안내](observability/README.md), [코드 지도](sfl/ARCHITECTURE.md), [기존 실행 안내](docs/README_legacy.md)를 참고한다. 기록 재검산은 새 학습·실망 실험을 수행하지 않는다.

### 자료 구조

- `site/`: 연구 개요, E1-E7 원자료 색인, 보고서와 계측 기록
- `sfl/`: 폭·경로 계획, 전송·재조립, 분할 학습 및 SDN 확장
- `scripts/`: 실험·분석·계측·공개 자료 생성
- `configs/measurements/`: 출처·해시·구현 감사 원장
- `docs/`: 제출 원고, 실험 기록, 설계 과정과 연구 비교
- `output/prose_awarenet/`: 27쪽 제출 보고서, 그림 11개·표 7개

이 공개 저장소는 비공개 개발 저장소의 `awarenet` 최종 작업본을 별도 스냅샷으로 게시한다. 개발 브랜치나 이전 Git 이력은 포함하지 않는다. 옛 커밋 식별자는 측정 자료의 복구 출처이며 공개 이력에서 바로 조회되지 않을 수 있다. 필요한 원파일은 [출처 원장](configs/measurements/publication_evidence_2026-09-27.json)에 따라 함께 제공한다.
