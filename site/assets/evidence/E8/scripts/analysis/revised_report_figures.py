"""Architecture drawings and scientific plots for the scheduler-focused report."""
from pathlib import Path
import hashlib
import html
import json
import os
import subprocess
import sys
import zipfile
from reportlab.graphics import renderPDF, renderSVG
from paper_diagrams import Fig, ROOT, OUT, INK, MUTED, LINE, BLUE, TEAL, PURPLE, PALE, WHITE


def native_figures():
    fs={}
    f=Fig('R1_architecture',520,'AwareNet의 구성과 학습 흐름','기기는 앞부분, 서버는 뒷부분을 학습하고 중계 서버는 텐서 조각을 전달한다.')
    fs[f.stem]=f
    f.box(385,20,630,110,PALE,LINE,r=8)
    f.text(700,35,'AwareNet 스케줄러',34,INK,True,'middle')
    f.text(700,83,'계산 시간 · 전송량 · 경로 용량',26,MUTED,False,'middle')
    for x,title in [(30,'기기'),(516,'중계 서버'),(1100,'학습 서버')]:
        f.text(x+130,189,title,27,INK,True,'middle')
    f.box(30,237,260,202,PALE,LINE,r=8)
    for i in range(3):
        f.device(52+i*75,263,51,47)
        for j in range(4):f.box(53+i*75+j*11,335,8,48-(i*7),PURPLE if j<4-i else '#DCE1E6',None)
    f.text(160,402,'채널 비율 w',26,PURPLE,False,'middle')
    for y,label in [(243,'E1'),(367,'E2')]:
        f.box(576,y,238,70,WHITE,TEAL,r=5);f.text(695,y+17,label,30,TEAL,True,'middle')
    f.server(1150,264,147,142);f.text(1222,426,'재조립 → 학습',25,BLUE,False,'middle')
    f.path([(292,322),(430,322),(430,278),(570,278)],TEAL)
    f.path([(430,322),(430,402),(570,402)],TEAL)
    f.path([(820,278),(998,278),(998,324),(1140,324)],TEAL)
    f.path([(820,402),(998,402),(998,324)],TEAL,arrow=False)
    f.text(430,247,'활성값',25,TEAL,True,'middle');f.text(998,247,'활성값',25,TEAL,True,'middle')
    f.path([(1145,457),(1033,488),(370,488),(287,437)],BLUE,True)
    f.text(720,468,'기울기',24,BLUE,True,'middle')
    f.path([(480,130),(480,163),(158,163),(158,185)],PURPLE,True)
    f.path([(893,130),(893,163),(695,163),(695,185)],PURPLE,True)
    f.text(345,139,'채널 수',22,PURPLE);f.text(808,139,'경로 / 전송 비율',22,PURPLE)

    f=Fig('R2_control',565,'라운드 경계의 의사결정','경로 평가 뒤에 폭의 비용을 비교하고, 변경 속도와 복귀 조건으로 제어를 안정화한다.')
    fs[f.stem]=f
    boxes=[(30,235,'1. 관측','계산 · 전송량 · 용량'),(385,235,'2. 경로 평가','최대 시간 + 평균 시간'),(740,235,'3. 채널 수 선택','시간 이득과 축소 페널티'),(1095,235,'4. 적용','다음 라운드')]
    for x,y,title,sub in boxes:
        f.box(x,y,275 if x<1095 else 275,118,PALE,LINE,r=7)
        f.text(x+138,y+21,title,29,INK,True,'middle');f.text(x+138,y+74,sub,21,MUTED,False,'middle')
    for x in [308,663,1018]:f.arrow(x,294,x+66,294,TEAL)
    f.box(740,54,275,99,WHITE,PURPLE,True,r=6)
    f.text(878,73,'망 용량이 변했는가?',24,PURPLE,True,'middle');f.text(878,115,'이번에는 채널 수 유지',21,PURPLE,False,'middle')
    f.path([(523,231),(523,105),(733,105)],PURPLE,True)
    f.path([(1021,105),(1233,105),(1233,229)],PURPLE,True)
    f.text(878,189,'용량이 안정되면',22,MUTED,False,'middle')
    f.path([(1233,359),(1233,496),(168,496),(168,359)],BLUE,True)
    f.text(700,465,'완료된 라운드의 계산·전송 시간을 수집',25,BLUE,False,'middle')
    f.text(520,385,'경로 이동 수 제한',22,MUTED,False,'middle')
    f.text(878,385,'한 라운드에 한 단계',22,MUTED,False,'middle')
    f.text(878,421,'복귀는 두 번 확인',22,MUTED,False,'middle')

    f=Fig('R3_testbed',560,'KOREN 실험 배치','HPC 안의 논리 기기들이 KOREN의 두 VM을 경유하여 학습 서버와 텐서를 교환한다.')
    fs[f.stem]=f
    f.domain(40,230,1320,294,'HPC',INK)
    for row in range(4):
        for c in range(8):f.box(82+c*25,313+row*25,17,17,PURPLE,None)
    f.text(185,439,'CPU 프로세스 32개',27,PURPLE,False,'middle')
    f.server(1111,311,134,125);f.text(1178,458,'V100 · 학습 서버',27,BLUE,False,'middle')
    f.text(700,18,'KOREN',32,TEAL,True,'middle')
    for x,labels in [(385,('E1','E2')),(825,('E3','E4'))]:
        f.domain(x,78,322,124,'VM',TEAL)
        for j,label in enumerate(labels):
            f.box(x+23+j*152,137,124,46,WHITE,TEAL,r=4);f.text(x+85+j*152,146,label,23,TEAL,False,'middle')
    f.path([(305,365),(354,365),(354,215),(545,215),(545,204)],TEAL)
    f.path([(354,270),(985,270),(985,204)],TEAL)
    f.path([(610,204),(610,302),(1060,302),(1060,366),(1104,366)],TEAL)
    f.path([(1050,204),(1050,302)],TEAL,arrow=False)
    f.text(708,351,'논리 중계 4개 · 공유 용량 반영',28,MUTED,False,'middle')
    f.text(708,413,'활성값 전송 / 기울기 반환',27,TEAL,False,'middle')
    f=Fig('R7_channels',610,'CNN을 선택한 이유: 채널 수 조절','계층 분할은 계산 위치, 채널 선택은 모델 크기, 조각 나누기는 전송 방식을 결정한다.')
    fs[f.stem]=f
    f.text(30,10,'① 계층 분할: 어디에서 계산하는가',29,INK,True)
    for x,label,color in [(70,'기기: 앞부분',PURPLE),(905,'서버: 뒷부분',BLUE)]:
        f.box(x,65,425,92,PALE,LINE,r=7)
        f.text(x+212,93,label,31,color,True,'middle')
    f.arrow(507,111,889,111,TEAL)
    f.label(700,67,'활성값 →',26,TEAL)
    f.text(700,137,'고정 분할 지점',23,MUTED,False,'middle')
    f.line(30,193,1370,193)
    f.text(30,213,'② 채널 선택: 얼마나 큰 모델을 쓰는가',29,INK,True)
    for x,n,label,size in [(85,8,'w = 1.0 · 128채널','4 MiB'),(535,6,'w = 0.75 · 96채널','3 MiB'),(985,4,'w = 0.5 · 64채널','2 MiB')]:
        for j in range(8): f.box(x+j*33,278,25,76,PURPLE if j<n else '#E5E9ED',None)
        f.text(x+127,369,label,26,INK,False,'middle')
        f.text(x+127,411,size,28,PURPLE,True,'middle')
    f.line(30,463,1370,463)
    f.text(30,482,'③ 조각 나누기: 어떻게 전달하는가',29,INK,True)
    f.box(77,536,244,42,TEAL,None)
    f.arrow(340,556,505,556,TEAL)
    for j in range(4):f.box(530+j*65,536,54,42,TEAL,None)
    f.text(850,539,'같은 텐서를 나누어 전송',28,INK)

    f=Fig('R8_application',660,'활용 예시: 여러 현장의 영상 분류 모델 갱신','현장 장비가 모델 앞부분을 학습하고, 허용된 중계 서버를 거쳐 중앙 GPU 서버와 함께 모델을 갱신하는 적용 예시.')
    fs[f.stem]=f
    f.text(210,16,'여러 현장',31,INK,True,'middle')
    f.text(735,16,'사용 가능한 중계 서버',31,INK,True,'middle')
    f.text(1200,16,'중앙 학습 서버',31,INK,True,'middle')
    for y,label,sub in [(80,'현장 A','계산 지연'),(255,'현장 B','전송 혼잡')]:
        f.box(40,y,340,138,PALE,LINE,r=8)
        f.device(64,y+37,62,49)
        f.text(237,y+18,label,28,INK,True,'middle')
        f.text(237,y+67,sub,27,PURPLE if y==80 else TEAL,False,'middle')
    for y,label in [(80,'중계 1'),(255,'중계 2')]:
        f.box(624,y+24,220,83,WHITE,TEAL,r=6)
        f.text(734,y+47,label,29,TEAL,True,'middle')
    f.path([(387,146),(616,146)],TEAL)
    f.path([(387,319),(491,319),(491,159),(616,159)],LINE,True)
    f.path([(491,319),(616,319)],TEAL)
    f.text(491,369,'혼잡 시 경로 변경',24,TEAL)
    f.path([(850,146),(998,146),(998,232),(1088,232)],TEAL)
    f.path([(850,319),(998,319),(998,232)],TEAL,arrow=False)
    f.server(1100,139,180,152)
    f.text(1190,327,'모델 뒷부분 학습',26,BLUE,False,'middle')
    f.text(1190,367,'라운드별 집계',26,BLUE,False,'middle')
    f.box(355,453,690,95,PALE,PURPLE,r=7)
    f.text(700,471,'AwareNet',31,PURPLE,True,'middle')
    f.text(700,510,'계산 시간 + 전송 시간 → 채널 수 + 경로',24,INK,False,'middle')
    f.path([(349,500),(208,500),(208,403)],PURPLE,True)
    f.path([(1052,500),(1360,500),(1360,413)],BLUE,True)
    f.text(43,570,'기기별 채널 수 조절',26,PURPLE)
    f.text(1040,570,'공동 모델 갱신',26,BLUE)
    f.text(700,624,'원본 이미지: 현장 보관   |   실선: 활성값 전송 (기울기는 역방향)',23,MUTED,False,'middle')
    return fs


def main():
    out=OUT/'figures';out.mkdir(parents=True,exist_ok=True)
    qa=ROOT/'tmp/pdfs/revised_figures';qa.mkdir(parents=True,exist_ok=True)
    poppler=Path('C:/Users/DISLAB/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe')
    fs=native_figures();items=[]
    for stem,f in fs.items():
        p=out/(stem+'.svg');renderSVG.drawToFile(f.d,str(p));s=p.read_text(encoding='utf8').replace('font-family: Diagram Malgun Bold;','font-family: Malgun Gothic, sans-serif; font-weight: 700;').replace('font-family: Diagram Malgun;','font-family: Malgun Gothic, sans-serif;').replace('<title>...</title>','<title>'+f.title+'</title>');p.write_text(s,encoding='utf8')
        renderPDF.drawToFile(f.d,str(qa/(stem+'.pdf')))
        subprocess.run([str(poppler),'-scale-to-x','2400','-scale-to-y','-1','-singlefile','-png',str(qa/(stem+'.pdf')),str(out/stem)],check=True,capture_output=True)
        items.append(dict(stem=stem,title=f.title,caption=f.subtitle))
    libs=ROOT/'tmp/report-plot-libs'
    if libs.exists():sys.path.insert(0,str(libs))
    os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.font_manager import FontProperties
    font=FontProperties(fname='C:/Windows/Fonts/malgun.ttf')
    plt.rcParams.update({'font.family':font.get_name(),'font.size':13,'axes.spines.top':False,'axes.spines.right':False,
        'axes.edgecolor':'#AEB9C2','axes.labelcolor':INK,'xtick.color':MUTED,'ytick.color':MUTED,'text.color':INK,'svg.fonttype':'path','axes.unicode_minus':False})
    m=json.loads((ROOT/'configs/measurements/report_metrics_revised.json').read_text(encoding='utf8'))
    def save(fig,stem,title,caption):
        fig.savefig(out/(stem+'.png'),dpi=220,facecolor='white');fig.savefig(out/(stem+'.svg'),facecolor='white');plt.close(fig)
        items.append(dict(stem=stem,title=title,caption=caption))
    fig,ax=plt.subplots(figsize=(12,4.4),layout='constrained');y=np.arange(4)
    for offset,arm,label,color in [(-.17,'uniform','기준선: 전체 채널 · 단일 연결','#AEBBC5'),(.17,'widthpath','AwareNet: 폭 · 경로 제어',TEAL)]:
        vals=[r[arm]['mean_round_s'] for r in m['scenarios']];ax.barh(y+offset,vals,height=.29,color=color,label=label)
        for yy,v in zip(y+offset,vals):ax.text(v+1.1,yy,f'{v:.2f}',va='center',fontsize=12)
    for i,r in enumerate(m['scenarios']):ax.text(131,i,f'{r["time_reduction_pct"]:.1f}% 단축',ha='right',va='center',fontsize=14,color=TEAL,fontweight='bold')
    ax.set_yticks(y,[r['label'] for r in m['scenarios']]);ax.invert_yaxis();ax.set_xlim(0,133);ax.set_xticks([0,30,60,90,120]);ax.set_xlabel('평균 라운드 시간 (초)');ax.legend(loc='lower left',bbox_to_anchor=(0,1.01),ncol=2,frameon=False,fontsize=11);ax.grid(axis='x',alpha=.18);ax.set_axisbelow(True)
    save(fig,'R4_time','조건별 평균 라운드 시간','32프로세스·3시드. 각 24라운드의 초기 4라운드를 제외한 시드 평균을 집계했다.')
    fig,(ax,bx)=plt.subplots(1,2,figsize=(12,4.4),layout='constrained',gridspec_kw={'width_ratios':[1.15,1]})
    for arm,label,color in [('uniform','기준선','#8A9AA7'),('widthpath','AwareNet',TEAL)]:
        rr=m['traces']['traffic_'+arm];ax.plot([r['round'] for r in rr],[r['time_s'] for r in rr],marker='o',markersize=3,label=label,color=color)
    ax.axvspan(8,19.9,color='#E4EBEF',alpha=.6);ax.set_title('(a) 트래픽 몰림 · 3시드 평균',fontsize=14,loc='left');ax.set_xlabel('로그 round');ax.set_ylabel('라운드 시간 (초)');ax.set_xticks([0,4,8,12,16,20,23]);ax.legend(frameon=False,fontsize=10);ax.grid(alpha=.15)
    a=np.ones((5,24));a[:4,:]=.75
    from matplotlib.colors import ListedColormap,BoundaryNorm
    bx.imshow(a,aspect='auto',cmap=ListedColormap([PURPLE,'#E4E9ED']),norm=BoundaryNorm([.5,.9,1.1],2),interpolation='nearest',extent=[-.5,23.5,4.5,-.5])
    bx.set_yticks(range(5),['c0','c8','c16','c24','나머지 28개']);bx.set_xticks([0,8,16,23]);bx.set_xlabel('로그 round');bx.set_title('(b) 연산 지연 · 기기별 폭',fontsize=14,loc='left')
    from matplotlib.patches import Patch
    bx.legend(handles=[Patch(color=PURPLE,label='폭 0.75'),Patch(color='#E4E9ED',label='폭 1.0')],loc='upper center',bbox_to_anchor=(.5,-.17),ncol=2,frameon=False,fontsize=11)
    for seed in (1,2,3):
        rr=[json.loads(s) for s in (ROOT/f'out/wp_scen32_slow_s{seed}_bothmp_widthpath.jsonl').read_text(encoding='utf8').splitlines() if s.strip()]
        for r in rr:
            if 'round' in r:assert {k:v for k,v in r['plan'].items() if v<1}=={f'c{i}':.75 for i in (0,8,16,24)}
    save(fig,'R5_actions','서로 다른 병목에서 관측한 제어','몰림 구간과 시간 응답, 연산 지연 기기 네 개의 폭 선택을 원로그에서 확인했다.')
    fig,ax=plt.subplots(figsize=(12,4.6),layout='constrained')
    colors=['#758795',PURPLE,BLUE,TEAL];offsets=[(-83,-38),(-18,18),(-27,-47),(18,10)]
    for r,c,offset in zip(m['accuracy_200'],colors,offsets):
        ax.scatter([s['mean_round_s'] for s in r['seeds']],[s['tail50_accuracy_pct'] for s in r['seeds']],s=42,facecolors='none',edgecolors=c,linewidths=1.3)
        ax.scatter(r['mean_round_s'],r['tail50_accuracy_pct'],s=85,c=c,zorder=4)
        label='기준선' if r['lam'] is None else f'λ={r["lam"]}'
        ax.annotate(f'{label}\n{r["mean_round_s"]:.2f}초 · {r["tail50_accuracy_pct"]:.1f}%',(r['mean_round_s'],r['tail50_accuracy_pct']),xytext=offset,textcoords='offset points',fontsize=12,color=c)
    ax.set_xlim(5.5,22.5);ax.set_ylim(49,70);ax.set_xlabel('평균 라운드 시간 (초)');ax.set_ylabel('마지막 50라운드 평균 정확도 (%)');ax.grid(alpha=.18)
    ax.text(.015,.95,'● 두 시드 평균   ○ 개별 시드',transform=ax.transAxes,fontsize=11,color=MUTED)
    save(fig,'R6_accuracy','폭 축소 페널티에 따른 시간·정확도','8프로세스·200라운드·2시드. 평가 대상은 CIFAR-10 시험 집합의 앞 2,000개다.')
    order=['R1_architecture','R7_channels','R2_control','R3_testbed','R4_time','R5_actions','R6_accuracy','R8_application']
    items.sort(key=lambda r:order.index(r['stem']))
    ledger=dict(figures=items,metrics='configs/measurements/report_metrics_revised.json',metrics_sha256=hashlib.sha256((ROOT/'configs/measurements/report_metrics_revised.json').read_bytes()).hexdigest(),new_experiments=False)
    (out/'revised_sources.json').write_text(json.dumps(ledger,ensure_ascii=False,indent=2),encoding='utf8')
    cards=''.join(f'<article><h2>{html.escape(r["title"])}</h2><img src="figures/{r["stem"]}.svg"><p>{html.escape(r["caption"])}</p><a href="figures/{r["stem"]}.svg">SVG</a> · <a href="figures/{r["stem"]}.png">PNG</a></article>' for r in items)
    (OUT/'figures.html').write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><title>AwareNet 연구 그림</title><style>body{max-width:1100px;margin:35px auto;font-family:Malgun Gothic,sans-serif;color:#20303c}article{padding:25px;border-bottom:1px solid #ddd}img{width:100%}p{line-height:1.7}</style><h1>AwareNet 연구 그림</h1><p>구조 → CNN 채널 → 제어 절차 → 실험 배치 → 결과 → 활용 예시.</p>'+cards+'</html>',encoding='utf8')
    with zipfile.ZipFile(OUT/'AwareNet_구조도_조건그림.zip','w',zipfile.ZIP_DEFLATED) as z:
        for r in items:
            for ext in ('.png','.svg'):z.write(out/(r['stem']+ext),'figures/'+r['stem']+ext)
        z.write(out/'revised_sources.json','figures/revised_sources.json');z.write(OUT/'figures.html','figures.html')
    print(json.dumps({'figures':len(items),'new_experiments':False}))


if __name__=='__main__':main()
