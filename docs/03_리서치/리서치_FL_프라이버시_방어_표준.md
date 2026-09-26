# 리서치 — 표준 연합학습은 프라이버시를 어떻게 방어하나 (14번 문서)

> 발단 질문: "일반 LLM 도 대화를 수집하는데 (그리고 FL 도 그래디언트가 새는데)
> 어떻게 방어하나?" — 심사 예상 공격. 이 문서는 업계·논문 표준을 조사해
> 우리가 가져올 것과 말할 수 있는 수위를 확정한다.
> 연결: 4번(보안_위협과_입장), 13번 §2.7(5겹 방어), 실험_L시리즈 LM-8.

## 1. 핵심 사실 — 구글조차 "FL만"으로는 안 된다고 보고 겹겹이 쌓았다

**Google Gboard 프로덕션 스택** (가장 성숙한 실전 배치):
FedAvg + **Secure Aggregation**(Bonawitz et al., CCS 2017 — 서버는 개별 업데이트를
못 보고 합만 복호화; SecAgg+ Bell et al., CCS 2020) + **user-level DP**
(DP-FTRL, Kairouz et al., ICML 2021 — 2022년 스페인어 Gboard 가 공식 DP 보장을
가진 최초의 프로덕션 신경망; ACL 2023 Industry 논문 기준 LM 20개+를 ρ-zCDP 로
배포, 라운드당 ~6,500 디바이스) + 최근 **TEE 집계**(Confidential Federated
Computations, arXiv 2404.10764).

기타 실전: Apple (local DP 애널리틱스 + iOS 13 부터 FL+DP — Siri 화자 인식·
QuickType), MELLODDY (제약 10사 — trunk 업데이트만 공유 + secure aggregation,
JCIM 2023), NVIDIA FLARE (EXAM 20개 병원, Nature Medicine 2021; HE 플러그인).

→ **심사 답변의 최선 소재**: "FL 도 샌다"는 지적은 맞다. 그래서 업계 표준 방어가
이미 존재하고(SecAgg·DP·TEE), 우리는 그 표준과 **호환되는 구조**다.

## 2. 공격 클래스 (알고 있어야 하는 것)

| 공격 | 출처 | 우리 관련성 |
|---|---|---|
| Gradient inversion (DLG) | Zhu et al., NeurIPS 2019; Geiping et al., NeurIPS 2020 | per-example 그래디언트가 최악 — **배치·집계가 클수록 급격히 어려워짐** (§4의 완화 논리) |
| Membership/property inference | Shokri S&P 2017; Melis S&P 2019 | DP 만이 수학적 상한 제공 |
| **분할학습 활성값 역산** | He et al., ACSAC 2019 | 절단면이 얕을수록 위험 — cut 깊이가 완화 변수 |
| **FSHA (feature-space hijacking)** | Pasquini et al., CCS 2021 | **악의적 서버** 위협 모델 — 우리 배치(서버=운영 주체 단일)에서는 위협 모델 명시로 경계 설정; NoPeek(distance correlation, ICDMW 2020)도 능동 공격엔 무력함을 알고 있어야 함 |
| 라벨 유출 (two-party SL) | Li et al., ICLR 2022 | 인지·언급용 |
| Gradient disaggregation | Lam et al., ICML 2021 | "집계=완화"는 "불가능"이 아니라 "현저히 어려움"으로 표현해야 하는 이유 |

## 3. 방어 도구함 요약 (막는 것 / 채택 / 우리 난이도)

| 방어 | 막는 것 | 실전 채택 | 어댑터-only SFL 적용 |
|---|---|---|---|
| Secure Aggregation | 서버가 개별 업데이트 보기 (honest-but-curious) | Gboard·MELLODDY, **Flower 내장**(SecAggPlusWorkflow) | 낮음~중간 — 어댑터 집계 경로에만 (활성값 경로 불가) |
| DP (DP-SGD/DP-FedAvg/DP-FTRL) | inversion·MIA 전부에 **수학적 상한** | Gboard 프로덕션, Flower·TFF 내장, Opacus | 클리핑은 낮음; 의미 있는 ε 은 클라 수 적으면 곤란 → "DP 파이프라인 검증"까지만 주장 |
| 동형암호 (Paillier/CKKS) | 서버 평문 접근 | FATE 기본, FLARE 플러그인 (크로스-사일로) | 중간~높음 — 언급용 |
| TEE | 서버 운영자 자신 + 원격 증명 | Google Confidential FC | 높음 — 향후 과제 언급용 |
| 희소화/압축 | (부수적) DLG 원논문: 희소화 ≥20% 면 공격 실패 보고 | — | 낮음 (보장 아님, 덤) |
| **강건 집계** (Krum·coordinate median·trimmed mean·norm clipping) | 클라이언트 포이즈닝 | **norm clipping 이 실무 1차 표준** (Sun et al. 2019 — DP 클리핑이 백도어도 완화) | **낮음 — 수십 줄, 즉시 적용 대상** |

## 4. LoRA 특유의 결론 — "어댑터만 보내서 안전"은 금지 문장

- 반례 존재: PEFT 대상 gradient inversion (**CVPR 2025**, 악의적 사전학습 모델+
  어댑터로 파인튜닝 데이터 복원), MineGrad. → **"LoRA 라서 원천 안전" 주장 금지.**
- 다만 그 공격들은 대부분 (a) 악의적 서버/모델 조작 (b) per-step 그래디언트 접근을
  가정. 우리 설정 = honest-but-curious 서버 + **다수 로컬 스텝 후 델타** + **다중
  클라 FedAvg 평균** + 파라미터의 ~1% 미만 → 공격 표면이 훨씬 좁다. 단 정량 보장
  논문은 없으므로 **"완화 요인"으로만** 말한다.
- DP 를 붙일 때의 직접 레시피: **FFA-LoRA** (Sun et al., ICLR 2024 — A 고정·B 만
  학습으로 저랭크 곱의 노이즈 증폭·집계 불일치 해소). 로드맵 항목.
- 활성값 경로는 LoRA 와 무관하게 §2 위협이 그대로 — **어댑터-only 로 활성값
  문제를 덮지 않는다** (4번 문서의 기존 입장 유지).

## 5. 우리가 지금 하는 것 / 로드맵 (사전 등록)

**즉시 (낮은 비용)**
1. TLS 전송 암호화 (기존)
2. **서버 측 어댑터 norm clipping** — 포이즈닝·유출 동시 완화, run_l2/fed_server
   집계부에 수십 줄. *구현 백로그 P1 등록*
3. **집계 후 개별 업데이트 즉시 폐기** (ephemeral updates — 구글도 강조하는 원칙)
   를 코드·문서에 명시
4. 옵트인 기부 질문의 **사람 검수 게이트** (LM-8) — 데이터 포이즈닝 방지의 우리 판

**로드맵 (언급용)**: Flower SecAgg+ 호환 구조, FFA-LoRA 기반 DP, TEE 집계.

## 6. 확정 문안 — 정직하고 방어 가능한 주장 (발표·질의응답용)

**금지**: "프라이버시 보장" / "유출 불가능" / "LoRA 만 보내므로 안전".

**표준 문안**:
> "원문 데이터와 사용자 질문은 기기를 떠나지 않고, 서버는 수집·저장하지 않습니다.
> 서버로 가는 것은 전체 파라미터의 1% 미만인 어댑터 델타뿐이며, 다수 로컬 스텝과
> 클라이언트 간 평균을 거친 값이라 개별 입력 복원은 알려진 공격 기준으로 현저히
> 어렵습니다 (Geiping et al., NeurIPS 2020). 연합학습 자체가 완전한 보장이 아님은
> 알고 있으며 — 그래서 구글도 SecAgg 와 DP 를 겹쳐 씁니다 — 우리는 그 표준 방어와
> 호환되는 구조로 설계했고, 어댑터 norm clipping 과 집계 후 즉시 폐기를 적용하며
> SecAgg+/FFA-LoRA 기반 DP 를 로드맵에 두고 있습니다."

**한 줄**: 위험이 없다가 아니라 — **위험을 알고 있고, 표준 경로가 있으며, 우리는
그 경로 위에 있다.**

## 7. 네트워크 보안 결합 — 재는 팀의 +α (사전 등록)

FL 보안을 모델층에서만 다루지 않고 **망층과 잇는다**. 세 층:

**7.1 망 격리층 — "KOREN 이라서 가능"의 보안판.** FL 트래픽이 폐쇄 연구망
(+VXLAN 오버레이) 안에서만 흐름 = 외부 관측 기회 자체의 제거. 여기에 **mTLS
상호 인증**(등록 기관 인증서만 라운드 참여)을 얹어 폐쇄망+포트 통제(26022)+
인증서의 3중 접근 통제. *구현: fed_server ssl wrap — 백로그 P1.*

**7.2 컨트롤러의 보안 확장 — 같은 컨트롤러, 보안 손잡이.** 이미 있는 대역내
측정·폭/배제 손잡이를 재사용: 어댑터 델타 norm 이상치(--clip-norm 신호)·예상 밖
업데이트 크기/빈도·미등록 주소 → **측정 기반 선별 = 측정 기반 격리** (포이즈닝
의심 노드를 컨트롤러가 좁히고 끊는다). 새 시스템이 아니라 기존 기계의 확장.

**7.3 트래픽 메타데이터 유출 실측 — 복제 불가 실험.** 암호화해도 패킷 크기·
타이밍은 샌다: 어댑터 동기 크기 ∝ rank 이므로 관측자는 **기관별 rank(=연산
능력)와 라운드 참여 여부**를 pcap 만으로 추정 가능 — 참여 자체가 메타데이터
유출(traffic analysis; SecAgg 도 이 층은 못 막는다). KOREN 실WAN 에서 ⓐ rank
추정이 실제로 되는지 실측 ⓑ 방어 = **최대 rank 크기로 패딩**(KB급 비용) 후 추정
실패 확인. rank 사다리는 우리 고유 설계라 이 실험은 우리만 만들 수 있다.
"재는 팀이 자기 시스템의 부채널을 재서 막는다."

→ 실측 등록: 실험_L시리즈 §5 **LM-9** (부채널)·**LM-10** (mTLS 오버헤드).

## 8. 축자 재현(regurgitation) 통제 — 기업 관행과 우리 기준선 (사전 등록)

**기업들의 수단**: ① 학습 전 중복 제거 — 암기량은 반복 횟수에 로그-선형 증가
(Carlini "Quantifying Memorization" 2022), dedup 만으로 축자 재현 ~10배 감소
(Lee et al. 2021) ② PII 스크러빙(민감 패턴 사전 제거) ③ DP 학습(§1) ④ **출력측
재현 필터** — Copilot 중복 필터(공개 코드와 ~150자급 연속 일치 시 제안 억제)류의
서빙 시점 n-gram 대조 ⑤ 배포 전 암기 감사 — 카나리아/추출 공격 (Secret Sharer,
Carlini 2019; run_l2 --canary-domain 이 우리 판).

**기준점의 조작적 정의 (학계 표준)**:
- **추출 가능 암기**: 학습 데이터 앞부분을 프롬프트로 → **이어지는 50토큰 축자
  일치**면 암기 판정 (Carlini 2021/2022, Nasr 2023 — 사실상의 표준 컷)
- **노출 지표(exposure)**: 카나리아 확률 순위의 연속값 계측
- **반사실 기준**: 그 예시를 빼도 맞히면 일반화, 못 맞히면 순수 암기 —
  "일부는 학습해도 된다"의 이론적 경계선 (공통 패턴=일반화, 고유 문장=암기)

**우리 규격 — 기준은 '암기 금지'가 아니라 '무엇의 축자 재현을 금지하는가'**:
| 층 | 내용 | 규칙 |
|---|---|---|
| 승인층 | 검수 통과한 배포용 사실 | 축자 재현 **허용** — 유출이 아니라 기능 (변형 반복도 허용) |
| 원문층 | 민감 원문·기부 질문 원문 | 학습 투입 금지 원칙. 파생 지식 투입 시: **연속 50토큰 축자 일치 금지선** + 서빙 시 원문층 대조 n-gram 필터 + 배포 전 카나리아 감사 게이트. 코퍼스 내 1회만(dedup)·표현 변형으로만 증폭 |

→ "어디까지 학습해도 되나" = 층(승인/원문) × 문턱(50토큰) × 게이트(카나리아 감사)
의 3좌표로 고정. 13번 v2 검수 게이트·LM-8 과 연결.

**자기 실측 (2026-08-27, run_l2 --canary-domain B1, 16×30)**: 가짜 비밀을 한
기관에만 주입 → 추출률 단독 100% / **연합 100%** / 베이스 0%. 집계 평균은 비밀을
희석하지 못했다 (지식 보존을 위해 라운드를 늘린 레시피에서는 비밀도 함께 보존됨 —
유틸리티와 프라이버시가 같은 손잡이라는 실증). 두 층 분리가 선택이 아니라 필수인
이유를 남의 논문이 아니라 **우리 리그의 숫자**로 말할 수 있다.

## 출처 (주요)

Bonawitz CCS 2017 · Bell CCS 2020 · Kairouz ICML 2021 (DP-FTRL) · Xu ACL 2023
Industry (Gboard DP) · Google Confidential Federated Computations arXiv 2404.10764 ·
Apple "Learning with Privacy at Scale" · MELLODDY JCIM 2023 · EXAM Nature Medicine
2021 · Zhu NeurIPS 2019 (DLG) · Geiping NeurIPS 2020 · Pasquini CCS 2021 (FSHA) ·
He ACSAC 2019 · Vepakomma ICDMW 2020 (NoPeek) · Li ICLR 2022 · Lam ICML 2021 ·
Blanchard NeurIPS 2017 (Krum) · Yin ICML 2018 · Cao NDSS 2021 (FLTrust) · Sun
arXiv 2019 (norm clipping vs backdoor) · Sun ICLR 2024 (FFA-LoRA) · CVPR 2025
(PEFT gradient inversion) · Flower SecAgg+/DP/Opacus 공식 문서 · NVIDIA FLARE HE.
