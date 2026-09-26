# -*- coding: utf-8 -*-
"""기준선 B-HeteroFL — 폭 배정 정책만 구현한 재현판.

  Enmao Diao, Jie Ding, Vahid Tarokh,
  "HeteroFL: Computation and Communication Efficient Federated Learning for
   Heterogeneous Clients", ICLR 2021.  arXiv:2010.01264.

  원문 확보 (2계통 교차대조, 이번 구현에서 직접 재확인함)
    (1) 본문 : https://ar5iv.labs.arxiv.org/html/2010.01264   §3.1 / §3.2 / §3.3 / Alg.1 / §4
    (2) 저자 코드 : github.com/diaoenmao/HeteroFL-Computation-and-Communication-
                   Efficient-Federated-Learning-for-Heterogeneous-Clients (master)
                   src/utils.py(process_control), src/fed.py(make_model_rate/split_model/
                   combine), src/modules/modules.py(Scaler), src/models/resnet.py
    본문과 코드가 어긋나는 곳은 **코드를 정본**으로 삼고 그 지점을 아래에 표시했다.

  ══ 이 논문이 하는 일 (요지) ═══════════════════════════════════════════
  §3.1  은닉 채널 수를 d_l^p = r^(p-1)·d_g 로 줄인 **접두(prefix) 부분망**을 배포한다.
        r = 채널 축소비, p = 1..P 등급 번호.  §4 에서 r=0.5, P=5.
        등급 {a,b,c,d,e} 의 **폭(채널) 비** = 1, 0.5, 0.25, 0.125, 0.0625.
        (파라미터 수 비는 그 제곱  R = r^(2(p-1))  — 폭 비와 절대 혼동하지 말 것)
        반올림은 저자 resnet.py 의 ceil(model_rate*base) → 우리 models.w(c,p) 와 동일 연산.
  Alg.1 "Determine computation complexity level p based on L_m".
        L_m 정의(§3.1 원문 인용): "The local capabilities information L_m is an
        abstraction of the computation and communication capabilities of a local client m."
        → **서버가 t=0 전에 이미 받아 둔 외생 입력**이다.
        갱신은 "Update L_{1:K}, eta   (Optional)" — 말 그대로 선택사항.
        ★ L_m 을 **어떻게 재는지, 등급으로 어떻게 사상하는지 논문은 한 줄도 주지 않는다.**
  §4    배정 시나리오가 둘이고 **둘 다 매 라운드 실측을 보지 않는다.** (원문 인용)
        "We annotate Fix for experiments with a fixed assignment of computation
         complexity levels, and Dynamic for local clients uniformly sampling
         computation complexity levels at each communication round."
        - Fix     : 한 번 정하고 학습 내내 불변.
        - Dynamic : 매 라운드 비율 multinomial 재추첨. **기기 능력과 무관한 재추첨**이다.
                    저자 fed.py: torch.multinomial(cfg['proportion'],
                                 num_samples=num_users, replacement=True)
  §3.3  Scaler : 학습 시 활성값을 rate=p_k/p_global 로 나눔, 추론 시 항등.  → [M1]
  §3.2  sBN    : 학습 중 BN 러닝통계 미추적 + 학습 후 서버가 클라를 순회해 누적 수집. → [M2]
  §3.1  집계   : 그 원소를 **실제로 가진 클라만** 평균. 저자 fed.py combine() 의 count 텐서
                (count += 1 → 마지막에 count 로 나눔) = **머릿수 균등 평균**. → [M3]

  ★ 이 논문의 성격 = **폭 배정이 정적이거나(Fix), 능력과 무관한 무작위(Dynamic)다.**
    바로 그래서 우리(매 라운드 망·기기를 실측해 폭을 다시 정함)의 대조축이 된다.
    여기에 실측 반응성을 한 방울이라도 섞으면 대조 자체가 무의미해진다 — 섞지 않았다.
    아래 decide() 에는 Fix 경로에 재계산 자체가 존재하지 않는다.

  ══ 원문 대 우리 설정 — 차이를 전부 여기 모았다 (원문은 X / 우리는 Y / 이유는 Z) ══
  [D1] 사다리.
       X: r=0.5, P=5 → 폭 {1, 0.5, 0.25, 0.125, 0.0625}.
       Y: LADDER=(0.25, 0.5, 0.75, 1.0), 하한 p_min=0.25.
       Z: a/b/c(1.0/0.5/0.25) 는 우리 칸과 **정확히 일치**한다. 그러나
          d(0.125)·e(0.0625) 는 우리 사다리에 칸이 없어 p_min=0.25 로 접힌다.
          → 유효 등급 수 P_eff = 3. 절대 정확도 수치를 논문과 나란히 놓으면 안 된다.
          → 0.75 는 0.5 의 거듭제곱이 아니라 **HeteroFL 에 없는 칸**이다. 쓰지 않는다.
            (쓰면 논문에 없는 개선을 넣는 것이 된다 — 충실도 규칙 4 위반)
          ※ d·e 를 0.25 로 올려 접는 것은 HeteroFL 을 **정확도 쪽으로는 유리**하게,
            **시간 쪽으로는 불리**하게 만든다. 순효과는 미정 — 보고 대상.
  [D2] 등급 비율(model_mode).
       X: §4 의 'a-b-c-d-e' 표기. 두 등급 혼합의 뜻은 원문이 명시한다 —
          "in 'c-e', 'b-e', or 'a-e', half of the clients are trained with larger
           models ... while the other half are trained with the model 'e'"
          → 두 등급 혼합 = 50/50 = 저자 코드 표기 'a1-e1'. Dynamic 은 "uniformly
            sampling" 이므로 다등급도 균등 확률로 읽는 것이 본문과 정합한다.
       Y: 기본값 model_mode="a1-b1-c1" (= 논문의 'a-b-c' 설정, 균등).
       Z: 'a-b-c' 는 우리 사다리에 **손실 없이** 1:1로 들어가는 유일한 다등급 설정이다.
          5등급 'a1-b1-c1-d1-e1' 도 인자로 받는다(d·e 는 [D1] 대로 접힘).
       ※ 재확인한 문장: "the ratio of the number of weak learners is fixed to 50%"
          (§4, 표 해설). 조사자가 재확인 못 했다고 표시한 문장인데 **실재한다.**
          두 등급 혼합의 50/50 을 가리키는 말로 읽힌다.
  [D3] L_m 의 출처와 갱신 주기. ★ 이 파일의 충실도 핵심.
       X: 외생 입력. 측정 절차 없음. 갱신은 Optional.
          저자 Fix 코드는 능력을 **아예 보지 않고** 클라 인덱스 순서로 등급을 얹는다.
       Y: assign="capability"(기본) — **프로파일 라운드(첫 관측) 딱 한 번만** 보고
          등급을 확정한 뒤 **영구 동결**. 이후 라운드에서 재계산 경로가 없다.
          assign="index" — 저자 코드 그대로 인덱스 순서(능력 완전 무시).
       Z: Alg.1 의 "based on L_m" 한 줄이 capability 근거의 전부다. 매 라운드
          다시 재는 것은 우리 방법이지 이 논문이 아니므로 1회로 못 박았다.
  [D4] L_m 산식.
       X: 없음(논문이 안 준다).
       Y: L_m ≈ comp1[k] + bytes1[k]*8/Ck[k]   (배치당 전폭 연산초 + 자기회선 전송초)
       Z: §3.1 의 "computation and communication capabilities" 를 그대로 옮긴 최소 근사.
          ★ 공유회선 결합항(Σ_j bytes_j/C_shared)은 **일부러 뺐다.** 그건 우리
            controller.predict 의 기여이고 HeteroFL 에는 대응 개념이 전무하다
            (원문은 통신을 파라미터 수로만 논한다). ctl.predict() 를 호출하지 않는 이유.
  [D5] 분할.
       X: 순수 FL — 모델 전체가 클라에 있다.
       Y: SFL — 앞단만 클라, 뒷단은 서버.
       Z: 폭 배정 규칙 자체는 그대로 옮겨지나 집계 적용 지점이 앞단/뒷단 둘로 쪼개진다
          (fed_server.aggregate). 배정 정책 파일인 여기서는 영향 없음.
  [D6] 규모/참여.
       X: M=100 클라, 라운드당 C=0.1 (10대) 부분 참여. (원문: "We have 100 clients,
          and the fraction C of active clients per communication round is 0.1")
       Y: 우리 G2 는 4~8대 **전원** 참여.
       Z: HeteroFL 의 이득(작은 부분망이 더 많은 지역모델과 평균됨)이 우리 규모에서
          **축소된다.** 이건 우리가 HeteroFL 을 **불리하게** 만드는 쪽이다 — 반드시 보고.
  [D7] 이질성의 원인.
       X: **기기 등급**을 받는다.
       Y: 우리 이질성의 주 원인은 **망**이다.
       Z: L_m 정의가 "computation and communication capabilities" 라 자기회선을 L_m 에
          넣는 것은 원문 정의 안이다. 다만 그 측정은 1회뿐이고, 망이 변해도 반응하지 않는다.
  [D8] 소규모 N 에서의 fix 분배.
       X: 저자 process_control 은 num_users // sum(proportion) 을 쓴다. M=100 전제라
          이 몫이 0 이 되는 경우를 처리하지 않는다(모자란 꼬리는 **마지막 등급으로 패딩**).
       Y: 몫이 0 이면(등급 수 > 클라 수) 앞에서부터 등급을 하나씩 준다.
       Z: 저자 코드 그대로면 IndexError 로 죽는다. 분배 의도(등급을 고루 깔기)를
          최소 변경으로 살린 것. 패딩 규칙 자체는 저자 코드 그대로 유지했다.

  ══ ■ 우리 코드에 부품이 없어 이 기준선이 원 논문보다 불리해지는 지점 ══════
     (구현하지 않았다. models.py / fed_server.py 가 읽기전용이다. 전부 보고 대상.)
  [M1] Scaler (§3.3, 식 4). 배치 시 활성값을 rate=p_k/p_global 로 나누는 층.
       저자 modules.py: `output = input / self.rate if self.training else input`.
       동기(§3.3): 여러 epoch 지역학습하면 등급별로 표현 스케일이 갈라진다.
       없으면 그 발산을 보정 못 한다 → **폭이 섞일수록·지역 배치가 길수록 손해가 커진다.**
       우리 models.BasicBlock 에 대응물 0건. → **HeteroFL 을 약하게 만드는 최대 요인.**
       파일 끝 `Scaler` 와 `PATCH_BASICBLOCK_SCALER` 에 옮겨 붙일 참조 구현을 뒀다(미사용).
  [M2] sBN (§3.2). 학습 중 BN 통계 미추적(momentum=None, track_running_stats=False)
       + 학습 후 track=True 모델로 학습데이터를 훑어 누적 통계 수집(train_classifier_fed.stats()).
       우리 BN 은 기본값(momentum=0.1, track=True)이라 학습 중 통계를 그대로 쓴다.
       게다가 우리는 **라운드마다** 정확도를 재서 TTA 를 뽑는데 sBN 은 사후 절차라
       매 평가마다 전 클라 순회가 끼어들어 벽시계 측정을 오염시킨다.
       → **재현 불가.** 권고: ㉠ 모든 정책에 동일한 기본 BN 을 써서 BN 방식을 상수로 묶고
         "sBN 미적용"을 한계로 명시. 어느 쪽이든 논문 절대 수치(CIFAR10 a=91.19% /
         e=77.09% 류)와 우리 수치를 나란히 놓지 말 것.
       ※ 본문("학습 후 1회")과 저자 코드(매 global epoch stats() 호출)가 어긋난다.
         어느 쪽이 논문 수치를 낸 설정인지 확정 못 함 — 재현 불가라 결론은 안 바뀐다.
  [M3] 머릿수 균등 집계. 저자 combine() 은 표본 수 n 을 **보지 않는다** (count += 1).
       우리 models.nested_average 는 acc += v*n / cnt += n (표본 수 가중, FedAvg 식).
       non-IID 에서 결과가 갈린다. 논문 충실 재현이면 머릿수 균등으로 돌려야 한다.
       파일 끝 `count_uniform_average` 가 nested_average 드롭인 대체품이다(미사용).
  [M4] label_split / masked cross-entropy. 클라가 보유한 라벨 행만 출력층에 살리고
       집계에도 그 행만 반영하는 non-IID 장치. 우리에게 없다. 구현 안 함.
  [M5] 부분 참여(C=0.1, M=100 풀). → [D6].
  ※ 자기증류 없음은 무관하다 — HeteroFL 은 자기증류를 쓰지 않는다(그건 FjORD 옵션).

  ══ 확인 못 한 것 (지어내지 않았다) ══════════════════════════════════
  · 논문 본문이 'a-b-c-d-e' = 5등급 **균등**이라고 숫자로 못 박은 문장은 여전히 못 찾았다.
    근거는 (i) "uniformly sampling computation complexity levels" (§4) (ii) 저자 코드
    파서(m[0]/int(m[1:])) 와 README 예시('a2-b8'=20%/80%, 'a1-b1-c1'=균등)의 추론이다.
  · Fix 시나리오에서 클라 인덱스에 등급을 배정하는 **기준**을 논문이 밝힌 문장은 못 찾았다.
    저자 코드는 인덱스 순서로 반복 배치할 뿐 능력을 안 본다(→ assign="index" 로 재현 가능).
  · Algorithm 1 전사는 ar5iv HTML 경유다. 첨자 조판(M_{p:P,t} 등)은 원 PDF 대조 미완.
  · HeteroFL 의 SFL 확장 선례 유무는 조사 범위 밖.
"""
import random

LADDER = (0.25, 0.5, 0.75, 1.0)

# 저자 utils.py:  cfg['model_split_rate'] = {'a':1,'b':0.5,'c':0.25,'d':0.125,'e':0.0625}
# 이 값이 resnet.py 의 hidden_size = ceil(model_rate * base) 로 들어간다 → **폭 비**다.
PAPER_SPLIT_RATE = {"a": 1.0, "b": 0.5, "c": 0.25, "d": 0.125, "e": 0.0625}


def paper_levels(r=0.5, P=5):
    """§3.1 의 폭 비 r^(p-1), p=1..P.  원문 기본값 r=0.5, P=5 (§4).

    PAPER_SPLIT_RATE 와 같은 값을 내는지 확인용으로도 쓴다(자기시험에서 대조).
    """
    return [r ** (p - 1) for p in range(1, P + 1)]


def snap_to_ladder(x, ladder=LADDER, p_min=0.25):
    """원문 폭 비 x 를 우리 사다리 칸으로 옮긴다.  [D1]

    · x >= p_min : 가장 가까운 칸. 원문 1.0/0.5/0.25 는 **정확히 일치**하므로 무손실.
    · x <  p_min : p_min 으로 접는다. 우리 사다리엔 0.125·0.0625 칸이 아예 없다.
    타이브레이크는 작은 쪽 — 논문에 없는 칸(0.75)으로 새는 것을 막는다.
    """
    below = [v for v in ladder if v <= p_min]
    floor_v = max(below) if below else min(ladder)
    if x < p_min:
        return floor_v
    return min(ladder, key=lambda v: (abs(v - x), v))


def parse_model_mode(mode, ladder=LADDER, p_min=0.25, split_rate=None):
    """저자 utils.process_control 의 model_mode 파서를 그대로 옮긴 것.

        'a1-b1-c1' → 등급 글자 m[0], 비율 몫 int(m[1:]).
        README 예: 'a2-b8' = a 20% / b 80%,  'a1-b1-c1' = 3등급 균등.
    반환: (levels, proportion). levels 는 **우리 사다리로 스냅된** 폭 값이다 [D1].
    """
    sr = split_rate or PAPER_SPLIT_RATE
    levels, proportion = [], []
    for m in mode.split("-"):
        m = m.strip()
        if not m:
            continue
        levels.append(snap_to_ladder(sr[m[0]], ladder, p_min))
        proportion.append(int(m[1:]) if len(m) > 1 else 1)
    if not levels:
        raise ValueError(f"빈 model_mode: {mode!r}")
    return levels, proportion


def fix_rate_sequence(levels, proportion, num_users):
    """저자 utils.process_control 의 **fix** 분기.

        num_users_proportion = num_users // sum(proportion)
        model_rate += np.repeat(levels[i], num_users_proportion * proportion[i])
        model_rate += [model_rate[-1]] * (num_users - len(model_rate))   # 마지막 등급 패딩

    패딩 규칙까지 저자 코드 그대로다. 몫이 0 인 소규모 N 만 [D8] 대로 보강했다.
    """
    tot = sum(proportion)
    npu = num_users // tot if tot else 0
    seq = []
    for lv, pr in zip(levels, proportion):
        seq += [lv] * (npu * pr)
    if not seq:                     # [D8] 등급 수 > 클라 수. 저자 코드는 여기서 죽는다.
        seq = list(levels)[:num_users]
    seq = seq[:num_users]
    if seq:                         # 저자 코드의 마지막-등급 패딩
        seq += [seq[-1]] * (num_users - len(seq))
    return seq


class Baseline:
    name = "HeteroFL"
    paper = ("Enmao Diao, Jie Ding, Vahid Tarokh, \"HeteroFL: Computation and "
             "Communication Efficient Federated Learning for Heterogeneous Clients\", "
             "ICLR 2021 (arXiv:2010.01264)")

    def __init__(self, ks, p_min=0.25, mode="fix", model_mode="a1-b1-c1",
                 assign="capability", seed=1, **kw):
        """ks = 클라이언트 id 리스트.

        mode       "fix"     : §4 Fix. 등급을 **한 번** 정하고 학습 내내 불변.
                   "dynamic" : §4 Dynamic. 매 라운드 비율 multinomial 재추첨(능력 무관).
        model_mode 저자 표기. 기본 'a1-b1-c1' = 논문의 'a-b-c' 균등 [D2].
                   'a1-b1-c1-d1-e1'(5등급) 도 받는다 — d·e 는 p_min 으로 접힌다 [D1].
        assign     "capability" : Alg.1 "based on L_m". **프로파일 라운드 1회만** 관측을
                                  보고 등급을 확정한 뒤 영구 동결 [D3].
                   "index"      : 저자 Fix 코드 그대로 클라 인덱스 순서(능력 완전 무시).
        seed       Dynamic 재추첨용. 무작위를 결정론으로 바꾸지 않는다(충실도 규칙 2) —
                   시드만 고정해 재현 가능하게 한다.
        """
        if mode not in ("fix", "dynamic"):
            raise ValueError(f"mode 는 'fix'|'dynamic': {mode!r}")
        if assign not in ("capability", "index"):
            raise ValueError(f"assign 은 'capability'|'index': {assign!r}")
        self.ks = list(ks)
        self.p_min = p_min
        self.mode = mode
        self.model_mode = model_mode
        self.assign = assign
        self.seed = seed
        self.levels, self.proportion = parse_model_mode(model_mode, LADDER, p_min)
        self._rng = random.Random(seed)
        self._r = 0            # rule_bench 가 라운드를 안 넘겨주므로 내부 카운터를 둔다
        self._fixed = None     # Fix 모드에서 **동결된** {k: width}. 한 번 차면 안 바뀐다.
        self._ctl = None       # 실행 식별 (아래 _new_run 참조)

    # ── L_m (Alg.1 / §3.1) ────────────────────────────────────────────
    def _capability(self, ctl, k):
        """L_m 근사 [D4]. 논문에 산식이 없어 최소 근사로 잡았다.

            L_m ≈ (배치당 전폭 연산초) + (배치당 전폭 바이트 / 자기회선)

        ★ 공유회선 결합항은 넣지 않는다 — HeteroFL 에 그 개념이 없다.
          그래서 ctl.predict() 도 부르지 않는다(그 안에 결합항이 들어 있다).
        관측이 없으면 None → 아직 프로파일 전이라는 신호.
        """
        comp = ctl.comp1.get(k)
        if comp is None:
            return None
        byt = ctl.bytes1.get(k, 0.0)
        ck = ctl.Ck.get(k)
        return comp + (byt * 8.0 / ck if ck else 0.0)

    def _new_run(self, ctl):
        """새 학습 실행이면 동결을 푼다.

        HeteroFL 자체엔 리셋 개념이 없다(한 번 배포하면 끝). 이건 순전히 시험대 사정이다 —
        rule_bench 는 조건마다 **새 Controller** 를 만들어 같은 Baseline 인스턴스로 재생한다.
        그래서 ctl 객체가 바뀌면 '다른 배치'로 본다. 같은 실행 안에서는 절대 풀리지 않는다.
        (id() 는 GC 후 재사용될 수 있어 못 믿는다 → 객체 참조를 들고 `is` 로 비교한다.)
        """
        if ctl is not self._ctl:
            self._ctl = ctl
            self._fixed = None
            self._r = 0
            self._rng = random.Random(self.seed)
            return True
        return False

    # ── 배정 ──────────────────────────────────────────────────────────
    def _order_by_capability(self, ctl, ks):
        """L_m 오름차순(= 값싼 클라 먼저)으로 줄 세운다. 앞자리가 큰 등급을 받는다.

        관측이 하나라도 없으면 None 을 돌려 '아직 프로파일 전'을 알린다.
        """
        cost = {k: self._capability(ctl, k) for k in ks}
        if any(v is None for v in cost.values()):
            return None
        return sorted(ks, key=lambda k: (cost[k], k))

    def _fix_plan(self, ctl, ks):
        """반환 (plan, freeze). freeze=True 면 이 배정을 영구 동결한다."""
        seq = fix_rate_sequence(self.levels, self.proportion, len(ks))
        if self.assign == "index":
            # 저자 코드 그대로 — 클라 인덱스 순서에 등급을 얹는다. 능력을 안 본다.
            # 이건 t=0 에 이미 확정 가능하므로 곧바로 동결한다.
            return dict(zip(sorted(ks), seq)), True
        order = self._order_by_capability(ctl, ks)
        if order is None:
            # 프로파일 라운드 전 — L_m 이 아직 없다. HeteroFL 은 원래 t=0 전에 L_m 을
            # 외생 입력으로 받지만 우리 실험에선 첫 관측 전까지 알 길이 없다 [D3].
            # 인덱스 순서로 **임시** 배정하고 동결하지 않는다.
            return dict(zip(sorted(ks), seq)), False
        return dict(zip(order, seq)), True

    def _dynamic_plan(self, ks):
        """§4 Dynamic — 저자 fed.make_model_rate 의
           torch.multinomial(proportion, num_samples=M, replacement=True) 와 동치.
        **매 라운드** 다시 뽑고, 능력 정보를 보지 않는다.
        결정론으로 바꾸지 않는다 (충실도 규칙 2)."""
        tot = float(sum(self.proportion))
        w = [p / tot for p in self.proportion]
        picks = self._rng.choices(self.levels, weights=w, k=len(ks))
        return dict(zip(sorted(ks), picks))

    # ── 진입점 ────────────────────────────────────────────────────────
    def decide(self, rnd, ctl, batches):
        """반환 {client_id: width}. width 는 반드시 LADDER 안의 값.

        ★ Fix 경로에는 '재계산' 이라는 분기가 존재하지 않는다. _fixed 가 차 있으면
          그대로 돌려준다. 망이 변해도, 기기가 느려져도 반응하지 않는다 — 그게 이 논문이다.
        """
        self._new_run(ctl)
        ks = list(getattr(ctl, "ks", None) or self.ks)
        self._r = int(rnd) + 1                     # 다음 호출이 읽어갈 라운드 번호

        if self.mode == "dynamic":
            plan = self._dynamic_plan(ks)
        elif self._fixed is not None:
            plan = dict(self._fixed)               # ★ 동결. 여기서 끝. 재계산 없음.
        else:
            plan, freeze = self._fix_plan(ctl, ks)
            if freeze:
                self._fixed = dict(plan)           # 프로파일 1회 → 영구 동결 [D3]
        return {k: (v if v in LADDER else snap_to_ladder(v, LADDER, self.p_min))
                for k, v in plan.items()}


# ══════════════════════════════════════════════════════════════════════════
#  아래는 **현재 비활성**인 참조 구현이다. models.py / fed_server.py 가 읽기전용이라
#  여기서 끼울 수 없다. 종합자가 그대로 옮겨 붙일 수 있게 논문/저자코드대로 적어 둔다.
#  이 둘이 빠진 채로 돌리면 HeteroFL 이 원 논문보다 **불리**해진다 → [M1][M3] 보고 대상.
# ══════════════════════════════════════════════════════════════════════════

class Scaler:
    """[M1] §3.3 / 식 (4) — 저자 modules.py 의 Scaler.

        output = input / rate   (학습 시에만),   추론 시 항등
        rate = p_k / p_global   (저자 resnet.py: scaler_rate = model_rate / global_model_rate)
        위치 = 파라미터 층 직후, BN·활성화 **앞**.

    nn.Module 로 만들려면 models.BasicBlock 을 고쳐야 하는데 그 파일이 읽기전용이다.
    여기서는 순수 호출형으로만 둔다 — **현재 어디서도 호출하지 않는다.**
    """

    def __init__(self, rate):
        self.rate = float(rate)

    def __call__(self, x, training=True):
        return x / self.rate if (training and self.rate != 1.0) else x


# models.BasicBlock 에 [M1] 을 끼울 때의 정확한 수정안. 지금은 문자열일 뿐이다.
PATCH_BASICBLOCK_SCALER = r"""
# --- models.py BasicBlock 수정안 ([M1] Scaler, §3.3 식 4) ------------------
#  class BasicBlock(nn.Module):
#      def __init__(self, cin, cout, stride=1, scaler_rate=1.0):
#          ...
#          self.scale = scaler_rate          # = p_k / 1.0  (전역 폭이 1.0 이므로)
#      def forward(self, x):
#          s = self.scale if self.training else 1.0      # 추론 시 항등 (저자 코드 그대로)
#          y = F.relu(self.b1(self.c1(x) / s))           # 파라미터 층 직후·BN 앞
#          y = self.b2(self.c2(y) / s)
#          return F.relu(y + (x if self.sc is None else self.sc(x)))
#  ClientNet/ServerNet 이 p 를 이미 들고 있으므로 _stage(..., scaler_rate=p) 로 흘려주면 된다.
#  stem 의 conv 뒤에도 같은 나눗셈이 들어가야 §3.3 위치 규정과 정확히 맞는다.
# --------------------------------------------------------------------------
"""


def count_uniform_average(full_sd, updates):
    """[M3] §3.1 식 (1)~(3) / 저자 fed.py combine() — **머릿수 균등** 중첩 평균.

    models.nested_average 의 드롭인 대체품이다 (updates = [(sd, n_samples)]).
    저자 코드는 표본 수 n 을 **보지 않는다**: count += 1, 마지막에 count>0 원소만 count 로 나눔.
    아무도 안 가진 바깥 원소는 전역 값을 그대로 둔다(제로패딩 평균 아님) — 우리 쪽과 동일.
    **현재 아무 데서도 호출하지 않는다.** HeteroFL 충실 실행 시 nested_average 대신 써야 한다.
    """
    import torch
    acc = {k: torch.zeros_like(v, dtype=torch.float64) for k, v in full_sd.items()}
    cnt = {k: torch.zeros_like(v, dtype=torch.float64) for k, v in full_sd.items()}
    for sd, _n in updates:                 # ← n 을 **일부러 무시**한다 (논문/저자코드 그대로)
        for k, v in sd.items():
            idx = tuple(slice(0, s) for s in v.shape)
            acc[k][idx] += v.double()
            cnt[k][idx] += 1.0
    out = {}
    for k in full_sd:
        m = cnt[k] > 0
        out[k] = torch.where(m, acc[k] / cnt[k].clamp(min=1), full_sd[k].double())
        out[k] = out[k].to(full_sd[k].dtype)
    return out


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "..", "_archive", "rule_search_2026-08"))
    from rule_bench import bench

    # ── 사다리 사상 점검 (지어낸 값이 없는지 눈으로 확인) ──────────────
    lv = paper_levels(r=0.5, P=5)
    print("원문 폭 비 r^(p-1), r=0.5, P=5 :", lv)
    print("PAPER_SPLIT_RATE {a..e}        :", [PAPER_SPLIT_RATE[c] for c in "abcde"])
    print("우리 사다리로 스냅 [D1]        :", [snap_to_ladder(x) for x in lv],
          "  ← d(0.125)·e(0.0625) 는 p_min=0.25 로 접힘, 0.75 는 안 씀")
    print("model_mode 'a1-b1-c1'  파싱    :", parse_model_mode("a1-b1-c1"))
    print("fix 분배 N=4 / N=8             :",
          fix_rate_sequence(*parse_model_mode("a1-b1-c1"), 4),
          fix_rate_sequence(*parse_model_mode("a1-b1-c1"), 8))

    b = Baseline([f"c{i}" for i in range(4)])
    bench(lambda ctl, batches, alpha=1.2: b.decide(getattr(b, "_r", 0), ctl, batches),
          Baseline.name, verbose=True)

    # 논문의 두 시나리오를 모두 보인다 (§4). Dynamic 은 무작위이므로 시드만 고정.
    b2 = Baseline([f"c{i}" for i in range(4)], mode="dynamic")
    bench(lambda ctl, batches, alpha=1.2: b2.decide(getattr(b2, "_r", 0), ctl, batches),
          Baseline.name + "-Dynamic", verbose=True)

    # 저자 Fix 코드 그대로의 인덱스순 배정(능력 완전 무시) — 대조용.
    b3 = Baseline([f"c{i}" for i in range(4)], assign="index")
    bench(lambda ctl, batches, alpha=1.2: b3.decide(getattr(b3, "_r", 0), ctl, batches),
          Baseline.name + "-Fix(index순, 저자코드 그대로)", verbose=True)

    # 원문 대표 5등급 설정도 보인다 — d·e 가 p_min 으로 접히는 모습 [D1][D2].
    b4 = Baseline([f"c{i}" for i in range(4)], model_mode="a1-b1-c1-d1-e1")
    bench(lambda ctl, batches, alpha=1.2: b4.decide(getattr(b4, "_r", 0), ctl, batches),
          Baseline.name + "-Fix(a1-b1-c1-d1-e1, d·e 접힘)", verbose=True)
