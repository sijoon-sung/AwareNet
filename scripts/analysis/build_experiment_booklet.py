from pathlib import Path
import json
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'output/pdf/AwareNet_실험조건_및_검증기록_20261001.pdf'
OUT.parent.mkdir(parents=True, exist_ok=True)
pdfmetrics.registerFont(TTFont('MG', 'C:/Windows/Fonts/malgun.ttf'))
pdfmetrics.registerFont(TTFont('MGB', 'C:/Windows/Fonts/malgunbd.ttf'))
BLUE = colors.HexColor('#315c70')
styles = {
 'title': ParagraphStyle('title', fontName='MGB', fontSize=23, leading=32, textColor=BLUE, spaceAfter=16),
 'h': ParagraphStyle('h', fontName='MGB', fontSize=13, leading=20, textColor=BLUE, spaceBefore=14, spaceAfter=8),
 'body': ParagraphStyle('body', fontName='MG', fontSize=10, leading=16, wordWrap='CJK', spaceAfter=9),
 'cell': ParagraphStyle('cell', fontName='MG', fontSize=9, leading=13.5, wordWrap='CJK'),
 'note': ParagraphStyle('note', fontName='MG', fontSize=8.5, leading=13, wordWrap='CJK', textColor=colors.HexColor('#586770'), spaceAfter=8),
}
story=[]
def p(s,kind='body'): return Paragraph(s,styles[kind])
def text(s,kind='body'): story.append(p(s,kind))
def title(n,s):
 if story: story.append(PageBreak())
 text('EXPERIMENT RECORD  /  '+n,'note');text(s,'title')
def table(headers,rows,widths):
 data=[[p(str(v),'cell') for v in r] for r in [headers]+rows]
 t=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
 t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e9f0f3')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('LINEBELOW',(0,0),(-1,0),.8,BLUE),('LINEBELOW',(0,1),(-1,-1),.35,colors.HexColor('#d7dfe3'))]))
 story.extend([t,Spacer(1,9)])
def kv(rows):table(['항목','실행 조건'],rows,[100,407])
BASE='https://sijoon-sung.github.io/AwareNet/site/'
def link(label,path):return '<link href="'+BASE+path+'" color="#315c70">'+label+' ↗</link>'
M=json.loads((ROOT/'configs/measurements/report_metrics_revised.json').read_text(encoding='utf-8'))
A=json.loads((ROOT/'site/assets/ablation-20261001.json').read_text(encoding='utf-8'))

title('01','AwareNet 실험 조건 및 검증 기록')
text('실험별 설정 · 시드와 반복 · 비교 결과 · 원자료\u2003|\u20032026.10.01','note')
text('기존 실행 기록을 실험 단위로 정리했다. 학습 시간, 모델 축소 정도, 텐서 전송량을 중심으로 비교하고, 결과를 다시 확인할 수 있도록 원로그와 설정 파일을 연결했다.')
table(['ID / 실험','규모와 실행 길이','시드 또는 반복'],[
 ['A  KOREN 전송 부하','동시 전송 8~96개 / 3라운드','독립 시드 반복 미확인'],
 ['B  KOREN 병목 대응','32 논리 클라이언트 / 24라운드','1·2·3 / 24실행'],
 ['C  장기 학습·λ 비교','8클라이언트 / 200라운드','1·2 / 8실행'],
 ['D  기능 켜기·끄기','8클라이언트 / 24라운드','1·2·3 / 15실행'],
 ['E  순환 채널 검증','4클라이언트 / 300라운드','s1·s2·s3 표기 / 6실행'],
 ['F  Fashion-MNIST','3클라이언트 / 100라운드','41·42·43 / 9실행'],
 ['G  동일 연결 수 진단','4조건 × 6정책','조건별 3회 / 72회'],
 ['H  LoRA 분할 공동 학습','3클라이언트 / 16라운드','독립 시드 반복 미확인'],
 ['I  LoRA 어댑터 전송','3클라이언트 / 6라운드','정책별 1실행'],
 ['J  Jetson 연산·전력','1대 / 모드별 30스텝','3모드 / 90측정 스텝'],
 ['K  영상 분류 시연','3클라이언트 / 20라운드','41 / 1실행'],
 ['L  업무 문답 시연','3클라이언트 / 16라운드','73 / 1실행'],
],[185,179,143])
text('읽는 기준','h')
text('시드는 난수 초기값, 라운드는 학습·집계 주기, 반복은 같은 조건의 재실행 횟수다. 한 실행 안의 여러 라운드나 스텝을 독립 시드로 세지 않았다. ResNet-18은 CNN 모델이며, LoRA는 Qwen 언어모델에 적용한 학습 기법이다.','note')

title('02','KOREN 전송과 병목 대응')
text('A. 동시 전송 수를 늘린 사전 측정','h')
kv([['구성','HPC → KOREN VM → HPC. 실제 텐서 전송의 종단 간 시간을 측정했다.'],['조건','동시 전송 8~96개, 상·하행 각각 약 4.2 MB, 4배치 × 3라운드, TCP 연결 2개. 배치·버스트 전송을 구분했다.'],['관측','배치 전송 중앙값: 8개 약 0.41초 → 32개 약 2.18초. 독립 시드 반복은 확인되지 않았다.']])
text('원로그의 용량 설정 필드를 실제 회선 속도나 제한 적용의 증거로 사용하지 않았다. 측정값은 접속·중계·호스트 처리를 포함한다. '+link('전송 원로그·측정 코드','assets/koren-link-measurements.zip'),'note')
text('B. 32 논리 클라이언트의 병목 대응','h')
kv([['모델·학습','CIFAR-10 / ResNet-18 / 분할 지점 2 / 배치 32 / 클라이언트당 4배치 / 24라운드.'],['실행 규모','HPC의 CPU 클라이언트 프로세스 32개, V100 학습 서버, VM 2대와 논리 중계 4개. 4조건 × 2정책 × 3시드(1·2·3) = 24실행.'],['제어 설정','접속 5/2 Mbps, 초기 중계 56 Mbps 설정. 폭 후보 0.5·0.75·1.0, λ=70초, 이동 상한 3.'],['비교·집계','전폭·고정 배정·연결 1개와 폭·경로·분할 제어·연결 2개를 비교했다. 초기 4라운드를 제외한 평균을 시드별로 구한 뒤 3시드를 평균했다.']])
rows=[]
for x in M['scenarios']:
 u=x['uniform']['mean_round_s'];v=x['widthpath']['mean_round_s']
 rows.append([x['label'],f'{u:.2f}',f'{v:.2f}',f'{100*(u-v)/u:.1f}%'])
table(['조건','기준 (초)','AwareNet (초)','시간 단축'],rows,[177,110,110,110])
text('구성 전체의 비교다. 연결 수가 달라 경로 선택 또는 조각 분할만의 효과로 분리하지 않는다. '+link('시드별 집계·출처','assets/evidence/E8/configs/measurements/report_metrics_revised.json'),'note')

title('03','학습 길이와 제어 기능 비교')
text('C. 200라운드 장기 학습과 λ 비교','h')
text('CIFAR-10·ResNet-18·분할 지점 2·배치 32·4배치, 8클라이언트. 기준 방식과 λ=18·70·280의 4설정을 시드 1·2에서 실행했다(총 8실행). 초기 4라운드를 제외해 시간을 집계했다. λ는 폭 축소에 부여하는 비용의 가중치이며 단위는 초다.')
table(['설정','라운드 시간 (초)','평균 폭','시간 단축'],[['기준 방식','19.11','1.000','-'],['λ=280','15.15','1.000','20.7%'],['λ=70','12.90','0.977','32.5%'],['λ=18','8.01','0.832','58.1%']],[150,132,110,115])
text('32클라이언트를 물리 장비 32대로 구성한 실험과 구분한다. 8클라이언트 축소 실행의 네트워크 배율 0.1은 클라이언트 수와 별도 설정이다. '+link('장기 학습 집계','assets/evidence/E8/configs/measurements/report_metrics_revised.json'),'note')
text('D. AwareNet 기능 켜기·끄기','h')
text('CIFAR-10·ResNet-18, 8클라이언트·24라운드·4배치·분할 지점 2. 중계 125 Mbps × 4, 10초 목표 기반의 기존 제어기를 비교했다. 5설정 × 3시드(1·2·3) = 15실행. 초기 10라운드를 제외한 시간·폭을 평균했다.')
table(['설정','폭 제어','경로','분할','시간 (초)','평균 폭'],[[r['label'],r['width_control'],r['path_control'],r['multipath'],f"{r['time_s']:.2f}",f"{r['mean_width']:.3f}"] for r in A['rows']],[147,66,66,66,81,81])
text('폭+경로와 전체 기능은 비슷한 시간에 각각 0.813과 0.927의 평균 폭을 유지했다. 분할 설정은 연결 수도 바꾼다. 폭만 제어한 실행은 경로가 고정됐는지 원로그로 확인했다. '+link('15개 로그·설정·재집계 코드','assets/ablation-20261001.zip'),'note')
text('E. 순환 채널 구현 검증','h')
text('4클라이언트·300라운드. w25r·w50r 각 3개 시드 표기(s1·s2·s3), 총 6개 로그를 확인했다. 독립적인 채널 선택 검증이며 위 결합 제어 실험에 합산하지 않는다. 실행 인자 곁파일은 확인되지 않아 시드 표기는 파일명 기준으로 기록했다.','note')

title('04','다른 데이터셋과 동일 연결 수')
text('F. Fashion-MNIST 실제 학습','h')
kv([['데이터·모델','공식 학습 60,000개·시험 10,000개 / ResNet-18 / 분할 지점 2 / GroupNorm. 28×28 회색조를 3채널로 복제했다.'],['학습 조건','3클라이언트, 100라운드 × 클라이언트당 8스텝, 배치 32. Adam 학습률 0.0006, 클라이언트·라운드별 옵티마이저 초기화.'],['비교 설정','전폭 [1,1,1], 고정 채널 [0.5,0.75,1], 순환 채널 [0.5,0.75,1]. 시드 41·42·43 × 3설정 = 9실행.'],['공정 비교','시드 내 초기 가중치와 미니배치 인덱스를 맞췄다. 서로 겹치지 않는 계층화 IID 데이터 분할을 사용했다.'],['측정 범위','로컬 GPU 학습과 프로세스 내부 텐서 교환. 축소 구성의 활성값·기울기 바이트 합은 전폭의 75%였다. TCP 전송량 측정과 구분한다.']])
text('20라운드 예비 실행은 같은 시드 41·42·43을 사용했다. 이를 합쳐 6시드로 계산하지 않았다. '+link('학습 설정·결과·코드','assets/awarenet_followup_20261001.zip'),'note')
text('G. 연결 수를 맞춘 TCP 전송 진단','h')
text('모든 정책에 클라이언트당 TCP 연결 2개를 적용했다. 3클라이언트, 전폭 페이로드 4 MiB, λ=2초. 기준·균등·경로·폭·독립·결합의 6정책을 4조건에서 각 3회 반복했다(72회).')
table(['병목 조건','연산 시간 설정 (초)','중계 (Mbps)','접속 (Mbps)'],[['중계 혼잡','0.01 / 0.01 / 0.01','64 / 192','800 / 800'],['연산 지연','1.6 / 0.01 / 0.01','192 / 192','800 / 800'],['접속 제한','0.01 / 0.01 / 0.01','192 / 192','6.4 / 6.4'],['혼합','1.6 / 0.01 / 0.01','64 / 192','800 / 800']],[108,170,114,115])
text('혼합 조건에서 독립 제어는 0.927초·평균 폭 0.667, 결합 제어는 0.934초·평균 폭 0.833이었다. 432건의 페이로드 해시 일치를 확인했다.','body')
text('로컬 TCP와 응용 수준 속도 제한을 사용하고, 연산은 지정 시간 대기로 모사했다. 학습 시드 실험이나 KOREN 실측이 아닌 전송·정책 진단이다. '+link('72회 원기록','assets/awarenet_followup_20261001.zip'),'note')

title('05','LoRA 공동 학습과 전송')
text('H. 분할 공동 학습·연합 집계','h')
kv([['모델·구성','Qwen2.5-0.5B / LoRA 랭크 16 고정 / 분할 지점 2. VM 2대와 HPC에 배치한 3개 논리 클라이언트의 실행 기록.'],['학습 길이','16라운드 × 30 로컬 스텝. 기본 집계와 서버 측 집계를 포함한 변형 실행을 구분했다.'],['검증 내용','분할 순·역전파와 라운드 단위 어댑터 집계, 자체 문답 18개에 대한 공동 학습 결과를 확인했다.'],['반복 정보','독립 학습 시드 반복 수를 확정할 메타데이터가 없다. 16라운드를 16회 반복으로 계산하지 않았다.']])
text(link('LoRA 분할 학습 근거 E4','evidence.html#E4')+' · '+link('원기록 연결·집계','assets/evidence/E8/configs/measurements/final_report_evidence_2026-09-26.json'),'note')
text('I. LoRA 어댑터 업로드 경로 제어','h')
kv([['실행 설정','Qwen2.5-0.5B / 랭크 16 고정 / 3클라이언트 / 6라운드 × 10 로컬 스텝. 경로 용량 설정 40·20 Mbps. 클라이언트당 어댑터 약 35 MB.'],['비교·반복','고정 배정과 경로 제어를 각각 1회 실행했다. 독립 시드 반복은 확인되지 않았다. VM1·VM2에 복사된 동일 로그를 중복 집계하지 않았다.'],['집계 지표','6라운드 전체의 어댑터 업로드 시간 평균. 학습·활성값 교환을 포함한 전체 라운드 시간과 구분한다.']])
table(['고정 배정','경로 제어','업로드 시간 단축'],[['20.74초','16.75초','19.3%']],[169,169,169])
text('적용 범위','h')
text('CNN 실험은 채널 비율과 전송 제어를 비교했고, LoRA 기록은 분할 공동 학습과 어댑터 업로드 제어를 확인했다. 위 LoRA 실행은 랭크를 고정했으므로 동적 랭크·폭 조절의 성능 검증으로 표기하지 않았다.')
text(link('LoRA 원로그와 추가 검증','followup.html')+' · 원파일: out/vm1/l3net_uniform.jsonl, out/vm1/l3net_widthpath.jsonl. 실행 설정: scripts/exp/run_l3net.sh.','note')

title('06','실제 장비 측정과 활용 시연')
text('J. Jetson 연산·전력 프로파일','h')
text('Jetson Orin Nano Super 8 GB 한 대에서 Qwen2.5-0.5B·LoRA 랭크 32·FP32·배치 1·시퀀스 길이 256을 실행했다. 전력 모드별 준비 3스텝을 제외하고 30스텝씩 측정했다. 총 90스텝이며 독립 시드 반복은 확인되지 않았다.')
table(['전력 모드','스텝 시간 중앙값','평균 입력 전력'],[['MAXN SUPER','554.1 ms','11.969 W'],['25 W','608.9 ms','10.985 W'],['15 W','903.7 ms','8.852 W']],[169,169,169])
text('모드 명칭의 전력과 실제 입력 전력(VDD_IN)을 구분했다. 이 기록은 독립 연산·전력 측정이며 연합학습에 참여한 Jetson 실행이 아니다. '+link('Jetson 원자료 E2','evidence.html#E2'),'note')
text('K·L. 실제 학습 로그를 사용한 활용 시연','h')
table(['항목','K. 영상 분류','L. 업무 문답'],[
 ['데이터','PneumoniaMNIST+ 64×64\n학습 4,708개·시험 624개','가상 기업 지침 9개\n학습 문장 54개·문답 18개'],
 ['모델','ResNet-18 / GroupNorm\n분할 지점 2 / 순환 채널','Qwen2.5-0.5B\nLoRA 랭크 16 / 분할 지점 2'],
 ['참여·조절','논리 클라이언트 3개\n채널 비율 0.5·0.75·1','논리 클라이언트 3개\n랭크 16 고정'],
 ['학습 길이','20라운드 × 12스텝\n배치 16','16라운드 × 12스텝\n배치 4'],
 ['학습률','0.0006 / Adam','0.0003 / 기울기 클립 1'],
 ['시드·실행','시드 41 / 1실행','시드 73 / 1실행'],
 ['검증','분할 학습·집계 후\n전체 시험셋 예측','분할 학습·어댑터 집계 후\n자체 문답 응답'],
],[100,203,204])
text('로컬 학습 시스템에서 실행한 시연이다. 공개 의료 데이터와 가상 기업 문장을 사용했으며 실제 병원·기업 배포나 KOREN 전송 실험에 합산하지 않았다. '+link('설정·학습 로그·예측 파일','assets/demo/evidence.zip'),'note')

title('07','원자료와 재현 안내')
table(['실험','원자료 위치 / 공개 링크'],[
 ['A',link('KOREN 전송 원자료 ZIP','assets/koren-link-measurements.zip')+'<br/>out/line_scale.jsonl, out/line_scale_detail/'],
 ['B·C',link('시드별 집계 JSON','assets/evidence/E8/configs/measurements/report_metrics_revised.json')+'<br/>B: out/wp_scen32_*<br/>C: out/wp_r8mix_acc_*'],
 ['D',link('15개 로그·설정·재집계 ZIP','assets/ablation-20261001.zip')+'<br/>'+link('시드별 값·파일 해시','assets/ablation-20261001.json')],
 ['E',link('채널 선택 근거 E9','evidence.html#E9')+'<br/>out/w25r_s{1,2,3}.jsonl, out/w50r_s{1,2,3}.jsonl'],
 ['F·G',link('추가 실험 원자료 ZIP','assets/awarenet_followup_20261001.zip')+'<br/>out/followup_20261001/fashion_100r/<br/>out/followup_20261001/equal_connections_v2/'],
 ['H·I',link('LoRA 근거 E4','evidence.html#E4')+' · '+link('전송 기록 안내','followup.html')+'<br/>out/fed_split/, out/vm1/l3net_*.jsonl'],
 ['J',link('Jetson 근거 E2','evidence.html#E2')+'<br/>configs/measurements/koren_jetson_2026-09-23.json'],
 ['K·L',link('활용 시연 근거 ZIP','assets/demo/evidence.zip')+'<br/>cnn_config.json, cnn_history.json,<br/>enterprise_config.json 및 학습·예측 기록'],
],[64,443])
text('표를 다시 계산하는 방법','h')
text('D의 ZIP을 풀고 python reaggregate.py를 실행하면 15개 로그에서 시간과 평균 폭을 다시 계산한다. B·C는 집계 JSON의 seeds 항목에서 시드별 값과 원파일 경로를 확인한다. F·G는 manifest.json의 조건과 raw/results 기록을 함께 확인한다.')
text('지표와 검증 범위','h')
text('시간 단축률 = (기준 시간 - 적용 시간) / 기준 시간 × 100. 평균 폭은 선택한 채널 비율의 평균이며 정확도의 대체 지표가 아니다. 텐서 바이트는 응용 데이터 크기이고 패킷 헤더를 포함한 회선 사용량과 다르다. 시드별 평균을 같은 비중으로 집계했으며, 이 문서의 요약표는 신뢰구간이나 유의성 검정을 제시하지 않는다.','note')
text('KOREN 실험에서는 종단 프로그램의 중계 선택과 분할 전송을 사용했다. KOREN 내부 라우터·스위치를 제어한 실험으로 표기하지 않았다. 독립 시드 정보가 없는 기록은 해당 범위를 명시했으며 원로그를 보존했다.','note')

def footer(c,doc):
 c.setStrokeColor(colors.HexColor('#ccd8de'));c.line(44, forty:=40,551,forty)
 c.setFont('MG',8);c.setFillColor(colors.HexColor('#61727c'))
 c.drawString(44,27,'AwareNet  |  실험 조건 및 검증 기록  |  2026.10.01')
 c.drawRightString(551,27,str(doc.page))
SimpleDocTemplate(str(OUT),pagesize=(595.28,841.89),rightMargin=44,leftMargin=44,topMargin=40,bottomMargin=54,title='AwareNet 실험 조건 및 검증 기록',author='AwareNet').build(story,onFirstPage=footer,onLaterPages=footer)
print(OUT)
