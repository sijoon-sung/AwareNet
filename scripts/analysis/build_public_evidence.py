"""Publish byte-preserving evidence copies and a claim-to-source index.

No experiment is run. Original records are never rewritten. Python stdlib only.
"""
from pathlib import Path
import hashlib
import html
import json
import shutil
import statistics
import zipfile

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / 'site/assets/evidence'
URL = 'https://sijoon-sung.github.io/AwareNet/site/'


def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def rows(p):
    return [json.loads(line) for line in p.read_text(encoding='utf-8-sig').splitlines() if line.strip()]


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    groups = []

    def group(id, title, claim, conditions, limits, files):
        records = []
        for p in sorted(set(Path(x) for x in files)):
            p = p if p.is_absolute() else ROOT / p
            if not p.is_file():
                raise FileNotFoundError(p)
            rel = p.relative_to(ROOT).as_posix()
            dst = DEST / id / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, dst)
            raw = p.read_bytes()
            item = dict(source_path=rel, public_path=f'{id}/{rel}', bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            if rel.startswith('_archive/v2/jetson/'):
                item['recovered_from_commit'] = '582b1d4e249918b2e1075d2a014acd00393ce1cb'
                item['historical_path'] = rel.removeprefix('_archive/v2/')
                item['sha256_lf_normalized'] = hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest()
            records.append(item)
        archive = DEST / f'{id}.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
            for r in records:
                z.write(DEST/r['public_path'], r['source_path'])
        g = dict(id=id, title=title, claim=claim, conditions=conditions, limits=limits,
                 archive=f'{id}.zip', archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(), files=records)
        groups.append(g)
        return g

    files = []
    koren = []
    for cond in ('normal', 'traffic', 'slow', 'vary'):
        result = dict(condition=cond)
        for policy in ('uniform', 'widthpath'):
            means = []
            for seed in (1, 2, 3):
                stem = f'out/wp_scen32_{cond}_s{seed}_bothmp_{policy}'
                files.extend(stem+ext for ext in ('.jsonl', '.args.json', '.profile.json'))
                rr = [r for r in rows(ROOT/(stem+'.jsonl')) if 'round' in r]
                assert [r['round'] for r in rr] == list(range(24))
                key = 'makespan' if 'makespan' in rr[0] else 'makespan_s'
                means.append(statistics.mean(r[key] for r in rr[4:]))
                args = read(ROOT/(stem+'.args.json'))
                assert args['clients'] == 32 and args['alpha'] == 1.2
                assert args['multipath'] == (policy == 'widthpath')
            result[policy] = dict(seed_means_s=means, mean_s=statistics.mean(means))
        result['reduction_pct'] = 100*(1-result['widthpath']['mean_s']/result['uniform']['mean_s'])
        koren.append(result)
    files += ['scripts/exp/run_scen32.sh', 'scripts/exp/run_real.sh', 'scripts/exp/scenario_perturb.sh',
              'scripts/exp/conditions.json', 'scripts/exp/cond.py', 'sfl/fed_client.py', 'sfl/fed_server.py',
              'sfl/net/real_rig.sh']
    files += list(ROOT.glob('out/scen32_*_s[123]_bothmp_perturb.log'))
    g = group('E1', 'KOREN 시나리오: 결합 시스템의 완료 시간',
              '기존 기준선과 폭·경로 결합 시스템의 조건별 평균 라운드 시간을 재집계한다.',
              'HPC의 CPU 클라이언트 32프로세스·V100 서버, KOREN VM 2대·논리 엣지 4개. CIFAR-10 CNN, cut=2, 배치 32×4, 24라운드×3시드×4조건×2정책. 초기 4라운드를 제외한 시드별 평균을 다시 평균한다.',
              '32대 물리 기기 실험이 아니다. tc 용량 교란과 연산 지연을 주입했다. 기준선과 결합 정책의 출구 수·폭·배정이 함께 달라 순수 경로 효과 및 동일 정확도 도달 시간을 입증하지 않는다. args.alpha=1.2는 지연 기준선 배율이며, 데이터 분할은 fed_client의 alpha-dir 기본값 0.5다. 로그의 mp 필드보다 실행 인자 및 출구 기록을 우선한다.', files)
    g['statistics'] = koren

    files = [ROOT/'_archive/v2/jetson/results/jetson_compute_anchor.json',
             ROOT/'_archive/v2/jetson/scripts/measure_lora_train_speed.py', ROOT/'docs/photo/HW2_Jetson_Orin_Nano.jpg']
    files += [p for p in (ROOT/'_archive/v2/jetson/results').glob('*_anchor/*') if p.is_file()]
    anchor = read(files[0])
    medians = []
    for mode, d in anchor['power_modes'].items():
        assert len(d['step_times_ms']) == 30
        m = statistics.median(d['step_times_ms'])
        assert round(m, 1) == d['step_median_ms']
        folder = {'MAXN_SUPER':'maxn_super', '25W':'25w', '15W':'15w'}[mode]+'_b1_s256_anchor'
        raw = read(ROOT/f'_archive/v2/jetson/results/{folder}/lora_train_speed.json')
        assert raw['step_times_ms'] == d['step_times_ms']
        medians.append(dict(mode=mode, n=30, median_ms=m, reported_median_ms=round(m,1)))
    g = group('E2', 'Jetson: 장비 연산 프로파일',
              '한 보드에서 측정한 전력 모드별 전체 학습 스텝 시간의 차이를 확인한다.',
              'Jetson Orin Nano Super 8GB 한 대. 2026-08-13~14 기록. Qwen2.5-0.5B FP32, LoRA r=32(q_proj/v_proj), batch=1, seq=256. 각 모드 warmup=3 제외 후 30스텝, 총 90스텝.',
              'KOREN 32프로세스 실행에 Jetson을 연결한 통합 실험이 아니다. 전체 LoRA 스텝 시간을 CNN 폭별 비용이나 반환 후 연산 시간으로 그대로 사용할 수 없다. 소프트웨어 버전은 환경 로그의 기록값이다. 원시 스텝·tegrastats·환경·콘솔과 측정 스크립트를 함께 제공한다.', files)
    g['statistics'] = medians
    g['provenance_note'] = '복구 파일은 Windows CRLF 바이트를 그대로 공개한다. 실행 환경의 script_sha256=297ec815b0522c3678161555fddd5318b64a3d155692ba636197635acbd11640은 공개 측정 스크립트의 LF 정규화 해시와 일치한다. 원본 이력은 비공개이며 공개 저장소에는 해당 파일의 사본을 포함한다.'

    group('E3', 'KOREN 전송: 실측값 주입의 입력',
          '지연 주입 재현에 사용한 실제 TCP 왕복 전송 기록을 추적한다.',
          'n=8, shrink=1.0, TCP, 경유 종점 2개. 배치당 상행·하행 각각 4.2 MB, 4배치×3라운드. batch와 burst는 서로 다른 송신 패턴이다.',
          'cap_mbps=8000은 설정값이며 물리 링크의 측정 용량이 아니다. aggregate_mbps 필드도 링크 용량으로 해석하지 않는다. 공통 측정 시간창 기반 처리율과 기기별 지연을 구분해야 한다. 이 입력의 재사용은 새로운 KOREN 실험을 의미하지 않는다.',
          ['out/line_scale_detail/n8_s1.0_tcp_batch_1788881912.json', 'out/line_scale_detail/n8_s1.0_tcp_burst_1788881939.json',
           'scripts/measurement/line_scale.py', 'scripts/measurement/line_scale.sh', 'configs/measurements/koren_jetson_2026-09-23.json'])

    old = read(ROOT/'configs/measurements/final_report_evidence_2026-09-26.json')
    files = [s['path'] for s in old['sources'] if s['path'].startswith(('out/fed_split/', 'out/scale_lora/'))]
    files += ['sfl/experiments/run_fed_split_lora.py',
              'docs/02_실험/실험_연합분할LoRA_문답증명_사전등록_2026-09-13.md',
              'docs/02_실험/실험_대형모델_분할LoRA_사전등록_2026-09-13.md']
    group('E4', 'LoRA: 분할 실행·집계·메모리',
          '분산 배치에서 실제 학습과 어댑터 집계를 수행하고 메모리 제약을 확인했다.',
          'KOREN VM 2대의 논리 클라이언트 3개와 HPC. Qwen2.5-0.5B, cut=2, rank=16, 16라운드×30스텝. strict 판정이 적용된 18문항: 미학습 0, 단독 6, 연합 두 방식 각 12개 정답. 7B 분할 10스텝은 별도 실행이다.',
          '소규모 자체 문답 실습이며 일반 벤치마크 또는 개인정보 보호의 입증이 아니다. 모델을 층으로 분할하는 SFL이며 특성 분할 VFL과 다르다. 앞부분 메모리 프로파일과 실제 분할 시스템 최대 메모리를 구분한다.', files)

    lab = read(ROOT/'site/assets/lab/manifest.json')
    group('E5', '가상 Linux 망: 커널·패킷·계측',
          'tc 집행, 실제 TCP 조각 전송, 재조립 및 관측을 한 실행에서 확인했다.',
          'virtual-20260926T142615Z. QEMU Linux, 4네임스페이스, 8논리 클라이언트, 128 KiB/기기, 폭=1.0. 한 경로 감소와 공유 IFB 병목. 18라운드·144전송·35,058패킷. 각 정책에 프로브 비용 포함.',
          '한 번의 로컬 가상 실행이며 라운드는 독립 반복이 아니다. 새 KOREN 측정·학습 성능이 아니다. raw tc 카운터의 포맷 문제와 정규화 기록을 보존한다. TCP 커널 알고리즘 패치는 하지 않았다.',
          ['site/assets/lab/manifest.json']+[f"site/assets/lab/{r['path']}" for r in lab['files']])

    audit = read(ROOT/'configs/measurements/network_implementation_audit_2026-09-26.json')
    group('E6', '구현: 폭·경로·권한 경계',
          '실제 코드로 구현 범위와 프로토타입 범위를 확인한다.',
          '계획기, TCP 전송·재조립, tc/IFB/HTB 스크립트 및 OS-Ken 확장을 제공한다.',
          '관리하거나 권한을 위임받은 호스트가 집행 대상이다. KOREN 코어 경로 제어와 기관 간 위임은 검증하지 않았다. OS-Ken 코드 존재는 실제 OVS 적용 증거가 아니다. 패킷 처리는 커널과 고정 전송 코드가 담당하고 계획은 라운드 수준에서 수행한다.',
          ['configs/measurements/network_implementation_audit_2026-09-26.json', 'sfl/plan.py', 'sfl/proto.py']+[r['path'] for r in audit['current_sources']])

    files = [p for p in ROOT.glob('out/wp_r8mix*') if p.suffix in ('.json', '.jsonl')]
    group('E7', '축소 실험과 실측값 주입 재현',
          '8프로세스 실행과 과거 측정값을 입력한 재현의 조건을 보존한다.',
          'r8mix 계열은 원래 파일명·args·profile로 실행을 구분한다. 200R 정확도 계열과 24R 시간 계열은 별개다. Jetson·KOREN 수치 주입은 2026-09-23 보고서의 가정과 집계에 따른다.',
          'SHRiNK를 참고한 축소 구성은 32대 물리 시스템과의 동등성을 입증하지 않는다. OOM·CPU 제약 때문에 실행 크기를 줄인 것으로, 8개와 32개의 결과를 합산하지 않는다. 주입값을 사용한 모형·로컬 결과를 하드웨어 재측정으로 표기하지 않는다.',
          files+['scripts/exp/conditions.json', 'docs/02_실험/실측주입_재현실험_2026-09-23.md', 'docs/02_실험/measured_replay_2026-09-23.json'])

    revised = read(ROOT/'configs/measurements/report_metrics_revised.json')
    published_paths = {r['source_path'] for g in groups for r in g['files']}
    extra_sources = [s['path'] for s in revised['sources'] if s['path'] not in published_paths]
    g = group('E8', '보고서 재집계: 시간·정확도·제어 동작',
          '기존 실행의 시간, 폭, 응용 전송량과 정확도를 함께 재집계하고 본문 그림으로 연결한다.',
          '32프로세스 24R×3시드: 초기 4R 제외 시간·폭·바이트, 최종 round 23 정확도. 8프로세스 200R×2시드: 초기 4R 제외 시간·폭, round 150–199 평균 정확도. E1·E7의 원시 로그 및 실행 인자를 사용한다.',
          'λ=280: 시간 20.7% 단축, 정확도 65.52%→65.22%. λ=70: 32.5% 단축, 63.17%. λ=18: 58.1% 단축, 53.59%. 모든 비교는 단일 출구 기준선과 두 출구 AwareNet의 구성 비교다. 정확도 평가는 시험 데이터 앞 2,000개와 실행별 최대 학습 폭을 사용했다. 두 시드의 요약값이며 독립 반복 수를 늘리는 후속 평가가 필요하다.',
          extra_sources+['configs/measurements/report_metrics_revised.json',
              'scripts/analysis/build_revised_report_metrics.py', 'scripts/analysis/revised_report_figures.py',
              'scripts/analysis/paper_diagrams.py', 'scripts/analysis/build_prose_report.py',
              'output/prose_awarenet/figures/revised_sources.json'])
    g['statistics'] = revised['accuracy_200']

    group('E9', '설계 선택의 이유: 용어·개발 과정·활용 예시',
          '클라이언트, CNN 모델 폭·폭 비율, LoRA 랭크를 정의하고 설계 선택의 이유를 문헌·코드·개발 기록에 연결한다. 은닉 차원 축소와 LoRA의 결합은 후속 검증 설계로 제공한다.',
          '8/29 방향 검토, 9/2 다중 경로 설계, 9/9 이후 컨트롤러 기록과 현재 모델 코드를 함께 제공한다. 4·3·2MiB는 배치 32, cut 2, FP32의 텐서 모양에 따른 계산이다.',
          '과거 문서는 당시의 제안·시행착오다. 현재 주장은 제출 보고서와 E1–E8을 따른다. 병원 등 기관 간 공동 학습은 기대 효과의 적용 시나리오다. 자체 정확도 제외의 과거 이유와 현재의 탐색 결과 해석도 보존한다. 멘토 의견은 설계 전환 회의록의 기록과 연결한다.',
          ['docs/03_리서치/용어와_설계선택_활용시나리오_2026-09-27.md',
           'docs/03_리서치/클라이언트_모델폭_LoRA_용어정리_2026-09-28.md',
           'docs/04_설계기록/LoRA_은닉차원축소_확장검토_2026-09-28.md',
           'docs/04_설계기록/설계전환_회의록.md',
           'docs/01_제출발표/방향검토보고서_AwareNet.md',
           'docs/03_리서치/실전_포지셔닝_FL배치지형.md',
           'docs/04_설계기록/설계_멀티패스_분할전송.md',
           'docs/04_설계기록/설계기록_컨트롤러.md',
           'sfl/models.py', 'sfl/models_llm.py',
           'sfl/experiments/run_fed_split_lora.py', 'sfl/experiments/run_scale_lora.py',
           'scripts/analysis/final_results_page.py'])

    manifest = dict(version=1, date='2026-09-28', kind='historical evidence publication; no new experiments',
                    byte_preserving_copies=True, groups=groups)
    (DEST/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    shutil.copyfile(DEST/'manifest.json', ROOT/'configs/measurements/publication_evidence_2026-09-27.json')
    esc = html.escape
    parts = ['<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AwareNet | 원자료 및 주장 근거</title><link rel="stylesheet" href="style.css"></head><body><header class="site-header"><div class="container header-inner"><a class="brand" href="index.html">AwareNet</a><nav><a href="index.html">연구 개요</a><a href="assets/report.pdf">보고서</a><a href="https://github.com/sijoon-sung/AwareNet">GitHub</a></nav></div></header><main class="container evidence-page"><p class="kicker">EVIDENCE REGISTER / 2026.09.28</p><h1>원자료와 주장 근거</h1><p class="intro">측정 대상, 실행 조건, 집계 방법과 해석 범위를 자료별로 정리했다. 원파일은 바이트를 변경하지 않고 복사했으며, 아래 목록에서 개별 파일과 SHA-256을 확인할 수 있다.</p><div class="links"><a href="assets/evidence/manifest.json">전체 출처·해시 원장</a><a href="assets/evidence/verify_evidence.py">재집계·해시 검증 코드</a></div><p class="note">SHA-256은 공개 파일의 동일성을 확인한다. 측정 장비나 당시 실행 환경의 독립적인 인증을 의미하지 않는다. 원본 비공개 저장소의 이력 대신 검증에 필요한 파일 사본과 복구 커밋 식별자를 공개한다.</p><nav class="contents" aria-label="증거 목록">']
    parts += [f'<a href="#{g["id"]}">{g["id"]} · {esc(g["title"])}</a>' for g in groups]
    parts.append('</nav>')
    md = ['# AwareNet 주장과 원자료 색인', '', '2026-09-28 갱신. 공식 제출 본문과 홈페이지가 사용하는 근거를 연결한다.', '', f'[공개 원자료 페이지]({URL}evidence.html) · [전체 원장](../configs/measurements/publication_evidence_2026-09-27.json)', '', '| ID | 자료 | 주장과 범위 |', '|---|---|---|']
    for g in groups:
        id = g['id']
        parts.append(f'<section id="{id}"><div class="section-title"><span class="section-id">{id}</span><h2>{esc(g["title"])}</h2></div><p>{esc(g["claim"])}</p><dl class="facts"><dt>조건·집계</dt><dd>{esc(g["conditions"])}</dd><dt>해석 범위</dt><dd>{esc(g["limits"])}</dd></dl>')
        if id == 'E2':
            parts.append('<p class="note">'+esc(g['provenance_note'])+'</p>')
            parts.append('<table><thead><tr><th>전력 모드</th><th>스텝 수</th><th>중앙값 (ms)</th></tr></thead><tbody>'+''.join(f'<tr><td>{r["mode"]}</td><td>{r["n"]}</td><td>{r["reported_median_ms"]}</td></tr>' for r in medians)+'</tbody></table>')
        parts.append(f'<p><a class="download" href="assets/evidence/{g["archive"]}">{id} 원자료 ZIP · {len(g["files"])}개 파일</a></p><details><summary>개별 원파일과 해시 ({len(g["files"])}개)</summary><ul class="file-list">')
        for r in g['files']:
            parts.append(f'<li><a href="assets/evidence/{esc(r["public_path"])}">{esc(r["source_path"])}</a><code>{r["sha256"]}</code><small>{r["bytes"]:,} bytes</small></li>')
        parts.append('</ul></details></section>')
        md.append(f'| [{id}]({URL}evidence.html#{id}) | {g["title"]} | {g["claim"]} {g["limits"]} |')
    parts.append('<section><h2>재집계 방법</h2><p>저장소의 site/assets/evidence 폴더에서 아래 명령을 실행하면 모든 원파일·ZIP 해시를 확인하고 KOREN 시간·정확도·전송량, 200라운드의 시간·정확도, Jetson 중앙값, LoRA 문답 점수를 다시 계산한다. Python 표준 라이브러리만 필요하다.</p><pre>python verify_evidence.py</pre></section></main><footer class="container">AwareNet · 측정과 재현의 범위는 각 자료의 조건을 따른다.</footer></body></html>')
    (ROOT/'site/evidence.html').write_text('\n'.join(parts), encoding='utf-8')
    (ROOT/'docs/EVIDENCE.md').write_text('\n'.join(md)+'\n', encoding='utf-8')
    print(json.dumps(dict(groups=len(groups), files=sum(len(g['files']) for g in groups), koren=koren, jetson=medians)))


if __name__ == '__main__':
    main()
