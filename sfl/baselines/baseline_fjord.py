# -*- coding: utf-8 -*-
"""FjORD 기준선 — NeurIPS'21 원문을 우리 SFL 시험대에 **충실히** 옮긴 판.

  Horvath, Laskaridis, Almeida, Leontiadis, Venieris, Lane.
  "FjORD: Fair and Accurate Federated Learning under heterogeneous targets with
   Ordered Dropout." NeurIPS 2021. arXiv:2102.13451.
  (원문 PDF 를 직접 열어 §3.1~3.4, §4 Algorithm 1, Eq.(1), §5.1 을 축자 확인했다.
   확인 경로: proceedings.neurips.cc .../6aed000af86a084f9cb0264161e29dd3-Paper.pdf)

  ══════════════════════════════════════════════════════════════════════════
  ★ FjORD 의 폭 배정은 **두 층**이다. 어느 쪽도 실측 적응이 아니다.
  ══════════════════════════════════════════════════════════════════════════

  ① 상한 p_max^i  — **정적**. 학습 전에 기기 군집(tier)으로 정해지고 실행 내내 안 바뀐다.
     §3.4: 기기를 능력이 비슷한 것끼리 군집화하고 군집마다 p_max 를 하나 붙인다.
           군집화는 기기 사양 기반 휴리스틱이거나 실제 기기 위 벤치마크이며,
           논문은 이를 "시스템 설계 결정"으로 남긴다.
     §5.1: 실험에서는 "각 클라를 기기 군집 하나에 배정"하는 식으로 이질성을 모사한다.
     Algorithm 1 라인 3: 서버는 라운드마다 클라 i 에게 p_max^i-부분모델을 내려보낸다.
     → **라운드별 재배정 기구가 알고리즘에 없다.** 우리 방법과 갈리는 지점이 바로 여기다.

  ② 실제 학습 폭 p_(i,k) — **매 local iteration 마다 균등 무작위 재표집**.
     Algorithm 1 라인 4~5: `for k <- 0 to E-1  // Local iterations`
                           `Device i samples p_(i,k) ~ D_P | D_P <= p_max^i`
     본문(§4)도 "각 클라는 E local iterations 를 돌고 매 local iteration k 마다
     조건부 분포에서 p 를 뽑는다"고 못박는다. 실험 D_P = U_5 (P={0.2,...,1.0} 균등).
     → **클라를 자기 p_max 에 고정하면 그건 FjORD 가 아니다.** 기대폭이 상한보다 낮고,
       그 차이가 라운드 시간·정확도 양쪽에 다 걸린다. 이 파일은 그 함정을 피한다.

  ══════════════════════════════════════════════════════════════════════════
  원문과 우리 설정이 갈리는 곳 (원문은 X / 우리는 Y / 이유 Z)
  ══════════════════════════════════════════════════════════════════════════

  [D1] 사다리
       원문 X: P = {i/k}, 주 설정 U_5 = {0.2,0.4,0.6,0.8,1.0} (uniform-5).
       우리 Y: LADDER = (0.25,0.5,0.75,1.0) = uniform-4.
       이유 Z: 우리 models.py 가 이 4단으로 고정돼 있다. 알고리즘은 P 만 갈아끼우면
               그대로 성립한다(§3.1 은 P 를 임의의 이산 집합으로 정의). 다만 **논문의
               정확도 수치와 직접 대조는 불가**하다 — 사다리가 다르기 때문이다.

  [D2] 표집 입도 (가장 큰 결손)
       원문 X: p 를 **local iteration(=미니배치)마다** 재표집. 실험은 local epoch 1 이므로
               한 라운드 안에서 배치 수만큼 p 가 바뀐다(저자 재구현 Flower baselines/fjord 의
               ODSampler 도 배치마다 np.random.choice 로 뽑는다).
       우리 Y: **라운드마다 1회** 재표집. p ~ Uniform{ s in LADDER : p_min <= s <= p_max^k }.
       이유 Z: sfl/fed_server.py 는 라운드 시작에 plan={k: p} 를 정해 RSTART 로 내려보내고
               그 라운드 내내 고정한다(읽기 전용 파일이라 못 고친다). 게다가 우리는 SFL 이라
               배치마다 p 가 바뀌면 절단면 활성 텐서의 채널 수가 배치마다 달라지고 서버
               뒷단(ServerNet)도 배치마다 갈아끼워야 한다 — hub 구조가 라운드 단위 p 를 전제한다.
       손익  : **기대폭은 같다**(균등표집이므로). 다른 것은 분산 구조다. 배치별 표집은 한
               라운드 안에서 폭을 평균내 주지만 라운드별 표집은 그 평균화를 못 받는다.
               → 정확도 곡선이 더 출렁일 수 있고, 그건 **FjORD 에게 불리한 방향**이다.
               이 근사는 우리 인프라의 제약이지 논문의 결함이 아니다. 종합자는 이걸 명시하라.

  [D3] 군집화 신호
       원문 X: 기기 **사양** 또는 기기 위 **벤치마크** (연산 능력 기준). 망은 안 잰다.
       우리 Y: 프로파일 라운드(첫 관측) **한 번**의 실측 라운드 시간으로 클라를 줄세운다.
               tier_signal="round_time"(기본) 이면 ctl.predict 의 전폭 예상시간,
               "compute" 면 ctl.comp1 만 쓴다.
       이유 Z: 우리 시험대의 이질성은 기기가 아니라 **회선**에서 온다. 여기서 연산만 보고
               등급을 매기면 FjORD 는 실제 병목과 무관하게 등급을 배정하게 되고, 그건
               **허수아비**다. 논문이 군집화를 "시스템 설계 결정"으로 열어뒀으므로,
               우리 환경에서 FjORD 를 배치하는 설계자가 고를 법한 **가장 유리한 신호**를
               준다. 단 **한 번만 재고 그 뒤로는 영구히 고정** — 이게 논문의 정적 배정이다.
       주의  : 프로파일 라운드는 논문에 없는 절차다. 논문은 사양표로 미리 안다고 가정한다.
               우리는 사양표가 없어 첫 라운드 관측을 벤치마크로 쓴다(논문이 허용한 두 경로 중
               "benchmarking" 쪽). 그 라운드 동안은 전원 최고 등급(=전폭)으로 돈다.

  [D4] 등급 분포 (drop scale, §5.1)
       원문 X: uniform-n, drop scale ds 에서 최상위 군집 n 은 1 - Σ ds/n 을, 나머지 군집은
               각각 ds/n 을 갖는다. 예: ds=1.0 · uniform-5 → 전 군집 20% 씩 균등,
               ds=0.5 → (0.1,0.1,0.1,0.1,0.6) 로 상위 편중. 평가는 ds ∈ {0.5, 1.0}.
               ※ 인쇄된 합 범위(i=0..n-1)를 그대로 더하면 ds=1 에서 최상위가 0% 가 되어
                 바로 뒤 예시와 모순된다. 예시 두 개(ds=1.0 균등 / ds=0.5 최상위 60%)가
                 서로 정합하므로 **합은 i=1..n-1 (n-1 항)** 이 맞다. 이 파일은 예시를 따른다.
       우리 Y: n=4 로 같은 공식. ds=1.0 → 각 25%; ds=0.5 → 하위 3개 각 12.5%, 최상위 62.5%.
       이유 Z: 사다리가 4단이라 n=4. 기본값 ds=1.0 — 논문의 주 평가 설정(§5.2/§5.3)이다.
       배정  : 클라 수 N 이 작아 비율이 딱 안 떨어진다. 능력 순으로 줄세운 뒤 i 번째 클라를
               분위수 (i+0.5)/N 가 떨어지는 군집에 넣는다(§5.1 의 "각 클라를 군집 하나에
               배정"의 자연스러운 이산화). N=4·ds=1.0 → 정확히 각 등급 1명.

  [D5] 집계 소속
       원문 X: Eq.(1) 은 껍질 (s_(j-1), s_j] 를 **p_max^i >= s_j 인 클라**만 모아 표본수
               가중평균한다. 클라가 한 에폭 동안 상한까지 다 갱신했으니 정당하다.
       우리 Y: fed_server.py 가 **그 라운드에 실제 배포한 p_k** 로 소속을 정한다(hub.up 에
               p 를 같이 싣고 nested_average 가 인덱스별로 누산).
       이유 Z: [D2] 때문에 우리 클라는 그 라운드에 p_max 까지 갱신하지 않는다 — 표집된
               p 까지만 갱신한다. 그러니 소속도 p 여야 맞다. 소속을 p_max 로 올리면 학습되지
               않은 바깥 채널이 평균에 들어가 **오히려 틀린다**.
       ✔ 집계 자체는 동치: models.py 의 nested_average 는 인덱스별로 (그 위치를 실제로
         보낸 클라만) 표본수 가중평균하고 아무도 안 보낸 위치는 이전 전역값을 유지한다.
         저자 재구현 strategy.py 의 fjord_average(큰 p 부터 내림차순 덮어쓰기)와 값이 같다.
         제로패딩 평균 금지 원칙도 우리가 이미 지킨다. **이 부품은 갖췄다.**

  ══════════════════════════════════════════════════════════════════════════
  우리 코드에 없어서 **빼고 간** 부품 (지어내지 않았다. 종합자는 전부 보고하라)
  ══════════════════════════════════════════════════════════════════════════

  [M1] 자기증류(KD, §3.2).  L_d = KL(SM_p, SM_pmax, T) + CE(max(SM_pmax), y_label).
       최종형은 α=T=1 이라 학생이 교사 출력을 그대로 모사하고, 교사(p_max)도 함께 역전파한다
       (= 배치마다 forward/backward 2회).
       ▶ 우리 sfl/ 에 KD 경로가 없어 **못 넣었다**. 그래서 이 기준선의 이름은
         "FjORD (w/o KD)" 다. 논문의 **주 보고 수치는 KD 포함본**이므로 이름을 정직하게 붙인다.
       ▶ 방향: §5.3 절제 결과는 KD 이득이 p>0.4 에서 나타나고 p<=0.4 에서는 사그라든다고 한다.
         즉 KD 를 빼면 **큰 폭에서 정확도가 손해**다 → 이 기준선은 원 논문보다 불리하다.
       ▶ 반대 방향도 있다: KD 는 배치당 forward 2회라 **연산이 늘어난다**. 논문은 벽시계를
         재지 않아(라운드/FLOPs/파라미터만) 이 비용이 안 보이지만, 우리 축은 벽시계 TTA 라
         KD 를 켰다면 그대로 손해로 잡혔을 것이다. 즉 KD 생략은 정확도에선 불리, 시간에선
         유리 — **양방향 왜곡이고 상쇄 크기를 우리는 모른다.** 단정하지 마라.

  [M2] 폭별 BatchNorm 통계 (§3.1 각주 6).  FjORD 는 dropout rate p 마다 BN 통계를 따로 둔다.
       ▶ 우리 models.py 는 층마다 nn.BatchNorm2d 하나뿐이고 앞쪽 슬라이스를 공유한다.
         폭이 섞이면 running_mean/var 이 서로 다른 p 의 통계로 오염된다 — FjORD 가 각주로
         명시해 피한 바로 그 문제다. **이 기준선은 그 보호막 없이 돈다 → 불리하다.**
       ▶ 우리 실험의 "전원 0.25 로 낮추면 정확도 곡선이 불안정(하락 4회)" 현상이 이 BN 공유
         탓인지는 **확인 안 된 가설**이다. 인과로 쓰지 마라.

  [M3] eFD / FjORD+eFD 기준선.  FjORD 가 실제로 이긴 상대다(§5.2). 우리 저장소에 랜덤
       드롭아웃 계열이 없어 구현하지 않았다. FjORD 대비만 할 거면 필수는 아니다.

  [M4] 우리에게 없는 게 아니라 **FjORD 에 없는 것**: 학습 중 망/기기 재측정. 서버가 라운드마다
       회선을 재는 기구가 Algorithm 1 에 없다. 우리 controller.observe_round()/C_eff EWMA 의
       대응물이 없다 — 그게 우리 빈칸이다.
       ※ 단 §3.4 에 "일시적 기기 부하를 p_max 를 낮춰 모델링하는 것도 프레임워크가 지원할
         수 있다"는 **한 문장**이 있다(원문 확인함). 그러나 (a) 그 기구가 Algorithm 1 에 없고
         (b) 어떻게 부하를 감지하는지 안 밝히고 (c) 그 설정으로 실험한 결과가 없다.
         **우리 신규성을 주장할 때 이 문장을 모른 척하면 안 된다.** 정직한 대비는
         "FjORD 는 가능성을 언급했고, 우리는 측정 기구·결정 규칙·실측 평가를 준다" 이다.

  ══════════════════════════════════════════════════════════════════════════
  시험대 점수에 대하여
  ══════════════════════════════════════════════════════════════════════════
  rule_bench 의 기대 행동(조건1 유지 / 조건2·3 낙오자 좁힘)은 **우리 규칙의 기대**다.
  FjORD 는 회선을 안 보므로 조건1 에서도 무작위로 좁히고(→ FAIL), 조건3 의 교란에도
  등급이 얼어 있어 반응하지 않는다. **그게 논문이 시키는 것이다.** 점수를 올리려고
  결정론으로 바꾸거나 회선을 다시 재게 만들면 그 순간 이 기준선은 FjORD 가 아니게 된다.

  ★ 이 기준선의 시험대 점수는 **씨앗 잡음이다. 단일 실행 점수를 인용하지 마라.**
    폭이 무작위라 판정이 씨앗마다 흔들린다. seed 0~11 로 12회 돌린 결과:
        조건1  0/12   (항상 FAIL — 등급이 회선과 무관하게 폭을 벌린다. 결정론적)
        조건2  2/12   (판정이 마지막 라운드만 보는데 그게 무작위 추첨이다)
        조건3  5/12   (동전던지기. '반응'이 아니라 표집 잡음이 우연히 낮게 찍힌 것)
        조건4 11/12   (ds=1.0 이면 8명 중 6명이 이미 p_max<1.0 → 거의 항상 좁아 보인다)
    기본 seed=0 은 3/4 가 나오는데 이건 FjORD 의 행동 적합도를 **과대평가**한다.

  ★ 기대폭: ds=1.0 · uniform-4 에서 등급별 조건부 평균은 0.25/0.375/0.5/0.625,
    전체 평균 **0.4375**. 즉 FjORD 는 uniform(p=1.0) 대비 라운드가 크게 짧다.
    **느린 허수아비가 아니다** — 시간에서는 억센 상대이고, 대신 라운드당 학습량을 내준다.
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from controller import LADDER                                        # noqa: E402


def tier_proportions(n, drop_scale):
    """§5.1 drop scale — 군집별 기기 비율. 하위 n-1 군집 각 ds/n, 최상위 = 나머지.

    인쇄된 합 범위(i=0..n-1)를 그대로 쓰면 ds=1 에서 최상위가 0% 가 되어 바로 뒤
    예시(ds=1.0 uniform-5 → 각 20%)와 모순된다. 예시 두 개가 서로 정합하므로
    n-1 항 합이 맞다 — 예시를 따른다. (docstring [D4] 참조)
    """
    share = float(drop_scale) / n
    props = [share] * (n - 1) + [1.0 - share * (n - 1)]
    if props[-1] < 0:                       # ds > n/(n-1) 같은 병적 입력 방어
        props = [1.0 / n] * n
    return props


class Baseline:
    """FjORD — 정적 등급 상한 + 상한 이하 균등 무작위 표집."""

    name = "FjORD (w/o KD)"
    paper = ("Samuel Horvath, Stefanos Laskaridis, Mario Almeida, Ilias Leontiadis, "
             "Stylianos I. Venieris, Nicholas D. Lane. FjORD: Fair and Accurate "
             "Federated Learning under heterogeneous targets with Ordered Dropout. "
             "NeurIPS 34 (2021). arXiv:2102.13451.")

    def __init__(self, ks, p_min=0.25, drop_scale=1.0, ladder=LADDER,
                 tier_signal="round_time", seed=0, verbose=True, **kw):
        """ks = 클라이언트 id 리스트.

        drop_scale  : §5.1 ds. 논문 평가값 {0.5, 1.0}. 기본 1.0 = 주 설정(균등 군집).
        ladder      : P (폭 사다리). 우리는 uniform-4. 논문 주 설정은 uniform-5.
        tier_signal : 프로파일 라운드에서 클라를 줄세울 신호 ([D3] 참조).
                      "round_time" = 전폭 예상 라운드 시간(회선 포함, 기본·FjORD 에 유리)
                      "compute"    = 연산시간만 (논문의 기기 벤치마크에 더 가깝지만
                                     우리 시험대에서는 병목과 무관해져 허수아비가 된다)
        seed        : 표집 재현용. **결정론으로 바꾸는 게 아니다** — 논문이 무작위 표집이므로
                      무작위로 뽑되, 실험을 재현할 수 있게 씨앗만 고정한다.
        """
        self.ks = list(ks)
        self.p_min = float(p_min)
        self.drop_scale = float(drop_scale)
        self.ladder = tuple(sorted(ladder))
        self.tier_signal = tier_signal
        self.seed = int(seed)
        self.verbose = verbose
        self._ctl = None                    # 실행(run) 경계 감지용 — 새 Controller = 새 실행
        self._reset(None, self.ks)

    # ── 실행 상태 ────────────────────────────────────────────────────
    def _reset(self, ctl, ks):
        self._ctl = ctl
        self.ks_run = list(ks)
        self.pmax = None                    # 아직 등급 미확정 = 프로파일 라운드 전
        self.rng = random.Random(self.seed)
        self._r = 0

    # ── ① 정적 등급 배정 — 실행당 **딱 한 번** ────────────────────────
    def _benchmark(self, ctl, ks, batches):
        """프로파일(벤치마크) 라운드 한 번의 실측. 관측이 없으면 None.

        ★ 이 함수는 실행당 한 번만 불린다. FjORD 에는 라운드별 재측정이 없다."""
        comp1 = getattr(ctl, "comp1", None) or {}
        if not all(k in comp1 for k in ks):
            return None                                     # 라운드 0 — 아직 관측 없음
        if self.tier_signal == "round_time":
            b1 = getattr(ctl, "bytes1", None) or {}
            if all(k in b1 for k in ks):
                try:
                    return ctl.predict({k: 1.0 for k in ks}, batches)
                except Exception:
                    pass
        gam = getattr(ctl, "gamma", None) or {}
        return {k: batches * comp1[k] * (1.0 ** gam.get(k, 1.2)) for k in ks}

    def _assign_tiers(self, T):
        """능력 순으로 줄세워 drop-scale 분포에 맞는 군집(tier)에 배정하고 **영구 고정**."""
        ks = list(T)
        order = sorted(ks, key=lambda k: (-T[k], str(k)))   # 느린 쪽부터 = 저등급부터
        n = len(self.ladder)
        props = tier_proportions(n, self.drop_scale)
        cdf, acc = [], 0.0
        for pr in props:
            acc += pr
            cdf.append(acc)
        N = len(order)
        out = {}
        for i, k in enumerate(order):
            q = (i + 0.5) / N
            j = 0
            while j < n - 1 and q >= cdf[j]:
                j += 1
            out[k] = max(self.ladder[j], self.p_min)
        return out

    # ── ② 상한 이하 균등 무작위 표집 ──────────────────────────────────
    def _sample(self, pmax):
        """p ~ D_P | D_P <= p_max  (Algorithm 1 라인 5). D_P = 사다리 위 균등분포.

        논문은 이걸 **local iteration 마다** 한다. 우리는 라운드마다 한다 ([D2])."""
        cand = [s for s in self.ladder if self.p_min - 1e-9 <= s <= pmax + 1e-9]
        if not cand:
            cand = [self.ladder[0]]
        return self.rng.choice(cand)

    # ── 인터페이스 ───────────────────────────────────────────────────
    def decide(self, rnd, ctl, batches):
        ks = list(getattr(ctl, "ks", None) or self.ks)
        if ctl is not self._ctl:            # 새 Controller = 새 실행 → 등급 다시 얼린다
            self._reset(ctl, ks)
        if list(ks) != list(self.ks_run):   # 클라 집합이 바뀌면(N=4→8) 역시 새 실행
            self._reset(ctl, ks)

        if self.pmax is None:
            T = self._benchmark(ctl, ks, batches)
            if T is None:
                # 프로파일 라운드: 아직 아무 관측이 없다. 논문은 사양표로 등급을 미리
                # 알지만 우리는 모른다 → 이 한 라운드만 전원 최고 등급으로 돌려 벤치마크를
                # 얻는다 ([D3]). 여기서 폭을 낮추면 실측이 전폭 기준이 아니게 된다.
                self._r = rnd + 1
                return {k: self.ladder[-1] for k in ks}
            self.pmax = self._assign_tiers(T)
            if self.verbose:
                sh = ", ".join(f"{k}:{self.pmax[k]}" for k in sorted(self.pmax))
                print(f"{'':22s}[FjORD] 등급 고정(ds={self.drop_scale}, "
                      f"신호={self.tier_signal}, N={len(ks)}) → {sh}")

        # p_max 는 이제 절대 안 바뀐다. 매 라운드 바뀌는 건 표집된 p 뿐이다.
        plan = {k: self._sample(self.pmax[k]) for k in ks}
        self._r = rnd + 1
        return plan


if __name__ == "__main__":
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "..", "_archive", "rule_search_2026-08"))
    from rule_bench import bench
    b = Baseline([f"c{i}" for i in range(4)])
    bench(lambda ctl, batches, alpha=1.2: b.decide(getattr(b, "_r", 0), ctl, batches),
          Baseline.name, verbose=True)
