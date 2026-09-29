"""Render a 1080p narrated demonstration exclusively from measured model outputs."""
import argparse
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import subprocess
import wave

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/healthcare_enterprise_demo"
W, H, FPS = 1920, 1080, 24
BG = "#F3F6FA"
INK = "#14243D"
MUTED = "#63738A"
LINE = "#DAE2EC"
TEAL = "#078E85"
BLUE = "#306BDD"
PURPLE = "#8462C9"
RED = "#CC5260"
COLORS = [BLUE, TEAL, PURPLE]

def js(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))

CFG = js("cnn_config.json")
MET = js("cnn_verified_metrics.json")
CNN = js("cnn_history.json")
LH = js("enterprise_history.json")
LR = js("enterprise_inference.json")["models"]
DOCS = js("enterprise_corpus.json")
STORY = js("storyboard.json")
CW = np.load(OUT / "cnn_weights.npz")
LW = np.load(OUT / "enterprise_aggregation.npz")

@lru_cache(None)
def font(size, bold=False):
    return ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf" if bold else "C:/Windows/Fonts/malgun.ttf", size)

def txt(d, x, y, s, size=28, color=INK, bold=False):
    d.text((int(x), int(y)), str(s), font=font(size, bold), fill=color)

@lru_cache(2000)
def lines(s, width, size, bold=False):
    result = []
    for para in str(s).split("\n"):
        line = ""
        for char in para:
            if font(size, bold).getlength(line + char) > width:
                result.append(line); line = char
            else:
                line += char
        result.append(line)
    return result

def wrap(d, x, y, s, width, size=28, color=INK, bold=False, gap=1.45):
    for i, line in enumerate(lines(str(s), width, size, bold)):
        txt(d, x, y + i * size * gap, line, size, color, bold)
    return len(lines(str(s), width, size, bold)) * size * gap

def card(d, box, fill="white", outline=LINE, radius=22):
    d.rounded_rectangle(tuple(map(int, box)), radius=radius, fill=fill, outline=outline, width=2)

def pill(d, x, y, text, color=TEAL, bg="#E8F5F3", size=22):
    width = font(size, True).getlength(text) + 28
    card(d, (x, y, x + width, y + 40), fill=bg, outline=bg, radius=12)
    txt(d, x + 14, y + 4, text, size, color, True)
    return width

def arrow(d, x1, y1, x2, y2, color=MUTED, width=4):
    d.line((x1,y1,x2,y2), fill=color, width=width)
    a = math.atan2(y2-y1,x2-x1)
    d.polygon([(x2,y2),(x2-15*math.cos(a-.45),y2-15*math.sin(a-.45)),
               (x2-15*math.cos(a+.45),y2-15*math.sin(a+.45))], fill=color)

def image_fit(im, image, box, mode="contain"):
    x,y,x2,y2 = map(int, box)
    source = image.convert("RGB")
    factor = min((x2-x)/source.width,(y2-y)/source.height)
    dest = source.resize((int(source.width*factor),int(source.height*factor)),Image.Resampling.BICUBIC)
    im.paste(dest,(x+(x2-x-dest.width)//2,y+(y2-y-dest.height)//2))

@lru_cache(150)
def source_image(name):
    return Image.open(OUT / "images" / name).convert("RGB")

def xray(im,d,idx,box,label=True):
    card(d,box,fill="#101C29",outline="#263748",radius=12)
    image_fit(im,source_image(f"test_{idx}.png"),(box[0]+12,box[1]+12,box[2]-12,box[3]-12))
    if label:
        txt(d,box[0]+18,box[1]+14,f"TEST {idx:04d}",18,"#B7C7D9")

def chart(d, box, series, ymax, labels=None, percent=False, log=False, start_round=0):
    x,y,x2,y2=box
    for j in range(5):
        yy=y2-(y2-y)*j/4
        d.line((x,yy,x2,yy),fill=LINE,width=1)
        val=ymax*j/4
        txt(d,x-65,yy-12,f"{val:.0f}" if percent else f"{val:.1f}",18,MUTED)
    for ci, (values,color) in enumerate(series):
        if not values: continue
        points=[]
        # Fixed x domain; traces expand as measured rounds are revealed.
        max_round=20 if len(labels or [])==21 else 16
        for r,v in enumerate(values):
            yy=y2-(y2-y)*max(0,min(1,v/ymax))
            points.append((x+(x2-x)*(r+start_round)/max_round,yy))
        if len(points)>1: d.line(points,fill=color,width=4)
        px,py=points[-1]; d.ellipse((px-5,py-5,px+5,py+5),fill=color)
    txt(d,x,y2+10,"0",18,MUTED)
    txt(d,x2-15,y2+10,"20" if len(labels or [])==21 else "16",18,MUTED)
    txt(d,x2-95,y2+43,"라운드",19,MUTED)

def heatmap(array, width, height, limit=None):
    ar=np.array(array,dtype=float)
    lim=limit or max(np.abs(ar).max(),1e-8)
    val=np.clip(ar/lim,-1,1)
    base=np.ones((*val.shape,3))*np.array([244,247,251])
    pos=np.array([20,142,152]); neg=np.array([53,87,156])
    rgb=np.where((val>=0)[...,None],base*(1-val[...,None])+pos*val[...,None],
                 base*(1+val[...,None])+neg*(-val[...,None]))
    return Image.fromarray(rgb.clip(0,255).astype("uint8")).resize((width,height),Image.Resampling.NEAREST)

HEAT = {k:heatmap(CW[k],220,165,limit=.23) for k in CW.files}
LLIMIT=float(np.abs(LW["clients"][:, :64, :]).max())
LHEAT=[heatmap(a[:64,:],210,150,LLIMIT) for a in LW["clients"]]
LHEAT_GLOBAL=heatmap(LW["global_weights"][:64,:],260,175,LLIMIT)

def hospital_icon(d,x,y,color):
    d.rounded_rectangle((x,y,x+50,y+50),radius=12,fill=color)
    d.rectangle((x+21,y+11,x+29,y+39),fill="white")
    d.rectangle((x+11,y+21,x+39,y+29),fill="white")

def canvas(scene,t,duration,absolute,total,index):
    im=Image.new("RGB",(W,H),BG); d=ImageDraw.Draw(im)
    d.rectangle((0,0,W,82),fill=INK)
    txt(d,70,20,"AwareNet",32,"white",True)
    txt(d,282,26,"APPLICATION DEMO  /  CNN + LoRA",22,"#BDCBE0")
    txt(d,1260,26,"로컬 GPU 실행 · 실제 학습·추론 기록",23,"#E0EAF7")
    txt(d,76,109,f"{index+1:02d}",28,TEAL,True)
    txt(d,140,102,scene["title"],42,INK,True)
    if scene["id"] in ["hospital_data","cnn_train","cnn_aggregate","xray_normal","xray_pneumonia","hospital_results"]:
        detail="PneumoniaMNIST+ · 공개 X-ray · 가상 병원 3곳 · 단일 GPU에서 실행한 연구용 분류 시연"
    elif scene["id"] in ["enterprise_data","lora_train","lora_aggregate","qa_ops","qa_support","qa_security","enterprise_results"]:
        detail="가상 회사 ‘네오링크’ · 부서별 지침 9개 · Qwen2.5-0.5B + LoRA rank 16 · 실제 모델 생성"
    else:
        detail="개별 클라이언트의 학습 → 연합 집계 → 같은 입력에 대한 결과 확인"
    txt(d,77,170,detail,23,MUTED)
    # Subtitle segments match narration time and are never more than two lines.
    subs=scene["subtitles"]
    seg=min(len(subs)-1,int(max(0,t-.7)/max(.001,scene["audio_seconds"])*len(subs)))
    card(d,(70,907,1850,1028),fill=INK,outline=INK,radius=18)
    sub=subs[seg]
    textlines=lines(sub,1680,29)
    ypos=921+(72-len(textlines)*40)/2
    for j,line in enumerate(textlines):
        txt(d,110,ypos+40*j,line,29,"white")
    txt(d,78,1040,"2026.09.29  |  실험 로그·체크포인트 기반 재생",18,MUTED)
    txt(d,1685,1040,f"{int(absolute)//60:02d}:{int(absolute)%60:02d} / {int(total)//60:02d}:{int(total)%60:02d}",18,MUTED)
    d.rectangle((0,H-5,int(W*absolute/total),H),fill=TEAL)
    return im,d

def scene_intro(im,d,t,p):
    card(d,(76,233,931,851));card(d,(957,233,1844,851))
    pill(d,110,263,"01 · 병원 영상 분류",BLUE,"#EAF0FC")
    xray(im,d,MET["cases"][0]["index"],(112,333,493,750))
    txt(d,523,352,"세 병원의 영상",34,INK,True)
    txt(d,523,410,"클라이언트별 학습",26,MUTED)
    arrow(d,641,462,641,529,TEAL)
    txt(d,523,561,"공통 CNN 모델",34,TEAL,True)
    txt(d,523,625,"정상 / 폐렴 분류",27,INK)
    txt(d,112,791,"공개 연구 영상으로 실제 학습·추론",25,MUTED)
    pill(d,993,263,"02 · 기업 업무 도우미",PURPLE,"#F0ECF9")
    for i,(department,caption) in enumerate([("운영","장애 대응"),("고객지원","응답 기한"),("보안","공유 승인")]):
        card(d,(995,340+112*i,1799,430+112*i),fill="#F7F9FC")
        txt(d,1020,359+112*i,department,29,COLORS[i],True)
        txt(d,1210,362+112*i,caption,28,INK)
    txt(d,994,714,"LoRA 연합학습 → 업무 질문에 답변",32,PURPLE,True)
    txt(d,995,791,"시연용 가상 규정 · 모델이 직접 생성한 답변",25,MUTED)

def scene_hospital_data(im,d,t,p):
    for ci in range(3):
        x=76+600*ci
        card(d,(x,233,x+570,831))
        hospital_icon(d,x+26,258,COLORS[ci])
        txt(d,x+95,260,f"병원 {chr(65+ci)}",35,INK,True)
        pill(d,x+363,264,f"클라이언트 {ci+1}",COLORS[ci],"#F0F4FA",19)
        for k in range(4):
            xx=x+30+(k%2)*252;yy=340+(k//2)*167
            card(d,(xx,yy,xx+228,yy+151),fill="#132331",outline="#132331",radius=10)
            image_fit(im,source_image(f"client_{ci}_{k}.png"),(xx+6,yy+6,xx+222,yy+145))
        txt(d,x+30,696,f"학습 영상 {CFG['train_per_client'][ci]:,}장",29,INK,True)
        txt(d,x+30,751,f"채널 비율 {CFG['widths'][ci]*100:.0f}%   ·   서버와 앞·뒷부분 분할",23,MUTED)
    txt(d,80,860,"원래 학습/시험 분할 유지 · 학습 4,708장 / 시험 624장 · 각 클라이언트는 서로 다른 학습 영상 사용",22,MUTED)

def scene_cnn_train(im,d,t,p):
    r=max(1,min(20,int(p*20)+1)); row=CNN[r]
    pill(d,76,231,f"ROUND {r:02d} / 20",BLUE,"#EAF0FC",24)
    txt(d,1420,240,"기록된 손실·정확도",23,MUTED)
    for ci in range(3):
        y=298+176*ci
        card(d,(76,y,644,y+153))
        txt(d,100,y+16,f"병원 {chr(65+ci)}",27,COLORS[ci],True)
        txt(d,416,y+20,f"손실 {row['clients'][ci]['loss']:.3f}",24,INK,True)
        # The current rolled output channel set at the cut (128 full channels).
        width=int(128*CFG['widths'][ci]); off=r%128
        for k in range(32):
            active=((4*k-off)%128)<width
            d.rounded_rectangle((103+k*15.5,y+69,114+k*15.5,y+95),radius=3,fill=COLORS[ci] if active else LINE)
        txt(d,102,y+111,f"절단면 채널 {width}/128  ·  라운드마다 선택 위치 이동",20,MUTED)
    card(d,(674,298,1250,818));card(d,(1273,298,1844,818))
    txt(d,708,324,"클라이언트 학습 손실",27,INK,True)
    chart(d,(767,419,1210,704),[([CNN[j]['clients'][c]['loss'] for j in range(1,r+1)],COLORS[c]) for c in range(3)],2.0,labels=list(range(21)),start_round=1)
    txt(d,708,775,"교차 엔트로피 · 각 라운드 12배치 평균",20,MUTED)
    txt(d,1305,324,"집계 모델 시험 정확도",27,INK,True)
    txt(d,1310,368,f"{row['accuracy']*100:.1f}%",53,TEAL,True)
    chart(d,(1370,473,1807,704),[([x['accuracy']*100 for x in CNN[:r+1]],TEAL)],100,labels=list(range(21)),percent=True)
    txt(d,1308,775,"고정 시험 영상 624장",20,MUTED)
    txt(d,80,860,"실제 ResNet-18 · cut 2 · 배치 16 · 채널 선택/집계는 저장소 코드 사용 · 네트워크 전달은 로컬 프로세스에서 재현",21,MUTED)

def scene_cnn_aggregate(im,d,t,p):
    for ci in range(3):
        x=76+405*ci
        card(d,(x,260,x+363,645))
        txt(d,x+28,289,f"병원 {chr(65+ci)}의 갱신",29,COLORS[ci],True)
        im.paste(HEAT[f"client_{ci}"],(int(x+70),372))
        txt(d,x+28,570,f"채널 {int(64*CFG['widths'][ci])} / 64",25,MUTED)
    arrow(d,1251,462,1362,462,TEAL,5)
    card(d,(1390,260,1844,645),fill="#EAF6F3",outline="#A4D4CB")
    txt(d,1418,289,"전역 모델",34,TEAL,True)
    im.paste(HEAT['global_weights'].resize((285,190)),(1470,356))
    txt(d,1420,570,"학습된 채널끼리 결합",26,INK)
    card(d,(76,697,1844,824))
    txt(d,112,718,"채널 위치 정렬",30,INK,True)
    arrow(d,403,748,502,748)
    txt(d,546,718,"표본 수를 반영해 평균",30,INK,True)
    arrow(d,967,748,1060,748)
    txt(d,1105,718,"갱신된 모델을 다음 라운드에 배포",30,TEAL,True)
    txt(d,80,860,"색상: 실제 stem 합성곱 가중치 일부 · 양수/음수 표현 · 작은 모델이 학습하지 않은 채널은 그대로 유지",21,MUTED)

def scene_xray(im,d,t,p,case_index):
    case=MET["cases"][case_index]; truth=["정상","폐렴"][case['label']]
    card(d,(76,235,678,855))
    xray(im,d,case['index'],(103,264,649,757))
    txt(d,109,786,f"데이터 라벨: {truth}  ·  TEST {case['index']:04d}",28,INK,True)
    for col,(name,probs) in enumerate([("학습 전",case['initial_probs']),("연합학습 후",case['final_probs'])]):
        x=711+582*col
        card(d,(x,235,x+550,855),fill="white" if col==0 else "#ECF7F4",outline=LINE if col==0 else "#A7D5C9")
        pill(d,x+30,263,name,BLUE if col==0 else TEAL,"#EAF0FC" if col==0 else "#D6EDE7",23)
        for k,label in enumerate(["정상","폐렴"]):
            yy=376+k*134
            txt(d,x+31,yy,label,28,INK,True)
            txt(d,x+370,yy,f"{probs[k]*100:.1f}%",28,COLORS[col],True)
            d.rounded_rectangle((x+31,yy+55,x+510,yy+85),radius=8,fill=LINE)
            q=probs[k]*(min(1,t/1.8) if col else 1)
            d.rounded_rectangle((x+31,yy+55,x+31+max(2,479*q),yy+85),radius=8,fill=BLUE if col==0 else TEAL)
        predicted=int(np.argmax(probs)); ok=predicted==case['label']
        txt(d,x+31,697,"모델 예측",22,MUTED)
        txt(d,x+31,738,["정상","폐렴"][predicted],40,INK,True)
        pill(d,x+294,750,"라벨 일치" if ok else "라벨 불일치",TEAL if ok else RED,"#DAEEE6" if ok else "#F9E9EC",22)
    txt(d,80,872,"모델 출력 확률 표시 · 원영상 64×64를 화면에 확대 · 공개 연구용 데이터이며 임상 진단용 시연이 아님",20,MUTED)

def scene_hospital_results(im,d,t,p):
    card(d,(76,235,1087,847));card(d,(1114,235,1844,847))
    txt(d,111,262,"고정 시험 영상 624장",31,INK,True)
    for i,(label,value,color) in enumerate([("학습 전",MET['initial_accuracy'],BLUE),("연합학습 후",MET['accuracy'],TEAL)]):
        yy=346+i*119
        txt(d,113,yy,label,28,INK,True)
        d.rounded_rectangle((315,yy+7,927,yy+57),radius=10,fill="#ECF0F6")
        d.rounded_rectangle((315,yy+7,315+612*value,yy+57),radius=10,fill=color)
        txt(d,941,yy+7,f"{value*100:.1f}%",29,color,True)
    txt(d,115,626,f"일치 {MET['correct']}장",43,TEAL,True)
    txt(d,491,626,f"오분류 {MET['errors']}장",43,RED,True)
    txt(d,115,721,f"폐렴 재현율 {MET['sensitivity']*100:.1f}%   ·   정상 특이도 {MET['specificity']*100:.1f}%",28,INK)
    txt(d,115,781,"하나의 공개 데이터셋·한 시드에서 실행한 활용 시연",22,MUTED)
    txt(d,1146,262,"오분류도 그대로 제시",31,INK,True)
    for ci,case in enumerate(MET['cases'][2:4]):
        x=1148+333*ci
        xray(im,d,case['index'],(x,336,x+292,653))
        txt(d,x,687,"라벨  "+["정상","폐렴"][case['label']],25,INK,True)
        txt(d,x,737,"예측  "+["정상","폐렴"][case['predicted']],25,RED,True)
    txt(d,80,872,"선택 규칙: 고정 시험 순서에서 조건에 맞는 첫 사례 · 전체 624개 예측과 체크포인트 재적재 검증 결과 제공",20,MUTED)

def scene_enterprise_data(im,d,t,p):
    for ci,(department,subtitle) in enumerate([("운영","장애 대응·배포"),("고객지원","응답 기한·공지"),("보안","권한·로그 공유")]):
        x=76+600*ci
        card(d,(x,237,x+570,833))
        pill(d,x+27,262,f"부서 {ci+1} / 클라이언트 {ci+1}",COLORS[ci],"#F0F3FA")
        txt(d,x+28,328,department,39,INK,True)
        txt(d,x+28,385,subtitle,25,MUTED)
        for j,doc in enumerate(DOCS['documents'][ci*3:ci*3+3]):
            yy=450+j*113
            txt(d,x+29,yy,doc['id'],19,COLORS[ci],True)
            wrap(d,x+29,yy+32,doc['text'],510,25,INK)
    txt(d,80,862,"부서별 규정 3개 × 질문 표현 6개 = 학습 18문항씩 · 평가 질문은 별도로 작성 · 가상 회사·가상 정책임을 명시",21,MUTED)

def scene_lora_train(im,d,t,p):
    r=max(1,min(16,int(p*16)+1)); rec=LH['federated'][r-1]
    pill(d,76,231,f"ROUND {r:02d} / 16",PURPLE,"#F0ECF9",24)
    card(d,(76,300,916,836));card(d,(946,300,1844,836))
    for ci,dep in enumerate(["운영","고객지원","보안"]):
        yy=333+ci*151
        pill(d,105,yy,dep,COLORS[ci],"#F0F4FA",23)
        txt(d,295,yy+4,f"손실 {rec['clients'][ci]['loss']:.4f}",27,INK,True)
        txt(d,296,yy+57,"기본 가중치 고정  +  LoRA 어댑터 학습",22,MUTED)
        for k in range(16):
            d.rounded_rectangle((107+k*9,yy+68,113+k*9,yy+111),radius=2,fill=COLORS[ci])
    txt(d,979,327,"실제 부서별 학습 손실",29,INK,True)
    chart(d,(1045,418,1795,690),[([x['clients'][ci]['loss'] for x in LH['federated'][:r]],COLORS[ci]) for ci in range(3)],1.5,start_round=1)
    txt(d,982,771,"앞단 어댑터 평균  ·  서버 뒷단은 순차 공동 갱신",25,PURPLE,True)
    txt(d,80,863,"고정 LoRA rank 16 · cut 2 · 각 부서 라운드당 12스텝 · 배치 4 · CNN 채널 제어와 LoRA rank는 서로 다른 변수",20,MUTED)

def scene_qa(im,d,t,p,qindex):
    single=LR[1]['questions'][qindex]; fed=LR[2]['questions'][qindex]
    card(d,(76,232,1844,373),fill="#EAF0F9",outline="#D6E0EF")
    txt(d,104,252,"직원의 질문",22,BLUE,True)
    wrap(d,104,294,fed['q'],1690,31,INK,True)
    for ci,row in enumerate([single,fed]):
        x=76+900*ci
        card(d,(x,410,x+868,838),fill="white" if ci==0 else "#ECF7F4",outline=LINE if ci==0 else "#A7D5C9")
        pill(d,x+30,437,"운영 부서만 학습" if ci==0 else "세 부서 연합학습",BLUE if ci==0 else TEAL,"#EAF0FC" if ci==0 else "#D9EFE8",23)
        # Type-in is presentation pacing; text comes directly from generation JSON.
        response=row['answer']
        if font(39,True).getlength(response)>790:
            breaks=[k for k,ch in enumerate(response) if ch==' ']
            midpoint=min(breaks,key=lambda k:abs(font(39,True).getlength(response[:k])-font(39,True).getlength(response[k+1:])))
            response=response[:midpoint]+'\n'+response[midpoint+1:]
        shown=response[:int(len(response)*min(1,max(0,(t-1.0)/2.4)))]
        wrap(d,x+33,523,shown,790,39,INK,True)
        ok=row['correct']
        pill(d,x+31,747,"규정과 일치" if ok else "규정과 불일치",TEAL if ok else RED,"#D9EFE8" if ok else "#F9E9EC",23)
        txt(d,x+323,754,f"원본 생성 시간 {row['seconds']:.2f}초",21,MUTED)
    txt(d,80,865,f"질문 문형은 학습에서 제외 · 연결된 원문 규정 {fed['fact']} · 화면 답변은 생성 결과를 그대로 재생",21,MUTED)

def scene_lora_aggregate(im,d,t,p):
    for ci,dep in enumerate(["운영", "고객지원", "보안"]):
        x=76+400*ci
        card(d,(x,262,x+350,662))
        pill(d,x+25,288,dep,COLORS[ci],"#F0F4FA",25)
        im.paste(LHEAT[ci],(x+68,381))
        txt(d,x+28,577,"학습한 LoRA 행렬",24,INK,True)
    arrow(d,1240,460,1350,460,PURPLE,5)
    card(d,(1385,262,1844,662),fill="#F1EEF9",outline="#CFC3E9")
    txt(d,1417,292,"공통 어댑터",35,PURPLE,True)
    im.paste(LHEAT_GLOBAL,(1480,366))
    txt(d,1418,577,"A·B 행렬별 평균",26,INK,True)
    # One pass of update tiles represents the actual aggregation operation; no blinking.
    move=min(1,max(0,(p-.15)/.5))
    if 0<move<1:
        for ci in range(3):
            x0=230+ci*400; y0=675
            xx=int(x0+(1600-x0)*move); yy=int(y0+(675-y0)*move)
            d.rounded_rectangle((xx,yy,xx+44,yy+28),radius=5,fill=COLORS[ci])
    card(d,(76,715,1844,833))
    txt(d,108,739,"서버 뒷단 어댑터",28,INK,True)
    txt(d,447,741,"운영 → 고객지원 → 보안 순서로 공동 갱신",29,PURPLE,True)
    txt(d,80,863,"실제 q_proj.B 일부 표시 · 앞단 집계 결과와 세 클라이언트 평균의 최대 차이 0 · 전체 어댑터 체크포인트 보관",20,MUTED)

def scene_enterprise_results(im,d,t,p):
    card(d,(76,235,1120,839));card(d,(1150,235,1844,839))
    txt(d,110,264,"같은 18문항으로 비교",32,INK,True)
    for i,(row,label,color) in enumerate(zip(LR,["기본 모델","운영 부서만","세 부서 연합"],[MUTED,BLUE,TEAL])):
        yy=355+i*125
        txt(d,111,yy,label,29,INK,True)
        for q in range(18):
            xx=348+(q%9)*66; py=yy+(q//9)*39
            d.rounded_rectangle((xx,py,xx+52,py+27),radius=5,fill=color if row['questions'][q]['correct'] else LINE)
        txt(d,979,yy+10,f"{row['correct']}/18",35,color,True)
    txt(d,111,766,"정답 수: 생성 문장에 규정의 전체 답변이 포함되는지 확인",23,MUTED)
    txt(d,1184,265,"평가 범위",32,INK,True)
    wrap(d,1184,347,"가상 내부 규정 9개\n학습 질문 54개\n새로운 질문 표현 18개",600,30,INK,gap=1.75)
    card(d,(1182,577,1807,782),fill="#F0F4FA")
    wrap(d,1209,600,"부서별로 나뉜 지침을\n공통 업무 모델에 반영하는\n작은 규모의 실제 학습 시연",563,29,PURPLE,True,gap=1.75)
    txt(d,80,866,"같은 사실에 대한 문형 일반화 평가 · 실제 기업 데이터·일반 업무 성능 평가가 아님 · 응답 원문 54개 모두 제공",20,MUTED)

def scene_closing(im,d,t,p):
    for i,(title,sub,value,caption,color) in enumerate([
        ("병원 이미지 분류","CNN / 서로 다른 채널 수",f"{MET['accuracy']*100:.1f}%","공개 시험 영상 624장",BLUE),
        ("기업 업무 문답","LoRA / 부서별 지침 학습",f"{LR[2]['correct']}/18","가상 규정 9개 · 새 질문 표현",PURPLE)]):
        x=76+i*900
        card(d,(x,237,x+868,614))
        txt(d,x+32,266,title,37,INK,True)
        txt(d,x+32,324,sub,25,MUTED)
        txt(d,x+32,390,value,72,color,True)
        txt(d,x+32,520,caption,27,INK)
    card(d,(76,649,1844,833),fill=INK,outline=INK)
    txt(d,110,673,"AwareNet의 역할",30,"white",True)
    wrap(d,449,675,"학습 자원과 통신 조건을 함께 고려해 클라이언트의 공동학습을 지원",1310,32,"white",True)
    txt(d,112,764,"이번 영상: 로컬 활용 시연    |    기존 KOREN: 폭·경로 스케줄링 실측 자료 별도 제공",24,"#C0D1E6")
    txt(d,79,861,"영상: MedMNIST+ / Yang et al. · CC BY 4.0 · 확대 표시  |  모델: Qwen2.5-0.5B  |  실험·생성 로그 및 재현 코드 제공",20,MUTED)

RENDERERS={
    "intro":scene_intro,"hospital_data":scene_hospital_data,"cnn_train":scene_cnn_train,
    "cnn_aggregate":scene_cnn_aggregate,"xray_normal":lambda im,d,t,p:scene_xray(im,d,t,p,0),
    "xray_pneumonia":lambda im,d,t,p:scene_xray(im,d,t,p,1),"hospital_results":scene_hospital_results,
    "enterprise_data":scene_enterprise_data,"lora_train":scene_lora_train,"lora_aggregate":scene_lora_aggregate,
    "qa_ops":lambda im,d,t,p:scene_qa(im,d,t,p,0),"qa_support":lambda im,d,t,p:scene_qa(im,d,t,p,6),
    "qa_security":lambda im,d,t,p:scene_qa(im,d,t,p,12),"enterprise_results":scene_enterprise_results,
    "closing":scene_closing}

def timings():
    cur=0; parts=[]
    for scene in STORY:
        with wave.open(str(OUT / "narration" / f"{scene['id']}.wav"),'rb') as f:
            scene['audio_seconds']=f.getnframes()/f.getframerate()
            spec=(f.getnchannels(),f.getsampwidth(),f.getframerate())
            audio=f.readframes(f.getnframes())
        scene['subtitles']=[s.strip()+"." for s in scene['narration'].split(".") if s.strip()]
        scene['duration']=math.ceil(max(scene['minimum_seconds'],scene['audio_seconds']+1.6)*FPS)/FPS
        scene['start']=cur;cur+=scene['duration']
        parts.append((scene,spec,audio))
    return cur,parts

def srt_time(t):
    return f"{int(t)//3600:02d}:{int(t)//60%60:02d}:{int(t)%60:02d},{int(t%1*1000):03d}"

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--preview',action='store_true');a=ap.parse_args()
    total,parts=timings()
    (OUT/'frames').mkdir(exist_ok=True)
    for i,scene in enumerate(STORY):
        t=scene['duration']*.62
        im,d=canvas(scene,t,scene['duration'],scene['start']+t,total,i)
        RENDERERS[scene['id']](im,d,t,t/scene['duration'])
        im.save(OUT/'frames'/f"{i+1:02d}_{scene['id']}.png")
    # All-scene contact sheet for visual review.
    contact=Image.new('RGB',(1440,math.ceil(len(STORY)/3)*300),'white')
    for i,scene in enumerate(STORY):
        frame=Image.open(OUT/'frames'/f"{i+1:02d}_{scene['id']}.png").resize((480,270))
        xx=(i%3)*480;yy=(i//3)*300;contact.paste(frame,(xx,yy))
        ImageDraw.Draw(contact).text((xx+8,yy+274),f"{i+1:02d} {scene['id']}",font=font(16),fill=INK)
    contact.save(OUT/'contact_sheet.jpg',quality=95)
    (OUT/'timeline.json').write_text(json.dumps(STORY,ensure_ascii=False,indent=2),encoding='utf-8')
    print('DURATION',total,'seconds',flush=True)
    if a.preview:return
    spec=parts[0][1];nch,sw,sr=spec
    with wave.open(str(OUT/'narration.wav'),'wb') as out:
        out.setnchannels(nch);out.setsampwidth(sw);out.setframerate(sr)
        for scene,this_spec,data in parts:
            assert this_spec==spec
            lead=int(.7*sr)*nch*sw
            count=round(scene['duration']*sr)*nch*sw
            out.writeframes(b'\x00'*lead+data+b'\x00'*max(0,count-lead-len(data)))
    subs=[];counter=1
    for scene in STORY:
        for j,text in enumerate(scene['subtitles']):
            start=scene['start']+.7+scene['audio_seconds']*j/len(scene['subtitles'])
            end=scene['start']+.7+scene['audio_seconds']*(j+1)/len(scene['subtitles'])
            subs.append(f"{counter}\n{srt_time(start)} --> {srt_time(end)}\n{text}\n")
            counter+=1
    (OUT/'AwareNet_병원_기업_시연.srt').write_text('\n'.join(subs),encoding='utf-8')
    ff=imageio_ffmpeg.get_ffmpeg_exe()
    silent=OUT/'demo_silent.mp4'
    cmd=[ff,'-y','-f','rawvideo','-vcodec','rawvideo','-s',f'{W}x{H}','-pix_fmt','rgb24','-r',str(FPS),'-i','-',
         '-an','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',str(silent)]
    log=open(OUT/'render_ffmpeg.log','w',encoding='utf-8')
    proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=log)
    try:
        for i,scene in enumerate(STORY):
            print('RENDER',i+1,scene['id'],flush=True)
            for f in range(round(scene['duration']*FPS)):
                t=f/FPS
                im,d=canvas(scene,t,scene['duration'],scene['start']+t,total,i)
                RENDERERS[scene['id']](im,d,t/scene['duration']*scene['duration'],t/scene['duration'])
                proc.stdin.write(im.tobytes())
    finally:
        proc.stdin.close()
    if proc.wait()!=0: raise RuntimeError('ffmpeg render failed')
    output=OUT/'AwareNet_병원_기업_시연.mp4'
    subprocess.run([ff,'-y','-i',str(silent),'-i',str(OUT/'narration.wav'),'-c:v','copy','-c:a','aac','-b:a','160k',
                    '-movflags','+faststart',str(output)],check=True,stdout=subprocess.DEVNULL,stderr=log)
    log.close()
    manifest={'video':output.name,'seconds':total,'resolution':[W,H],'fps':FPS,
        'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'sources':{}}
    for name in ['cnn_config.json','cnn_verified_metrics.json','cnn_history.json','enterprise_history.json',
                 'enterprise_inference.json','enterprise_corpus.json','storyboard.json','cnn_weights.npz','enterprise_aggregation.npz']:
        p=OUT/name
        manifest['sources'][p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
    (OUT/'video_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print('FINISHED',output,output.stat().st_size,flush=True)

if __name__=='__main__':main()
