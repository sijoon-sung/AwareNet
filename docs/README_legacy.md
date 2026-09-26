<!-- Historical development and operation guide; current summary is ../README.md. -->
# AwareNet — 폭과 네트워크를 결합한 분할 연합학습 시스템

> **정적 소개 홈페이지:** [`site/index.html`](../site/index.html). 아키텍처·결합 수식·KOREN/Jetson/LoRA 근거·구현 한계·계측 결과를 한 페이지로 연결한다. GitHub Pages 배포 워크플로를 포함했다. [게시 구조 안내](../site/PUBLISHING.md)
>
> **추가 통합 계측 실험:** [실험 보고서](../site/assets/lab/report.html) · [조건·결과 JSON](../site/assets/lab/summary.json) · [Wireshark PCAP](../site/assets/lab/capture.pcapng) · [재현 방법](../observability/README.md). 실제 Linux 가상망에서 18라운드·본 전송 144개를 완료했다. 경로 감소 조건의 프로브 포함 시간은 고정 두 경로보다 38.6% 짧았으나, 공유 병목에서는 단일 경로보다 11.5% 길었다. 한 번의 가상 검증이며 신규 KOREN 성능·학습 정확도 결과가 아니다.

> **최신 제출 원고:** [중간보고서 양식의 서술형 보고서](../docs/01_제출발표/AwareNet_서술형보고서_2026-09-26.md) · [26쪽 PDF](../output/prose_awarenet/AwareNet_서술형보고서.pdf) · [편집·복사용 HTML](../output/prose_awarenet/AwareNet_서술형보고서.html). 요약문 3쪽, 본문·참고문헌·계측 부록 21쪽. **그림 11개·표 7개**로 구조·구현 상태·실험 조건·결과를 연결했다. [구조·실험 그림 갤러리](../output/prose_awarenet/figures.html) · [PNG/SVG 묶음](../output/prose_awarenet/AwareNet_구조도_조건그림.zip) · [양식·브랜치·신규성 검토 근거](../docs/03_리서치/서술형보고서_신규성및출처검토_2026-09-26.md)

> **시각 자료 보조본:** [폭·네트워크 결합 모델과 하드웨어 검증](../docs/01_제출발표/AwareNet_통합보고서_2026-09-26.md) · [10쪽 PDF](../output/final_awarenet/AwareNet_종합보고서.pdf) · [도식·차트 9종 갤러리](../output/final_awarenet/index.html) · [PNG/SVG 묶음](../output/final_awarenet/AwareNet_이미지팩.zip). 원자료 39개를 추적하며 실제 실험과 주입 재현의 범위를 구분한다.

> **핵심 관점:** 폭은 계산량·전송 바이트를, 경로는 공유 자원 아래의 실효 전송률을 바꾼다. 공통 완료 시간과 폭 보존의 대가를 모델링해 상호 보완한다. 기존 `widthpath` 결합 시스템을 중심으로, `network`는 폭을 고정한 경로 대조군으로 설명한다. [추가 후보 판정·남은 항목](../docs/01_제출발표/기여_판정과_최종정리_2026-09-26.md)

> **기관 경계·실제 네트워크 집행 정정:** 기기·엣지·서버의 관리 권한은 각각 확인한다. 현행 tc/IFB/HTB, 과거 OVS/VXLAN·ACK 우선 큐, TCP 연결·응용 신뢰성 개선을 [구현 감사 §8](../docs/04_설계기록/네트워크중심_아키텍처_및_경로주장_2026-09-22.md)에 연결했다. 커널 TCP 알고리즘 수정이나 기관 간 위임 실증으로 확대하지 않는다. 패킷·조각·라운드별 고정/적응 제어 및 AI 판단 시간의 분석 예시는 보고서 PDF 13~14쪽에 있다.

> **9/23 실측값 주입:** 다른 브랜치 이력의 젯슨 원시 90스텝과 KOREN 전송 기록을 복구했다. [실측 주입 재현 보고서](../docs/02_실험/실측주입_재현실험_2026-09-23.md) — 원본 출처·변환 가정·480개 모형 사례·15회 로컬 TCP 결과. 대표 조건 약 10% 단축은 실측값을 넣은 재현 결과이며 신규 KOREN 학습 성능이 아니다.

> **핵심 기여 재검토:** [설계→실험 4차 반복 기록](../docs/04_설계기록/핵심기여_설계실험_반복검토_2026-09-22.md). 준비된 기울기의 반환 순서와 이후 기기 계산을 함께 검토했다. 로컬 큐 실험의 이득은 도착 시각에 따라 사라질 수 있어, 새 제어는 연구 후보로 두고 런타임에는 관측을 추가했다. KOREN 성능이나 신규성 확정 주장이 아니다.

> **네트워크 효과 분리 검증(2026-09-22):** 같은 모델·학습량에서 혼잡한 경유 구간을 피해 activation/gradient의 완료 지연을 줄일 수 있는지 검증한다.
> 폭 선택은 학습 모듈의 입력으로 두고, 공유 업링크·허용 종점·전환 비용을 고려하는 `--policy network`를 추가했다.
> 기기–엣지 전체 망의 SDN 권한을 가정하지 않는다. [경로 주장·아키텍처·선전송 검토](../docs/04_설계기록/네트워크중심_아키텍처_및_경로주장_2026-09-22.md)

> 기준 브랜치: **awarenet**. 기존 고정 분할점의 폭·경로·분할 전송 실험은 HPC↔KOREN VM 2대, 논리 엣지 4개에서 수행했다. 8~32는 실행별 논리 참여자 수다.
> `network`는 로컬 학습 라운드·소켓·기울기 검사를 통과했으며 새 KOREN 성능은 실측 전이다. `device-budget`은 폭 정책 비교용, SuperSFL 가변 깊이와 OS-Ken/OVS는 후속 프로토타입이다.
> K-디지털 챌린지 넷챌린지 캠프 시즌13 · 팀 AwareNet (충남대학교) · [문서 길잡이](../docs/INDEX.md)

## 기존 실측 결과와 해석 범위

| 32개 논리 참여자, 3시드 | 기존 기준선 → 결합 시스템의 평균 라운드 |
|---|---:|
| 정상 | 63.19 → 47.64초 (24.6% 감소) |
| 트래픽 몰림 | 109.51 → 62.87초 (42.6% 감소) |
| 연산 느림 | 79.12 → 47.26초 (40.3% 감소) |
| 용량 변동 | 72.97 → 53.48초 (26.7% 감소) |

각 실행 앞 4라운드를 제외한 평균을 3시드 평균했다. 출구 수·폭·경로가 함께 바뀐 시스템 비교이므로 순수 계획기 효과나 같은 정확도까지의 단축으로 해석하지 않는다. 새 정책의 수치도 아니다. [원자료·재계산·비판 검토](../docs/01_제출발표/기존성과_근거보고서_및_비판검토_2026-09-19.md)

## 처음 왔다면

| 무엇이 궁금한가 | 여는 문서 |
|---|---|
| 전체 결론·결합 수식·하드웨어와 LoRA 실험 | [9/26 확정 종합 보고서](../docs/01_제출발표/AwareNet_통합보고서_2026-09-26.md) — 10쪽 PDF·발표용 그림·원자료 연결 |
| 최종적으로 무엇을 제안·주장할 것인가 | [9/26 기여 판정과 최종 정리](../docs/01_제출발표/기여_판정과_최종정리_2026-09-26.md) — 추가 후보 채택 조건·제어 범위·증거·제출용 요약 |
| 지금 풀 문제와 구현 변경 | [네트워크 중심 아키텍처](../docs/04_설계기록/네트워크중심_아키텍처_및_경로주장_2026-09-22.md) — 경로 주장·공유 병목·선전송·PyTorch 환경·검증 |
| 폭 제어 대조군 | [기기 연산 예산 정책](../docs/04_설계기록/문제정의_기기연산예산_SFL_2026-09-22.md) |
| 기존 성과가 어디까지 입증됐나 | [기존 근거보고서](../docs/01_제출발표/기존성과_근거보고서_및_비판검토_2026-09-19.md) — KOREN·축소 실험·한계 |
| 코드가 어떻게 생겼나 | [`sfl/ARCHITECTURE.md`](../sfl/ARCHITECTURE.md) — 3층 지도 + "이 일은 이 파일" |
| 실험 조건·근거·판정을 한 장에 | [`docs/02_실험/한장_조건과_리서치_2026-09-09.md`](../docs/02_실험/한장_조건과_리서치_2026-09-09.md) |
| 무엇이 잘못됐고 어떻게 고쳤나 | [`docs/04_설계기록/문제와_해결_2026-09.md`](../docs/04_설계기록/문제와_해결_2026-09.md) — 코드 결함 14건 + 조건 오류 |
| 왜 이런 규칙인가 | [`docs/04_설계기록/설계기록_컨트롤러.md`](../docs/04_설계기록/설계기록_컨트롤러.md) §12 결합 최적화, §13 인지층 |
| 후속 가변 깊이 후보 | [SuperSFL 결합 초안](../docs/04_설계기록/SuperSFL_AwareNet_결합알고리즘.md) — 현재 우선순위에서 보류 |

전 문서 목차: [`docs/INDEX.md`](../docs/INDEX.md).

## 폴더 구성

```
sfl/                 본체 (→ sfl/ARCHITECTURE.md)
  sense.py             인지: 기기 연산·바이트·접속 실측, 라운드 관측, 엣지 용량 추정
  plan.py              계획: 물 채우기 → 경로 단계(총합 + N·max) → 결합 최적화 폭 (순수 함수)
  network_control.py   네트워크 정책: 고정 학습 요구 → 공유 자원 제약 → 종점 배정 → 완료 보고
  barrier_schedule.py  연구 후보: 준비된 기울기 순서·이후 계산 범위·개입 보류 검사 (런타임 미연결)
  device_budget.py     폭 정책 대조군: 연산 예산 내 최대 폭 → 허용 종점 배정
  policies.py          라운드 정책 레지스트리 (uniform / widthpath = 3층 스케줄러)
  fed_server.py / fed_client.py   서버·기기 (라운드, 계측, 사전 진단, 즉시 내보내기)
  mpsend.py, chunker.py, proto.py  분할 전송(출구 2개 조각 왕복)과 소켓 규약
  models*.py           CNN 분할 모델(폭 슬라이스·중첩 평균) / ViT / 언어모델+LoRA
  fluidsim.py          유체 시뮬레이터 (3층 시뮬, 100대)
  supersfl_net.py       후속 후보: 동적 분할 깊이 × 회선 경로 계획, 학습 런타임 미연결
  sdn/                 보유 엣지 OVS용 OS-Ken OpenFlow 1.3 집행기 (미배포)
  net/                 리그: real_rig.sh(실회선, 역터널 4개 + tc 2층) · hairpin_lo.sh(루프백) · paths/hetero/perturb
  demo/                실증 플랫폼: run_demo_real.py(:8778 라이브·교란·재생) · platform_index.html · LoRA 삼면비교(demo_server.py :8777)
  experiments/, baselines/   8월 실험 러너와 비교 기법 (이력)
tests/               단위시험 — bash scripts/run_tests.sh fast
scripts/
  exp/                 실험 드라이버 (→ scripts/exp/README.md, 조건 원장 conditions.json + cond.py)
  measurement/         회선·리그 측정 (line_scale*, real_selftest, rig_selftest, hpc_vm_link)
  analysis/            표·시각화·재생 (scen32_report/viz, combo_table, replay_plan, trace_sense, report_html_0910)
  figs/, build/        그림·발표자료, 데이터셋 준비
docs/                문서 6 폴더 (→ docs/INDEX.md)
out/                 산출물 (git 제외) — 실험 로그 jsonl · reports/ HTML·PDF
deploy/remote/       원격(HPC·VM) 배포 키트
_archive/, scripts/old/, docs/old/   지난 판 (git 제외, 로컬 기록)
```

## 자주 하는 일

Windows 로컬에는 `.venv`에 PyTorch 2.6.0+cu124 / torchvision 0.21.0+cu124를 설치했고 RTX 3080 CUDA 실행을 확인했다. 현재 SFL 의존성은 `requirements-sfl.txt`다.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_network_control tests.test_micro_e2e tests.test_network_runtime tests.test_aggregate_width_sync
```

```bash
# 빠른 검증 (컴파일 전수 + 계획·조각·시뮬 시험). HPC 에서는 PY=~/env/bin/python (시스템 python3 에는 torch 가 없다)
PY=~/env/bin/python bash scripts/run_tests.sh fast
# 전체 (인지 층·서버 조각 기울기·정합 검증) — torch 필요
PY=~/env/bin/python bash scripts/run_tests.sh full

# 32대 시나리오 (HPC, 실회선 리그) — 6장면, 약 4시간
nohup bash scripts/exp/run_scen32.sh > out/scen32.log 2>&1 < /dev/null &
python scripts/analysis/scen32_report.py && python scripts/analysis/scen32_viz.py   # 표 + out/reports/scen32_시간축.html

# 실증 플랫폼 (HPC, 일반 사용자로 — root 는 VM ssh 키가 없다)
python sfl/demo/run_demo_real.py --cond demo8            # http://<HPC>:8778  (교란 버튼 = tc 실제 변경)
bash scripts/exp/verify_demo.sh > out/verify_demo.log     # 자동 검증

# 결정 재생 / 인지 추적 (로그 → 인지 → 계획 재현)
python scripts/analysis/replay_plan.py out/wp_scen32_traffic_s1_bothmp_widthpath.jsonl 9 13
python scripts/analysis/trace_sense.py out/wp_scen32_traffic_s1_bothmp_widthpath.jsonl 9 20
```

## 실험 환경

HPC(V100, 16코어; 기기 프로세스 + 서버) ↔ KOREN VM 2대(엣지 4개 = 역방향 SSH 터널 포트 묶음, BASE 12100) ↔ HPC 서버.
접속 회선 상한은 HPC egress tc(기기·출구별), 엣지 용량은 VM tc(부모 ceil + 기기별 내려받기 자식 클래스). 자가 검사: `scripts/measurement/real_selftest.py`.
조건은 `scripts/exp/conditions.json` 에 값마다 출처(실측/논문/우리선택/장비제약)와 함께 있다. 자세한 것은 `docs/02_실험/실험환경_VM_HPC.md`, `docs/04_설계기록/설계_실회선_리그.md`.

## 알려진 한계

- 폭 보존은 정확도 보장이 아니다. 같은 평가 모델의 정확도·목표 도달 시간 검증이 필요하다.
- 현재 실제 경로 집행은 종점 변경·SSH 터널·tc다. OS-Ken/OVS의 학습 런타임 연결과 KOREN 실증은 완료하지 않았다.
- 새 연산 예산은 시간 예측 기준이며 메모리/OOM·배터리·하드 실시간 보장을 제공하지 않는다.
- 기존 `xfer`에는 서버 시간·오버헤드가 포함된다. 새 모드의 차감 잔차도 순수 회선 시간은 아니다.
- 32개 논리 참여자 최종 로그는 3시드·24라운드다. 물리 장비 32대 실험, 8대 축소와 학습 수렴의 동등성을 뜻하지 않는다.
- 상세 결함과 검증 상태: [구현 검사](../docs/04_설계기록/구현범위_검사_2026-09-19.md), [9/22 변경](../docs/04_설계기록/문제정의_기기연산예산_SFL_2026-09-22.md).
