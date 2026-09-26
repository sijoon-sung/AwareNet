# 보유 엣지 VM SDN 집행기

이 폴더는 **OS-Ken + OpenFlow 1.3 + Open vSwitch**로 AwareNet이 관리하는 엣지 브리지의 서비스 흐름을 바꾸는 코드다. 기기↔첫 엣지의 외부 회선, KOREN 백본, 남의 스위치 제어권을 가정하지 않는다.

## 제어 경계

```text
기기(AwareNet 클라이언트, 허용 엣지 주소에 연결)
  → 외부망/연구망 (관측만)
  → 우리 엣지 VM의 veth/OVS ingress
  → OS-Ken이 지정한 OVS 터널 포트
  → 분할학습 서버
```

현재 학습 런타임은 `network_control.plan_routes()`의 `sets`를 앱 종점으로 집행한다. 이 결과를 OVS에 연결할 때는 `{"clients": {cid: {"route": routes} ...}}` 형태로 바꾸고 `policy.build_policy()`에 운영자가 등록한 ingress 주소·포트 매핑을 제공할 수 있다. **이 변환·게시를 학습 런타임이 자동 실행하지는 않는다.** 기존 SuperSFL 출력도 같은 정책 빌더의 입력 후보지만 가변 깊이는 아직 학습기에 연결되지 않았다.

현재 `network`의 완료 보고는 앱 수준 확인이며, 아래 OpenFlow barrier 응답이나 패킷 카운터 검증을 대신하지 않는다. [현재 경로 주장과 실증 조건](../../docs/04_설계기록/네트워크중심_아키텍처_및_경로주장_2026-09-22.md)

Linux 엣지에서 `pip install -r requirements-sdn.txt` 후 OS-Ken 앱을 실행한다. 환경변수 `AWARENET_SDN_DPID`, `AWARENET_SDN_PORTS`(쉼표로 구분한 허용 출력 포트), `AWARENET_SDN_INGRESS_PORT`, `AWARENET_SDN_SERVICE_IP`, `AWARENET_SDN_SERVICE_PORT`, `AWARENET_SDN_POLICY`를 실제 보유 브리지에 맞게 지정한다. `ovs-vsctl set bridge <bridge> protocols=OpenFlow13`와 `ovs-vsctl set-controller <bridge> tcp:<controller>:6633`로 연결한 뒤 저장소 루트에서 `PYTHONPATH="$PWD" osken-manager sfl/sdn/osken_controller.py`를 실행한다.

첫 배포의 확인 순서는 다음과 같다.

1. `ovs-ofctl -O OpenFlow13 show <bridge>`로 DPID와 포트 번호 확인.
2. 소유한 테스트 veth에서 서비스 TCP 흐름 1개를 보내고 `ovs-ofctl -O OpenFlow13 dump-flows <bridge>`의 AwareNet cookie와 패킷 카운터 확인.
3. OVS 입력 전후의 서버 수신 바이트·시간을 비교. 카운터가 0이면 SSH 터널이나 호스트 스택이 OVS를 우회하는 것이므로 실험을 실패로 기록.
4. 정책 오류·컨트롤러 단절 시 기존 연결이 유지되는지 확인. 현재 구현은 정책 교체 중 짧은 삭제/재설치 간격이 있으므로, 무중단 전환은 추후 bundle 또는 이중 테이블 방식으로 검증해야 한다.

정책 파일은 **컨트롤러 운영 계정만 쓸 수 있는 디렉터리**에 두고, 컨트롤러 포트는 보유 VM의 관리 네트워크에서만 열어야 한다. 코드가 정책의 DPID·입력 포트·서비스 IP/포트·출력 포트를 제한한다. 클라이언트 등록과 원본 IP의 신뢰 확인은 배포 단계에서 추가해야 한다.

공식 참고: [OS-Ken 앱](https://docs.openstack.org/os-ken/latest/writing_os_ken_app.html), [OpenFlow 1.3 flow-mod](https://docs.openstack.org/os-ken/latest/ofproto_v1_3_ref.html), [OVS OpenFlow](https://docs.openvswitch.org/en/latest/faq/openflow/).
