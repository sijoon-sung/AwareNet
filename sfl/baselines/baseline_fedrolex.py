# -*- coding: utf-8 -*-
"""FedRolex 기준선 — 이질-폭 FL 의 **롤링 부분모델 추출(rolling sub-model extraction)**.

  Samiul Alam, Luyang Liu, Ming Yan, Mi Zhang.
  "FedRolex: Model-Heterogeneous Federated Learning with Rolling Sub-Model Extraction."
  NeurIPS 2022 (Advances in Neural Information Processing Systems 35). arXiv:2212.01548v2.

  ── 원문 확인 경로 (요약글 아님. 아래는 전부 직접 열어 읽은 것) ──────────────
    · arXiv e-print LaTeX 원본:  approach.tex(§3.2 Eq(4)·Algorithm 1·§3.3),
                                 supplementary.tex(A.2 Eq(10), A.4 보폭 r),
                                 results.tex(§4.1 sBN, §4.2 용량 분포)
    · 조판 PDF 20쪽:             p.4-5 (Eq(4)+Algorithm 1), p.16 (Eq(10))
    · 공식 구현:                 AIoT-MLSys-Lab/FedRolex, resnet_server.py
                                 ResnetServerRoll.split_model() / make_model_rate() / combine()

═══════════════════════════════════════════════════════════════════════════════
 ★ 먼저 읽어라 — 이 기준선이 우리 인터페이스에서 무엇을 하고 무엇을 못 하는가
═══════════════════════════════════════════════════════════════════════════════
 FedRolex 가 라운드마다 바꾸는 것은 **"채널을 몇 개"가 아니라 "어느 채널"** 이다.

   · 폭 β_n 은 Algorithm 1 의 헤더 `Input : D_n, β_n  ∀n ∈ N` — 알고리즘의 **입력 상수**다.
     라운드 루프 어디에도 β 를 다시 정하는 줄이 없다.
   · §3.1: "β_n denote the model capacity of client n … the proportion of nodes
     extracted from each layer in θ for client n." — 기기 용량으로 주어지는 상수.
   · 공식 코드 make_model_rate() 도 'fix'(고정 배열) / 'dynamic'(고정 사전분포에서
     매 라운드 무작위 재추첨) 두 모드뿐. 'dynamic' 조차 관측도 되먹임도 없다.
   · 논문 전체(본문+부록 20쪽)에 지연시간·대역폭·낙오자·마감선·벽시계 시간에 대한
     결정 규칙이 **하나도 없다**. 실험 지표는 라운드 수 대비 정확도뿐이다.

 따라서 이 파일의 decide() 는 **정적이다.** 프로파일 라운드 1회로 등급을 고정한 뒤
 마지막 라운드까지 같은 폭을 낸다. 시험대의 조건2·3(낙오자 좁힘/교란 반응)에서
 FAIL 이 나오는 것이 정상이다 — 그게 논문이 시키는 것이다. 점수를 올리려고
 매 라운드 재측정하는 순간 그건 FedRolex 가 아니라 우리 방법이 된다.

 논문의 핵심 기여인 Eq(4) 롤링 창은 **빼지 않았다.** rolling_index_set() /
 Baseline.window() 로 정확히 구현했고 자기시험에서 성질을 검증한다. 다만 우리
 파이프라인이 그 인덱스를 소비하지 못한다 (아래 '옮기지 못한 것' 참조).

═══════════════════════════════════════════════════════════════════════════════
 ■ Equation (4), §3.2 (PDF p.5) — 롤링 창 인덱싱. 그대로 옮김
═══════════════════════════════════════════════════════════════════════════════
   S^(j)_{n,i} = { {ĵ, ĵ+1, …, ĵ+⌊β_n K_i⌋−1}                      if ĵ+⌊β_n K_i⌋ ≤ K_i,
                 { {ĵ, …, K_i−1} ∪ {0, …, ĵ+⌊β_n K_i⌋−1−K_i}       else.
   where ĵ = j mod K_i.

   기호: N=클라 수, n=클라 인덱스, j=통신 라운드, i=층 인덱스, K_i=층 i 의 전체 노드 수,
        β_n=클라 n 의 모델 용량, S^(j)_{n,i}=라운드 j 에 클라 n 이 받는 층 i 의 노드 인덱스.

   · 순환(wrap-around) 처리는 위 else 가지가 전부다. 창이 K_i 를 넘으면 0 으로 되돌아
     두 조각 {ĵ..K_i−1} ∪ {0..(ĵ+⌊β_n K_i⌋−1−K_i)} 을 합친다.
   · **ĵ 는 (j, K_i) 에만 의존한다 — n 이 없다.** 같은 라운드의 모든 클라가 같은 시작점,
     길이만 다르다. (공식 코드 roll = self.rounds % output_size 에도 m 이 없다.)
   · 보폭: Appendix A.4 — "In FedRolex, r=1, i.e., the kernels are advanced by 1 from
     one iteration to the next iteration." 일반형은 라운드당 1+⌊β_n(1−r)K_i⌋ 칸,
     r∈[0,1]. r=1 이면 보폭 1 → ĵ = j mod K_i (= Eq(4) 그대로).

 ■ Algorithm 1: FedRolex (PDF p.5) — 그대로 옮김
     Initialization ; θ^(0), N
     Input  : D_n, β_n  ∀n ∈ N            ← β 는 입력. 루프에서 갱신되지 않는다.
     Output : θ^J
     Server Executes
     for j ← 0 to J−1 do
         Sample subset M from N
         Broadcast θ^(j)_{m, S^(j)_{m,i}} to client m ∈ M   ∀i, S^(j)_{m,i} from Eq (4)
         for each client m ∈ M do  clientStep(θ^(j)_m, D_m)
         Aggregate θ^(j+1)_{[i,k]} according to Equation (10)
     end for
     Subroutine clientStep(θ^(j)_n, D_n):
         m_n ← len(D_n);  for k ← 0 to m_n:  θ_n ← θ_n − η ∇l(θ_n; d_{n,k});  return θ_n

 ■ Equation (10), Appendix A.2 (PDF p.16) — 선택적 집계. 그대로 옮김
     θ_{[i,k]} = ( 1 / Σ_{m∈M_k} p_m ) · Σ_{m∈M_k} p_m · θ_{m,[i,k]}
     M ⊂ N = 이번 라운드에 뽑힌 클라. M_k ⊂ M = **k 번째 파라미터를 실제로 갱신한** 클라들.
     §3.2: "The parameter remains unchanged if no clients updated it."
     p_m 기본값(A.2): "unless otherwise stated, the weight of all clients is assumed to be
     the same, i.e, p_m = 1/N" → 사실상 단순 산술평균. Appendix A.3 Table 5 가 가중 3종
     (모델크기 비례/갱신횟수 비례/혼합)을 시험했으나 무가중보다 유의하게 낫지 않아 무가중 채택.

     → **우리는 이미 이걸 갖고 있다.** sfl/models.py:nested_average 의 의미론이 Eq(10)
       과 같다: 건드린 클라만 누적(acc/cnt), cnt==0 이면 이전 전역값 유지
       (out[k] = torch.where(m, acc/cnt, full_sd[k])). 인덱스 위치만 접두→회전으로
       바꾸면 그대로 Eq(10) 이다. (논문 기본은 무가중이므로 n=1 로 두면 정확히 재현.
       우리 nested_average 는 표본 가중이라 Eq(10) 의 일반형 p_m 쪽에 해당한다.)

 ■ HeteroFL / FedDropout 과 무엇이 다른가 — **집계식은 다르지 않다** (정직한 답)
     부록 A.6 의 Algorithm 2(HeteroFL) / Algorithm 3(FedDropout) 도 마지막 줄이
     "Aggregate θ^(j+1)_{[i,k]} according to Equation (10)" 로 **글자 그대로 같다.**
     달라지는 것은 broadcast 줄 하나뿐이다:
        HeteroFL/FjORD (Eq 6): S = {0,1,…,⌊β_n K_i⌋−1}        ← j 에 의존하지 않는다
        FedDropout     (Eq 5): S = {k_c | k_c ∈ [0,K_i−1], 1≤c≤⌊β_n K_i⌋}  (무작위)
        FedRolex       (Eq 4): S = 회전 창
     달라지는 것은 M_k 의 구성이다. HeteroFL 은 큰 인덱스 k 일수록 M_k 가 작아지고,
     β_max<1 이면 바깥 채널의 M_k=∅ 이 되어 영원히 초기값이다. FedRolex 는 회전 덕에
     모든 k 의 |M_k| 기대값이 같아진다 → "evenly trained".

═══════════════════════════════════════════════════════════════════════════════
 ■ 원문과 우리 설정이 다른 곳 — '원문은 X, 우리는 Y, 이유는 Z'
═══════════════════════════════════════════════════════════════════════════════
 (D1) 사다리.       원문은 β={1, 1/2, 1/4, 1/8, 1/16} 5단 기하열(§4.1).
                    우리는 LADDER=(0.25,0.5,0.75,1.0) 4단 선형, 하한 0.25.
                    이유: 우리 models.py/controller.py 가 이 사다리로 고정되어 있고
                    p_min 아래로는 내리지 않는 것이 우리 시스템의 규약이기 때문.
                    → 원문의 1/8, 1/16 은 우리 시스템에 존재하지 않는다.
 (D2) 순수 FL vs SFL. 원문은 순수 FL(분할 없음). 우리는 SFL — 클라 앞단/서버 뒷단이
                    활성값을 주고받는다. 원문에 절단면 인덱스 합의 문제가 없다.
                    → 아래 '옮기지 못한 것 (2)' 참조.
 (D3) 등급의 출처.  원문의 β_n 은 **기기 사양**에서 외생적으로 주어진다 (Algorithm 1 Input).
                    우리 실험대는 기기가 동일하고 **회선만 다르다** — 우리는 망을 잰다.
                    원문은 β 를 어떻게 정하는지에 대한 규칙을 주지 않으므로, 우리는
                    ① 원문 §4.2 의 실험 설정("the distributions of client model capacities
                    are uniform")을 그대로 쓰고 ② 어느 클라가 어느 등급인지는
                    **프로파일 라운드 1회 관측 순위**로 정한 뒤 **영구 동결**한다.
                    이유: 등급을 클라 번호로 임의 배정하면(느린 클라에 1.0, 빠른 클라에
                    0.25 가 걸릴 수 있음) 기준선이 우연으로 망가진 허수아비가 된다.
                    ★ 이것은 '적응'이 아니다 — 관측은 딱 한 번, 그 뒤로는 되먹임이 없다.
                    ★ 논문을 문자 그대로 읽는 경로도 남겨두었다: betas= 로 외생 β 를
                      직접 주면 관측을 아예 하지 않는다 (assign="given").
 (D4) 창 길이.      원문 Eq(4) 는 floor ⌊β_n K_i⌋, 공식 코드는 ceil(np.ceil(...)).
                    우리는 **ceil** 을 기본으로 쓴다. 이유: 우리 models.py 의
                    w(c,p)=ceil(c·p) 와 채널 수가 정확히 일치해야 슬라이스가 성립한다.
                    (length_mode="floor" 로 원문 식 그대로도 낼 수 있게 열어 두었다.)
 (D5) 회전 방향.    원문 Eq(4) 는 정방향(창 시작 = j mod K). 공식 코드의
                    torch.roll(arange(K), j)[:L] 은 역방향(창 시작 = (K−j) mod K).
                    같은 순환을 반대로 도는 것이라 통계적 성질은 같다.
                    우리는 **논문 Eq(4)(정방향)** 를 따른다. (roll_dir="code" 로 역방향도 가능.)
 (D6) 참여율·라운드 수. 원문은 100 클라 중 10% 참여 × 수백~800 라운드.
                    우리는 N=4~8 전원이 매 라운드 참여, 라운드 12~14.
                    → 아래 '★ 회전 한 바퀴 계산' 참조. 이 차이는 결과 해석에 직접 영향.

═══════════════════════════════════════════════════════════════════════════════
 ■ 옮기지 못한 것 / 우리에게 없는 부품 — **구현하지 않았다. 종합자에게 보고한다.**
═══════════════════════════════════════════════════════════════════════════════
 (1) 정적 배치정규화(sBN) + conv 뒤 scalar module.
     §4.1: "We replace the batch Normalization in PreResNet18 with static batch
     normalization … and add a scalar module after each convolution layer."
     우리 models.py 는 평범한 nn.BatchNorm2d(running stats 추적)를 쓴다.
     롤링을 켜면 채널 c 의 running_mean/var 이 매 라운드 전혀 다른 부분모델 문맥에서
     갱신되므로 sBN 없이는 통계가 오염된다. **이건 선택이 아니라 필수 부품이다.**
     ★ sBN 없이 롤링만 켜서 정확도가 나쁘게 나오면 그건 FedRolex 재현이 아니라
       허수아비다. 우리 실험대에서 롤링을 실제로 켤 거면 sBN 을 먼저 넣어야 한다.
 (2) SFL 절단면(cut)을 가로지르는 인덱스 합의.
     롤링을 켜면 활성값 텐서 채널의 '정체'가 라운드마다 바뀐다. ServerNet 첫 conv 의
     입력채널 인덱스가 ClientNet 마지막 stage 의 출력 인덱스와 반드시 같아야 한다.
     FedRolex 는 분할이 없어 이 부품이 논문에 아예 없다 — **새로 설계해야 하는 부분.**
 (3) 인덱스 기반 slice/scatter.
     models.py:slice_into 는 s[tuple(slice(0,n) for n in d.shape)] 로 모든 차원을
     앞쪽 접두로 자르고, nested_average 도 접두 위치에 누적한다. 회전 창을 쓰려면
     차원별 인덱스 벡터(출력채널=perm_i, 입력채널=perm_{i-1})와 advanced indexing /
     index_put_ 이 필요하다. 드롭인 아님 — 다만 경계가 명확한 유한한 개조다.
     (fed_server.py:60-61, 77, 89, 111 의 slice_into 호출이 전부 perm-aware 로 바뀌어야 함.)
 (4) shortcut/downsample conv 의 인덱스 장부.
     공식 코드는 shortcut 의 in_idx 를 대응 conv1 의 in_idx 에서, out_idx 를 현재 stage
     의 idx 에서 따로 가져온다. 우리 BasicBlock.sc 는 통짜 접두 슬라이싱을 받는다.
 (5) 라운드별 클라 표집(M ⊂ N). 원문 10% 참여. 우리는 전원 참여.
 → 위 (1)~(4) 때문에 **이 파일은 폭 배정만 집행하고 롤링은 집행하지 않는다.**
    Eq(4) 는 순수 산술로 구현·검증만 해 두었다 (window() / rolling_index_set()).

═══════════════════════════════════════════════════════════════════════════════
 ★ 회전 한 바퀴 계산 — 이 기준선을 불리하게 세우지 않기 위한 필수 보고
═══════════════════════════════════════════════════════════════════════════════
   보폭 r=1(FedRolex 기본)은 라운드당 1칸. 층 i 의 창이 한 바퀴 돌려면 K_i 라운드.
   우리 ResNet18 stage 폭 BASE=(64,128,256,512), 전역모델(β=1) 기준 K_max=512.
     → **가장 넓은 층이 한 바퀴 도는 데 512 라운드가 필요하다.**
   우리 run_g2.py 기본 rounds=14, rule_bench 로그도 12~14 라운드다.
     → 14/512 ≈ 2.7%. 창은 **한 바퀴는커녕 3%도 못 돈다.**
   결과: FedRolex 의 핵심 이득("모든 k 의 |M_k| 가 같아져 전역모델이 고르게 학습된다")
   은 우리 라운드 예산에서 **원리적으로 발현될 수 없다.** 이건 우리 실험대의 제약이지
   FedRolex 의 결함이 아니다. FedRolex 를 정확도 축에서 기준선으로 세울 거면
   라운드 예산을 K_max 급으로 늘리거나, 이 한계를 논문에 명시해야 한다.
   (우리 축은 TTA(벽시계)이고 FedRolex 에는 시간 개념이 아예 없으므로, 이 기준선의
    쓰임은 '정적 폭 배정 계열이 시간 축에서 어떻게 행동하는가' 를 보여주는 데 있다.)

═══════════════════════════════════════════════════════════════════════════════
 ★ 신규성 판정 (이 기준선이 우리 주장에 주는 위협)
═══════════════════════════════════════════════════════════════════════════════
   · FedRolex 는 **정적 폭 배정을 유지한 채** '바깥 채널이 덜 학습된다' 문제를 이미
     해결했다. 우리 논문의 동기를 "정적 배정은 바깥 채널을 덜 학습시킨다" 로 세우면
     FedRolex 가 그 동기를 무력화한다. 우리 주장은 **TTA(벽시계 시간)** 위에 세워야 한다.
   · 표면적 유사점 하나: 공식 코드의 model_split_mode='dynamic' 은 매 라운드 클라 용량을
     고정 다항분포에서 재추첨한다. 관측도 되먹임도 없는 무작위 추첨이라 '적응'이 아니지만,
     심사자가 '라운드마다 폭이 바뀌는 선례'로 지목할 수 있다. 선제적으로 구분해 둘 것.
   · 두 축은 직교하며 실제로 합성 가능하다: 우리 컨트롤러가 p 를 정하고, 그 p 짜리 창을
     FedRolex 방식으로 롤링. 경쟁이 아니라 결합 가능한 관계로 쓰는 편이 정확하다.
"""
import math

try:                                            # models.py 는 torch 를 끌어온다 — 선택적 import
    from models import BASE, LADDER, w          # noqa: F401
except Exception:                               # pragma: no cover
    LADDER = (0.25, 0.5, 0.75, 1.0)
    BASE = (64, 128, 256, 512)

    def w(c, p):
        return max(1, int(math.ceil(c * p)))


# ═══════════════════════════════════════════════════════════════════════════
#  Equation (4) — 롤링 창 인덱싱 (순수 산술. 논문 그대로)
# ═══════════════════════════════════════════════════════════════════════════

def window_len(K, beta, length_mode="ceil"):
    """창 길이 ⌊β_n K_i⌋.

    원문 Eq(4) 는 floor, 공식 코드(resnet_server.py)는 int(np.ceil(...)).
    우리 기본은 ceil — models.py:w(c,p)=ceil(c·p) 와 채널 수가 맞아야 하기 때문(D4).
    """
    L = math.floor(beta * K) if length_mode == "floor" else math.ceil(beta * K)
    return max(1, min(int(L), int(K)))


def rolling_offset(rnd, K, beta=1.0, overlap_r=1.0, roll_dir="paper",
                   length_mode="ceil"):
    """창 시작점 ĵ.

    r=1 (FedRolex 기본, Appendix A.4) → 보폭 1 → ĵ = j mod K_i  (= Eq(4) 그대로).
    r<1 → A.4 일반형: 라운드당 1+⌊β_n(1−r)K_i⌋ 칸 전진.
          ※ 일반형에서는 보폭이 β_n 에 걸리므로 시작점이 클라마다 갈린다.
             Eq(4) 의 'ĵ 에 n 이 없다' 는 성질은 r=1 에서만 성립한다. 원문도 r=1 이 기본.
    roll_dir="code" → 공식 코드 torch.roll 의 역방향 (D5). 통계적으로는 동치.
    """
    K = int(K)
    if overlap_r >= 1.0:
        step = 1
    else:
        step = 1 + int(math.floor(beta * (1.0 - overlap_r) * K))
    j = (int(rnd) * step) % K
    return (K - j) % K if roll_dir == "code" else j


def rolling_index_set(rnd, K, beta, overlap_r=1.0, roll_dir="paper",
                      length_mode="ceil"):
    """Equation (4) 그대로. 층 i 의 노드 인덱스를 **창 순서 그대로** 돌려준다.

        S^(j)_{n,i} = {ĵ, …, ĵ+L−1}                       if ĵ+L ≤ K_i
                    = {ĵ, …, K_i−1} ∪ {0, …, ĵ+L−1−K_i}   else      (L = ⌊β_n K_i⌋)

    순환 처리는 else 가지가 전부다 — 창이 K_i 를 넘으면 0 으로 되돌아 두 조각을 합친다.
    """
    K = int(K)
    L = window_len(K, beta, length_mode)
    jh = rolling_offset(rnd, K, beta, overlap_r, roll_dir, length_mode)
    if jh + L <= K:                                     # Eq(4) 첫째 가지
        return list(range(jh, jh + L))
    return list(range(jh, K)) + list(range(0, jh + L - K))   # Eq(4) else 가지 (wrap)


def static_index_set(K, beta, length_mode="ceil"):
    """Equation (6) — 정적 추출(HeteroFL/FjORD). 대조용. j 에 의존하지 않는다.
       S^(j)_{n,i} = {0, 1, …, ⌊β_n K_i⌋−1}"""
    return list(range(window_len(K, beta, length_mode)))


# ═══════════════════════════════════════════════════════════════════════════
#  Baseline
# ═══════════════════════════════════════════════════════════════════════════

class Baseline:
    name = "FedRolex"
    paper = ("Alam, Liu, Yan, Zhang. FedRolex: Model-Heterogeneous Federated "
             "Learning with Rolling Sub-Model Extraction. NeurIPS 2022. arXiv:2212.01548v2")

    def __init__(self, ks, p_min=0.25,
                 betas=None,              # 외생 β_n (Algorithm 1 의 Input 을 문자 그대로)
                 capacity_dist="uniform", # §4.2 "distributions … are uniform"
                 overlap_r=1.0,           # Appendix A.4. FedRolex 기본 r=1
                 roll_dir="paper",        # "paper"=Eq(4) 정방향 / "code"=torch.roll 역방향
                 length_mode="ceil",      # D4. 원문식은 "floor"
                 **kw):
        """ks = 클라이언트 id 리스트.

        betas 를 주면 그것이 곧 Algorithm 1 의 `Input : β_n` 이다 — 관측을 아예 하지 않는다.
        안 주면 §4.2 의 균등 용량 분포를 쓰되, 어느 클라가 어느 등급인지만
        **프로파일 라운드 1회** 관측 순위로 정하고 영구 동결한다 (D3).
        """
        self.ks = list(ks)
        self.p_min = p_min
        self.overlap_r = float(overlap_r)
        self.roll_dir = roll_dir
        self.length_mode = length_mode
        self.capacity_dist = capacity_dist
        # 사다리에서 p_min 이상만 사용 (우리 규약: 하한 아래로 내리지 않는다)
        self.levels = tuple(p for p in LADDER if p >= p_min - 1e-12) or (LADDER[-1],)

        # β_n : Algorithm 1 의 입력 상수. **한 번 정해지면 다시는 바뀌지 않는다.**
        self.beta = dict(betas) if betas else None
        self.assign_mode = "given" if betas else capacity_dist
        self.frozen = self.beta is not None      # 외생 β 면 이미 동결 상태
        self._r = 0                              # 내부 라운드 카운터 (rule_bench 용)
        self._ctl = None                         # 배치(deployment) 식별용

    # ── β 배정: 딱 한 번만 실행된다 ────────────────────────────────────────
    def _rank(self, ctl, batches):
        """프로파일 라운드 관측으로 클라를 **느린 순서**로 세운다.

        원문에는 이런 절차가 없다 — 원문의 β_n 은 기기 사양에서 외생적으로 온다(D3).
        우리 실험대는 기기가 동일하고 회선만 다르므로, 등급을 임의로 꽂으면
        기준선이 우연으로 망가진다(허수아비). 관측은 **여기 한 번뿐**이고
        그 뒤 어떤 라운드에서도 다시 부르지 않는다.
        """
        ks = list(ctl.ks)
        full = {k: 1.0 for k in ks}
        try:
            T = ctl.predict(full, batches)
            if all(k in T for k in ks):
                return sorted(ks, key=lambda k: -T[k])
        except Exception:
            pass
        # 폴백: 자기 회선이 느릴수록 / 연산이 느릴수록 낮은 등급
        def cost(k):
            b = ctl.bytes1.get(k, 0.0)
            c = ctl.Ck.get(k)
            return ctl.comp1.get(k, 0.0) + (b * 8 / c if c else 0.0)
        return sorted(ks, key=lambda k: -cost(k))

    def _freeze(self, ctl, batches):
        """β_n 을 확정하고 동결한다. 이 함수는 배치당 정확히 한 번만 호출된다."""
        ks = list(ctl.ks)
        n, m = len(ks), len(self.levels)
        order = self._rank(ctl, batches)          # 느린 순 → 빠른 순
        # §4.2: "the distributions of client model capacities are uniform"
        #   → N 명을 |β| 등분해 각 등급에 같은 수를 배정한다.
        #     가장 느린 조가 가장 작은 β, 가장 빠른 조가 β=1.0.
        self.beta = {}
        for r, k in enumerate(order):
            self.beta[k] = self.levels[min(m - 1, (r * m) // max(1, n))]
        self.frozen = True
        return self.beta

    # ── 롤링 창 (Eq 4) — 구현·검증만. 우리 파이프라인은 아직 소비하지 못한다 ──
    def layer_K(self):
        """전역모델(β=1)의 층별 K_i. stem 은 BASE[0] 과 같은 폭이다."""
        return {"stem": BASE[0], **{f"stage{i}": c for i, c in enumerate(BASE)}}

    def window(self, rnd, k, beta=None):
        """라운드 rnd 에 클라 k 가 받는 층별 노드 인덱스 = Eq(4) 의 S^(j)_{k,i}."""
        b = beta if beta is not None else (self.beta or {}).get(k, 1.0)
        return {nm: rolling_index_set(rnd, K, b, self.overlap_r,
                                      self.roll_dir, self.length_mode)
                for nm, K in self.layer_K().items()}

    def full_cycle_rounds(self):
        """창이 한 바퀴 도는 데 필요한 라운드 수 (층별). r=1 이면 K_i."""
        if self.overlap_r >= 1.0:
            return dict(self.layer_K())
        out = {}
        for nm, K in self.layer_K().items():
            b = max(self.beta.values()) if self.beta else 1.0
            step = 1 + int(math.floor(b * (1.0 - self.overlap_r) * K))
            out[nm] = int(math.ceil(K / step))
        return out

    # ── decide ────────────────────────────────────────────────────────────
    def decide(self, rnd, ctl, batches):
        """{client_id: width}.

        ★ **정적이다.** 라운드 0(관측 없음)에는 전폭을 내고, 관측이 처음 생긴 라운드에
          β_n 을 확정한 뒤 **마지막 라운드까지 같은 값을 낸다.** 논문 Algorithm 1 의
          루프에 β 를 갱신하는 줄이 없기 때문이다. 회선이 나빠지든 낙오자가 생기든
          FedRolex 는 반응하지 않는다 — 논문에 벽시계·대역폭·낙오자 개념이 없다.
        """
        # rule_bench 는 한 Baseline 객체로 여러 조건(= 서로 다른 연합)을 연달아 돌린다.
        # 조건이 바뀌면 새 배치이므로 동결 상태를 버린다 (외생 β 는 유지).
        if ctl is not self._ctl:
            self._ctl = ctl
            if self.assign_mode != "given":
                self.beta, self.frozen = None, False
        self._r = int(rnd) + 1                  # rule_bench 가 rnd 를 안 주므로 내부 카운터

        ks = list(ctl.ks)
        if not self.frozen:
            # 프로파일 라운드: 아직 관측이 없으면 전폭으로 한 라운드 돌며 관측을 만든다.
            if not ctl.comp1 or ctl.C is None:
                return {k: 1.0 for k in ks}
            self._freeze(ctl, batches)
        # 새 클라가 나타나면(전원참여가 아닐 때) 전폭으로 채운다 — 원문은 β 를 전원에 대해
        # 미리 갖고 있으므로 이 경우가 없다.
        return {k: self.beta.get(k, 1.0) for k in ks}


# ═══════════════════════════════════════════════════════════════════════════
#  자기시험
# ═══════════════════════════════════════════════════════════════════════════

def _selftest_eq4():
    """Eq(4) 의 성질을 직접 확인한다 (논문 §3.2 / Figure 1 / Appendix A.4)."""
    print("=" * 78)
    print("  Equation (4) 롤링 창 검증")
    print("=" * 78)
    K = 8
    print(f"  K_i={K}, length_mode=floor(원문식), r=1")
    for j in range(4):
        row = []
        for b in (0.25, 0.5, 0.75, 1.0):
            row.append(f"β={b}:{rolling_index_set(j, K, b, length_mode='floor')}")
        print(f"    j={j}  " + "  ".join(row))
    # 성질 1: 같은 라운드의 모든 클라가 같은 시작점 (ĵ 에 n 이 없다)
    ok1 = all(rolling_index_set(3, K, b, length_mode="floor")[0] == 3 % K
              for b in (0.25, 0.5, 0.75, 1.0))
    # 성질 2: 라운드 내부 중첩 — 소폭 창은 대폭 창의 (회전 좌표계에서의) 접두다
    big = rolling_index_set(3, K, 1.0, length_mode="floor")
    ok2 = all(big[:len(rolling_index_set(3, K, b, length_mode="floor"))]
              == rolling_index_set(3, K, b, length_mode="floor")
              for b in (0.25, 0.5, 0.75, 1.0))
    # 성질 3: wrap-around (else 가지) — K=8, j=6, β=0.5 → {6,7} ∪ {0,1}
    w6 = rolling_index_set(6, 8, 0.5, length_mode="floor")
    ok3 = w6 == [6, 7, 0, 1]
    # 성질 4: 한 바퀴 돌면 모든 인덱스를 정확히 L 번씩 본다 (evenly trained)
    cnt = [0] * K
    for j in range(K):
        for i in rolling_index_set(j, K, 0.5, length_mode="floor"):
            cnt[i] += 1
    ok4 = len(set(cnt)) == 1
    # 성질 5: Eq(6) 정적 추출과 j=0 에서만 일치, j>0 에서는 다르다
    ok5 = (rolling_index_set(0, K, 0.5, length_mode="floor") == static_index_set(K, 0.5, "floor")
           and rolling_index_set(1, K, 0.5, length_mode="floor") != static_index_set(K, 0.5, "floor"))
    # 성질 6: 공식 코드 방향(torch.roll)은 역방향 — 시작점 (K−j) mod K
    ok6 = rolling_index_set(3, K, 0.5, roll_dir="code", length_mode="floor")[0] == (K - 3) % K
    for tag, ok in [("ĵ 는 n 에 의존하지 않는다 (같은 라운드 = 같은 시작점)", ok1),
                    ("라운드 내부 중첩 유지 (회전 좌표계에서 소폭 = 대폭의 접두)", ok2),
                    (f"wrap-around else 가지  j=6,K=8,β=0.5 → {w6}", ok3),
                    (f"한 바퀴 후 갱신 횟수 균등 → {cnt}", ok4),
                    ("Eq(6) 정적 추출과 j=0 만 일치, j>0 은 다름", ok5),
                    ("roll_dir='code' 는 역방향 (D5)", ok6)]:
        print(f"    [{'OK ' if ok else 'NG '}] {tag}")
    # 보폭 일반형 (Appendix A.4)
    print(f"    r=0.5 일반형 보폭 (K=8, β=0.5): 1+floor(0.5*0.5*8) = "
          f"{1 + int(math.floor(0.5 * 0.5 * 8))} 칸/라운드 → "
          f"j=1 시작점 {rolling_offset(1, 8, 0.5, overlap_r=0.5)}")
    return all([ok1, ok2, ok3, ok4, ok5, ok6])


def _selftest_budget():
    """★ 회전 한 바퀴에 필요한 라운드 수 — 기준선을 불리하게 세우지 않기 위한 보고."""
    print("\n" + "=" * 78)
    print("  ★ 우리 라운드 예산에서 롤링이 발현되는가")
    print("=" * 78)
    b = Baseline([f"c{i}" for i in range(4)])
    cyc = b.full_cycle_rounds()
    print(f"    층별 K_i = {b.layer_K()}")
    print(f"    r=1 보폭 1 → 한 바퀴 필요 라운드 = {cyc}")
    J = 14                                   # run_g2.py 기본 rounds
    Kmax = max(b.layer_K().values())
    print(f"    우리 예산 J={J} 라운드 (run_g2 기본) → 가장 넓은 층 {Kmax} 중 "
          f"{J}/{Kmax} = {100.0*J/Kmax:.1f}% 만 회전")
    for beta in (0.25, 0.5, 0.75, 1.0):
        seen = set()
        for j in range(J):
            seen |= set(rolling_index_set(j, Kmax, beta))
        print(f"      β={beta}: J={J} 동안 전체 {Kmax}채널 중 {len(seen)}개 "
              f"({100.0*len(seen)/Kmax:.1f}%) 만 학습됨")
    print("    → FedRolex 의 '고르게 학습된다' 이득은 이 예산에서 원리적으로 발현 불가.")
    print("      (우리 실험대의 제약이지 FedRolex 의 결함이 아니다 — 보고 대상)")


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    _selftest_eq4()
    _selftest_budget()

    print("\n" + "=" * 78)
    print("  β 배정이 정적인지 확인 (Algorithm 1: β 는 Input, 루프에서 안 바뀐다)")
    print("=" * 78)

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "..", "_archive", "rule_search_2026-08"))
    from rule_bench import bench
    b = Baseline([f"c{i}" for i in range(4)])
    bench(lambda ctl, batches, alpha=1.2: b.decide(getattr(b, "_r", 0), ctl, batches),
          Baseline.name, verbose=True)
    print(f"\n  마지막 조건의 동결된 β_n = {b.beta}")
    print("  ※ 조건2·3 의 FAIL 은 정상이다 — FedRolex 는 회선/낙오자/벽시계에 반응하는")
    print("    규칙을 갖고 있지 않다. 반응하게 만들면 그건 FedRolex 가 아니다.")
