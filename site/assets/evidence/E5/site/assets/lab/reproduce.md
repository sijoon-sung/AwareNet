# AwareNet 통합 계측소

실제 Linux `tc`·TCP 전송·수신 해시 검증을 TShark(Wireshark의 CLI), Prometheus, Grafana와 연결한다. 가상 조건의 실제 패킷 실험이며 KOREN 실측·새 학습 실험으로 해석하지 않는다.

## 확정 실행

- 실행 ID: `virtual-20260926T142615Z`
- QEMU TCG, 2 vCPU, 1 GiB RAM, Alpine 3.24.2 / Linux 6.18.52
- iproute2 7.0.0, Python 3.14.7, TShark 4.6.6
- Grafana 13.2.2, Prometheus 3.15.0
- 4개 네임스페이스, 8개 논리 클라이언트 스레드, 2개 TCP 경로
- 본 전송 128 KiB/client, 조각 4 KiB, 폭 1.0 고정
- edge_drop: 4라운드/정책. E1 2→0.5 Mbit/s(R2), E2 2 Mbit/s
- shared_access: 2라운드/정책. 두 경로 뒤의 하나의 IFB를 합계 2 Mbit/s로 제한
- 각 경로 HTB + netem 단방향 10 ms. 의도적인 무작위 손실은 설정하지 않음
- 세 정책 모두 두 경로를 동일하게 프로브하며, 프로브의 시간·바이트를 부담함
- 단일 실행, 실행 순서 고정, 독립 반복/유의성 검사 없음

`summary.json`은 용량 감소 후 R2–R4 및 공유 병목 R1–R2의 평균이다. 원시 `rounds.json`은 첫 라운드도 포함한다. `executed-source.tgz`는 실행 당시의 정확한 소스이고 최신 소스에는 tc JSON 카운터 호환 수정이 추가되었다.

## Linux 게스트에서 재현

다른 작업이 없는 **폐기 가능한 Linux VM**의 root 셸에서 실행한다. 스크립트는 `awn-client`, `awn-edge1`, `awn-edge2`, `awn-server` 네임스페이스를 만들고 종료 시 삭제한다. 같은 이름이 이미 있으면 시작을 거부한다. 호스트 PC의 네트워크 인터페이스를 지정하지 않는다.

Alpine 예시:

```sh
apk add python3 iproute2 iproute2-tc ethtool tshark tcpdump
python3 scripts/observability/virtual_lab.py study --output /root/awarenet-run
```

수집기가 있으면 `--collector http://10.0.2.2:19108`을 추가한다. QEMU user networking의 `10.0.2.2`는 호스트 loopback에 대응한다. 수집기 주소는 자신의 격리된 배치에 맞춰 지정한다. 패킷은 클라이언트 namespace의 `any`에서 TCP 포트 20500만 캡처한다.

## Windows에서 사용한 계측소

전역 설치 대신 공식 배포본을 `tmp/lab-tools/` 아래에 풀었다. 이 대용량 실행 파일은 공개 저장소에 넣지 않는다.

| 도구 | 공식 다운로드 | 압축 해제 위치 |
|---|---|---|
| QEMU | https://qemu.weilnetz.de/w64/qemu-w64-setup-20260811.exe | `tmp/lab-tools/qemu/` |
| Alpine | https://dl-cdn.alpinelinux.org/alpine/v3.24/releases/x86_64/alpine-virt-3.24.2-x86_64.iso | `tmp/lab-tools/downloads/alpine.iso` |
| Grafana | https://dl.grafana.com/grafana/release/13.2.2/grafana_13.2.2_34846740809_windows_amd64.tar.gz | `tmp/lab-tools/grafana/grafana-13.2.2/` |
| Prometheus | https://github.com/prometheus/prometheus/releases/download/v3.15.0/prometheus-3.15.0.windows-amd64.zip | `tmp/lab-tools/prometheus/prometheus-3.15.0.windows-amd64/` |

QEMU의 공식 SHA-512, Alpine ISO의 공식 SHA-256, Prometheus의 공식 SHA-256을 비교했다. ISO의 `boot/vmlinuz-virt`, `boot/initramfs-virt`를 `tmp/lab-tools/alpine/boot/`로 추출한다. QEMU의 파일 경로에는 상대 경로를 사용한다(해당 Windows 빌드의 한글 경로 처리 문제).

```powershell
python scripts/observability/start_local_station.py
python scripts/observability/vm_console.py launch
python scripts/observability/vm_console.py console --command root --seconds 10
```

게스트 로그인 후 `ip link set eth0 up`, `udhcpc -i eth0 -q`를 실행하고 패키지를 설치한다. 이 실행에서는 게스트 DNS가 응답하지 않아 수집기의 고정 Alpine 미러 캐시를 이용했다. `/etc/apk/repositories`의 main/community 주소를 각각 `http://10.0.2.2:19108/alpine/v3.24/main`, `http://10.0.2.2:19108/alpine/v3.24/community`로 두었다. 캐시는 호스트에서 공식 HTTPS 원본만 가져오며 APK 서명 검증은 유지한다.

```sh
mkdir -p /root/awlab
wget -qO /root/bundle.tgz http://10.0.2.2:19108/bundle.tgz
tar -xzf /root/bundle.tgz -C /root/awlab
python3 /root/awlab/scripts/observability/virtual_lab.py study --output /root/run --collector http://10.0.2.2:19108
```

호스트에서 실행 ID별 결과 폴더를 지정해 분석한다:

```powershell
python scripts/observability/summarize_lab.py --run output/observability/<run-id>
```

- 통합 화면: http://127.0.0.1:19108/station
- Grafana: http://127.0.0.1:13000/d/awarenet-lab
- Prometheus: http://127.0.0.1:19090
- 모든 서비스는 loopback에만 바인딩한다. Grafana 익명 권한은 Viewer이다.
- `tmp/observability/current.json`에 이 작업이 띄운 PID를 기록한다. 종료할 때 해당 PID의 실행 파일을 확인한 뒤 `Stop-Process -Id <PID>`를 사용한다. 공개 웹에 이 로컬 서비스를 노출하지 않는다.

## Wireshark에서 열기

`capture.pcapng`를 Wireshark에서 열고 `awarenet.lua`를 개인 Lua 플러그인 폴더에 둔다. 또는 CLI에서:

```sh
tshark -X lua_script:observability/wireshark/awarenet.lua -r capture.pcapng -Y 'tcp.port == 20500 && awarenet'
```

주요 필드: `awarenet.tid`, `awarenet.cid`, `awarenet.seq`, `awarenet.offset`, `awarenet.bytes`, `awarenet.fin`, `awarenet.ack`. 기존 9바이트 BII 프레이밍을 해석한다. 이 도구는 TCP 프로토콜 수정이 아니다.

## 해석 시 주의할 점

1. TCP ACK RTT는 텐서 완료 시간이나 netem 설정값과 다르다. Wireshark 재전송 분석 플래그를 실제 링크 손실률로 바꾸지 않는다.
2. tc class 카운터는 프로브·프로토콜·재전송까지 포함하므로 본 전송 페이로드와 같지 않다.
3. 최초 실행의 실시간 class bytes는 iproute2 7의 `stats.bytes` 형식을 읽지 못해 0이었다. 저장된 실제 스냅샷에서 재계산했으며 `counter-normalization.json`에 수정 근거를 남겼다. 원시 로그는 변경하지 않았다.
4. Grafana의 플러그인 자동 업데이트 실패는 원본 번들 복구와 자동 업데이트 비활성화로 해결했다. Prometheus에 수집된 원래 시계열을 조회한다.
5. `adaptive_dual`은 검증용 프로브 비례 조각 할당이다. 기존 `network`/`widthpath` 전체 알고리즘 또는 AI 에이전트 성능을 의미하지 않는다.

GitHub Pages에는 녹화된 수치·그림·PCAP만 배포한다. Grafana와 수집기는 정적 웹사이트의 서버 기능이 아니다.
