"""Validate saved outcomes and build the follow-up evidence index (no training)."""
import collections
import csv
import hashlib
import json
from pathlib import Path
import statistics as st
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/"out/followup_20261001"


def load(p): return json.loads(p.read_text(encoding="utf-8"))


def main():
    result={"scope":"local follow-up only; not new KOREN measurement"}
    for folder in ("fashion","fashion_100r"):
        run=BASE/folder
        done=load(run/"complete.json"); manifest=load(run/"manifest.json")
        rows=load(run/"results.json")
        assert done["runs"]==done["expected"]==len(rows)==9
        groups=collections.defaultdict(list)
        for row in rows:
            p=run/f"s{row['seed']}_{row['arm']}"
            pred=np.load(p/"predictions.npz")
            assert len(pred["labels"])==10000
            assert int((pred["predictions"]==pred["labels"]).sum())==row["correct"]
            logs=[json.loads(x) for x in (p/"rounds.jsonl").read_text().splitlines()]
            assert [x["round"] for x in logs]==list(range(1,manifest["rounds"]+1))
            assert all(np.isfinite(x["mean_loss"]) for x in logs)
            groups[row["arm"]].append(row)
        for seed in manifest["seeds"]:
            cohort=[x for x in rows if x["seed"]==seed]
            assert len(cohort)==3 and len({x["initial_sha256"] for x in cohort})==1
            shards=load(run/f"seed_{seed}_partition.json")
            flat=sum(shards,[])
            assert len(flat)==len(set(flat))==60000
        aggregate={arm:dict(n=len(v),accuracy_pct=st.mean(x["accuracy"] for x in v)*100,
                   sd_pp=st.stdev(x["accuracy"] for x in v)*100,
                   train_wall_s=st.mean(x["training_wall_s"] for x in v),
                   activation_gradient_bytes=v[0]["activation_gradient_bytes"]) for arm,v in groups.items()}
        paired={}
        for other in ("full","prefix"):
            delta=[(next(x for x in rows if x["seed"]==s and x["arm"]=="rolling")["accuracy"]-
                    next(x for x in rows if x["seed"]==s and x["arm"]==other)["accuracy"])*100 for s in manifest["seeds"]]
            paired["rolling_minus_"+other]=dict(per_seed_pp=delta,mean_pp=st.mean(delta),sd_pp=st.stdev(delta))
        result[folder]=dict(aggregate=aggregate,paired=paired,rounds=manifest["rounds"])
    run=BASE/"equal_connections_v2"
    done=load(run/"complete.json")
    rows=[json.loads(x) for x in (run/"raw.jsonl").read_text().splitlines()]
    assert len(rows)==done["measurements"]==done["expected"]==72
    groups=collections.defaultdict(list)
    for row in rows:
        assert row["hash_checks"]==6
        assert all(len(s)==2 for s in row["sets"].values())
        groups[row["scenario"],row["policy"]].append(row)
    table=[]
    for (scenario,policy),v in sorted(groups.items()):
        assert len(v)==3
        table.append(dict(scenario=scenario,policy=policy,n=3,wall_s=st.mean(x["wall_s"] for x in v),
                     wall_sd_s=st.stdev(x["wall_s"] for x in v),mean_width=st.mean(x["mean_width"] for x in v),
                     planning_ms=st.mean(x["planning_s"] for x in v)*1000))
    result["equal_connections"]=table
    result["integrity"]=dict(training_runs_verified=18,paired_initialization=True,disjoint_training_shards=True,
                              full_test_predictions_verified=True,tcp_measurements=72,hash_checks=432)
    sources=[p for p in BASE.rglob("*") if p.is_file() and p.suffix in (".json",".jsonl",".npz") and p.name!="summary.json"]
    result["file_hashes"]={str(p.relative_to(ROOT)).replace("\\","/"):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    (BASE/"summary.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    with (BASE/"equal_connections.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=list(table[0])); w.writeheader(); w.writerows(table)
    a=result["fashion_100r"]["aggregate"]
    lines=["# 追加 검증 및 차별성 검토 — 2026-10-01".replace("追加","추가"),"",
      "## 결론과 판정","",
      "모델 축소와 경로 제어의 결합 자체, 또는 LoRA 적용 자체를 최초성으로 주장하지 않는다. 기존 연구와 겹치는 범위가 확인되었다. 현재의 기여 후보는 공유 자원과 중계 선택을 반영해 불필요한 모델 축소를 줄이는 SFL 실행 구조와 실제 계측 근거다. 이번 로컬 실험은 해당 주장에 필요한 구성 요소를 점검하며, 네트워크와 학습을 통합한 목표 정확도 도달 시간의 증명은 남아 있다.","",
      "## 1. 차별성에 직접 관련된 선행연구","",
      "| 연구 | 확인한 내용 | AwareNet에서 비교할 지점 |","|---|---|---|",
      "| [Joint Routing and Model Pruning, 2026](https://arxiv.org/abs/2603.15188) | 분산 FL에서 라우팅과 프루닝을 결합하고 경로별 모델 유지량을 고려 | SFL의 배치별 활성값·기울기 왕복, 허용 중계, 상태 전환 시 모델 축소 억제의 구체적 차이 |",
      "| [Joint Model Pruning and Resource Allocation, GLOBECOM 2024](https://arxiv.org/abs/2408.01765) | 모델 프루닝과 무선 대역폭 배분 공동 최적화 | 공유 접속·중계 용량과 응용 계층 실행의 차이 |",
      "| [Low-Latency Federated Fine-Tuning, 2026](https://arxiv.org/abs/2602.01024) | 연합 언어모델의 클라이언트별 프루닝과 대역폭 배분 | LoRA 사용 자체보다 실제로 연결한 제어 범위와 실행 근거 |","",
      "위 비교는 논문 초록과 과제 정의를 확인한 범위다. 이 논문들을 재현하거나 동일 조건에서 이긴 결과는 아니다.","",
      "## 2. Fashion-MNIST 실제 추가 학습","",
      "기존 CIFAR-10 및 X-ray 시연과 다른 의류 10분류 데이터셋이다. 저장소의 분할 ResNet-18, 서브모델 추출 및 집계 코드를 사용했다. 3클라이언트, 100라운드, 라운드당 8스텝, 배치 32, 시드 41/42/43으로 전폭·고정 채널·순환 채널을 비교했다. 학습 표본 60,000개를 중복 없이 분할하고, 동일 시드 내 초기 가중치와 미니배치 인덱스를 맞췄다. 공식 시험셋 10,000개 전체에서 종료 모델을 평가했다.","",
      "| 방식 | 채널 비율 | 정확도 평균 ± 시드 표준편차 | 활성값·기울기 바이트 비율 |","|---|---|---:|---:|"]
    names={"full":"전폭","prefix":"고정 채널","rolling":"순환 채널"}
    for arm in ("full","prefix","rolling"):
        x=a[arm]; ratio=x["activation_gradient_bytes"]/a["full"]["activation_gradient_bytes"]
        lines.append(f"| {names[arm]} | {'1/1/1' if arm=='full' else '0.5/0.75/1'} | {x['accuracy_pct']:.2f}% ± {x['sd_pp']:.2f}%p | {ratio:.2f} |")
    lines += ["","바이트는 실제 생성한 텐서의 크기이며 소켓 전송량은 아니다. 실행은 로컬 순차 학습과 메모리 내 활성값·기울기 전달이다. 따라서 이 결과로 KOREN 속도 향상이나 폭·경로 결합의 정확도 효과를 주장하지 않는다. 세 시드의 표준편차는 신뢰구간이 아니다.","",
      "20라운드 파일럿 9개 실행을 먼저 수행했다. 높은 학습 손실과 짧은 학습 길이를 확인한 뒤, 모든 방식의 학습 길이를 동일하게 100라운드로 늘렸다. 그 외 설정은 유지했다. 파일럿과 본 실행은 같은 시드를 쓰므로 독립 6시드로 합치지 않는다. 두 단계의 모든 결과를 보존한다.","",
      "[100라운드 조건](../../out/followup_20261001/fashion_100r/manifest.json) · [결과](../../out/followup_20261001/fashion_100r/results.json) · [실행기](../../scripts/analysis/fashion_followup.py)","",
      "## 3. 연결 수를 맞춘 전송 진단","",
      "모든 정책에 클라이언트당 TCP 연결 2개, 클라이언트 3개, 같은 경로 용량과 λ=2초를 적용했다. 전폭 페이로드는 4MiB이며 폭에 비례해 크기를 줄였다. 4조건 × 6정책 × 3반복, 72회를 모두 보존했다. 실행 순서는 반복마다 섞었다.","",
      "**범위:** 실제 로컬 TCP로 바이트를 전송하되 연산 시간은 sleep, 중계 속도는 응용 계층 페이싱으로 주입했다. 기존 계획기 `sfl/plan.py`를 호출했다. 프로파일은 설정값을 알고 있는 조건이며 온라인 추정 오차·KOREN·커널 큐·기존 전송 프레임의 검증을 포함하지 않는다. 학습을 하지 않아 정확도 이득도 판단하지 않는다. 학습 실험과 일부 시간이 겹친 로컬 진단으로, 엄격한 호스트 격리 벤치마크는 아니다.","",
      "| 조건 | 고정 배정 | 정적 분산 | 경로만 | 폭만 | 독립 제어 | 결합 제어 |","|---|---:|---:|---:|---:|---:|---:|"]
    scenarios={"relay_congestion":"중계 집중","compute_straggler":"연산 지연","access_limited":"접속 제한","mixed":"혼합 병목"}
    for sc,label in scenarios.items():
        cells=[]
        for policy in ("fixed","balanced","path","width","independent","joint"):
            x=next(x for x in table if x["scenario"]==sc and x["policy"]==policy)
            cells.append(f"{x['wall_s']:.3f}s / {x['mean_width']:.3f}")
        lines.append("| "+label+" | "+" | ".join(cells)+" |")
    lines += ["","각 칸은 **측정 완료 시간 / 평균 폭**이다. 독립 제어는 고정 배정에서 폭을 정한 뒤 경로를 조정하는 사용자 정의 대조군이며 특정 선행논문을 재현한 정책이 아니다. 정적 분산 대조군은 초기부터 양쪽 경로를 사용한다.","",
      "- 통신 병목 단독에서는 정적 분산·경로만·결합 제어가 비슷했다. 이 조건은 결합의 독자적 이득을 뒷받침하지 않는다.",
      "- 연산 지연이나 접속 제한 단독에서도 결합 제어와 폭만 제어의 차이가 작았다.",
      "- 혼합 병목에서는 결합 제어가 독립 제어와 비슷한 시간에 더 큰 평균 폭을 유지했다. 이것은 모델 크기 보존 근거이며 정확도 보존을 직접 증명하지 않는다.",
      "- 최초 256KiB 입력은 기존 코드의 2MiB 미만 단일 연결 규칙 때문에 동일 연결 수 검사에서 중단했다. 유효 전송 결과를 생성하기 전에 중단했으며 폴더를 보존했다. 4MiB와 16배 용량으로 전송시간 규모를 유지해 새 폴더에서 재실행했다.","",
      "[조건](../../out/followup_20261001/equal_connections_v2/manifest.json) · [72회 원로그](../../out/followup_20261001/equal_connections_v2/raw.jsonl) · [집계 CSV](../../out/followup_20261001/equal_connections.csv) · [실행기](../../scripts/analysis/equal_connection_probe.py)","",
      "## 4. 세부 구현에서 남은 우선 과제","",
      "1. **통합 비교:** 같은 두 연결, 같은 데이터·시드·학습량에서 고정/폭만/경로만/독립/결합을 실제 학습과 함께 실행하고 목표 정확도 도달 시간을 비교한다.",
      "2. **시간 예측 검증:** 예측과 관측의 오차, 관측 지연, 설정 변경 비용을 기록한다. 새 TCP 진단은 알려진 프로파일을 사용하므로 이 항목을 해결하지 않았다.",
      "3. **품질 기준:** λ는 폭 축소 비용이다. 폭·랭크 유지량을 정확도 유지로 바꾸어 표현하지 않는다. 데이터 이질성과 장기 성능을 함께 평가한다.",
      "4. **경로 실행의 완결성:** 연결 실패·재조립 타임아웃·재연결·정책 적용 실패를 학습 라운드 로그와 연결한다. 현재 기능의 존재와 실패 복구 완료를 구분한다.",
      "5. **LoRA 범위:** 랭크 선택 모듈과 고정 랭크 경로 실험을 통합하고, 랭크 변경 시 optimizer/집계 인덱스 일관성을 검증해야 동적 랭크·경로 공동 실행을 주장할 수 있다.","",
      "## 5. 발표와 KOREN 후속 계획","",
      "[발표용 코드·원자료 동선](../01_제출발표/발표_근거_안내.md)과 [KOREN SDN·L2VPN·T-SDN 후속 검증](../05_KOREN_장비/KOREN_후속연계_검증계획_2026-10-01.md)을 연결했다. 과거 폴더를 이동해 기존 원자료 링크를 깨뜨리는 대신 현재 코드, 실험 조건, 원로그, 집계, 공개자료의 역할을 구분했다.","",
      "검증: 18개 학습 실행의 10,000개 예측과 기록 정확도 일치, 시드별 초기 가중치 일치, 60,000개 학습 인덱스 중복 없음, 72회 전송의 432개 수신 해시 확인. [기계 판독 집계와 파일 해시](../../out/followup_20261001/summary.json). 공개 보고서·홈페이지에는 아직 반영하지 않았다.",""]
    (ROOT/"docs/02_실험/추가검증_2026-10-01.md").write_text("\n".join(lines),encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!="file_hashes"},ensure_ascii=False,indent=2))


if __name__=="__main__": main()
