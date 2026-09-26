# -*- coding: utf-8 -*-
"""기준선 B-HSF — HeteroSplitFed 의 **정적 p_k 배정**.

  서지 (확정, 원문 대조 완료)
    [본체·학회지판] J.-H. Ryu and H. Yang, "A Study on Distributed Learning Algorithm for
      Heterogeneous Client Settings in Computing Capabilities" (클라이언트의 서로 다른
      학습 능력을 고려한 분산학습 알고리즘 연구), J. Korean Inst. Commun. Inf. Sci.
      (한국통신학회논문지), vol. 50, no. 2, pp. 195-204, Feb. 2025.
      DOI 10.7840/kics.2025.50.2.195 · KCI ART003173411 · 충남대 DNCL.
    [학회 2쪽판] J. Ryu and H. Yang, "HeteroSplitFed: 클라이언트의 서로 다른 학습능력과
      통신환경을 고려한 분산학습 기법 연구", Proc. KICS Winter Conf., pp. 1229-1230,
      Feb. 2024 (학부우수논문상). DBpia NODE11737563. **원문 미확보** — 아래 §5 참조.
    ※ arXiv/국제학술지판은 존재하지 않는다.

  ────────────────────────────────────────────────────────────────────────────
  §0. 이 파일이 무엇이고 무엇이 아닌가  (제1원칙: 허수아비 금지)
  ────────────────────────────────────────────────────────────────────────────
  ★★ HeteroSplitFed 논문에는 **p_k 를 정하는 절차가 없다.** ★★

  원문 대조로 확인한 사실 세 가지 (ft.txt 전문 검색 결과):
    (1) Table 1 의 p_k 정의는 "The ordered dropout rate for each client k" 한 줄뿐이고,
        논문 전체에서 p_k 가 14회 등장하지만 **산출식·절차가 단 한 번도 나오지 않는다.**
        Algorithm 1·2 어디에도 p_k 를 정하는 줄이 없다 → p_k 는 알고리즘의 **외생 입력**.
    (2) p_k 에 **라운드 첨자 t 가 붙지 않는다** (W_{k,t,p_k}^C — t 는 붙고 p_k 는 안 붙는다).
        → 라운드 간 불변. 재측정·재배정이 원리적으로 없다.
    (3) 실험(Table 2)에서 p 는 리스트로 **손으로 지정**된다:
          5클라: [0.8]*5 / [0.4]*5 / [0.8,0.8,0.8,0.2,0.2] / [0.8,0.2,0.2,0.2,0.2] / [0.2]*5
          10클라: 위 패턴을 2배로 늘린 5종
        사실상 {0.2, 0.4, 0.8} 세 값, 혼합 조건에서는 {0.2, 0.8} 두 값뿐이다.

  배정 근거에 대한 원문의 유일한 문장 (Ⅱ.2.3절, 원문 그대로):
    "클라이언트는 … FedServer에서 업데이트된 클라이언트 부분 모델을 전달받아
     **클라이언트의 컴퓨팅 능력을 고려하여** 클라이언트 부분 모델에 비율 p_k 로 OD를
     적용한 서브 모델 W_{k,t,p_k}^C 를 생성한다"
  "고려하여" 이상의 구체화가 없다. 그리고 **망은 보지 않는다** — 학회지판은 제목에서
  통신을 뺐고("…in Computing Capabilities"), 초록도 computational capabilities 뿐이며,
  논문 전체에 대역폭·RTT·전송시간·벽시계·TTA 수치가 **하나도 없다**(순수 시뮬레이션,
  성능 축은 정확도 단 하나).

  따라서 이 파일의 정직한 이름은 "HeteroSplitFed 를 그대로 구현한 것"이 아니라
    **"HSF 관행을 따른 정적 배정 — 기기 컴퓨팅 능력만으로 p_k 를 한 번 정하고 전 라운드 불변"**
  이며, **배정 규칙 자체는 우리가 정의했다**(§2). HSF 가 그런 규칙을 제시했다고 쓰면
  그게 오히려 허수아비다 — 없는 절차를 있다고 세우는 것이므로.

  ────────────────────────────────────────────────────────────────────────────
  §1. 두 가지 사용법
  ────────────────────────────────────────────────────────────────────────────
  (A) plan= 을 주면 **논문 그대로**다. p 는 실험자가 손으로 지정하는 외생 입력이고
      전 라운드 불변 — 이것이 HSF 의 literal 동작이다. Table 2 의 리스트를 그대로 넣어라.
          Baseline(ks, plan=[0.8, 0.8, 0.2, 0.2])     # 논문 Table 2 혼합 조건
      리스트는 sorted(ks) 순으로 위치 배정하고, 클라가 더 많으면 **패턴을 타일링**한다.
      타일링은 우리 선택이나 원문과 어긋나지 않는다: 원문의 5→10 확장에서
      [0.8,0.8,0.8,0.2,0.2] 의 10클라 대응은 [0.8]*6+[0.2]*4 이고, 이는 그 리스트를
      타일링한 것과 **다중집합이 같다**(6고·4저). 클라 id 는 원문 시뮬레이션에서
      교환 가능하므로 위치가 아니라 다중집합이 조건을 정한다.
      ※ 단 원문 10클라 집합이 5클라 집합의 타일링인 것은 **아니다** — [0.4]*10 이 없고
        대신 40/60 혼합이 들어간다. 그래서 PAPER_PLANS 에 10클라판을 **따로 실었다**.
  (B) plan= 을 안 주면 **첫 관측 한 번으로 기기 등급을 매기고 동결**한다(§2).
      우리 러너에는 손으로 줄 p 벡터가 없으므로 자동화를 위해 필요한 최소 보완이다.

  ────────────────────────────────────────────────────────────────────────────
  §2. (B) 의 배정 규칙 — **논문에 없다. 우리가 정의한 것이다.**
  ────────────────────────────────────────────────────────────────────────────
  원칙: 논문이 보는 축(기기 컴퓨팅 능력)만 보고, 논문이 안 보는 축(망)은 절대 안 본다.
    · 읽는 것   : ctl.comp1[k]  (p=1.0 배치당 연산초 = 컴퓨팅 능력의 유일한 실측 대리값)
                  ctl.gamma[k]  (연산의 p 지수 — 폭을 연산비용으로 환산하는 데만 씀)
    · 안 읽는 것: ctl.Ck, ctl.C, ctl.bytes1, ctl.predict  ← **망·바이트·시간 일체 금지**
      (self-test ① 의 _Spy 가 __getattr__ 로 실제 속성 접근을 가로채 이 금지를 검증한다.
       실행 결과: 읽은 필드 = ['comp1', 'gamma', 'ks'] · 금지 필드 접촉 없음)

  규칙:
      ref     = median_k( comp1[k] )                # 이 판의 '표준 기기' 속도
      cap_k   = ref / comp1[k]                      # 상대 컴퓨팅 능력 (클수록 빠른 기기)
      p_k     = max{ p ∈ 사다리 : p^γ_k ≤ cap_k · (1+tol) },  하한 p_min
      → 한 번 정하면 **영구 동결**. 이후 라운드는 재측정도 재배정도 하지 않는다.

  tol (기기등급 허용오차) = 0.15 의 근거 — **점수용 손잡이가 아니다**:
    우리 시험대의 클라는 전부 **같은 물리 머신**에서 전역 LOCK 아래 GPU 를 공유한다.
    즉 기기 이질성이 0 이고, comp1 의 차이는 전부 경합 지터다. 실측 지터(중앙값 대비
    최대비)는 4개 G2 로그에서 1.05 / 1.02 / 1.07 / 1.09 배다. 한편 우리 사다리의 한 칸
    (1.0→0.75)은 연산비로 (1/0.75)^1.2 = **1.40배** 차이다.
    → 허용오차는 [1.09, 1.40) 사이여야 한다: 그보다 작으면 **지터를 기기 등급으로 둔갑**
      시켜 없는 이질성을 만들어내고(허수아비), 그보다 크면 진짜 등급차도 못 본다.
      0.15 는 그 구간 안이며 양쪽 여유가 있다. 논문의 등급 간격이 2배(0.8/0.4/0.2)로
      성긴 것과도 어긋나지 않는다.
    ※ 그래도 이 값은 **우리 선택**이므로, self-test 는 tol=0.0(순수 비율)도 함께 돌려
      민감도를 그대로 보고한다. 숨기지 않는다.

  ────────────────────────────────────────────────────────────────────────────
  §3. 원문과 우리 설정이 다른 지점 — 전부 '원문은 X, 우리는 Y, 이유는 Z'
  ────────────────────────────────────────────────────────────────────────────
  (a) 사다리 : 원문은 p ∈ {0.2, 0.4, 0.8} 손지정. 우리는 (0.25, 0.5, 0.75, 1.0) 4단.
      이유 = 우리 사다리는 코드 고정값(controller.py/models.py)이고 decide() 의 반환은
      반드시 그 안이어야 한다. 원문 값은 **최근접 rung 으로 snap** 한다:
      0.2→0.25, 0.4→0.5, 0.8→**0.75**(1.0 아님). 원문은 클라 앞단에 p=1.0 을 쓴 적이
      없다(전 조건이 컴퓨팅 제약 가정). 다만 Algorithm 1 FedServer 가
      `if |W_{k,t,p_k}^C| ≠ |V_t^C|` 로 **전폭 클라를 명시적으로 분기**하므로 p_k=1.0 은
      알고리즘 내에 있다 → (B) 모드에서 최상위 등급은 1.0 을 받을 수 있다.
  (b) 하한   : 원문 최저 0.2, 우리 p_min=0.25. 이유 = 우리 사다리 최저 rung이고
      설계상 '배제 없는 학습' 하한이다. 원문도 최저 등급을 하한으로 쓰므로 의미는 같다.
  (c) 순수 FL 이 아니다 : 원문은 우리와 **같이** SFL 이다(오히려 일치). 단 골격이
      SplitFedV2 — MainServer 에 W^S 가 하나뿐이고 클라 루프에서 순차 갱신되며
      서버측 FedAvg 가 없다. 우리 fed_server.py 도 한 폭 안에서는 정확히 V2 다.
  (d) 서버 뒷단 구조 : 원문은 **전폭 서버 하나 + 입력 A_k 제로패딩**(Algorithm 1 의
      Â ← A ∪ Z[:,:,p_k:]). 우리는 **폭별 뒷단 + 라운드 끝 폭간 nested_average**.
      우리 구조를 유지한다. 이유 = ① 원문 구조면 서버 몫이 p 와 무관해져 **폭 노브의
      절반이 죽는다** → TTA 실험 자체가 성립 안 함. ② 기준선은 "우리 구조 위에 p 배정
      정책만 갈아끼운 것"이어야 변인이 하나로 통제된다. 원문의 서버 구조까지 옮기면
      '같은 알고리즘의 폭만 바꾼 비교'가 아니게 된다.
      ※ 부작용: 이 기준선은 원문보다 **서버 연산이 p 를 따라 줄어드는 이득을 덤으로
        받는다**. 즉 이 항목에서는 기준선이 원문보다 **유리**하다(불리가 아니다).
  (e) 전송 : 원문은 시뮬레이션이라 실제 전송이 없다(패딩은 서버에서). 우리는 슬라이스
      전송이라 바이트 ∝ p. decide() 는 바이트를 안 보므로 이 차이는 배정에 무관.
  (f) 집계 : §4 참조 — 원문 집계를 hsf_average() 로 **빼지 않고 별도 제공**한다.
  (g) 모델/학습 설정 : 원문 ResNet50 · 첫 bottleneck stage 뒤 절단 · R=100 · E=10 ·
      batch 256 · Adam lr 1e-4 · Dirichlet α∈{1,10} · 클라 5/10.
      우리 ResNet18 · cut 기본 2 · SGD lr 0.05 · batches 4~10 · 클라 4/8. 전부 다르다.
      → 원문의 절대 정확도(63~65% 상한)를 우리 목표 정확도 근거로 쓰면 안 된다.
      → 원문에 벽시계·TTA·바이트가 전무하므로 **'HSF 의 TTA' 라는 값은 존재하지 않는다.**
         우리 TTA 표에 원문 수치를 나란히 놓는 것은 불가능하다.

  ────────────────────────────────────────────────────────────────────────────
  §4. 빼지 않았지만 기본 경로에 안 물린 것 — 원문 FedServer 집계 (hsf_average)
  ────────────────────────────────────────────────────────────────────────────
  Algorithm 1 FedServer 는 ① 제로패딩 ② 0 아닌 것만 세는 **비가중** 평균이다:
      w_{i,j} ← [ Σ_k w^k_{i,j}·1(w^k_{i,j} ≠ 0) ] / [ Σ_k 1(w^k_{i,j} ≠ 0) ]
  우리 nested_average 와 정확히 두 군데가 다르다:
      · 마스크 : 원문 1(w≠0) 값판정  vs  우리 shape 슬라이스 판정
        → 원문 마스크는 **실제 학습됐는데 값이 정확히 0.0 인 파라미터를 집계에서 빠뜨린다**
          (BatchNorm β·running_mean 은 초기값이 0). 논문은 이 취약점을 언급하지 않는다.
      · 가중   : 원문 비가중(클라 수로만 나눔)  vs  우리 n(표본 수) 가중
  이 파일은 원문 집계를 **hsf_average() 로 충실히 구현해 두었고**(빼지 않았다),
  self-test 가 두 마스크의 차이를 실제로 재서 보여준다. 다만 **기본 비교 경로에는
  물리지 않는다** — 물리면 변인이 '폭 배정'과 '집계' 둘이 되어 G2 비교가 무너진다.
  종합자에게: 원문 완전 재현을 원하면 fed_server.Hub.aggregate 의 nested_average 를
  hsf_average 로 갈아끼우면 된다(그때는 별도 실험으로 분리해 보고할 것).

  ────────────────────────────────────────────────────────────────────────────
  §5. 우리 코드에 없어서 못 넣은 부품 / 확인 못 한 것 (종합자 보고용)
  ────────────────────────────────────────────────────────────────────────────
  · 자기증류·sBN : 원문도 안 쓴다(FjORD 에서 OD 만 가져왔다). 우리와 일치 → 누락 없음.
  · fed_server.py 의 --policy 에 static 이 없다. 다만 **--policy oracle + --oracle-plan
    이 이미 정확히 '라운드 불변 정적 계획'** 이다(main() 이 시작 시 plan.update 를 한 번
    하고, 라운드 루프에서 plan 을 고치는 분기는 ours/random 뿐이다 — 코드 확인함).
    → to_oracle_plan_json() 으로 그대로 넘길 수 있다. fed_server 수정 불필요.
    ★ 단 run_g2.py 의 true_oracle(참 회선값 + 4^N 완전탐색)은 HSF 가 아니다.
      그것은 망까지 다 아는 **상한선**이지 HSF 재현이 아니다. 혼동하면 허수아비가 된다.
  · 원문의 유일한 정량 비교 상대인 FedAvg 대조군이 우리 러너에 없다(uniform 은 전폭
    SplitFed 이지 FedAvg 가 아니다). 이 파일 범위 밖.
  · 학회 2쪽판(pp.1229-1230) **원문 미확보**(DBpia 유료·본문 비공개). 제목에 '통신환경'이
    들어 있어 '거기서는 대역폭을 봤을 가능성'을 100% 배제하지 못한다. 다만 (a) 2쪽,
    (b) 학회지판 서론이 "논문[14]에서 제안한 기법을 확장하여"라고 명시, (c) 확장판에서
    제목·초록·본문·Table 1 의 통신 항목이 전부 사라짐, (d) 확장판에 대역폭·시간 수치가
    전무 → 위협 가능성은 낮다고 판단하나 **확인은 못 했다.**
  · 저자 공개 코드 저장소 없음. 대조 검증 경로는 저자 메일 요청뿐이다.

  ────────────────────────────────────────────────────────────────────────────
  §6. 이 기준선이 우리 시험대에서 어떻게 행동할 것인가 — 미리 밝혀둔다
  ────────────────────────────────────────────────────────────────────────────
  우리 G2 조건의 이질성은 **회선**(20/40/60/80 Mbps HTB)이고, 클라는 전부 같은 머신이라
  **기기 이질성이 0** 이다. HSF 는 기기만 보므로 → 등급이 전부 같게 나오고 → 전폭 유지.
    조건1 hold          : PASS 예상 (좁힐 이유가 없으니 안 좁힌다 — 우연이 아니라 정합)
    조건2 cut_straggler : FAIL 예상 (회선 낙오자를 **원리적으로 볼 수 없다**)
    조건3 react         : FAIL 예상 (재측정 자체가 없고, 교란도 회선 교란이다)
    조건4 cut_all       : FAIL 예상 (벽시계 목적함수가 없다)
  ★ 이 FAIL 들은 구현 실패가 아니라 **논문이 시키는 대로 한 결과**다. 점수를 올리려고
    Ck/C 를 훔쳐보면 그 순간 이 비교 전체가 무효가 된다. 하지 않았다(§2 감시 참조).

  ────────────────────────────────────────────────────────────────────────────
  §7. ★ 이 기준선이 우리 시험대에서 불리해지는 지점 — 종합자 필독 (허수아비 방어)
  ────────────────────────────────────────────────────────────────────────────
  나중에 "HSF 를 허수아비로 세웠다"는 비판이 나올 지점을 **우리가 먼저 적어 둔다.**

  (H1) 우리 시험대에는 HSF 가 볼 것이 없다 — 이게 가장 큰 불리함이다.
    HSF 는 기기 컴퓨팅 능력으로 p_k 를 정한다. 그런데 우리 G2 클라는 **전부 같은 물리
    머신**에서 전역 LOCK 아래 같은 GPU 를 공유한다 → 기기 이질성이 사실상 0 이다.
    실측 comp1 의 중앙값 대비 최대비는 4개 로그에서 1.05/1.02/1.07/1.09 배뿐이고,
    이것도 기기 차이가 아니라 **경합 지터**다. 반면 우리가 만든 이질성은 전부 회선이다.
    → HSF 는 원리적으로 볼 수 없는 축에서 시험받고 있다. 이 조건에서 HSF 가 전폭을
      유지하는 것은 **논문대로 옳게 동작한 것**이지 무능이 아니다.
    → 공정한 병기는 "우리 방법이 HSF 보다 낫다"가 아니라
      **"회선이 이질적이고 기기가 균질한 환경에서는 기기만 보는 정적 배정이 원리적으로
        낙오자를 볼 수 없다"** 이다. 전자로 쓰면 그게 허수아비다.
    → 반대 실험도 정직하게 밝혀야 한다: **기기가 이질적인 환경(G0/G1 처럼 클라를 서로
      다른 기기에 두는 조건)에서는 HSF 가 비자명한 배정을 내고 우리와 격차가 줄어든다.**
      우리는 그 조건을 아직 안 돌렸다.

  (H2) 원문이 최적화하는 축과 우리가 재는 축이 다르다.
    원문의 성능 축은 **정확도 하나**이고 벽시계·TTA·바이트가 전무하다. 우리 판정 기준은
    TTA 다. 즉 HSF 는 **자기가 겨냥한 적 없는 지표로 채점되고 있다.**
    → "HSF 의 TTA 가 나쁘다"는 문장은 쓸 수 없다. 쓸 수 있는 것은 "정적·기기전용 배정을
      우리 TTA 환경에 놓으면 이렇게 된다" 까지다.

  (H3) 반대로 이 기준선이 원문보다 **유리해진 지점도 있다** (§3-d).
    우리 구조(폭별 뒷단)를 그대로 쓰므로 서버 연산도 p 를 따라 줄어드는 이득을 덤으로
    받는다. 원문 구조(전폭 서버 하나 + 입력 제로패딩)였다면 폭을 줄여도 서버 몫이 안
    줄어 더 느렸을 것이다. 즉 시간 축에서 이 기준선은 원문보다 **후하게** 구현돼 있다.

  (H4) tol 은 우리가 넣은 손잡이다 — 그리고 **끄면 점수가 올라간다.**
    tol=0.0 이면 조건2 가 PASS 로 바뀐다. 그러나 그것은 **지터 1.5% 를 기기 등급으로
    둔갑시켜 얻은 가짜 통과**다(자세한 근거는 self-test ② 출력). 점수가 높은 쪽을
    고르면 없는 이질성을 발명하는 것이므로 기본값은 tol=0.15 로 둔다.
    → 이 선택은 점수를 **낮추는** 방향이다. 숨기지 않고 self-test 가 둘 다 출력한다.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from controller import LADDER                                    # noqa: E402


def _median(xs):
    s = sorted(xs)
    n = len(s)
    if not n:
        return None
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


class Baseline:
    name = "HeteroSplitFed(정적 p_k)"
    paper = ("J.-H. Ryu, H. Yang, J-KICS 50(2):195-204, Feb. 2025, "
             "DOI 10.7840/kics.2025.50.2.195 (학회판: KICS Winter Conf. 2024, pp.1229-1230)")

    # 논문 Table 2 가 실제로 쓴 p 리스트 — **원문에서 그대로 옮겼다** (ft.txt 대조 완료).
    #   5클라는 3열(FedAvg α=10 / HSF α=10 / HSF α=1), 10클라는 2열(HSF α=10 / HSF α=1).
    #   ★ FedAvg 대조군은 **5클라 조건에만** 있다 — 10클라·α=1 의 FedAvg 값은 논문에 없다.
    #   주석의 % 는 원문 Table 2 수치(100라운드 중 검증 최고 정확도). 우리 설정과 무관하며
    #   ResNet50·Adam lr 1e-4·E=10·batch 256 에 묶인 값이다 — 우리 목표 정확도 근거 금지.
    PAPER_PLANS = {
        # 5클라 : (FedAvg α=10, HSF α=10, HSF α=1)
        "all_high":  [0.8, 0.8, 0.8, 0.8, 0.8],          # 64.887 / 63.707 / 57.398
        "all_mid":   [0.4, 0.4, 0.4, 0.4, 0.4],          # 55.968 / 59.499 / 51.779
        "mix_3h2l":  [0.8, 0.8, 0.8, 0.2, 0.2],          # 50.587 / 56.818 / 51.226
        "mix_1h4l":  [0.8, 0.2, 0.2, 0.2, 0.2],          # 46.100 / 51.630 / 45.914
        "all_low":   [0.2, 0.2, 0.2, 0.2, 0.2],          # 45.874 / 50.896 / 39.101
        # 10클라 : (HSF α=10, HSF α=1). **5클라 집합의 타일링이 아니다** —
        #   [0.4]*10 이 없고 대신 40/60 혼합(mix10_4h6l)이 들어간다.
        "all_high10":  [0.8] * 10,                        # 64.801 / 61.475
        "mix10_6h4l":  [0.8] * 6 + [0.2] * 4,             # 56.203 / 51.782
        "mix10_4h6l":  [0.8] * 4 + [0.2] * 6,             # 51.757 / 48.122   ← 5클라 대응 없음
        "mix10_2h8l":  [0.8] * 2 + [0.2] * 8,             # 52.118 / 48.542
        "all_low10":   [0.2] * 10,                        # 52.486 / 48.341
    }
    # ★ 적대 검토 대비 — 원문이 언급하지 않는 비단조성을 우리가 먼저 짚어둔다:
    #   10클라 α=10 에서 [0.2]*10(52.486) > [0.8]*2+[0.2]*8(52.118) > [0.8]*4+[0.2]*6(51.757).
    #   즉 **고성능 클라를 섞는 것이 오히려 손해로 나온 칸이 둘**이다. 본문은 이를 언급하지
    #   않고 "클라 수가 증가해도 마찬가지로 기여함을 확인" 이라고만 쓴다.
    #   또 α=1 에서는 [0.2]*5(39.101) < [0.8,0.2×4](45.914) 로 순서가 뒤집힌다.
    #   → "HSF 가 폭 이질성의 이득을 보였다" 는 주장은 조건부로만 성립한다.

    def __init__(self, ks, p_min=0.25, plan=None, tol=0.15, **kw):
        """ks = 클라이언트 id 리스트.

        plan : None  → 첫 관측으로 기기 등급을 한 번 매기고 동결 (§1-B, 규칙은 우리 것)
               list  → 논문 Table 2 방식. sorted(ks) 순 위치 배정 + 부족하면 타일링 (§1-A)
               dict  → {cid: p} 그대로. 둘 다 사다리 최근접 rung 으로 snap 된다.
        tol  : 기기등급 허용오차. §2 참조. plan 을 주면 쓰이지 않는다.
        """
        self.ks = list(ks)
        self.p_min = p_min
        self.tol = float(tol)
        self.given = plan
        self.rungs = [p for p in LADDER if p >= p_min] or [min(LADDER)]
        self.plan = None            # ★ 동결된 배정. None 이면 아직 안 정해짐
        self.frozen_at = None
        self.trace = []             # 등급 산출 내역 (보고용)
        self._ctl = None
        self._ks = list(ks)
        self._r = 0                 # rule_bench 가 라운드 번호를 안 넘겨줘서 두는 내부 카운터
        self._run_r = 0             # **현재 실행 안에서의** 라운드 (frozen_at 보고용)

    # ── 사다리 맞춤 ────────────────────────────────────────────
    def _snap(self, v):
        """임의의 p 를 우리 사다리의 최근접 rung 으로. (원문 0.2/0.4/0.8 → 0.25/0.5/0.75)"""
        return min(self.rungs, key=lambda q: (abs(q - v), -q))

    def _expand(self, given, ks):
        """논문식 p 리스트를 클라 수에 맞춘다. 부족하면 **타일링**(원문의 5→10 확장 방식)."""
        if isinstance(given, dict):
            return {k: self._snap(given[k]) if k in given else 1.0 for k in ks}
        lst = list(given)
        return {k: self._snap(lst[i % len(lst)]) for i, k in enumerate(sorted(ks))}

    # ── 기기 등급 (§2 — 논문에 없는, 우리가 정의한 규칙) ──────────
    def _grade(self, ctl, ks, comp):
        gam = getattr(ctl, "gamma", {}) or {}
        vals = [comp[k] for k in ks if comp.get(k)]
        ref = _median(vals)
        rows, plan = [], {}
        for k in ks:
            c = comp.get(k)
            if not c:                       # 관측이 없는 클라는 벌하지 않는다 (전폭)
                plan[k], cap = 1.0, None
            else:
                cap = ref / c               # 상대 컴퓨팅 능력 (>1 이면 표준보다 빠름)
                g = gam.get(k, 1.2)         # G0 실측 중앙값. 연산 ∝ p^γ
                budget = cap * (1.0 + self.tol)
                p = self.p_min
                for q in self.rungs:        # q^γ 는 q 에 단조증가 → 마지막으로 통과한 게 최대
                    if q ** g <= budget:
                        p = q
                plan[k] = p
            rows.append((k, c, cap, plan[k]))
        self.trace.append({"ks": list(ks), "ref": ref, "tol": self.tol, "rows": rows})
        return plan

    def _reset(self, ctl, ks):
        """새 실행(새 로그·다른 클라 집합)이 시작되면 동결을 푼다.

        논문 위반이 아니다 — 한 번의 학습 실행 안에서는 여전히 영구 동결이다.
        rule_bench 가 하나의 Baseline 인스턴스로 4개 조건을 연달아 재생하기 때문에
        필요한 **시험대 적응**이다."""
        self._ctl, self._ks = ctl, list(ks)
        self.ks = list(ks)
        self.plan = None
        self.frozen_at = None
        self._run_r = 0

    # ── 결정 ───────────────────────────────────────────────────
    def decide(self, rnd, ctl, batches):
        """반환 {client_id: width}.  **batches 는 쓰지 않는다** — 원문에 배치·시간 개념의
        배정 근거가 없다. ctl 에서도 comp1/gamma 만 읽는다 (망 관련 필드 접근 금지)."""
        ks = list(getattr(ctl, "ks", None) or self.ks)
        if (ctl is not self._ctl) or (ks != self._ks):
            self._reset(ctl, ks)
        self._r = rnd + 1                      # rule_bench 용 내부 라운드 카운터
        r_in_run, self._run_r = self._run_r, self._run_r + 1

        # ★ 이미 정해졌으면 끝. 재측정도 재배정도 없다 (p_k 에 라운드 첨자 t 가 없다).
        if self.plan is not None:
            return dict(self.plan)

        # (A) 논문 그대로 — p 는 외생 입력
        if self.given is not None:
            self.plan = self._expand(self.given, ks)
            self.frozen_at = r_in_run
            return dict(self.plan)

        # (B) 프로파일 라운드 한 번으로 기기 등급 → 동결
        comp = getattr(ctl, "comp1", {}) or {}
        if not any(comp.get(k) for k in ks):
            return {k: 1.0 for k in ks}        # 라운드 0: 아직 관측이 없다 → 등급 보류
        self.plan = self._grade(ctl, ks, comp)
        self.frozen_at = r_in_run
        return dict(self.plan)

    # ── 러너 연결 도우미 ────────────────────────────────────────
    def to_oracle_plan_json(self):
        """fed_server.py 에 그대로 넘길 수 있는 정적 계획 JSON.

            python sfl/fed_server.py --policy oracle --oracle-plan '<이 문자열>' ...

        fed_server.main() 은 시작 시 한 번만 plan.update 하고 라운드 루프에서 plan 을
        고치는 분기는 ours/random 뿐이다 → oracle 경로가 곧 '라운드 불변 정적 계획'이다.
        (--policy static 을 새로 만들 필요가 없다. fed_server.py 는 읽기 전용이다.)"""
        return json.dumps(self.plan or {k: 1.0 for k in self.ks})


# ══════════════════════════════════════════════════════════════════════════
#  원문 Algorithm 1 FedServer 집계 — 충실 구현 (§4). 기본 경로엔 안 물린다.
# ══════════════════════════════════════════════════════════════════════════
def hsf_average(full_sd, updates):
    """HeteroSplitFed 의 FedServer 집계. nested_average 와 **자리를 바꿔 끼울 수 있게**
    같은 시그니처를 쓴다. updates = [(sd, n_samples)] — 단 **n 은 무시한다**(비가중).

        ① 제로패딩 : 소폭 상태 sd 를 전폭 크기 텐서에 앞쪽부터 채우고 나머지는 0
        ② 변형평균 : w ← Σ_k w^k·1(w^k≠0) / Σ_k 1(w^k≠0)

    우리 nested_average 와의 차이 (원문은 X, 우리는 Y):
      · 마스크 : 원문 1(w≠0) 값판정 / 우리 shape 슬라이스 판정.
        → 원문은 **학습됐지만 값이 정확히 0.0 인 파라미터를 집계에서 빠뜨린다.**
          BatchNorm 의 β(bias)·running_mean 은 초기값이 0 이므로 초기 라운드에 위험하다.
          논문은 이 취약점을 언급하지 않는다.
      · 가중   : 원문 비가중(클라 수로만 나눔) / 우리 n(표본 수) 가중.
        Dirichlet 비균등 분할 실험에서 실제로 결과를 바꾼다.
      · 분모 0 : 원문에 규정이 없다. 여기서는 전역 기존값을 유지한다 (우리 선택).
    """
    import torch
    acc = {k: torch.zeros_like(v, dtype=torch.float64) for k, v in full_sd.items()}
    cnt = {k: torch.zeros_like(v, dtype=torch.float64) for k, v in full_sd.items()}
    for sd, _n in updates:                       # ★ _n 무시 = 비가중 (원문 그대로)
        for k, v in sd.items():
            pad = torch.zeros_like(acc[k])       # ① V_{k,t}^C — 전부 0 인 전폭 텐서
            idx = tuple(slice(0, s) for s in v.shape)
            pad[idx] = v.double()                #    W ∪ V[:, :, p_k:]  (zero-padding)
            m = (pad != 0).double()              # ② 1(w ≠ 0)  ← 값판정 마스크
            acc[k] += pad * m
            cnt[k] += m
    out = {}
    for k in full_sd:
        m = cnt[k] > 0
        v = torch.where(m, acc[k] / cnt[k].clamp(min=1), full_sd[k].double())
        out[k] = v.to(full_sd[k].dtype)
    return out


# ══════════════════════════════════════════════════════════════════════════
#  자기시험
# ══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "..", "_archive", "rule_search_2026-08"))
    from rule_bench import bench
    b = Baseline([f"c{i}" for i in range(4)])
    bench(lambda ctl, batches, alpha=1.2: b.decide(getattr(b, "_r", 0), ctl, batches),
          Baseline.name, verbose=True)

    # ── 이하 추가 진단 (필수 블록은 위가 전부) ─────────────────────────
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    def dump(bl, title):
        print(f"\n  ── {title}: 기기 등급 산출 내역 ──")
        for t in bl.trace:
            print(f"   ref(중앙값)={t['ref']:.4f}  tol={t['tol']}")
            for k, c, cap, p in t["rows"]:
                cs = f"{c:.4f}" if c else "  없음"
                ps = f"{cap:.3f}" if cap else "  -  "
                print(f"     {k}  comp1={cs}  cap=ref/comp1={ps}  → p={p}")

    dump(b, "기본 tol=0.15")
    print(f"\n  동결 시점 = 각 실행의 decide() 첫 호출(#{b.frozen_at}) — 프로파일 라운드 직후 1회."
          f"\n  이후 전 라운드 동일. 재측정·재배정 없음 (p_k 에 라운드 첨자 t 가 없다).")
    print(f"  fed_server 용 정적 계획 = {b.to_oracle_plan_json()}")
    print("  ※ 위 4개 표는 시험대의 4개 조건을 **각각 새 실행**으로 재생한 것이다"
          "\n    (조건마다 Controller 가 새로 생성됨 → 동결 해제. §_reset 참조).")

    # ① 망 관련 필드를 정말 안 읽었는가 — 속성 접근 감시로 실증
    print("\n" + "=" * 78 + "\n  감시: decide() 가 ctl 의 어떤 필드를 읽는가\n" + "=" * 78)

    class _Spy(object):
        def __init__(self, o):
            object.__setattr__(self, "_o", o)
            object.__setattr__(self, "seen", set())

        def __getattr__(self, n):
            self.seen.add(n)
            return getattr(object.__getattribute__(self, "_o"), n)

    try:
        from controller import Controller
        from rule_bench import load, replay          # noqa: F401
        rows = load("g2_static_ours.jsonl")
        ctl = Controller(sorted(rows[0]["per_client"]))
        ctl.p = dict(rows[0]["plan"])
        obs = {k: tuple(v) for k, v in rows[0]["per_client"].items()}
        ctl.observe_round(obs, max(v[3] for v in obs.values()))
        spy = _Spy(ctl)
        Baseline([f"c{i}" for i in range(4)]).decide(1, spy, 8)
        banned = {"Ck", "C", "bytes1", "predict"} & spy.seen   # 망·바이트·시간 축
        print(f"   읽은 필드 : {sorted(spy.seen)}")
        print(f"   금지 필드(망·바이트·시간) 접촉 : "
              f"{sorted(banned) if banned else '없음 ✓  — 기기만 봤다'}")
    except Exception as e:
        print(f"   감시 건너뜀: {e}")

    # ② 민감도 — tol 은 우리가 넣은 손잡이다. 껐을 때도 그대로 보고한다
    print("\n" + "=" * 78 +
          "\n  민감도: tol=0.0 (순수 비율, 지터를 기기등급으로 그대로 받음)\n" + "=" * 78)
    b0 = Baseline([f"c{i}" for i in range(4)], tol=0.0)
    bench(lambda ctl, batches, alpha=1.2: b0.decide(getattr(b0, "_r", 0), ctl, batches),
          "HSF(정적) tol=0.0", verbose=False)
    dump(b0, "tol=0.0")
    print("""
  ★★ 위 조건2 PASS 를 '더 나은 설정' 으로 읽지 마라 — **가짜 통과다.** ★★
    tol=0.0 은 중앙값보다 조금이라도 느리면 곧바로 한 칸 내린다. 그런데 위 표에서
    c1/c2 의 comp1 은 중앙값 대비 겨우 0.2~1.5% 느릴 뿐이고, 우리 클라는 전부 **같은
    GPU 를 공유하는 같은 머신**이라 그 차이는 기기 등급이 아니라 **경합 지터**다.
    (사다리 한 칸은 연산비로 (1/0.75)^1.2 = 1.40배 차이다. 1.5% 는 그 1/27 이다.)
    즉 tol=0.0 의 조건2 PASS 는 '낙오자를 찾아낸 것' 이 아니라 **동전을 던져 2명을 고른
    것**이며, 그 2명이 회선 낙오자와 일치한다는 보장도 없다. 실제로 조건2 에서 좁혀진
    c1/c2 는 회선이 40/60Mbps 인 중간 클라이고, 진짜 낙오자인 c0(20Mbps)은 안 좁혔다.
    → 시험대 점수를 올리려고 tol 을 끄는 것은 **없는 기기 이질성을 발명하는 것**이고,
      그 순간 이 기준선은 허수아비가 된다. 기본값 tol=0.15 를 유지한다(§7-H4).""")

    # ③ 논문 Table 2 그대로 — p 를 손으로 지정하는 literal 모드
    print("\n" + "=" * 78 +
          "\n  논문 Table 2 혼합 조건 [0.8,0.8,0.8,0.2,0.2] → 사다리 snap\n" + "=" * 78)
    bp = Baseline([f"c{i}" for i in range(4)], plan=Baseline.PAPER_PLANS["mix_3h2l"])
    bench(lambda ctl, batches, alpha=1.2: bp.decide(getattr(bp, "_r", 0), ctl, batches),
          "HSF(정적) 논문 Table 2 [0.8,0.8,0.8,0.2,0.2]", verbose=False)
    for lst_name in ("mix_3h2l", "mix_1h4l", "all_low", "mix10_6h4l"):
        lst = Baseline.PAPER_PLANS[lst_name]
        for n in (4, 5, 10):
            ks_n = [f"c{i}" for i in range(n)]
            bn = Baseline(ks_n, plan=lst)
            got = bn._expand(lst, ks_n)
            hi = sum(1 for v in got.values() if v > 0.5)
            print(f"   {lst_name:12s}(원문 {len(lst)}개) → {n:2d}클라  "
                  f"{[got[k] for k in ks_n]}  (고폭 {hi}/{n})")
    print("   ※ 0.2→0.25, 0.4→0.5, 0.8→0.75 로 snap. 원문은 클라 앞단에 p=1.0 을 쓴 적이 없어")
    print("     0.8 은 1.0 이 아니라 0.75 로 내려붙인다 (§3-a).")

    # ④ 원문 집계 vs 우리 집계 — 빼지 않았음을 실측으로 보인다 (§4)
    print("\n" + "=" * 78 +
          "\n  원문 FedServer 집계(hsf_average) vs 우리 nested_average\n" + "=" * 78)
    try:
        import torch
        from models import nested_average
        full = {"conv.weight": torch.zeros(4, 3),        # 전폭
                "bn.bias": torch.zeros(4)}               # BatchNorm β — 초기값 0
        u_full = {"conv.weight": torch.ones(4, 3) * 2.0,
                  "bn.bias": torch.zeros(4)}             # ★ 학습했지만 값이 정확히 0.0
        u_half = {"conv.weight": torch.ones(2, 3) * 4.0,
                  "bn.bias": torch.ones(2) * 1.0}
        ups = [(u_full, 100), (u_half, 100)]             # 표본 수 동일
        ours = nested_average(full, ups)
        hsf = hsf_average(full, ups)
        print(f"   conv.weight[0] 우리 {ours['conv.weight'][0].tolist()}  "
              f"원문 {hsf['conv.weight'][0].tolist()}   (동일: 값이 0 이 아니므로)")
        print(f"   bn.bias        우리 {ours['bn.bias'].tolist()}")
        print(f"   bn.bias        원문 {hsf['bn.bias'].tolist()}")
        print("   → 앞 2칸: 전폭 클라의 β=0.0 이 원문 마스크에서 **학습 안 한 것으로 오인**되어")
        print("     분모에서 빠진다. 우리 1(w≠0) 재현이 맞고, 논문은 이 취약점을 언급 안 한다.")
        ups2 = [(u_full, 900), (u_half, 100)]            # 표본 9:1 비균등
        o2, h2 = nested_average(full, ups2), hsf_average(full, ups2)
        print(f"   표본 9:1 일 때 conv.weight[0] 우리(표본가중) {o2['conv.weight'][0][0]:.3f}  "
              f"원문(비가중) {h2['conv.weight'][0][0]:.3f}  ← 가중 차이가 실제로 값을 바꾼다")
    except Exception as e:
        print(f"   집계 대조 건너뜀: {e}")
