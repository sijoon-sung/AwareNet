# Jetson 측정 작업지시서

담당자가 이 문서만 보고 순서대로 실행하면 됩니다. 배경 설명은 없습니다.
**막히면 그 단계에서 멈추고, 에러 메시지 전체를 그대로 공유해 주세요.** 임의로 우회하지 마세요.

장비: **NVIDIA Jetson Orin Nano Super Developer Kit (8GB)**

> Super는 **MAXN SUPER(25W) 모드**를 쓸 수 있는 버전입니다. 이 모드를 쓰려면
> **JetPack 6.2 이상**이어야 합니다. 1-2에서 버전을 먼저 확인하세요.

---

## 0. 준비물 확인

- [ ] Jetson Orin Nano **Super** 개발자 키트 (8GB)
- [ ] **NVMe SSD (M.2 2280, 250GB 이상)** — 필수. microSD만으로 하면 측정값이 무효가 됩니다
- [ ] DC 전원 어댑터 19V / 45W 이상
- [ ] **유선 랜 케이블** — 필수. 와이파이로 측정하면 무효입니다
- [ ] 모니터·키보드 (초기 설정용) 또는 SSH 접속 환경

---

## 1. 셋업

### 1-1. NVMe 마운트

```bash
lsblk                                    # nvme0n1 보이는지 확인
sudo mkfs.ext4 /dev/nvme0n1
sudo mkdir -p /mnt/nvme
sudo mount /dev/nvme0n1 /mnt/nvme
echo '/dev/nvme0n1 /mnt/nvme ext4 defaults 0 2' | sudo tee -a /etc/fstab

echo 'export HF_HOME=/mnt/nvme/hf' >> ~/.bashrc
source ~/.bashrc
```

**확인**: `df -h /mnt/nvme` 에서 용량이 보이면 성공

### 1-2. JetPack 버전 확인

```bash
cat /etc/nv_tegra_release
sudo apt show nvidia-jetpack 2>/dev/null | grep Version
```

→ **버전을 기록해서 알려주세요.** 6.2 미만이면 업그레이드가 필요할 수 있습니다.

### 1-3. 전력 모드 번호 확인 — **먼저 이것부터**

Super는 모드 번호가 기존 모델과 다릅니다. **번호를 추측하지 말고 직접 확인**하세요.

```bash
sudo nvpmodel -q                              # 현재 모드
sudo nvpmodel -q --verbose | head -30         # 사용 가능한 모드 전체 목록
grep -E "^< POWER_MODEL|MAXN" /etc/nvpmodel.conf | head -10
```

출력에서 모드 번호와 이름을 아래 표에 적어주세요. 보통 `15W`, `25W`, `MAXN SUPER`가 있습니다.

| 모드 번호 | 이름 (예: 15W / 25W / MAXN SUPER) |
|---|---|
| 0 | |
| 1 | |
| 2 | |

> **MAXN SUPER가 목록에 없으면** JetPack이 6.2 미만입니다. 그 사실을 알려주세요.

### 1-4. 성능 모드 고정 (측정 전 매번 실행)

위에서 확인한 **가장 높은 모드 번호**를 `<N>`에 넣습니다.

```bash
sudo nvpmodel -m <N>             # 예: MAXN SUPER가 2번이면 -m 2
sudo jetson_clocks               # 클럭 고정
sudo nvpmodel -q                 # 적용 확인
```

**이 단계를 건너뛰면 측정값이 매번 달라져서 전부 다시 해야 합니다.**

### 1-5. PyTorch 설치 확인 — **가장 중요**

```bash
python3 -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

**반드시 `True`가 나와야 합니다.**

- `False`가 나오면 → **거기서 멈추고 알려주세요.** 일반 `pip install torch`는 Jetson에서 CUDA가 안 붙습니다. NVIDIA 전용 휠 또는 `nvcr.io/nvidia/l4t-pytorch` 컨테이너가 필요합니다
- `False` 상태로 측정하면 **전부 무효**입니다

### 1-6. 프로젝트 코드 받기

```bash
git clone <저장소 주소> ~/KORAN_SDN-AWARE_NET-
cd ~/KORAN_SDN-AWARE_NET-
pip3 install -r requirements.txt      # torch는 이미 설치되어 있으니 건너뛰어도 됨
export PYTHONPATH=.
```

### 1-7. 네트워크

```bash
curl -s ifconfig.me; echo          # 공인 IP 확인 → 이 값을 알려주세요 (KOREN 등록 필요)
```

→ **공인 IP를 알려주시면 제가 KOREN 허용 목록 등록을 요청합니다.** 등록 전에는 3번 항목(C)을 못 합니다.

---

## 2. 측정 A — 연산 시간 (최우선)

1-3에서 확인한 모드 번호를 씁니다. **15W 모드와 최고 모드(MAXN SUPER) 두 번** 측정합니다.

```bash
cd ~/KORAN_SDN-AWARE_NET- && export PYTHONPATH=.

# ① 15W 모드  (<A> = 15W 모드 번호)
sudo nvpmodel -m <A> && sudo jetson_clocks && sleep 10
sudo nvpmodel -q                                    # 15W 맞는지 확인하고 진행
python3 scripts/analysis/measure_lora_train_speed.py --device cuda --repeat 30 2>&1 | tee ~/anchor_15w.log

# ② 최고 모드  (<B> = MAXN SUPER 모드 번호)
sudo nvpmodel -m <B> && sudo jetson_clocks && sleep 10
sudo nvpmodel -q                                    # MAXN SUPER 맞는지 확인하고 진행
python3 scripts/analysis/measure_lora_train_speed.py --device cuda --repeat 30 2>&1 | tee ~/anchor_max.log
```

> 모드를 바꾼 뒤 **`nvpmodel -q`로 실제 적용을 확인하고** 측정하세요.
> 잘못된 모드로 잰 값은 무효입니다.

**기록할 것** (아래 표를 채워서 주세요)

| 항목 | 15W 모드 | MAXN SUPER 모드 |
|---|---|---|
| 적용된 모드 이름 (`nvpmodel -q` 출력) | | |
| 스텝 시간 중앙값 (ms) | | |
| 표준편차 (ms) | | |
| 앞 10회 평균 (ms) | | |
| 뒤 10회 평균 (ms) | | |

> **앞 10회와 뒤 10회 차이가 10% 이상이면** 발열로 느려지는 것입니다.
> 그 사실을 꼭 알려주세요 (냉각 보강 후 재측정 필요).

---

## 3. 측정 B — 메모리 한계

터미널 **두 개**를 띄웁니다.

**터미널 1 (모니터)**
```bash
sudo tegrastats --interval 500 | tee ~/mem_monitor.log
```

**터미널 2 (학습 실행)**
```bash
cd ~/KORAN_SDN-AWARE_NET- && export PYTHONPATH=.
export AWARENET_WORKLOAD=lora
export AWARENET_BASE_MODEL=Qwen/Qwen2.5-0.5B
export AWARENET_LORA_R=32
export AWARENET_SEQ_LEN=512
python3 scripts/analysis/measure_lora_train_speed.py --device cuda --repeat 5
```

학습이 끝나면 터미널 1을 Ctrl+C로 멈추고:

```bash
grep -oE 'RAM [0-9]+/[0-9]+MB' ~/mem_monitor.log | sort -t' ' -k2 -n | tail -1
```

### 메모리 부족(OOM)이 나면 — 순서대로 시도

한 단계씩 내려가면서 **어디서 성공했는지** 기록하세요.

| 단계 | 명령 | 결과 |
|---|---|---|
| 1 | `export AWARENET_SEQ_LEN=256` | 성공 / 실패 |
| 2 | 위 + 배치 축소 (`--batch-size 2`) | 성공 / 실패 |
| 3 | 위 + 배치 1 (`--batch-size 1`) | 성공 / 실패 |
| 4 | 여기까지 다 실패하면 **멈추고 알려주세요** | 4bit 양자화 적용이 필요합니다 |

**채워서 주실 표**

| 설정 | 성공 여부 | 피크 RAM (MB) |
|---|---|---|
| seq 512 / batch 4 | | |
| seq 256 / batch 4 | | |
| seq 256 / batch 2 | | |
| seq 256 / batch 1 | | |

---

## 4. 측정 C — 네트워크 (KOREN IP 등록 후에만)

```bash
# 도달 확인
ping -c 100 116.89.187.190 | tail -2

# 링크 프로파일
cd ~/KORAN_SDN-AWARE_NET- && export PYTHONPATH=.
python3 scripts/measurement/measure_link_profile.py 2>&1 | tee ~/link_profile.log
```

**기록할 것**

| 항목 | 값 |
|---|---|
| ping 평균 RTT (ms) | |
| ping 손실률 (%) | |
| mdev (지터, ms) | |

---

## 5. 측정 D — 서버 연결 (C 성공 후)

제가 서버를 띄워둔 시간에 맞춰 실행합니다. **실행 전에 연락 주세요.**

```bash
cd ~/KORAN_SDN-AWARE_NET- && export PYTHONPATH=.
export AWARENET_CID=jetson-001
export AWARENET_SUBPROC=0
export FLOWER_SERVER=116.89.187.190:8081
python3 -m edge.fl_client --cid jetson-001 2>&1 | tee ~/jetson_client.log
```

화면에 `fit 완료` 가 한 번이라도 뜨면 성공입니다. 로그 파일을 그대로 보내주세요.

---

## 6. 제출물

아래 파일들을 통째로 보내주시면 됩니다.

```
~/anchor_15w.log
~/anchor_max.log
~/mem_monitor.log
~/link_profile.log
~/jetson_client.log
```

그리고 **2·3·4번의 표를 채운 것**과, **1-2의 JetPack 버전**, **1-6의 공인 IP**.

---

## 7. 자주 나오는 문제

| 증상 | 조치 |
|---|---|
| `torch.cuda.is_available()` 가 False | **멈추고 알려주세요.** 이 상태의 측정은 전부 무효 |
| 측정값이 실행할 때마다 크게 다름 | `nvpmodel -m <N>` + `jetson_clocks` 를 안 한 것. 다시 하고 재측정 |
| `nvpmodel -m` 이 "invalid mode" 오류 | 모드 번호가 틀린 것. 1-3으로 돌아가 목록을 다시 확인 |
| 모드 목록에 MAXN SUPER가 없음 | JetPack 6.2 미만. 버전을 알려주세요 (업그레이드 판단 필요) |
| 뒤로 갈수록 느려짐 | 발열 스로틀링. **그 사실 자체를 기록해서 알려주세요** (숨기지 말 것) |
| 모델 다운로드가 느리거나 실패 | `echo $HF_HOME` 이 `/mnt/nvme/hf` 인지 확인. 아니면 1-1 다시 |
| `Out of memory` | 3번의 폴백 단계 순서대로. 다 실패하면 알려주세요 |
| ping이 안 나감 | KOREN IP 등록 전입니다. 1-6의 공인 IP를 저에게 주세요 |

---

## 8. 작업 순서 요약

```
1. 셋업 (NVMe → 모드번호 확인 → 성능모드 → torch CUDA 확인 → 코드)  ← torch가 False면 여기서 멈춤
2. 측정 A (연산 시간, 15W / MAXN SUPER 각각 30회)
3. 측정 B (메모리 한계, 폴백 표 채우기)
4. 공인 IP 알려주고 KOREN 등록 대기
5. 측정 C (네트워크)
6. 측정 D (서버 연결 — 사전 연락 후)
7. 로그 5개 + 표 3개 제출
```

**1번의 `torch.cuda.is_available()` 가 True가 아니면 2번 이후는 하지 마세요.**
