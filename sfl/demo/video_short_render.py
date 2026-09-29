"""112-second silent experiment viewer. All traces and outputs come from saved runs."""
import argparse
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import subprocess
import imageio_ffmpeg
import numpy as np
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/demo_short'
SRC=ROOT/'output/healthcare_enterprise_demo'
DATA=json.loads((OUT/'data.json').read_text(encoding='utf-8'))
PRED=np.load(SRC/'cnn_predictions.npz')
W,H,FPS,DURATION=1920,1080,24,112
BG='#FAFAF9';INK='#303332';MUTED='#6B706F';LINE='#DDDFDC';BLUE='#486777';GRAY='#9B9F9D'
CLIENT=['#486777','#768879','#927D69']

@lru_cache(None)
def font(size,bold=False,mono=False):
    name='consola.ttf' if mono else ('malgunbd.ttf' if bold else 'malgun.ttf')
    return ImageFont.truetype('C:/Windows/Fonts/'+name,size)

def text(d,x,y,s,size=25,color=INK,bold=False,mono=False):
    d.text((int(x),int(y)),str(s),font=font(size,bold,mono),fill=color)

def wrapped(d,x,y,s,width,size=25,color=INK,bold=False,spacing=1.5):
    lines=[]
    for paragraph in s.split('\n'):
        line=''
        for word in paragraph.split(' '):
            add=word if not line else line+' '+word
            if font(size,bold).getlength(add)>width and line:
                lines.append(line);line=word
            else:line=add
        lines.append(line)
    for i,line in enumerate(lines):text(d,x,y+i*size*spacing,line,size,color,bold)

def box(d,b,title=None):
    d.rectangle(b,fill='white',outline=LINE,width=1)
    if title:
        text(d,b[0]+17,b[1]+9,title,22,INK)
        d.line((b[0],b[1]+48,b[2],b[1]+48),fill=LINE,width=1)

@lru_cache(None)
def image(name):return Image.open(SRC/'images'/name).convert('RGB')

def photo(im,d,name,b,label=None):
    d.rectangle(b,fill='#13191F')
    pic=image(name);s=min((b[2]-b[0]-16)/pic.width,(b[3]-b[1]-16)/pic.height)
    pic=pic.resize((int(pic.width*s),int(pic.height*s)),Image.Resampling.BICUBIC)
    im.paste(pic,(int((b[0]+b[2]-pic.width)/2),int((b[1]+b[3]-pic.height)/2)))
    if label:text(d,b[0]+14,b[1]+9,label,17,'#CFD8E1',mono=True)

def plot(d,b,series,xmin,xmax,ymin,ymax,yticks,xlabel='round',log=False):
    x,y,x2,y2=b
    def fy(v):
        if log:v=math.log10(max(1e-6,v))
        return y2-(y2-y)*min(1,max(0,(v-ymin)/(ymax-ymin)))
    for v,label in yticks:
        py=y2-(y2-y)*(v-ymin)/(ymax-ymin)
        d.line((x,py,x2,py),fill='#E8EBEF',width=1)
        text(d,x-60,py-12,label,20,MUTED,mono=True)
    for vals,color in series:
        pts=[(x+(i-xmin)/(xmax-xmin)*(x2-x),fy(v)) for i,v in vals if i>=xmin]
        if len(pts)>1:d.line(pts,fill=color,width=3)
        if pts:
            px,py=pts[-1];d.ellipse((px-4,py-4,px+4,py+4),fill=color)
    for i in [xmin,(xmin+xmax)//2,xmax]:text(d,x+(i-xmin)/(xmax-xmin)*(x2-x)-10,y2+12,str(i),20,MUTED,mono=True)
    text(d,x2-92,y2+39,xlabel,20,MUTED)

def console(d,b,title,lines):
    d.rectangle(b,fill='#242827')
    d.rectangle((b[0],b[1],b[2],b[1]+39),fill='#303533')
    text(d,b[0]+16,b[1]+7,title,20,'#CFD4D0',mono=True)
    for i,(s,c) in enumerate(lines):
        text(d,b[0]+18,b[1]+53+i*29,s,23,c,mono=True)

def section(t):
    if t<24:return 'cnn_train',0
    if t<34:return 'cnn_infer',0
    if t<54:return 'lora_train',1
    if t<66:return 'lora_infer',1
    if t<98:return 'network',2
    return 'summary',3

def frame_base(t):
    key,active=section(t)
    im=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(im)
    d.rectangle((0,0,W,54),fill='#F0F1EE')
    text(d,25,11,'AwareNet',24,INK)
    text(d,249,13,'실험 기록',21,MUTED)
    text(d,1640,13,'저장된 실행 재생',20,MUTED)
    d.rectangle((0,55,W,112),fill='white')
    tabs=['01  영상 분류','02  업무 문답','03  KOREN 비교','04  결과']
    for i,tab in enumerate(tabs):
        x=249+i*388
        text(d,x,71,tab,23,INK if active==i else MUTED)
        if active==i:d.rectangle((x,109,x+178,111),fill=BLUE)
    d.line((0,112,W,112),fill=LINE,width=1)
    d.rectangle((0,113,218,1013),fill='#F4F5F2')
    text(d,22,144,'실험 설정',20,INK)
    if active==0:
        groups=[('모델',['ResNet-18','분할 지점: 2']),('클라이언트',['가상 병원 A / B / C','학습 영상 4,708장','시험 영상 624장']),('실행 환경',['RTX 3080','로컬 실행']),('데이터',['PneumoniaMNIST+','공개 연구용 X-ray'])]
    elif active==1:
        groups=[('모델',['Qwen2.5-0.5B','LoRA rank: 16']),('클라이언트',['운영 / 고객지원 / 보안','가상 업무 규정 9개','평가 질문 18개']),('실행 환경',['RTX 3080','로컬 실행']),('집계',['앞단 어댑터 평균','서버 뒷단 공동 갱신'])]
    else:
        groups=[('측정 환경',['KOREN','논리 클라이언트 32']),('학습 설정',['CIFAR-10','ResNet-18']),('비교 조건',['기준: 연결 1개','AwareNet: 연결 2개']),('분석 구간',['초기 4라운드 제외','라운드 완료 시간'])]
    for gi,(label,values) in enumerate(groups):
        yy=220+gi*178
        text(d,22,yy,label,18,MUTED)
        for j,value in enumerate(values):text(d,22,yy+37+j*34,value,18,INK)
    d.line((0,1013,W,1013),fill=LINE,width=1)
    caption={'cnn_train':'로컬 실행 · 20라운드 학습 기록',
             'cnn_infer':'공개 연구용 영상 · 가상 병원 분할 · 임상 검증 제외',
             'lora_train':'로컬 실행 · 16라운드 학습 기록',
             'lora_infer':'학습한 규정을 다른 문장으로 질문한 결과',
             'network':'기존 KOREN 실측 · 앞의 로컬 학습과 별도 실행',
             'summary':'전체 시스템 조건 비교 · 연결 수 차이 포함'}[key]
    text(d,248,1029,caption,20,MUTED)
    text(d,1710,1027,f'{int(t)//60:02d}:{int(t)%60:02d} / 01:52',21,MUTED,mono=True)
    d.rectangle((0,H-2,W*t/DURATION,H),fill=GRAY)
    return im,d,key

def cnn_training(im,d,t):
    hist=DATA['cnn'];wall=hist[-1]['elapsed']*min(1,t/21.5)
    rows=[r for r in hist[1:] if r['elapsed']<=wall];row=rows[-1] if rows else hist[1]
    r=row['round'];acc=row['accuracy']
    text(d,249,133,f'CNN 학습   {r:02d} / 20 라운드',28,INK)
    text(d,1120,138,f'ResNet-18 / cut=2 / batch=16 / elapsed={row["elapsed"]:.1f}s',23,MUTED,mono=True)
    box(d,(249,191,810,658),'클라이언트별 학습')
    for ci,p in enumerate([.5,.75,1.]):
        yy=254+ci*124
        photo(im,d,f'client_{ci}_0.png',(269,yy,390,yy+107))
        text(d,413,yy+4,f'병원 {chr(65+ci)} · client {ci}',24,INK)
        text(d,413,yy+42,f'channel={p:.2f}  loss={row["clients"][ci]["loss"]:.4f}',22,CLIENT[ci],mono=True)
        text(d,415,yy+79,f'채널 사용률 {p:.0%}',19,MUTED)
        d.rectangle((582,yy+89,764,yy+94),fill=LINE)
        d.rectangle((582,yy+89,582+182*p,yy+94),fill=CLIENT[ci])
    box(d,(840,191,1870,658),'집계 후 시험 정확도')
    text(d,867,253,f'{acc*100:.1f}%',42,INK)
    text(d,1120,272,'시험 영상 624장',24,MUTED)
    plot(d,(946,363,1818,564),[([(v['round'],v['accuracy']*100) for v in hist[:r+1]],BLUE)],0,20,0,100,[(0,'0'),(50,'50'),(100,'100')])
    logs=[]
    for rr in hist[max(1,r-1):r+1]:
        for c in rr['clients']:
            logs.append((f'round={rr["round"]:02d}  client=c{c["client"]}  width={c["width"]:.2f}  loss={c["loss"]:.6f}  act={str(c["activation_shape"]):<19}', '#C6CDC8'))
        logs.append((f'round={rr["round"]:02d}  global_accuracy={rr["accuracy"]:.6f}  elapsed={rr["elapsed"]:.3f}s', '#A9C1C9'))
    console(d,(249,685,1870,985),'cnn_history.json',logs[-8:])

def cnn_infer(im,d,t):
    case=DATA['cnn_metrics']['cases'][0 if t<29 else 1]
    text(d,249,133,'같은 영상의 학습 전·후 예측',28,INK)
    text(d,1260,138,'checkpoint: cnn_global_final.pt',23,MUTED,mono=True)
    box(d,(249,190,871,828),'시험 영상')
    photo(im,d,f'test_{case["index"]}.png',(269,252,850,786),f'test_{case["index"]:04d}  64x64')
    text(d,286,789,'데이터 라벨: '+['정상','폐렴'][case['label']],22,INK,True)
    box(d,(901,190,1870,828),'모델 예측')
    for ci,(name,pr) in enumerate([('학습 전',case['initial_probs']),('연합학습 후',case['final_probs'])]):
        yy=267+ci*234
        text(d,928,yy,name,28,INK,True)
        for k,label in enumerate(['정상','폐렴']):
            y=yy+57+k*58;text(d,930,y,label,24,MUTED)
            d.rectangle((1040,y+5,1630,y+31),fill='#E7EBF0')
            d.rectangle((1040,y+5,1040+590*pr[k],y+31),fill=GRAY if ci==0 else BLUE)
            text(d,1661,y,f'{pr[k]*100:.1f}%',26,INK,mono=True)
        text(d,927,yy+176,'예측: '+['정상','폐렴'][int(np.argmax(pr))],27,BLUE if ci else INK,True)
    box(d,(249,850,1870,985))
    text(d,277,875,'전체 시험 세트',24,MUTED)
    text(d,522,872,'543 / 624 일치',32,INK)
    text(d,965,871,'87.0%',36,INK)
    text(d,1237,881,'오분류 81장 · 저장 모델 재적재 검증',24,MUTED)
    text(d,278,939,'MedMNIST+ / Yang et al. · CC BY 4.0 · 원영상 확대 표시',20,MUTED)

def lora_train(im,d,t):
    hist=DATA['lora']['federated'];wall=hist[-1]['elapsed']*min(1,(t-34)/18.5)
    rows=[r for r in hist if r['elapsed']<=wall];row=rows[-1] if rows else hist[0];r=row['round']
    text(d,249,133,f'LoRA 학습   {r:02d} / 16 라운드',28,INK)
    text(d,1130,138,f'Qwen2.5-0.5B / rank=16 / elapsed={row["elapsed"]:.1f}s',23,MUTED,mono=True)
    box(d,(249,191,817,658),'부서별 학습')
    for ci,(dep,rule) in enumerate([('운영','P1 장애 → 10분 내 당직 SRE 보고'),('고객지원','골드 고객 → 30분 내 첫 응답'),('보안','외부 로그 → 마스킹·보안팀 승인')]):
        yy=261+ci*130
        text(d,272,yy,dep,25,CLIENT[ci])
        text(d,449,yy+3,f'loss={row["clients"][ci]["loss"]:.6f}',23,INK,mono=True)
        wrapped(d,272,yy+52,rule,516,24,MUTED)
    box(d,(847,191,1870,658),'학습 손실 · 로그 축')
    plot(d,(951,291,1819,553),[([(rr['round'],rr['clients'][ci]['loss']) for rr in hist[:r]],CLIENT[ci]) for ci in range(3)],
         1,16,-6,1,[(1,'1e1'),(-1,'1e-1'),(-3,'1e-3'),(-6,'1e-6')],log=True)
    logs=[]
    for rr in hist[max(0,r-7):r]:
        ls=', '.join(f'{c["loss"]:.6f}' for c in rr['clients'])
        logs.append((f'federated  round={rr["round"]:02d}  losses=[{ls}]  elapsed={rr["elapsed"]:.2f}s','#C6CDC8'))
    logs.append((f'front_adapter_mean  round={r:02d}  bytes={row["adapter_bytes"]}  clients=3','#A9C1C9'))
    console(d,(249,685,1870,985),'enterprise_history.json',logs[-8:])

def lora_infer(im,d,t):
    ix=6 if t<60 else 12;local=DATA['lora_inference']['models'][1]['questions'][ix];fed=DATA['lora_inference']['models'][2]['questions'][ix]
    text(d,249,133,'업무 지침에 대한 답변 비교',28,INK)
    text(d,1200,138,'enterprise_federated_front/back.pt',23,MUTED,mono=True)
    box(d,(249,191,1870,374),'평가 질문')
    wrapped(d,277,264,fed['q'],1540,29,INK)
    for i,row in enumerate([local,fed]):
        x=249+i*826
        box(d,(x,404,x+795,808),'운영 부서만 학습' if i==0 else '운영 + 고객지원 + 보안 연합학습')
        wrapped(d,x+27,492,row['answer'],735,31,INK)
        text(d,x+28,694,'규정과 일치' if row['correct'] else '규정과 불일치',24,MUTED)
        text(d,x+29,752,f'generation={row["seconds"]:.2f}s  policy={row["fact"]}',22,MUTED,mono=True)
    box(d,(249,838,1870,985))
    text(d,276,859,'18개 질문 전체 비교',24,MUTED)
    text(d,611,858,'기본 모델 0/18',28,INK)
    text(d,1013,858,'단독 6/18',28,INK)
    text(d,1385,858,'연합 18/18',28,INK)
    text(d,276,934,'학습한 규정 9개를 다른 문장으로 질문 · 가상 회사의 업무 지침으로 실제 학습·추론',23,MUTED)

def network(im,d,t):
    rr=min(23,4+int((t-66)/1.38));runs=DATA['network_runs'];a=runs['uniform'][rr];b=runs['widthpath'][rr]
    text(d,249,133,f'KOREN · 트래픽 몰림   {rr:02d} 라운드',28,INK)
    text(d,1290,138,'32 clients / seed=1 / CIFAR-10',23,MUTED,mono=True)
    box(d,(249,191,1294,658),'라운드 완료 시간 (초)')
    text(d,278,252,'기준 방식',23,MUTED);d.line((435,268,510,268),fill=GRAY,width=4)
    text(d,562,252,'AwareNet',23,BLUE,True);d.line((716,268,791,268),fill=BLUE,width=4)
    plot(d,(352,329,1250,552),[([(r['round'],r['makespan']) for r in runs[p][:rr+1]],c) for p,c in [('uniform',GRAY),('widthpath',BLUE)]],
         4,23,0,200,[(0,'0'),(100,'100'),(200,'200')])
    text(d,278,610,'실제 기록의 라운드 소요 시간 · 두 실행을 라운드 번호로 정렬',21,MUTED)
    box(d,(1324,191,1870,658),'경로·채널 비율 변경 기록')
    changes=[]
    for row in runs['widthpath'][max(0,rr-3):rr+1]:
        for c in row['changes']:changes.append((row['round'],c))
    text(d,1344,252,'round  client  relay       width',20,MUTED,mono=True)
    for i,(r,c) in enumerate(changes[-9:]):
        text(d,1344,293+i*34,f'{r:02d}     {c["client"]:<5}  {c["path_before"]}>{c["path_after"]:<3}   {c["width_before"]:.2f}>{c["width_after"]:.2f}',19,INK,mono=True)
    if not changes:text(d,1344,313,'이 구간에서는 배정 유지',23,MUTED)
    u=sum(r['makespan'] for r in runs['uniform'][4:rr+1])/(rr-3)
    v=sum(r['makespan'] for r in runs['widthpath'][4:rr+1])/(rr-3)
    box(d,(249,683,1870,835))
    text(d,274,703,f'현재까지 평균 (r4–r{rr})',23,MUTED)
    text(d,711,713,f'{u:.1f}s',38,INK);text(d,945,720,'→',28,MUTED)
    text(d,1040,713,f'{v:.1f}s',38,INK)
    text(d,1438,723,f'{100*(1-v/u):.1f}% 단축',29,INK)
    text(d,278,780,'기준: 전폭·고정 배정·연결 1개      AwareNet: 폭·경로 조정·연결 2개',23,MUTED)
    logs=[(f'uniform    round={rr:02d}  makespan={a["makespan"]:.4f}s  width=1.0000','#C6CDC8'),
          (f'widthpath  round={rr:02d}  makespan={b["makespan"]:.4f}s  mean_width={np.mean(list(b["plan"].values())):.4f}  changed={len(b["changes"])}','#A9C1C9')]
    console(d,(249,859,1870,985),'wp_scen32_traffic_s1_bothmp_*.jsonl',logs)

def summary(im,d,t):
    text(d,249,133,'기준 방식 대비 라운드 완료 시간',28,INK)
    text(d,1318,138,'KOREN / 24 rounds x 3 seeds',23,MUTED,mono=True)
    box(d,(249,191,1870,795),'원로그 24개에서 재집계 · 각 실행의 초기 4라운드 제외')
    text(d,277,262,'조건',24,MUTED);text(d,669,262,'기준 방식',24,MUTED)
    text(d,1100,262,'AwareNet',24,BLUE,True);text(d,1510,262,'시간 단축',24,MUTED)
    for i,s in enumerate(DATA['network_summary']):
        yy=332+108*i
        text(d,280,yy,s['label'],27,INK)
        d.rectangle((649,yy+8,649+3.2*s['uniform'],yy+33),fill=GRAY)
        text(d,649,yy+43,f'{s["uniform"]:.1f}s',24,INK,mono=True)
        d.rectangle((1099,yy+8,1099+3.2*s['widthpath'],yy+33),fill=BLUE)
        text(d,1099,yy+43,f'{s["widthpath"]:.1f}s',24,BLUE,mono=True)
        text(d,1510,yy+10,f'{s["reduction_pct"]:.1f}%',34,INK)
    box(d,(249,823,1870,985))
    text(d,278,842,'비교 조건',23,INK,True)
    text(d,470,842,'전폭·고정 배정·연결 1개  vs  폭·경로 조정·연결 2개',25,INK)
    text(d,278,890,'지표',23,INK,True)
    text(d,470,890,'라운드 소요 시간 · 목표 정확도 도달 시간과 구분',24,MUTED)
    text(d,278,938,'마지막 라운드 정확도 차이',21,MUTED)
    text(d,665,938,'정상 +4.63pp / 트래픽 -0.50pp / 연산 -1.20pp / 용량 -2.85pp',21,MUTED)

def make_frame(t):
    im,d,key=frame_base(t)
    {'cnn_train':cnn_training,'cnn_infer':cnn_infer,'lora_train':lora_train,'lora_infer':lora_infer,'network':network,'summary':summary}[key](im,d,t)
    return im

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--preview',action='store_true');a=ap.parse_args()
    (OUT/'frames').mkdir(exist_ok=True)
    samples=[3,15,26,31,42,51,57,63,76,87,96,105]
    contact=Image.new('RGB',(1440,4*285),'white')
    for i,t in enumerate(samples):
        frame=make_frame(t);frame.save(OUT/'frames'/f'{t:03d}.png')
        contact.paste(frame.resize((480,270)),((i%3)*480,(i//3)*285))
    contact.save(OUT/'contact_sheet.jpg',quality=95)
    if a.preview:return
    target=OUT/'AwareNet_시연_1분52초_무음.mp4'
    cmd=[imageio_ffmpeg.get_ffmpeg_exe(),'-y','-f','rawvideo','-vcodec','rawvideo','-s',f'{W}x{H}',
         '-pix_fmt','rgb24','-r',str(FPS),'-i','-','-an','-c:v','libx264','-preset','fast','-crf','19',
         '-pix_fmt','yuv420p','-movflags','+faststart',str(target)]
    with open(OUT/'ffmpeg.log','w',encoding='utf-8') as log:
        proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=log)
        try:
            for i in range(DURATION*FPS):
                if i%(FPS*10)==0:print('RENDER',i//FPS,'/',DURATION,flush=True)
                proc.stdin.write(make_frame(i/FPS).tobytes())
        finally:proc.stdin.close()
        assert proc.wait()==0
    result={'name':target.name,'seconds':DURATION,'width':W,'height':H,'fps':FPS,'audio':False,
            'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
    (OUT/'video_manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
