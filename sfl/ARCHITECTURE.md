# 코드 지도 (ARCHITECTURE)

> **확정 시스템 관점:** [폭·네트워크 결합 모형과 하드웨어·LoRA 검증](../docs/01_제출발표/AwareNet_통합보고서_2026-09-26.md). `plan.py`의 기존 결합 정책은 계산량과 네트워크 자원을 같은 시간 목표로 다룬다. `--policy network`는 폭을 고정해 경로 효과를 분리하는 검증 모드다. LoRA 연합 실습은 별도 실행 트랙이며 동적 경로 제어까지 통합한 실험으로 해석하지 않는다.

> **9/26 제출 범위:** [최종 기여·아키텍처·근거 정리](../docs/01_제출발표/기여_판정과_최종정리_2026-09-26.md). 현재 경유 종점 변경, 별도 전송 순서 연구 모듈, 미배포 OS-Ken 집행기의 상태를 구분한다. 조각별 제한적 재전송은 설계 후보이며 구현에 포함하지 않았다.

> 2026-09-10 정리판. 처음 보는 사람이 "어디를 열어야 하나"를 3분 안에 알게 하는 문서다.
> 규칙이 정해진 경위는 `docs/04_설계기록/설계기록_컨트롤러.md`, 잡은 결함은 `docs/04_설계기록/문제와_해결_2026-09.md`.
> **9/22 네트워크 검증 개선:** [`network_control.py`](network_control.py)와 `--policy network`는 학습 폭을 입력으로 받아 공유 병목 제약 안에서 경유 종점을 정한다. [경로 주장·변경 명세](../docs/04_설계기록/네트워크중심_아키텍처_및_경로주장_2026-09-22.md). `device-budget`은 폭 제어 대조군, 가변 깊이·OS-Ken 집행기는 후속 프로토타입이다.

## 네트워크 정책 (`--policy network`)

**9/23 실측값 주입 재현:** [`trace_replay.py`](trace_replay.py)와 `scripts/analysis/measured_replay.py`가 기존 KOREN 전송 시각·젯슨 전체 스텝 기록을 읽어 별도 시간 모형/TCP 주입 실험을 실행한다. 정규화된 원시 입력은 `configs/measurements/koren_jetson_2026-09-23.json`, 변환 가정은 `configs/measured_replay.json`이다. SFL 학습 런타임과 별도인 연구 모듈이며 [결과와 범위](../docs/02_실험/실측주입_재현실험_2026-09-23.md)를 함께 읽는다.

**기여 재검토용 프로토타입:** [`barrier_schedule.py`](barrier_schedule.py)는 준비된 기울기의 전송 순서와 이후 기기 계산을 대상으로 한다. 같은 단일 출구·닫힌 준비 집합에서만 적용되는 범위 검사이며 학습 정책 레지스트리에 연결하지 않았다. [실험과 반례](../docs/04_설계기록/핵심기여_설계실험_반복검토_2026-09-22.md).

새 관측은 `traffic.batch_compute`의 배치별 forward/backward/wait, `per_client_detail.gradient_events`의 배치 ID·서버 monotonic 준비/제출 완료 시각·바이트다. 비동기 전송에서는 제출 시각이 큐에 넣은 시각이며 wire 완료가 아니다. 클라이언트/서버 시계를 직접 비교하지 않는다.

`학습 모듈의 폭·라운드 바이트 → 공유 자원별 flow_rates → plan_routes → 종점/분할 가중치 → 기기 route_receipt → 다음 라운드 관측`.

`network_control`은 소켓·torch에 의존하지 않는다. `NetworkOnly`가 프로파일과 실행 상태를 연결한다. `--network-topology`는 논리 경로가 공유하는 업링크를 명시한다. `route_receipts`는 앱의 epoch·종점 완료 확인이며 OVS 설치 ACK가 아니다. 확인 실패 뒤에는 새 경로 계획을 중단한다.

`--micro-window`는 미회신 마이크로배치 수 상한이다. 서버가 표본 수로 가중한 기울기에 클라이언트가 다시 1/m을 곱하지 않는다. `micro>1`에서는 중첩된 시간을 경로 용량으로 해석하지 않고 경로 용량 관측을 동결한다. 기본 micro=1에서 경로 효과를 먼저 비교한다.

## 폭 정책 대조군 (`--planner device-budget`)

`last_detail의 기기 순·역전파 → ComputeTracker 갱신 → 연산 예산 내 최대 폭 → 허용 종점 배정 → dp·mpplan 지시 → 예측/실측 로그`.

`--compute-budget-s`는 기기 연산 시간 예산, `--deadline-s`는 전체 라운드 목표 진단이다. 새 모드에서 통신 지연만으로 폭을 줄이지 않는다. `--preflight`, 모든 기기의 `--edge-groups`, 등록 `--edges/--paths`가 필요하다. 현재는 직렬 실행만 허용한다. `budget_decision`과 `budget_outcome`을 구분해 읽는다. 실제 학습 성능은 미검증이다.

폭 한 종류만 학습한 라운드에도 `Aggregator.aggregate`가 서버 전역 상태·캐시를 동기화하도록 수정했다. 아래 그림과 목적함수는 기존 `--planner plan`에 대한 설명이다.

## 한 장 요약 — 3층

```
   기기 (fed_client.py)                      서버 (fed_server.py)
  ┌──────────────────────┐   활성값·기울기   ┌──────────────────────────────────────────────┐
  │ 모델 앞부분 계산       │ ───────────────▶ │  라운드 진행 · 계측 수집 · 뒷부분 계산 (GPU)   │
  │ 출구 A/B 로 조각 전송  │ ◀─────────────── │                                              │
  │ (mpsend / chunker)    │   내려받기        │  policies.WidthPath._apply_plan  ← 라운드마다  │
  └──────────────────────┘                  │    ① 인지  sense.Sensor  프로파일·관측·엣지 용량 │
        ▲    ▲                              │    ② 계획  plan.plan     경로 단계 → 목표 배정   │
        │    │ tc: 접속 상한(HPC egress)      │                         → 결합 최적화 폭        │
        │    └ 역터널 4개 = 엣지 1~4 (VM)     │    ③ 실행  출구별 종점 갱신 · 조각 배분 가중치   │
        │      엣지 용량 = VM tc (내려받기 자식) │              · 폭 슬라이스 (models.py)         │
   sfl/net/real_rig.sh                      └──────────────────────────────────────────────┘
```

데이터 흐름 한 줄: **기기가 계산해 올리면 → 서버가 시간을 재고(인지) → 계획이 다음 라운드의 폭·경로·분할을 정해(계획) → 체크인 응답에 실어 내려보낸다(실행).**

기존 `--planner plan --deadline opt`의 목적: `min max_k T_k(w, s) + λ · 평균(1 − w_k)` — 라운드(가장 느린 기기)에 폭을 잃은 값을 초로 환산해 더한 것. 새 예산 정책에는 이 λ 목적함수를 적용하지 않는다.

## 핵심 모듈 (여기만 알면 됨)

| 파일 | 층 | 역할 |
|---|---|---|
| `network_control.py` | 네트워크 계획·계약 | 공유 링크 제약, 고정 요구 바이트에 대한 종점 배정, 완료 보고 대조 |
| `sense.py` | 인지 | `Sensor`: 사전 진단(연산 1배치, 바이트, 출구별 접속 실측 `solo_probe`) → 프로파일. 라운드마다 `observe()`: 기기별 배치당 전송·라운드 총시간(창 3), **엣지 용량 추정** `edge_est` — 관측 처리량/기대 비율 <0.8 포화(창 중앙값), ≥0.95 풀림(관측값·1.5배씩 상승), 사이 유지; 두 엣지에 걸친 기기는 부하만 세고 시간은 귀속 안 함. 계획기는 `caps_effective(정적)` 을 쓴다 |
| `plan.py` | 계획 | 순수 함수. `water_fill/effective_rate`(경로 용량을 흐름이 나눠 씀, 접속 상한은 출구별) → `path_stage`(비용 = 기기 시간 총합 + N·max, 이동 문턱 = 계측 불확도 10% × 옮기는 기기 시간, 라운드당 `max_moves`) → 목표 배정(이동 상한 없이) → `opt_widths`(가장 느린 기기부터 한 칸 내려 max 이득이 가격 λ·Δw/N 을 10% 여유로 넘을 때만) → 히스테리시스(한 칸/라운드, 복귀 2라운드). `split_weights` = 조각 배분(정적 용량). `residual` = 관측 가산 잔차 |
| `policies.py` | 실행 | 정책 레지스트리 `uniform`(기준선: 회선 하나·고정 배정·전폭) / `widthpath --planner plan`(3층). `_apply_plan` 이 인지→계획→실행을 잇고, 실회선(엣지 모드)에서는 `fed_server.endpoints_for` 로 출구별 종점을 바꾼다. `--deadline opt --lam λ --max-moves n` |
| `fed_server.py` | 서버 | 라운드 진행·계측(`per_client_detail`: xfer, 출구별 바이트, t_round)·정책 호출·`micro_step`(즉시 내보내기 조각 기울기, 클라별 버퍼)·실행 인자 곁파일 `.args.json`·인지 결과 `.profile.json` |
| `fed_client.py` | 기기 | 앞부분 계산(`--speed`, `--threads` 로 연산 이질성), 사전 진단 응답, 출구 2개 조각 전송(`ChunkLinks`), `--init-sets rr` |
| `mpsend.py`, `chunker.py`, `proto.py` | 전송 | 상시 연결·조각 크기·가중 몫·기다리는 재조립·양방향·배압·비동기 회신·출구당 산 연결 하나 (설계 `docs/04_설계기록/설계_멀티패스_분할전송.md` 규칙 1~10) |
| `models.py` | 모델 | CNN 분할 모델, 폭 슬라이스 `slice_into` · 중첩 평균 `nested_average`(HeteroFL 식), `--norm gn` 옵션 |
| `fluidsim.py` | 시뮬 | 3층 유체 시뮬(100대) — `scripts/analysis/combo_sim.py, scale_sim.py` 가 사용, 실측 효율로 보정 |
| `controller_multi.py`, `paths.py` | (구판) | 9/6 이전 2단계 계획기 `plan_two_stage` 와 순수 함수 — `--planner two-stage` 로 남겨 둠(비교용). 현행은 `plan.py` |

절제 팔 만드는 법(`scripts/exp/conditions.json` 의 `arms`): `width3` 폭만(`--max-moves 0`) · `path3` 경로만(`--ladder 1.0`) · `mp` 분할 · `both3` 폭+엣지 · `bothmp` 폭+엣지+분할(제안) · `bothmpm` +즉시 내보내기.

## 리그 (`sfl/net/`)

- **`real_rig.sh`** — 실회선(2026-09-08~). `up N "acc목록" "엣지용량"`: VM 에 역방향 SSH 터널 4묶음(엣지 1~4), HPC egress tc 로 기기·출구별 접속 상한, VM tc 로 엣지 용량(부모 ceil) + 기기별 내려받기 자식 클래스 `3:(1000 + k·512 + 2i + x)`. 런타임 `access i aA aB` / `edge e cap`(교란). `edges` 가 종점 목록을 낸다. 자가 검사 `scripts/measurement/real_selftest.py` A~E.
- `hairpin_lo.sh` — 루프백 2층 리그(9/6~7 절제·망 효과). `paths.sh`, `hetero.sh`, `perturb.sh`, `protect.sh` — 8월 리그.

## 실증 플랫폼 (`sfl/demo/`)

`run_demo_real.py --cond demo8` — 실회선 위 라이브(:8778): `/state` JSON, `/perturb {"kind":"access"|"edge","idx","factor"}`, `/reset`. 교란은 `real_rig.sh access/edge` 를 실제로 부른다. `--replay <jsonl>` 은 리그 없이 재생. 자동 검증 `scripts/exp/verify_demo.sh`. `platform_index.html`(/platform) 홈, LoRA 삼면비교 `demo_server.py`(:8777).

## 실험 드라이버·분석 (`scripts/`)

`scripts/exp/README.md` 에 드라이버 → 결과 문서 표. 조건은 `conditions.json` 하나에서만(`cond.py --env`), 스크립트에 숫자를 쓰지 않는다(`tests/test_cond.py` 가 검사).
분석: `scen32_report.py`(표·viz JSON) → `scen32_viz.py`(시간축 HTML), `combo_table.py`, `replay_plan.py`(결정 재생), `trace_sense.py`(인지 추적), `report_html_0910.py`(종합 보고 HTML).
**드라이버는 반드시 저장소에 둔다** — 로컬에 먼저 쓰고 HPC 로 옮겨 검증한다.

## 테스트 (`tests/`, 진입점 `bash scripts/run_tests.sh {fast|full|rig}`)

- 새 정책: `tests.test_network_control`, `tests.test_device_budget` (torch 불필요). `tests.test_micro_e2e`, `tests.test_network_runtime`, `tests.test_aggregate_width_sync` (torch 필요, 실제 소켓·텐서 검증).
- FAST: `test_plan2.py`, `test_plan.py`/`test_two_stage.py`, `test_cond.py`, `test_chunker.py`, `test_fluidsim.py`, `test_fast.py` 및 새 순수 계획 검사.
- FULL(torch): `test_mp_act.py`, `test_sense.py`, `test_micro_srv.py`, 새 소켓·텐서 검사, `verify.py`(분할≡단일체).
- RIG(HPC): `real_selftest.py`, `verify_scen32.sh`, `verify_demo.sh`

## 자주 하는 일 → 여는 파일

- 계획 규칙을 고친다 → `plan.py` + `tests/test_plan2.py` 에 시험 추가, 로그로 재생해 확인(`replay_plan.py`)
- 인지 규칙을 고친다 → `sense.py` + `tests/test_sense.py`, 옛 로그로 추적(`trace_sense.py`)
- 새 조건 → `scripts/exp/conditions.json`(값마다 출처) → 드라이버는 `COND=` 로만
- 32대 시나리오 → `scripts/exp/run_scen32.sh` (교란 `scenario_perturb.sh`), 결과 `scen32_report.py`
- 시연 → `sfl/demo/run_demo_real.py`, 검증 `scripts/exp/verify_demo.sh`
