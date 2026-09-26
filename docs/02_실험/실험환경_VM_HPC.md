# 실험 환경 — KOREN VM 2대 + HPC V100 (2026-09-02 세팅)

> 무엇이 어디에 있고, 어떤 명령으로 실험을 거는지. 접속 정보(IP·허용 IP)는 `VM_INFO.md`(비공개).

## 1. 장비와 역할

| 장비 | 접속 | 사양 | 역할 |
|---|---|---|---|
| KOREN VM1 `koren-vm` (116.89.187.190) | SSH 26022, 허용 IP에서만 | 8코어 · 31GB · GPU 없음 | 집계 서버 A, 링크 실험의 서버 |
| KOREN VM2 `koren-vm2` (116.89.187.189) | SSH 26022, 허용 IP에서만 | 8코어 · 31GB · GPU 없음 | 클라이언트 4대(CPU), 집계 서버 B |
| HPC 이노베이션 허브 `koren-hpc` (10.246.246.33) | RNTier 런처가 켜져 있을 때만 `ssh koren-hpc` | V100 16GB · 16코어 · 158GB | GPU 실험 전용 (학습량별 정확도 궤적 등) |

- VM1 ↔ VM2: 같은 /26 대역, 왕복 지연 약 1.7ms, 사이 포트는 열려 있음(12000 확인). 실제 광역 구간은 아니고 같은 지점의 링크다.
- HPC → KOREN VM: HPC 의 공인 출구 116.89.174.50 이 VM 허용 목록에 등록되기 전까지는 막힘(신청서 제출).
- 바깥에서 VM 으로: 26022 만 열려 있음. 학습 서버 포트(12000번대)는 신청 반영 후 열림. 그 전에 PC 에서 붙으려면 SSH 터널(`ssh -L 12001:127.0.0.1:12001 koren-vm`).

## 2. VM 쪽 배치 (두 VM 동일)

```
~/awarenet/            현행 코드 (git archive 로 추적 파일만 배포 — data/out/.venv 는 유지)
~/awarenet/.venv/      torch CPU (VM1 은 기존 venv 심볼릭 링크, VM2 는 새로 설치)
~/awarenet/data/cifar10/   torchvision 이 내려받음
~/awarenet/out/        실험 로그 — vm_*.jsonl
```

옛 코드(`~/KORAN_SDN-AWARE_NET-`, `~/awarenet_v7`)는 손대지 않았다. VM2 에 8월 컨트롤러가 8080 포트로 아직 떠 있다(무해, 필요 시 종료).

## 3. 명령

```bash
# 배포·점검 (허용 IP 에서)
bash scripts/exp/vm_deploy.sh            # 코드 동기화 + 환경 점검 + FAST 테스트
bash scripts/exp/vm_deploy.sh status

# VM 실험
bash scripts/exp/vm_exp.sh smoke                  # VM1 안에서 서버+클라 4대, 2라운드
bash scripts/exp/vm_exp.sh link uniform,static,ours 12   # 서버 VM1 ← 클라 VM2, 정책 비교
bash scripts/exp/vm_exp.sh twosite 12             # 집계 서버 2곳 리허설 (widthpath)
bash scripts/exp/vm_exp.sh fetch                  # out/vm/ 로 회수
bash scripts/exp/vm_exp.sh kill

# HPC (런처 켜진 뒤)
bash scripts/exp/hpc_launch.sh          # 코드 동기화 + 스모크 + R(w) 전체를 nohup 으로
bash scripts/exp/hpc_launch.sh status
bash scripts/exp/hpc_fetch.sh           # out/hpc/ 로 회수 + 요약표
```

## 4. HPC 에서 먼저 도는 실험 — R(w) 예비 실험

`sfl/experiments/run_rw.py`: 전원 같은 폭 p 로 고정(oracle-plan)하고 라운드별 정확도를 기록한다.
폭 {0.25, 0.5, 0.75, 1.0} × 시드 {1, 2, 3} × 30라운드, 클라 4대 전부 GPU. 결과 `out/rw_p{p}_s{seed}.jsonl`,
요약 `out/rw_summary.json`. 용도: 공동 최적화 정식화의 R(w)(목표 정확도 도달 라운드 수) 적합 재료.
nohup 으로 걸어 두므로 런처가 꺼져도 HPC 에서 계속 돈다.

## 5. 접속 상태 (2026-09-02 저녁 확인)

KOREN 이 허용 IP 두 개(HPC 출구 116.89.174.50, 집 119.204.114.70)에 **TCP 22 · 10000~15000** 을 열어 주었다.
확인 방법: 두 IP 에서 VM 의 22·12001 에 붙으면 "연결 거부"(VM 까지 도달, 듣는 프로그램이 없을 뿐)가 오고, 26022 는 "시간 초과"(방화벽에서 차단)다.

| 출발지 → VM 2대 | 22 | 12001 | 26022 |
|---|---|---|---|
| HPC (116.89.174.50) | 도달 (거부 = 열림) | 도달 | 차단 |
| 집 (119.204.114.70) | 도달 | 도달 | 차단 |
| 연구실 (168.188.50.217) | 차단 | 차단 | 열림 (기존 허용) |

- 남은 문제 하나: **VM 의 sshd 가 26022 에서만 듣는다.** 새 IP 에는 26022 가 안 열렸으므로, 연구실에서 접속해
  두 VM 의 sshd 에 `Port 22` 를 추가하면 집·HPC 에서도 SSH 가 된다 (또는 KOREN 에 26022 추가 요청).
- 실험 트래픽은 지금도 가능: VM 에서 학습 서버를 12000번대로 띄우면 HPC·집에서 붙는다 (서버를 띄우려면 SSH 가 먼저 필요 → 위 항목).
- HPC 로 들어오는 연결은 여전히 불가(사설 IP). HPC 를 클라이언트/집계 서버 A 로 쓰려면 HPC → VM1 역방향 터널.
- 두 VM 이 같은 지점이라 "두 사이트" 실증은 아님 — 다른 POP 의 VM 이 필요하면 별도 신청.

## 6. 배치안 — 메인(집계) 서버는 HPC 에

![실험 배치도](../../out/fig/deploy_layout.png)

(생성: `python scripts/figs/make_deploy_fig.py`)

| 호스트 | 무엇을 돌리나 | 이유 |
|---|---|---|
| **HPC (V100)** | **집계 서버 A** = `fed_server.py` (모델 뒷부분 계산 + 컨트롤러) · 언어모델(LoRA) 서버 · R(w) 예비 실험 | GPU 가 여기뿐. 서버 뒷부분이 연산의 대부분 |
| KOREN VM2 | 클라이언트 4~8대 (`fed_client.py`, CPU, 스레드 2) | 서버와 다른 호스트 → 실제 링크를 지남. 앞부분 계산은 CPU 로 충분 |
| KOREN VM1 | 집계 서버 B (접속 지점 2곳 실험) · HPC 로 가는 역방향 터널의 종단 · 회선 측정 | 두 번째 접속 지점이 필요할 때만 |
| PC · 젯슨 | 실기기 클라이언트 (실WAN) | 회선이 실제로 다른 참여자 |

**클라이언트가 HPC 서버에 닿는 길** — HPC 는 사설 IP 라 바깥에서 직접 못 들어간다. 두 가지 중 하나:

1. **HPC 포털의 포트 포워딩**(10000~15000)이 공인 주소로 노출되면 그 주소로 접속 — 런처가 켜졌을 때 확인할 것:
   HPC 에서 `nc -l 12000` 을 띄우고 VM1 에서 `nc -zv 116.89.174.50 12000` (또는 포털이 알려주는 주소:포트).
2. 안 되면 **역방향 SSH 터널**: HPC 에서 `ssh -N -R 0.0.0.0:12000:localhost:12000 koren-vm` 을 걸어 두면
   VM2·PC 클라이언트는 `116.89.187.190:12000` 으로 붙고 트래픽이 VM1 → HPC 로 전달된다.
   전제: 116.89.174.50 이 VM 허용 목록에 등록(신청 중). VM1 sshd 에 `GatewayPorts yes` 필요.
   단, 이 경우 VM1↔HPC 구간은 SSH 안에 실리므로 회선 측정은 VM 쪽 구간만 의미가 있다.

PC 에서 HPC 로는 런처의 포트 포워딩으로 바로 붙는다(`localhost:포트`).

**코드 배치** — 세 곳 모두 같은 저장소를 같은 경로에 둔다(`~/awarenet`, git archive 로 추적 파일만).
실험은 로컬에서 ssh 로 지휘(`scripts/exp/vm_exp.sh`, `hpc_launch.sh`), 로그는 각 호스트 `out/` 에 쌓고
`fetch` 로 로컬 `out/vm/`, `out/hpc/` 에 모은다. 서버 포트는 HPC 범위에 맞춰 12000번대로 통일.

**실행 순서 (런처 켜진 뒤)**: ① `hpc_launch.sh` 로 코드 동기화 + R(w) 걸기 ② HPC 포트 노출 확인(위 1)
③ 되면 HPC 서버 ← VM2 클라이언트 4대로 링크 실험, 안 되면 역방향 터널(위 2) ④ 접속 지점 2곳(HPC + VM1).
