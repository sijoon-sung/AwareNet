# KOREN 정밀 실측 프로토콜 — 비교 항목 사전 등록 (10번 문서)

> 도구: `scripts/measurement/probe_server.py`(표적) + `koren_probe.py`(관측) +
> `koren_compare.py`(비교표). SSH 터널이 아니라 맨 TCP — 암호화·다중화 오버헤드 없음.
> **비교 항목과 판정 지표를 측정 전에 등록한다.** 로컬 스모크 통과(2026-08-27).

## 0. 정밀 수칙 — 이것을 지켜야 "정밀"이다

| 수칙 | 왜 |
|---|---|
| **A/B 교차** — 비교 표적들을 같은 분 안에 번갈아 측정 (`--targets a=…,b=…` 하나의 실행으로) | 시간대 편향 제거. 오전에 KOREN, 오후에 인터넷을 재면 비교가 아니라 시각 차이를 재는 것 |
| **fresh / steady 분리** — 새 연결(핸드셰이크+slow start 포함 = 실사용값)과 재사용 연결(정상상태)을 둘 다, 라벨 갈라서 | 24.2 vs 55Mbps 사건의 교훈 — 둘을 섞으면 어느 쪽도 아니게 됨 |
| perf_counter_ns · TCP_NODELAY · 웜업 1회 폐기 | ms 이하 정밀도, Nagle 지연 제거 |
| 분포로 보고 (p5/50/95/99 + IQR 지터) — 평균 단독 금지 | 꼬리가 본론 (버스트 p95 사건) |
| 반복 ≥3 · 시각(UTC)·관측지점·표적 메타데이터 자동 기록 | 재현성 |
| 리눅스 관측지점이면 ss -ti 재전송 전후차 기록 | 손실 대리 지표 |
| 버스트는 배리어 동시 출발 + 측정 전용 연결로 RTT 병행 샘플 (100ms) | 완료 편차와 지연 악화를 같은 사건에서 |

## 1. 사전 등록 비교 목록 (C1~C7)

| # | 비교 | 방법 | 1차 지표 | 이 비교가 답하는 것 |
|---|---|---|---|---|
| **C1** | **KOREN vs 상용 인터넷** | 같은 관측지점에서 두 표적 A/B 교차 (KOREN VM vs 상용 클라우드 VM, 같은 스펙) | RTT p50/p95 · 지터 IQR · 굿풋 · 재전송 | "왜 KOREN인가"의 수치화 — 연구망의 품질 우위(또는 차이 없음)를 정직하게 |
| **C2** | **POP 간 지역 이질성** | 관측지점 고정, 표적 = 판교·대전·(추가 POP) VM 교차 | RTT·굿풋의 지점 간 배율 | "일반 클라우드로 재현 불가능한 지리적 이질성" — 다지점 실증의 근거표 |
| **C3** | **평시 vs 라운드 경계 버스트** | `--burst-k {4,8,13,32}` 스윕 | RTT 악화배수(버스트 p95/평시 p50) · 완료 편차(spread) · 합산 굿풋 | 라운드 경계 혼잡의 실물 — K 에 따른 악화 곡선 (기존 13플로우 5배의 일반화) |
| **C4** | **전송 크기 vs 실효 굿풋** | `--sizes 0.5,1,4,8.39,32` × fresh/steady | 크기별 굿풋 곡선 · **slow-start 세금**(fresh/steady 비) | 마감 τ·어댑터 크기 설계의 입력 — "짧은 전송은 회선을 못 쓴다"의 정밀판 |
| **C5** | **시간대 자연 변동 (K2)** | cron 으로 1시간 간격 × 수일, 동일 인자 | 시각별 p50/p95 시계열 | 자연 변동 실재 여부 — 없으면 "연구망은 조용했다"고 그대로 씀 |
| **C6** | **SFL 실트래픽 vs 합성 벌크** | fed 리그의 per_client_detail(xfer) 과 C4 곡선 대조 | 같은 바이트에서의 시간 비 | 프로브가 실트래픽을 대표하는가 (on-wire 데이터셋의 검증 절) |
| **C7** | (후일) 유선 KOREN vs 이음5G 무선 액세스 | 대전 거점 확보 시, 동일 표적으로 액세스만 교체 | 전 지표 | 무선 구간의 변동성 — 컨트롤러의 자연 이질성 입력 |

## 2. 런북

```bash
# ① 표적(KOREN VM·상용 VM·POP 각각)에 서버 상주
nohup python3 scripts/measurement/probe_server.py --port 9099 > probe_srv.log 2>&1 &

# ② 관측지점에서 — C1+C3+C4 를 한 번에 (A/B 교차 자동)
python3 scripts/measurement/koren_probe.py \
  --targets koren=<판교IP>:9099,inet=<상용IP>:9099 \
  --label pc_lab --rtt-n 200 --sizes 0.5,1,4,8.39,32 --reps 3 --burst-k 13

# ③ C3 K 스윕 (버스트만 반복)
for k in 4 8 13 32; do python3 scripts/measurement/koren_probe.py \
  --targets koren=<판교IP>:9099 --label burst_k$k --rtt-n 20 --sizes 1 --reps 1 \
  --burst-k $k; done

# ④ C5 장기 수집 (관측지점 crontab)
# 0 * * * * cd <repo> && python3 scripts/measurement/koren_probe.py \
#   --targets koren=<IP>:9099 --label longrun --rtt-n 60 --sizes 8.39 --reps 1

# ⑤ 비교표
python3 scripts/measurement/koren_compare.py out/measure/probe_*.json --md out/measure/비교표.md
```

## 2.5 현실 제약 — KOREN VM 은 기본 인바운드가 26022 뿐이다

| 측정 | 포트 개방 전 (지금 가능) | 포트 개방 후 (본판) |
|---|---|---|
| RTT·지터 | **TCP connect(26022) 타이밍** — SYN/SYNACK 왕복이라 서버 불필요, `koren_probe.py --connect-only` | 프로브 서버 에코 (앱 계층 RTT 병행) |
| 굿풋 | ssh(26022) 다중 세션 스트리밍 (기존 `ssh_throughput.py`) — 암호화 오버헤드는 WAN 55Mbps 대역에서 미미하나 **"ssh 경유" 라벨 필수** | 맨 TCP fresh/steady 분리 |
| 버스트 | **ssh 세션 K개 병렬** (구 burst_test.py 방식 — 세션마다 독립 TCP 라 유효. 단일 터널 포워딩은 금지: 흐름이 한 TCP 에 몰려 head-of-line 오염) | 프로브 서버 U 플로우 K개 |
| C5 장기 | connect-RTT 만이라도 cron 수집 시작 가능 | 전 지표 |

신청서 항목: "측정용 TCP 포트 1개(9099) 인바운드 허용" — 개방 전에도 위 폴백으로
C1(RTT 축)·C3(ssh 판)·C5 를 시작한다.

## 3. 주의·한계 (정직 고지)

- 단방향 지연(OWD)은 클럭 동기 없이는 못 잰다 — 왕복만 보고, OWD 주장은 하지 않는다
- 관측지점 자체 회선이 상한이다 — 각 세션 첫머리에 루프백/근거리 기준치를 같이 기록
- 방화벽: 표적 포트(9099) 인바운드 허용 필요 — KOREN 은 등록 IP 에서만 (신청서 항목)
- C1 의 상용 표적은 **같은 스펙·같은 리전급** VM 으로 — 아니면 VM 성능 차이를 재게 된다
