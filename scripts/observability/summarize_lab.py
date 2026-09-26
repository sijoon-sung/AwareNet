"""Derive publication artifacts from a completed real virtual-network run.

Raw guest records and capture are immutable. iproute2 counter normalization is
written separately, including its provenance. No missing timing is imputed.
"""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import shutil
import statistics
import sys
import subprocess
import tarfile
import urllib.request
import urllib.parse

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/analysis'))
from paper_diagrams import Fig, INK, MUTED, LINE, TEAL, PURPLE, BLUE, PALE
from reportlab.graphics import renderSVG, renderPDF


def write_json(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')


def export_fig(fig,folder):
    svg=folder/(fig.stem+'.svg')
    renderSVG.drawToFile(fig.d,str(svg))
    text=svg.read_text(encoding='utf-8').replace('font-family: Diagram Malgun Bold;', 'font-family: Malgun Gothic, sans-serif; font-weight: 700;').replace('font-family: Diagram Malgun;', 'font-family: Malgun Gothic, sans-serif;')
    svg.write_text(text,encoding='utf-8')
    qa=ROOT/'tmp/pdfs/observability';qa.mkdir(parents=True,exist_ok=True)
    renderPDF.drawToFile(fig.d,str(qa/(fig.stem+'.pdf')))
    poppler=Path('C:/Users/DISLAB/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe')
    subprocess.run([str(poppler),'-scale-to-x','2400','-scale-to-y','-1','-singlefile','-png',str(qa/(fig.stem+'.pdf')),str(folder/fig.stem)],check=True,capture_output=True)


def topology():
    f=Fig('topology',620,'','','')
    f.domain(25,25,1350,380,'QEMU / Linux namespaces · 2 vCPU · 1 GiB')
    f.box(70,140,240,150,PALE,LINE,r=7)
    for i in range(8):f.device(95+(i%4)*50,172+(i//4)*47,32,27)
    f.text(190,308,'8 logical clients',27,anchor='middle')
    for i,y in enumerate([130,280],1):
        f.box(480,y,260,76,PALE,TEAL if i==1 else PURPLE,r=7)
        f.text(610,y+19,'E'+str(i)+' / HTB + netem',25,anchor='middle')
        f.path([(310,215),(385,215),(385,y+38),(480,y+38)],TEAL if i==1 else PURPLE)
        f.path([(740,y+38),(850,y+38),(850,215),(965,215)],TEAL if i==1 else PURPLE)
    f.server(1020,140,175,135)
    f.box(900,285,410,75,None,LINE,True,r=5)
    f.text(1105,301,'Shared IFB / 2 Mbit/s',25,anchor='middle')
    f.text(1105,331,'shared_access only',18,MUTED,anchor='middle')
    f.text(300,362,'128 KiB / client · 4 KiB chunks · width = 1.0',24,anchor='middle')
    f.text(835,85,'E1: 2 → 0.5 Mbit/s (R2)',23,TEAL)
    f.text(835,113,'E2: 2 Mbit/s · netem: 10 ms',23,PURPLE)
    for name,x in [('tc / events',40),('TShark / PCAP',315),('Collector',590),('Prometheus',865),('Grafana',1140)]:
        f.box(x,474,220,72,PALE,LINE,r=5)
        f.text(x+110,495,name,24,anchor='middle')
    f.path([(150,474),(150,440),(700,440),(700,474)],INK)
    for a,b in [(535,590),(810,865),(1085,1140)]:f.arrow(a,510,b,510,INK)
    f.text(700,573,'Owned virtual interfaces only · no KOREN core control',23,MUTED,anchor='middle')
    return f


def result_figure(summary):
    f=Fig('results',610,'','','')
    colors=[BLUE,TEAL,PURPLE]
    labels={'single':'Single','fixed_dual':'Fixed dual','adaptive_dual':'Adaptive dual'}
    for j,cond in enumerate(['edge_drop','shared_access']):
        x0=70+j*700; ymax=27 if j==0 else 11
        f.text(x0,20,('(a) Capacity drop / R2–R4' if j==0 else '(b) Shared bottleneck / R1–R2'),28,bold=True)
        f.text(x0,61,'Total seconds = transfer + probes',21,MUTED)
        plot_y,plot_h=115,315;left=x0+40;plot_w=525
        for tick in ([0,5,10,15,20,25] if j==0 else [0,2,4,6,8,10]):
            yy=plot_y+plot_h-tick/ymax*plot_h
            f.line(left,yy,left+plot_w,yy,LINE,1)
            f.text(left-13,yy-12,str(tick),20,MUTED,anchor='end')
        for i,policy in enumerate(['single','fixed_dual','adaptive_dual']):
            item=summary['groups'][cond][policy];x=left+35+i*175;w=95
            net=item['network_mean_s'];probe=item['probe_mean_s'];total=item['total_mean_s']
            nh=net/ymax*plot_h;ph=probe/ymax*plot_h
            f.box(x,plot_y+plot_h-nh,w,nh,colors[i],None)
            f.box(x,plot_y+plot_h-nh-ph,w,ph,'#DDE4E7',colors[i],width=1)
            f.text(x+w/2,plot_y+plot_h-nh-ph-33,f'{total:.2f}',25,bold=True,anchor='middle')
            f.text(x+w/2,448,labels[policy],21,anchor='middle')
            f.text(x+w/2,482,f'n = {item["rounds"]}',19,MUTED,anchor='middle')
        f.text(x0+300,532,'Bars: mean · independent repeats: 1',20,MUTED,anchor='middle')
    f.box(350,580,24,18,'#DDE4E7',None);f.text(386,574,'probe cost included',20,MUTED)
    f.text(770,574,'144/144 payload hashes matched',20,TEAL)
    return f


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);a=p.parse_args()
    folder=a.run.resolve();raw=folder/'run';site=ROOT/'site/assets/lab';site.mkdir(parents=True,exist_ok=True)
    if not raw.exists():
        with tarfile.open(folder/'lab-results.tar.gz') as arc:arc.extractall(folder,filter='data')
    rounds=json.loads((raw/'rounds.json').read_text());packets=json.loads((raw/'packets.json').read_text())
    assert len(rounds)==18 and all(x['all_hashes_match'] for x in rounds)
    assert packets['packets']>0 and packets['dissected_application_rows']>0
    derived=copy.deepcopy(rounds);corrections=[]
    for row in derived:
        name=f'kernel-{row["condition"]}-{row["policy"]}-r{row["round"]}.json'
        record=json.loads((raw/name).read_text())
        totals=[]
        for i in [1,2]:
            def count(when):return sum(x.get('stats',x).get('bytes',0) for x in record[when][f'awn-edge{i}']['classes'])
            totals.append(count('after')-count('before'))
        assert all(x>0 for x in totals)  # Both paths carry a probe, even for single.
        corrections.append({'condition':row['condition'],'policy':row['policy'],'round':row['round'],'source':name,
                            'original':row['kernel_bytes_delta'],'normalized':totals})
        row['kernel_bytes_delta']=totals
    write_json(folder/'rounds.normalized.json',derived)
    write_json(folder/'counter-normalization.json',{'reason':'iproute2 7 stores class counters in stats.bytes; raw event parser expected bytes. Timing and payload records are unchanged.','corrections':corrections})
    groups={}
    for condition in ['edge_drop','shared_access']:
        groups[condition]={}
        for policy in ['single','fixed_dual','adaptive_dual']:
            rr=[x for x in derived if x['condition']==condition and x['policy']==policy and (condition!='edge_drop' or x['round']>=2)]
            groups[condition][policy]={'rounds':len(rr),**{key:statistics.mean(x[field] for x in rr) for key,field in [('network_mean_s','network_seconds'),('probe_mean_s','probe_seconds'),('total_mean_s','total_seconds')]},'total_round_seconds':[x['total_seconds'] for x in rr]}
    reduction=100*(1-groups['edge_drop']['adaptive_dual']['total_mean_s']/groups['edge_drop']['fixed_dual']['total_mean_s'])
    shared_penalty=100*(groups['shared_access']['adaptive_dual']['total_mean_s']/groups['shared_access']['single']['total_mean_s']-1)
    summary={'run_id':folder.name,'round_count':len(rounds),'transfer_count':sum(len(x['clients']) for x in rounds),
             'packets':packets['packets'],'streams':packets['streams'],'application_rows':packets['dissected_application_rows'],
             'groups':groups,'edge_drop_total_reduction_pct':reduction,'shared_vs_single_total_increase_pct':shared_penalty,
             'conclusion':f'한 경로의 용량이 감소한 조건에서 적응 분할은 고정 분할보다 프로브 포함 완료 시간이 {reduction:.1f}% 짧았습니다. 공통 병목에서는 적응 두 경로가 단일 경로보다 {shared_penalty:.1f}% 느렸습니다. 경로 수를 늘리는 것보다 병목을 구분하는 것이 중요합니다.',
             'limitation':'한 번의 가상 실행입니다. 조건별 라운드는 독립 반복이 아니며 유의성·현장 성능·학습 정확도를 주장하지 않습니다. TCG 가상 CPU, 패킷 캡처, 고정된 정책 실행 순서의 영향을 포함합니다.',
             'new_koren_measurement':False,'new_training':False,'fixed_width':1.0,'clients':8,'payload_bytes_per_client':131072,'chunk_bytes':4096,
             'environment':json.loads((raw/'environment.json').read_text()),'packet_analysis':packets,
             'counter_normalization':'See counter-normalization.json; raw data preserved.'}
    write_json(folder/'summary.json',summary)
    export_fig(topology(),folder);export_fig(result_figure(summary),folder)
    for name in ['summary.json','counter-normalization.json','rounds.normalized.json','topology.svg','topology.png','results.svg','results.png']:
        shutil.copy2(folder/name,site/name)
    for name in ['capture.pcapng','rounds.json','events.jsonl','packets.csv','packets.json','environment.json','capture.log']:
        shutil.copy2(raw/name,site/name)
    shutil.copy2(ROOT/'observability/grafana/dashboard.json',site/'dashboard.json')
    shutil.copy2(ROOT/'observability/wireshark/awarenet.lua',site/'awarenet.lua')
    shutil.copy2(ROOT/'observability/README.md',site/'reproduce.md')
    # Preserve every kernel snapshot, logs, and the exact executed byte transport.
    with tarfile.open(folder/'lab-results.tar.gz') as _:pass
    runtime=ROOT/'tmp/observability'/folder.name
    shutil.copy2(runtime/'bundle.tgz',site/'executed-source.tgz')
    shutil.copy2(folder/'lab-results.tar.gz',site/'raw-results.tar.gz')
    files=[{'path':q.name,'sha256':hashlib.sha256(q.read_bytes()).hexdigest(),'bytes':q.stat().st_size} for q in sorted(site.iterdir()) if q.is_file() and q.name not in ['manifest.json','report.html']]
    write_json(site/'manifest.json',{'run_id':folder.name,'created_utc':datetime.now(timezone.utc).isoformat(),'files':files})
    rows=''
    for cond in groups:
        for policy,item in groups[cond].items():
            rows+=f'<tr><td>{cond}</td><td>{policy}</td><td>{item["rounds"]}</td><td>{item["network_mean_s"]:.3f}</td><td>{item["probe_mean_s"]:.3f}</td><td>{item["total_mean_s"]:.3f}</td></tr>'
    source_rows=''.join(f'<tr><td><a href="{html.escape(x["path"])}">{html.escape(x["path"])}</a></td><td>{x["bytes"]:,}</td><td><code>{x["sha256"]}</code></td></tr>' for x in files)
    report=f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AwareNet 통합 계측 실험</title><style>body{{font:15px/1.85 system-ui,sans-serif;color:#20333b;max-width:1080px;padding:40px 24px;margin:auto;background:#fbfcfa}}h1{{font-size:32px;letter-spacing:-.04em}}h2{{font-size:23px;margin-top:45px}}img{{width:100%;background:white;border:1px solid #dbe1dc}}table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{padding:12px;border-bottom:1px solid #dbe1dc;text-align:left}}code{{font-size:10px;overflow-wrap:anywhere}}a{{color:#0b796b}}.note{{border-left:3px solid #756298;padding:15px 22px;background:#f0edf5}}.overflow{{overflow:auto}}small{{color:#5e6f73}}</style><p><a href="../../index.html#lab">← AwareNet 소개</a></p><h1>통합 계측소를 이용한 가상 네트워크 실험</h1><small>{folder.name} · 실제 Linux tc/TCP · 새 KOREN 실측 없음 · 새 학습 없음</small><p class="note">{summary['conclusion']}</p>
<h2>1. 무엇을 실행했는가</h2><p>Linux 6.18.52, iproute2 7.0, TShark 4.6.6을 사용하는 Alpine 3.24.2를 QEMU TCG의 2 vCPU·1 GiB 환경에서 실행했다. 기기·엣지 2개·서버에 해당하는 네임스페이스 4개를 만들고 실제 veth와 커널 라우팅을 설정했다. 기기 네임스페이스 안의 8개 스레드가 논리 클라이언트이며 물리 기기 8대가 아니다.</p><img src="topology.svg" alt="가상 실험의 네임스페이스, 두 경유 경로 및 통합 계측 구조"><p>클라이언트마다 128 KiB의 결정적인 합성 바이트열을 4 KiB 조각으로 전송했다. 폭은 1.0으로 고정했다. 서버가 재조립한 바이트열의 SHA-256을 기존 양방향 전송 경로로 반환하고 클라이언트가 검증했다. 학습 활성값이나 모델 정확도를 측정한 실험은 아니다. 실험용 조각 크기 4 KiB는 운영 기본 하한 64 KiB와 다르다.</p>
<h2>2. 조건과 비교 정책</h2><p>각 경로에 HTB와 단방향 netem 10 ms를 적용했다. edge_drop에서는 첫 라운드에 두 경로가 각각 2 Mbit/s이며 R2부터 E1을 0.5 Mbit/s로 낮췄다. shared_access에서는 두 경로를 각각 2 Mbit/s로 두고 서버의 양쪽 ingress를 하나의 IFB에 모아 합계 2 Mbit/s로 제한했다. 이 공통 병목은 접속 병목의 용량 제약을 대신하는 가상 구성으로, 실제 무선 업링크를 재현한 것은 아니다.</p><p>single은 E1만 사용하고, fixed_dual은 두 경로에 같은 가중치를 준다. adaptive_dual은 매 라운드 두 개의 128 KiB 프로브를 동시에 보내 수신 확인까지의 처리율에 비례한 가중치를 준다. 모든 정책에 같은 프로브 비용을 부과했다. 동일한 두 경로를 사용하는 fixed_dual과 adaptive_dual이 정책 비교의 중심이다. 이는 검증용 비례 분할 정책이며 기존 widthpath 또는 network 계획기 전체의 성능 시험이 아니다.</p><p>실행 순서는 edge_drop → shared_access, 각 조건 내 single → fixed_dual → adaptive_dual로 고정했다. 연결은 정책별 라운드 사이에 재사용했다. 실행 순서를 무작위화하거나 여러 독립 시드로 반복하지 않았다.</p>
<h2>3. 관측 결과</h2><img src="results.svg" alt="프로브 포함 완료 시간의 조건별 정책 비교"><div class="overflow"><table><thead><tr><th>조건</th><th>정책</th><th>라운드</th><th>전송 평균(s)</th><th>프로브 평균(s)</th><th>합계 평균(s)</th></tr></thead><tbody>{rows}</tbody></table></div><p>edge_drop 집계는 용량 감소 이후 R2–R4이고 shared_access는 R1–R2이다. 전체 18라운드의 144개 본 전송이 모두 SHA-256 검사를 통과했다. 프로브 확인, 응용 메타데이터와 회신도 실제 TCP를 사용한다. 프로브 포함 시간은 프로브와 본 전송의 합이며 tc 적용·스냅샷 수집·라운드 사이 대기는 포함하지 않는다.</p><p>{summary['limitation']} 특히 단일 경로의 저속 라운드 중 긴 완료 시간이 있었으며 제거하지 않았다. 용량 감소 조건의 개선율을 KOREN 성능이나 독립 반복의 통계적 유의성으로 일반화하지 않는다.</p>
<h2>4. 패킷과 커널 근거</h2><p>TShark는 기기 네임스페이스의 any 인터페이스에서 TCP 20500번 포트만 캡처했다. 실제 PCAP에 {packets['packets']:,}개 패킷과 {packets['streams']}개 TCP 스트림이 있으며 Lua 해석기가 {packets['dissected_application_rows']:,}개 행에서 응용 전송 ID를 읽었다. 가상 인터페이스에서 TSO/GSO/GRO를 끈 상태를 환경 기록에 보존했다. TCP ACK RTT는 큐 대기와 TCP 흐름을 포함하며 설정된 netem 지연이나 텐서 완료 시간과 동일하지 않다. 재전송 플래그는 독립적으로 측정한 손실률이 아니다.</p><p>라운드 전후의 tc JSON을 보존했다. 실행 당시 카운터 파서는 top-level bytes를 예상했지만 iproute2 7.0은 stats.bytes를 반환하여 실시간 바이트 게이지가 0으로 기록되었다. 원본을 보존하고 저장된 커널 스냅샷에서 바이트 차이를 재계산하여 rounds.normalized.json과 counter-normalization.json에 명시했다. 시간과 무결성 결과는 변경하지 않았다. 이후 실행용 파서는 두 형식을 모두 지원하도록 수정했다.</p><p>Prometheus는 실제 완료 이벤트를 1초마다 수집했고 Grafana는 이 데이터를 조회한다. Grafana의 최초 플러그인 자동 업데이트 실패로 초기 화면 조회가 중단되어, 제공된 번들의 Prometheus 플러그인을 복구하고 자동 업데이트를 끈 뒤 실제 수집 시계열의 조회를 확인했다. 이는 전송 실험을 재실행하거나 새로운 성능 값을 만든 과정이 아니다.</p>
<h2>5. 주장과 한계</h2><p>입증 범위는 소유한 가상 Linux 인터페이스에서 커널 기능을 실제 설정하고, 선택한 경유 구간으로 실제 TCP 바이트를 나누어 보내고, 서버에서 결합·검증하고, 이를 패킷과 대시보드로 추적한 것이다. 기관 간 SDN 위임, KOREN 코어의 라우팅 변경, TCP slow start 커널 패치, 모델 정확도 개선은 입증하지 않았다. 경로 비율 조정은 응용 조각 스케줄러에서, 용량 설정은 커널 tc에서 수행했다.</p><p>공유 병목에서는 추가 경로의 효과가 사라졌으며 프로브와 동시 연결의 비용이 남았다. 따라서 적용 논리는 '다중 경로는 항상 빠르다'가 아니라 공유 자원과 완료 지연을 관측하여 폭 제어와 경로 제어의 적용 조건을 구분하는 데 있다.</p>
<h2>6. 재현과 원자료</h2><p><a href="reproduce.md">재현 안내</a> · <a href="raw-results.tar.gz">모든 원시 로그·커널 스냅샷</a> · <a href="executed-source.tgz">실행 당시 정확한 소스</a> · <a href="manifest.json">출처·SHA-256 원장</a></p><div class="overflow"><table><thead><tr><th>파일</th><th>바이트</th><th>SHA-256</th></tr></thead><tbody>{source_rows}</tbody></table></div></html>'''
    (site/'report.html').write_text(report,encoding='utf-8')
    print(json.dumps({k:summary[k] for k in ['round_count','transfer_count','packets','edge_drop_total_reduction_pct','shared_vs_single_total_increase_pct']}))

if __name__=='__main__':main()
