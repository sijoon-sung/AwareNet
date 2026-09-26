"""Build the final Korean report and reusable vector figures from archived evidence.

Uses reportlab and the bundled Poppler runtime. Does not run training, alter
historical experiments, or label replay as a hardware experiment.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import html
import json
import math
import shutil
import statistics
import subprocess
import sys
import zipfile

from reportlab.graphics.shapes import Drawing, Rect, Line, String, Polygon, Circle
from reportlab.graphics import renderPDF, renderSVG
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/final_awarenet'
FIG = OUT / 'figures'
QA = ROOT / 'tmp/pdfs/final_awarenet'
MANIFEST = ROOT / 'configs/measurements/final_report_evidence_2026-09-26.json'
DOC = ROOT / 'docs/01_제출발표/AwareNet_통합보고서_2026-09-26.md'
FONT = 'Malgun Gothic'
BOLD = 'Malgun Gothic Bold'
pdfmetrics.registerFont(TTFont(FONT, 'C:/Windows/Fonts/malgun.ttf'))
pdfmetrics.registerFont(TTFont(BOLD, 'C:/Windows/Fonts/malgunbd.ttf'))
pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=BOLD)
INK, MUTED, GRID = '#152439', '#52647B', '#DCE4EC'
TEAL, PURPLE, ORANGE, BLUE = '#007F78', '#6956AD', '#BB591F', '#2767AA'
PALE, WHITE = '#F4F7FA', '#FFFFFF'
W, H = 1400, 840


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8-sig'))


def rows(path):
    return [json.loads(line) for line in (ROOT / path).read_text(encoding='utf-8-sig').splitlines() if line.strip()]


def collect():
    used = []
    def source(path):
        used.append(path)
        return path
    ev = read(source('out/fed_split/eval_0913v1.json'))
    strict = read(source('out/fed_split/strict_0913v1.json'))
    federation = []
    for name, domains in ev['grid'].items():
        counts = {dom: {'correct': sum(bool(strict.get(name, {}).get(r['q'], r['ok'])) for r in v['detail']),
                        'n': v['n']} for dom, v in domains.items()}
        federation.append({'name': name, 'domains': counts,
                           'correct': sum(v['correct'] for v in counts.values()),
                           'n': sum(v['n'] for v in counts.values())})
    assert [v['correct'] for v in federation] == [0, 6, 12, 12]
    training = {}
    for mode, tag in [('shared', 'fed3_0913'), ('averaged', 'fed3v1_0913')]:
        rr = rows(source(f'out/fed_split/server_{tag}.jsonl'))
        assert len(rr) == 16 and [r['round'] for r in rr] == list(range(1, 17))
        training[mode] = {'rounds': len(rr), 'round_seconds_sum': sum(r['round_s'] for r in rr),
                          'clients': sorted(rr[0]['losses']), 'raw_rounds': rr}
    cost = rows(source('out/scale_lora/cost_llm_0913_vm.jsonl'))
    cost_pairs = []
    for short in ['0.5B', '1.5B', '3B', '7B']:
        pair = {r['part']: r for r in cost if r['model'].endswith('-' + short)}
        cost_pairs.append({'model': short, **pair})
    split = {}
    for model in ['0.5B', '3B', '7B']:
        rr = rows(source(f'out/scale_lora/device_llm_0913_Qwen_Qwen2.5-{model}.jsonl'))
        n = max(1, len(rr)//5)
        split[model] = {'steps': len(rr), 'first_fifth_loss': statistics.mean(r['loss'] for r in rr[:n]),
                        'last_fifth_loss': statistics.mean(r['loss'] for r in rr[-n:]),
                        'peak_rss_mb': max(r['rss_mb'] for r in rr),
                        'mean_step_s': statistics.mean(r['step_s'] for r in rr), 'raw_steps': rr}
    koren = []
    for cond, label in [('normal', '정상'), ('traffic', '트래픽 몰림'), ('slow', '연산 느림'), ('vary', '용량 변동')]:
        arm = {}
        for policy in ['uniform', 'widthpath']:
            vals = []
            for seed in (1, 2, 3):
                p = f'out/wp_scen32_{cond}_s{seed}_bothmp_{policy}.jsonl'
                rr = [r for r in rows(source(p)) if 'round' in r]
                assert len(rr) == 24 and [r['round'] for r in rr] == list(range(24)), p
                key = 'makespan' if 'makespan' in rr[0] else 'makespan_s'
                vals.append(statistics.mean(r[key] for r in rr[4:]))
            arm[policy] = {'mean_s': statistics.mean(vals), 'seed_means_s': vals}
        koren.append({'condition': cond, 'label': label, **arm,
                      'reduction_pct': 100*(1-arm['widthpath']['mean_s']/arm['uniform']['mean_s'])})
    normalized = read(source('configs/measurements/koren_jetson_2026-09-23.json'))
    replay = read(source('docs/02_실험/measured_replay_2026-09-23.json'))
    for p in ['sfl/plan.py', 'sfl/experiments/run_fed_split_lora.py',
              'docs/02_실험/실험_연합분할LoRA_문답증명_사전등록_2026-09-13.md',
              'docs/02_실험/실험_대형모델_분할LoRA_사전등록_2026-09-13.md',
              'docs/photo/HW2_Jetson_Orin_Nano.jpg']:
        source(p)
    manifest = {'date': '2026-09-26', 'purpose': 'Report evidence; historical records, no new training run',
                'federation': federation, 'federation_training': training, 'memory_cost_pairs': cost_pairs,
                'split_learning': split, 'koren_system': koren,
                'jetson_power_modes': normalized['jetson']['power_modes'], 'replay_snapshot': replay,
                'sources': [{'path': p, 'sha256': hashlib.sha256((ROOT/p).read_bytes()).hexdigest()} for p in used],
                'definitions': {'federation_scoring': 'saved strict overrides applied to all 18 heldout question forms',
                                'memory': 'archived peak_rss_mb divided by 1000 for plotted GB; front profile, not whole system',
                                'koren': '3 seed means; first 4 rounds excluded; multiple controls changed',
                                'lora_transport': 'activation and labels sent; gradients returned; no privacy guarantee',
                                'vertical_wording': 'model layer partitioning plus federation; not feature-partitioned VFL'}}
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return manifest


def col(value):
    return colors.HexColor(value)


class Figure:
    def __init__(self, stem, title, subtitle, footer):
        self.stem = stem
        self.title = title
        self.subtitle = subtitle
        self.footer = footer
        self.d = Drawing(W, H)
        self.rect(0, 0, W, H, WHITE)
        self.text(58, 44, title, 39, bold=True)
        self.text(58, 108, subtitle, 23, MUTED)
        self.line(58, 150, 1342, 150, GRID, 1)
        self.text(58, 787, footer, 20, MUTED)

    def text(self, x, y, text, size=25, color=INK, bold=False, anchor='start'):
        # Coordinates describe the top of the text box, not the baseline.
        text = text.replace('−', '-').replace('ᵢ', '_i')
        self.d.add(String(x, H-y-size, text, fontName=BOLD if bold else FONT,
                          fontSize=size, fillColor=col(color), textAnchor=anchor))

    def math(self, y, parts, size=38, bold=False, accents=None):
        """Typeset real subscripts/superscripts without missing Unicode glyphs."""
        font=BOLD if bold else FONT
        small=size*.57
        def sw(t,s):return pdfmetrics.stringWidth(t,font,s)
        def widths(p):
            if isinstance(p,str):return sw(p,size)
            base,sub,sup=p
            return sw(base,size)+max(sw(sub,small),sw(sup.replace('_',''),small))+2
        x=(W-sum(widths(p) for p in parts))/2
        for index,p in enumerate(parts):
            color=(accents or {}).get(index,INK)
            if isinstance(p,str):
                self.text(x,y,p,size,color,bold=bold);x+=widths(p);continue
            base,sub,sup=p
            self.text(x,y,base,size,color,bold=bold)
            sx=x+sw(base,size)
            if sub:self.text(sx,y+size*.62,sub,small,color,bold=bold)
            if sup:
                if '_' in sup:
                    a,b=sup.split('_')
                    self.text(sx,y-size*.24,a,small,color,bold=bold)
                    self.text(sx+sw(a,small),y+size*.05,b,size*.36,color,bold=bold)
                else:self.text(sx,y-size*.24,sup,small,color,bold=bold)
            x+=widths(p)

    def lines(self, x, y, lines, size=25, color=INK, leading=39, bold=False):
        for i, t in enumerate(lines):
            self.text(x, y+i*leading, t, size, color, bold)

    def rect(self, x, y, width, height, fill=WHITE, stroke=None, radius=0):
        self.d.add(Rect(x, H-y-height, width, height, rx=radius, ry=radius,
                        fillColor=col(fill) if fill else None,
                        strokeColor=col(stroke) if stroke else None, strokeWidth=1.5))

    def line(self, x1, y1, x2, y2, color=GRID, width=2, dashed=False):
        self.d.add(Line(x1, H-y1, x2, H-y2, strokeColor=col(color), strokeWidth=width,
                        strokeDashArray=[8, 6] if dashed else None))

    def arrow(self, x1, y1, x2, y2, color=TEAL, width=3, dashed=False):
        self.line(x1, y1, x2, y2, color, width, dashed)
        a = math.atan2(y2-y1, x2-x1)
        p = [(x2, H-y2)]
        for offset in [-.45, .45]:
            p.append((x2-16*math.cos(a+offset), H-(y2-16*math.sin(a+offset))))
        self.d.add(Polygon([v for pt in p for v in pt], fillColor=col(color), strokeColor=None))

    def box(self, x, y, w, h, heading, body, accent=TEAL):
        self.rect(x, y, w, h, PALE, GRID, 14)
        self.rect(x+25, y+28, 6, 30, accent)
        self.text(x+48, y+25, heading, 28, accent, True)
        self.lines(x+26, y+84, body, 24, leading=38)

    def save(self):
        renderPDF.drawToFile(self.d, str(QA / (self.stem+'.pdf')))
        renderSVG.drawToFile(self.d, str(FIG / (self.stem+'.svg')))
        # SVG fallbacks make the exported editable text portable to non-Windows viewers.
        p = FIG / (self.stem+'.svg')
        s = p.read_text(encoding='utf-8')
        s = s.replace('font-family: '+BOLD, 'font-weight: 700; font-family: '+FONT+', Noto Sans CJK KR, sans-serif')
        s = s.replace('font-family: '+FONT+';', 'font-family: '+FONT+', Noto Sans CJK KR, sans-serif;')
        s = s.replace('<title>...</title>', '<title>'+html.escape(self.title)+'</title>')
        s = s.replace('<desc>...</desc>', '<desc>'+html.escape(self.subtitle+' | '+self.footer)+'</desc>')
        p.write_text(s, encoding='utf-8')


def figures(data):
    out = []
    def new(*args):
        f=Figure(*args); out.append(f); return f
    f=new('01_coupled_system', '폭과 네트워크를 하나의 학습 완료 목표로 연결',
          '기기 계산량과 전송 자원은 서로 다른 제어 변수이며 같은 배치의 완료 시간에 함께 작용한다',
          '시스템 개념도  |  폭 고정 경로 실험은 효과 분리를 위한 대조군  |  기존 결합 정책과 함께 유지')
    f.box(58, 210, 360, 230, '학습 변수  w', ['모델 폭과 기기 계산량', 'activation·gradient 크기', '폭 축소에 따른 학습 대가'], PURPLE)
    f.box(982, 210, 360, 230, '네트워크 변수  S', ['허용된 경유 종점', '분할 비율과 공유 용량', '전환 비용과 완료 지연'], TEAL)
    f.box(505, 245, 390, 190, '공통 시간 모형', ['계산 시간 + 전송 시간', '가장 늦는 참여자의 완료'], BLUE)
    f.arrow(418, 335, 505, 335, PURPLE)
    f.arrow(982, 335, 895, 335)
    f.arrow(700, 435, 700, 513, BLUE)
    f.box(365, 515, 670, 145, '결합 판단과 실행', ['망 개선으로 보존할 폭을 판단하고 남는 계산 부하를 조절'], BLUE)
    f.text(700, 701, '관측  →  시간 예측  →  경로·폭 계획  →  전송·학습  →  다시 관측', 26, anchor='middle')

    f=new('02_joint_model', '상호 보완 관계를 담은 시간 모형',
          '기존 CNN 폭 정책의 배치당 근사식  |  직렬 계산·전송 기준  |  LoRA rank에는 별도 프로파일 필요',
          '근거: sfl/plan.py round_times · _t_one · opt_widths  |  폭 손실은 정확도 손실의 측정값이 아님')
    f.math(210, [('t','i',''),'(',('w','i',''),', S) = ',('c','i',''),' ',('w','i','γ_i'),
                 '  +  8 ',('b','i',''),' ',('w','i',''),' / ',('R','i',''),'(S)  +  ',('ε','i','')],38,True,
                 {**{i:PURPLE for i in (4,5,6)},**{i:TEAL for i in (8,9,10,11,12)}})
    f.text(440, 290, '폭에 따른 계산 시간', 26, PURPLE, anchor='middle')
    f.text(841, 290, '폭과 경로가 함께 정하는 전송 시간', 26, TEAL, anchor='middle')
    f.math(375,['J(w, S) = ',('max','i',''),' [ B · ',('t','i',''),'(',('w','i',''),', S) + ',
                ('δ','i',''),' ] + (λ/N) ',('Σ','i',''),'(1 - ',('w','i',''),')'],31)
    f.lines(92, 469, ['wᵢ: 정규화된 모델 폭       S: 모든 기기의 경로 배정       Rᵢ(S): 공유 제약 아래 전송률',
                     'cᵢ·bᵢ: 전폭 계산 시간·왕복 바이트       γᵢ: 계산 스케일 지수       εᵢ: 관측 잔차',
                     'B: 라운드의 배치 수       δᵢ: 경로 전환 비용       λ: 평균 폭 손실의 시간 단위 가격'], 24, leading=45)
    f.text(700, 657, '경로 개선  →  같은 폭의 전송 시간 감소  →  필요한 폭 축소량 감소', 29, TEAL, True, 'middle')
    f.text(700, 713, '구현은 단계적 탐욕 계획과 히스테리시스  ·  전역 최적해나 정확도 보장으로 해석하지 않는다', 23, MUTED, anchor='middle')

    f=new('03_hardware_evidence', '실제 장비와 실제 회선에서 이어진 검증',
          'KOREN 실망 학습과 Jetson 보드 측정은 각자의 원시 기록을 가진 별도 실험이다',
          'KOREN VM 2대 ≠ 물리 클라이언트 32대  |  Jetson 1대의 모드별 표본 ≠ 다수 보드 동시 학습')
    f.box(58, 212, 385, 240, 'KOREN VM 두 대', ['실제 CPU·메모리 자원', 'LoRA: 논리 기기 3개', 'VM1 c0·c1 / VM2 c2'], TEAL)
    f.box(953, 212, 389, 240, 'HPC 학습 서버', ['서버측 모델과 역전파', 'V100 16GB / CPU 실행', '라운드별 어댑터 집계'], BLUE)
    f.arrow(443, 298, 953, 298, TEAL)
    f.arrow(953, 392, 443, 392, PURPLE)
    f.text(700, 250, 'KOREN 실회선과 역방향 SSH 경유', 24, anchor='middle')
    f.text(700, 313, 'activation + labels', 25, TEAL, anchor='middle')
    f.text(700, 405, 'gradient / adapter', 25, PURPLE, anchor='middle')
    f.box(58, 531, 615, 190, 'Jetson Orin Nano 보드', ['MAXN / 25W / 15W에서 총 90스텝', '전체 LoRA 스텝·메모리·OOM 기록'], ORANGE)
    f.box(730, 531, 612, 190, '실측값을 이용한 후속 재현', ['기존 전송 기록과 Jetson 시간값을 입력', '시간 모형·로컬 TCP에서 설계 후보 비교'], BLUE)
    f.arrow(674, 625, 730, 625, BLUE, dashed=True)

    f=new('04_koren_results', 'KOREN 결합 시스템의 기존 실험 결과',
          '32개 논리 참여자  ·  조건별 3시드  ·  첫 4라운드 제외  ·  시드 평균의 평균',
          '기존 결합 시스템 비교: 폭·출구·경로가 함께 변경  |  동일 정확도 효과 또는 새 network 정책 성능이 아님')
    f.rect(910, 177, 24, 24, '#A7B3C3');f.text(946, 173, '기존 기준선', 23)
    f.rect(1130, 177, 24, 24, TEAL);f.text(1166, 173, '결합 시스템', 23)
    base_x, span, scale = 278, 780, 120
    for tick in (0, 30, 60, 90, 120):
        xx=base_x+span*tick/scale;f.line(xx, 228, xx, 724, GRID, 1)
        f.text(xx, 732, str(tick), 20, MUTED, anchor='middle')
    for i,r in enumerate(data['koren_system']):
        y=247+i*120
        f.text(65, y+20, r['label'], 28, bold=True)
        a,b=r['uniform']['mean_s'],r['widthpath']['mean_s']
        f.rect(base_x, y, span*a/scale, 32, '#A7B3C3')
        f.rect(base_x, y+43, span*b/scale, 32, TEAL)
        f.text(base_x+span*a/scale+12, y-2, f'{a:.2f} s', 23)
        f.text(base_x+span*b/scale+12, y+42, f'{b:.2f} s', 23, TEAL, True)
        f.text(1270, y+18, f'−{r["reduction_pct"]:.1f}%', 32, TEAL, True, 'end')

    f=new('05_execution_scope', '모델링에서 실제 실행까지 연결되는 구조',
          '경로 선택의 단위는 보유 VM의 경유 종점  |  기기의 접속망 전체를 제어한다는 가정을 두지 않는다',
          'OS-Ken 집행기는 별도 프로토타입  |  앱 완료 보고는 물리 경로 증명·OVS 설치 ACK·기기 인증과 구분')
    xs=[58,407,756,1105]
    for x,t,b,c in zip(xs,['관측','공통 계획','전송 집행','학습·집계'],
                       [['연산·왕복 바이트','경로별 실효율'],['공유 용량과 폭','전환 비용·한계'],['양방향 분할','재조립·완료 보고'],['기울기 전달','폭별 또는 LoRA 집계']],
                       [BLUE,PURPLE,TEAL,BLUE]):
        f.box(x, 233, 237, 212, t, b, c)
    for x in xs[:-1]:f.arrow(x+237, 339, x+349, 339, BLUE)
    f.line(1223, 473, 1223, 538, BLUE);f.arrow(1223, 538, 176, 538, BLUE);f.arrow(176, 538, 176, 445, BLUE)
    f.text(700, 559, '측정 결과를 다음 계획에 반영', 27, BLUE, anchor='middle')
    f.line(58, 641, 1342, 641, GRID)
    f.text(58, 674, '기기 권한', 27, PURPLE, True);f.text(230, 675, '일반 소켓·허용 종점 선택', 25)
    f.text(738, 674, '운영팀 권한', 27, TEAL, True);f.text(943, 675, '보유 VM·브리지 범위', 25)

    f=new('06_lora_federation', 'LoRA로 확인한 모델 분할과 연합 집계',
          'Qwen2.5 0.5B  ·  앞 2층 분할  ·  LoRA rank 16  ·  3개 논리 기기  ·  16라운드',
          '실제 구현: activation과 labels 전송, gradient 반환  |  본 그림은 앞·뒷단 모두 평균하는 v1 대조 실행')
    for y,label,c in [(205,'c0  /  도메인 B1',PURPLE),(363,'c1  /  도메인 B2',TEAL),(521,'c2  /  도메인 B3',BLUE)]:
        f.box(58, y, 356, 144, label, ['임베딩 + 앞 2층 + LoRA'], c)
        f.arrow(414, y+57, 669, y+57, c)
        f.arrow(669, y+99, 414, y+99, c)
    f.box(669, 205, 673, 426, 'HPC에서 기기별 뒷단 학습', ['나머지 층과 출력층 + LoRA', '기기별 어댑터와 optimizer 상태 보관', '기기 차례에 해당 상태로 순전파·역전파'], BLUE)
    f.rect(669, 665, 673, 98, PALE, GRID, 14)
    f.text(695, 677, '라운드 끝 앞·뒷단 어댑터 평균', 28, TEAL, True)
    f.text(695, 721, '다음 라운드의 학습 상태로 공유', 24)
    f.arrow(1005, 631, 1005, 665)
    f.text(527, 201, 'ACT + labels', 22, MUTED, anchor='middle')
    f.text(527, 679, 'GRAD 반환', 22, MUTED, anchor='middle')

    f=new('07_lora_results', '분산 도메인의 학습 결과가 연합 모델에 반영',
          '엄격 판정 적용  ·  heldout 문형 18개  ·  B1 8개 / B2 3개 / B3 7개  ·  단일 소규모 실행',
          '문형을 바꾼 알려진 사실 평가  |  새 지식 일반화·대규모 정확도·폭·경로 결합 성능을 입증하는 수치는 아님')
    names=['베이스','단독 B1','연합 뒷단 공유','연합 앞·뒷단 평균']
    for i,(name,r) in enumerate(zip(names,data['federation'])):
        y=230+i*120
        f.text(58, y+9, name, 27, bold=True)
        f.rect(363, y, 630, 47, PALE)
        f.rect(363, y, 630*r['correct']/18, 47, [GRID,PURPLE,BLUE,TEAL][i])
        f.text(1025, y+1, f'{r["correct"]}/18', 34, [MUTED,PURPLE,BLUE,TEAL][i], True)
        ds=r['domains']
        f.text(363, y+57, '  ·  '.join(f'{dom}  {ds[dom]["correct"]}/{ds[dom]["n"]}' for dom in ('B1','B2','B3')), 23, MUTED)
    f.text(1205, 242, '정답 수', 23, MUTED)
    f.text(1205, 348, '33.3%', 26, PURPLE)
    f.text(1205, 468, '66.7%', 26, BLUE)
    f.text(1205, 588, '66.7%', 26, TEAL)

    f=new('08_memory_scale', '모델 분할로 기기에 필요한 메모리를 낮춤',
          'KOREN VM CPU 프로파일  ·  batch 4 / sequence 256 / rank 16 / 앞 2층  ·  peak RSS',
          'front 단독 프로파일이며 서버 메모리·통신·전체 학습 시간을 포함하지 않음  |  GB = 기록 MB / 1000')
    f.rect(930, 178, 23, 23, '#A7B3C3');f.text(966, 174, '로컬 전체 모델', 23)
    f.rect(1180, 178, 23, 23, TEAL);f.text(1216, 174, '분할 front', 23)
    x0,span=275,812
    for tick in (0,10,20,30):
        xx=x0+span*tick/30;f.line(xx, 235, xx, 718, GRID, 1);f.text(xx,731,str(tick)+' GB',21,MUTED,anchor='middle')
    for i,p in enumerate(data['memory_cost_pairs']):
        y=248+120*i;f.text(58,y+18,p['model'],31,bold=True)
        lo,fr=p['local'],p['front'];b=fr['peak_rss_mb']/1000
        if 'error' in lo:
            f.text(x0, y, 'OOM  ·  원 실행에서 메모리 부족',25,ORANGE,True)
        else:
            a=lo['peak_rss_mb']/1000;f.rect(x0,y,span*a/30,32,'#A7B3C3');f.text(x0+span*a/30+12,y-2,f'{a:.2f}',24)
        f.rect(x0,y+43,span*b/30,32,TEAL);f.text(x0+span*b/30+12,y+41,f'{b:.2f}',24,TEAL,True)
    f.text(1215,626,'7B front',24,TEAL,anchor='middle')
    f.text(1215,663,'6.44 GB',32,TEAL,True,'middle')

    f=new('09_reasoning_and_evidence', '문제 정의에서 검증까지 이어지는 논리',
          '기기 자원과 전송 자원을 함께 모델링하고 각 실험이 뒷받침하는 주장으로 결론을 연결한다',
          '향후 과제: 실제 OVS 집행·동일 정확도까지의 시간·통합 LoRA 네트워크 제어  |  후속 후보의 성능은 미확정')
    steps=[('01','기기 부하','폭·모델 분할로 조절',PURPLE),('02','반복 왕복 전송','공유 병목·경유 선택',TEAL),
           ('03','공통 완료 목표','시간·폭 대가의 모델링',BLUE)]
    for i,(no,title,desc,c) in enumerate(steps):
        x=58+445*i;f.text(x,210,no,50,c,True);f.text(x,286,title,32,c,True);f.text(x,342,desc,25)
        if i<2:f.arrow(x+350,298,x+421,298,c)
    f.line(58,423,1342,423,GRID)
    for i,(title,body,c) in enumerate([
        ('실제 회선·학습',['KOREN 결합 실험','VM↔HPC LoRA 학습'],TEAL),
        ('실제 장비 프로파일',['Jetson 전력 모드별 시간','메모리·OOM 관측'],ORANGE),
        ('실측값 기반 재현',['시간 모형·로컬 TCP','새 제어의 조건·반례'],BLUE)]):
        f.box(58+445*i,481,394,223,title,body,c)
    return out


PSTYLE = ParagraphStyle('Body', fontName=FONT, fontSize=10.4, leading=16,
                        textColor=col(INK), wordWrap='CJK', spaceAfter=6)
SMALL = ParagraphStyle('Small', parent=PSTYLE, fontSize=8.4, leading=12, textColor=col(MUTED))


class Report:
    def __init__(self, path):
        self.c=canvas.Canvas(str(path),pagesize=(612,792),pageCompression=1)
        self.c.setTitle('AwareNet 폭과 네트워크 결합 시스템 종합 보고서')
        self.c.setAuthor('AwareNet')
        self.page=0;self.y=0
    def begin(self,kicker,title,subtitle):
        if self.page:self.c.showPage()
        self.page+=1;self.y=746
        self.c.bookmarkPage('page'+str(self.page))
        self.c.addOutlineEntry(title,'page'+str(self.page),level=0)
        self.c.setFillColor(col(MUTED));self.c.setFont(FONT,8.4)
        self.c.drawString(42,762,'AwareNet  /  KOREN  /  2026.09.26')
        self.c.drawRightString(570,762,kicker)
        self.c.setFillColor(colors.black);self.c.setFont(BOLD,21)
        self.c.drawString(42,720,title)
        self.y=699;self.para(subtitle,SMALL)
        self.c.setFillColor(col(MUTED));self.c.setFont(FONT,8)
        self.c.drawString(42,27,'근거와 실행 범위는 각 그림의 설명 및 마지막 페이지 참고')
        self.c.drawRightString(570,27,f'{self.page:02d}')
    def para(self,text,style=PSTYLE,gap=9):
        text=text.replace('−','-')
        p=Paragraph(text,style);_,h=p.wrap(528,700)
        if self.y-h<48:raise RuntimeError(f'page {self.page} overflow: {text[:70]}')
        p.drawOn(self.c,42,self.y-h);self.y-=h+gap
    def heading(self,text):
        self.y-=8;self.para('<b>'+text+'</b>',gap=6)
    def figure(self,f,width=528):
        factor=width/W;d=copy.deepcopy(f.d);d.scale(factor,factor)
        height=H*factor
        if self.y-height<48:raise RuntimeError('figure overflow')
        renderPDF.draw(d,self.c,42,self.y-height);self.y-=height+11
    def photo(self,path):
        self.c.drawImage(str(path),42,self.y-150,width=200,height=150,preserveAspectRatio=True,mask='auto')
        st=ParagraphStyle('Photo',parent=PSTYLE,fontSize=9.7,leading=15)
        p=Paragraph('<b>보관된 실제 Jetson 장비 사진</b><br/><br/>보드 전력 모드별 30개, 총 90개 스텝을 측정했다. 전체 스텝 중앙값은 MAXN 554.1ms, 25W 608.9ms, 15W 903.7ms다.<br/><br/>이 보드 프로파일과 VM의 분할 연합학습은 서로 다른 실행이다.',st)
        _,h=p.wrap(303,170);p.drawOn(self.c,267,self.y-h);self.y-=164
    def save(self):self.c.save()


def build_pdf(data,ff):
    r=Report(OUT/'AwareNet_종합보고서.pdf')
    r.begin('01  결론','폭과 네트워크를 결합한 분할 연합학습','시스템의 문제 정의와 모델링부터 KOREN 실험, Jetson 측정, LoRA 연합학습까지 연결한다.')
    r.figure(ff[0])
    r.heading('핵심 주장')
    r.para('AwareNet은 기기의 계산 부담을 조절하는 모델 폭과 통신 자원을 조절하는 경유 경로를 공통 완료 시간 모형으로 연결한다. 네트워크 개선으로 학습 폭을 보존할 여지를 만들고, 남는 기기 계산 부담을 폭 제어로 조절하는 시스템을 구현했다.')
    r.para('기존 KOREN 결합 실험, 실물 Jetson의 계산 프로파일, VM과 HPC 사이의 실제 LoRA 분할 연합학습이 서로 다른 측면의 근거를 제공한다. 각 실험의 장비·조건·측정 범위를 연결해 설명하는 것이 이번 결과의 강점이다.')
    r.para('<b>확정 범위</b>  기존 결합 시스템과 하드웨어 기반 검증을 중심에 둔다. 폭 고정 경로 정책은 네트워크 효과를 분리하는 대조군으로, 기울기 반환 순서는 후속 연구 후보로 배치한다.',SMALL)

    r.begin('02  모델링','서로 다른 변수를 공통 목적에 연결','두 제어가 상호 보완되는 이유는 왕복 바이트와 실효 전송률이 같은 시간 항에 함께 들어가기 때문이다.')
    r.figure(ff[1])
    r.para('<b>계산과 통신의 결합</b>  폭 w를 줄이면 계산 항 c·w^γ가 작아지고, 기존 CNN 근사에서는 전송 바이트 b·w도 작아진다. 경로 배정 S는 공유 링크를 사용하는 모든 기기의 전송률 R(S)에 영향을 준다. 같은 목표 시간에서 좋은 경로가 확보되면 폭을 덜 줄이고도 완료할 수 있다.')
    r.para('<b>폭 보존의 가격</b>  λ는 평균 폭 손실 한 단위를 시간으로 환산하는 설정값이다. Σ(1−w)/N은 실제 정확도 손실을 측정한 함수가 아니다. 폭 하한, 허용 종점, 공유 용량, 라운드별 이동 상한을 함께 적용한다.')
    r.para('식은 기존 plan.py를 설명하는 근사 모형이다. 구현은 경로 단계와 폭 단계의 탐욕적 개선 및 히스테리시스이며, 전역 공동 최적해를 증명한 것은 아니다. 잔차·효율 보정은 코드 경로에 따라 선택하며, LoRA rank에 CNN의 b·w 관계를 그대로 적용하지 않는다.',SMALL)

    r.begin('03  실제 환경','실제 하드웨어와 실회선을 활용한 검증','그림 속 장비의 역할과 물리 장비 수를 실험별로 구분한다.')
    r.figure(ff[2],width=528)
    r.photo(ROOT/'docs/photo/HW2_Jetson_Orin_Nano.jpg')
    r.para('KOREN 결합 리그에는 HPC의 논리 기기가 VM을 경유해 돌아오는 구성과 VM에 기기를 배치한 구성이 모두 있다. LoRA 연합 실험은 VM1에 c0·c1, VM2에 c2를 두고 HPC 서버와 통신했다. 8개 또는 32개 논리 참여자를 물리 단말 수로 환산하지 않는다.',SMALL)

    r.begin('04  KOREN 결과','결합 시스템의 효과를 실망에서 관찰','원 로그의 조건별 시드 평균을 재계산했다. 학습량과 경로가 함께 바뀐 시스템 비교다.')
    r.figure(ff[3])
    r.para('정상·트래픽 몰림·연산 느림·용량 변동에서 평균 라운드 시간은 기준선보다 약 24.6~42.6% 감소했다. 실제 회선, 가상머신의 CPU·메모리, tc 제한 및 교란을 포함한 실행 기록을 가진다는 점에서 순수 수치 모형만의 검토보다 구현 근거가 구체적이다.')
    r.para('축소 실행은 CPU·메모리 제약 때문에 필요한 실험 방식이었다. 32대 조건과 8대 실행은 각 로그의 논리 참여자 수·회선 상한·노이즈 조건으로 설명한다. 부하 비율을 맞춘 설계만으로 계산·학습·확률적 동작까지 동등해지는 것은 아니다.')
    r.para('여기서는 폭, 출구 수, 경로가 함께 바뀌었다. 따라서 감소율을 경로만의 효과나 같은 정확도까지의 시간 단축으로 표시하지 않는다. 새 network 정책 및 LoRA 실행의 성능과도 합산하지 않는다.',SMALL)

    r.begin('05  실행 구조','관측과 계획을 실제 전송에 연결','학습 변수와 네트워크 변수를 계층으로 구분하되 공통 관측과 시간 목표로 결합한다.')
    r.figure(ff[4])
    r.para('분할 전송은 activation과 gradient 양방향에 적용하며, 수신 측은 조각 위치·크기·중복 충돌을 확인해 완성본을 학습 단계에 전달한다. 제어기가 요구한 종점과 앱의 완료 보고를 대조해 다음 판단에 사용한다.')
    r.para('기기에는 일반 소켓 권한을 요구하고, 운영팀이 가진 VM과 브리지에서만 정책을 집행하는 구조다. KOREN 코어 라우터나 가입자 접속망에 대한 관리자 권한을 가정하지 않는다. 현재 엣지 변경은 경유 종점 변경이며 학습 상태의 서버 간 이동은 포함하지 않는다.')
    r.para('OS-Ken/OVS 집행기는 후속 프로토타입이다. 실제 스위치 설치 확인과 자동 계획 연동, 기기 인증·암호화는 남아 있다. 관련 로컬 경로·소켓·기울기·재현 테스트 53개는 통과했지만 현장 SDN 검증을 대신하지 않는다.',SMALL)

    r.begin('06  LoRA 구현','실제 분할 연합학습까지 이어진 구현','모델 분할, 양방향 역전파, 기기별 학습, 라운드 집계를 실회선에서 실행했다.')
    r.figure(ff[5])
    r.para('서로 다른 사실을 가진 B1·B2·B3 도메인을 세 논리 기기에 나눠 학습했다. 기기는 모델 앞부분을 실행하고 HPC 서버가 뒷부분의 손실과 gradient를 계산한다. 라운드마다 앞단 어댑터를 평균하는 실행과, 기기별 뒷단 상태까지 별도로 학습한 후 앞·뒷단 모두 평균하는 대조 실행을 보존했다.')
    r.para('후자의 서버 로그에는 16개 라운드가 있으며 라운드 시간 합은 588.8초다. 이는 전체 배포·준비 시간과 구분한다. 각 라운드의 평균 전 뒷단 상태 거리가 0보다 커 기기별 상태 갱신이 실제로 이루어진 기록도 남아 있다.')
    r.para('정확한 명칭은 <b>모델의 층 분할을 이용한 분할 연합학습</b>이다. 동일 샘플의 서로 다른 특징을 여러 기관이 가진 수직 연합학습 VFL과는 데이터 분할 방식이 다르다. LoRA에서는 학습 가능한 어댑터를 줄여 학습·집계 부담을 낮추지만 절단면 activation의 크기가 rank에 비례해 줄지는 않는다.',SMALL)

    r.begin('07  LoRA 결과','단독 학습을 넘어선 도메인 결합을 확인','18개 평가 문항의 원문 판정과 저장된 엄격 판정을 적용했다.')
    r.figure(ff[6])
    r.para('단독 B1 모델은 B1에서 6/8, B2·B3에서 0개를 맞혔다. 연합 모델은 다른 기기가 가진 B2·B3 사실에도 응답했다. 앞·뒷단 모두 평균한 대조군은 B1 4/8, B2 2/3, B3 6/7로 총 12/18이었다. 이는 실제 연합 집계가 작동한 소규모 기능 검증이다.')
    r.para('도메인 간 간섭도 관찰됐다. 앞·뒷단 평균 대조군의 B1 점수는 단독보다 낮다. 평가 대상은 학습 사실의 다른 문형이므로 광범위한 일반화 능력으로 해석하지 않는다. 문답에 등장하는 통신 숫자는 학습 코퍼스의 내용이며 이번 KOREN 회선 측정값으로 재인용하지 않는다.')
    r.para('activation과 토큰 labels가 서버로 전달된다. 한 기기에만 넣은 가짜 비밀을 묻는 카나리아 문항 3개가 연합 모델에서도 노출됐다. 따라서 데이터 비공개·프라이버시 보장을 성과로 주장하지 않는다.',SMALL)

    r.begin('08  자원 효과','기기에서 감당할 수 있는 모델 범위를 넓힘','메모리 프로파일과 실제 분할 학습 로그를 각각 확인한다.')
    r.figure(ff[7])
    r.para('VM의 7B 로컬 LoRA 프로파일은 OOM을 기록했고, 앞 2층만 보유한 front 프로파일은 약 6.44GB RSS로 실행됐다. 별도의 VM↔HPC 7B 실제 분할 학습에서는 10스텝을 수행했으며 기기 RSS는 약 7.94GB였다. 두 메모리 수치는 서로 다른 실행 조건이다.')
    sl=data['split_learning']['7B']
    r.para(f'7B 실제 분할 학습의 처음 2스텝 평균 손실은 {sl["first_fifth_loss"]:.2f}, 마지막 2스텝 평균은 {sl["last_fifth_loss"]:.2f}였다. 짧은 실행에서 역전파와 갱신이 성립한 증거이며, 수렴·정확도 또는 기존 CNN 폭·경로 결합 최적화가 LoRA에 통합됐다는 증거는 아니다.')
    r.para('분할은 기기 부담 일부를 서버 계산과 통신으로 옮긴다. 이 때문에 기기 자원만 줄여 보는 평가로는 부족하며, 폭·분할·어댑터 크기와 실제 네트워크 비용을 함께 관측하는 시스템 관점이 필요하다.',SMALL)

    r.begin('09  생각과 결론','설계의 변화와 각 검증 결과를 연결','새 기능을 늘리기보다 현재 구현과 증거가 지지하는 결론을 하나의 이야기로 묶었다.')
    r.figure(ff[8])
    r.para('초기 폭 조절에서 출발해 통신 병목을 함께 모델링했고, 실제 경유·양방향 분할 전송과 재조립으로 연결했다. 후속 network 정책은 폭을 고정해 경로 효과를 분리하도록 만들었다. 기울기 반환 순서의 연구는 어느 조건에서 계산과 전송이 겹칠 수 있는지 검토하는 보완 단계다.')
    r.para('Jetson과 KOREN의 기존 수치를 주입한 대표 조건에서 시간 모형은 9.97%, 로컬 TCP는 9.91% 단축을 보였다. 전체 스텝 중 이후 계산 비율을 0.5로 가정한 결과이며, 회선 계수 0.1배에서는 1.60%로 줄었다. 새 현장 학습 성능이나 실제 장비를 동시에 연결한 결과로 부르지 않는다.')
    r.para('추가 조각 재전송, 자동 공유 병목 탐지, 동적 분할 깊이는 후속 후보로 보존한다. 이번 확정 범위는 기존 결합 시스템, 실제 하드웨어의 실험 근거, LoRA 분할 연합학습 기능 검증이다.',SMALL)

    r.begin('10  최종 정리','제출에서 강조할 기여와 근거','코드·측정·평가 원문을 연결한 최종 주장 범위')
    r.heading('제출용 결론')
    r.para('AwareNet은 기기 부하를 조절하는 모델 폭과 통신 자원을 조절하는 네트워크 경로를 공통 시간 모형으로 연결한 분할 연합학습 시스템이다. 실제 KOREN 구간에서 기존 결합 시스템을 실행하고, Jetson 보드의 계산 자원 특성을 측정했으며, KOREN VM과 HPC 사이에서는 LoRA 기반 모델 분할과 연합 집계가 작동함을 확인했다. 이 성과는 모델링, 전송 구현, 실제 장비 측정, 학습 기능 검증을 연결한 시스템 구현의 근거다.')
    r.heading('현재 증거가 지지하는 범위')
    for t in ['결합 모형과 실행 구조: plan.py, network_control.py, mpsend.py, chunker.py 및 관련 검사.',
              '기존 KOREN 라운드 단축: 결합 시스템 비교. 동일 정확도 또는 순수 경로 효과는 별도 검증 필요.',
              'LoRA 분할 연합학습: VM CPU와 HPC 서버, 3개 논리 기기, 16라운드 및 18문항 평가.',
              '실물 Jetson: 모드별 30스텝 계산 프로파일. KOREN LoRA 연합 실행과 별도.',
              '남은 검증: 실제 OVS 집행과 신원 인증, 동일 정확도까지의 시간, LoRA와 동적 네트워크 제어의 통합.']:
        r.para('• '+t,gap=6)
    r.heading('근거 문서와 원자료')
    refs=[
        '[1] docs/02_실험/데이터_기록_2026-09-07.md  ·  KOREN 및 9/13 LoRA 실행 기록',
        '[2] docs/02_실험/실험_연합분할LoRA_문답증명_사전등록_2026-09-13.md',
        '[3] out/fed_split/eval_0913v1.json + strict_0913v1.json  ·  문답과 엄격 판정',
        '[4] out/fed_split/server_fed3v1_0913.jsonl  ·  16라운드 원시 로그',
        '[5] out/scale_lora/cost_llm_0913_vm.jsonl  ·  모델 크기별 자원 프로파일',
        '[6] configs/measurements/koren_jetson_2026-09-23.json  ·  Jetson·전송 원시 입력',
        '[7] configs/measurements/final_report_evidence_2026-09-26.json  ·  이번 재계산과 출처 해시',
        '[8] LoRA  arxiv.org/abs/2106.09685  ·  SplitLoRA  arxiv.org/abs/2407.00952',
        '[9] VFL 용어  arxiv.org/abs/2211.12814  ·  특징 분할과 모델 층 분할의 구분']
    for t in refs:r.para(html.escape(t),SMALL,gap=3)
    r.save()


def write_texts(data,ff):
    fig_md=lambda n: f'![{ff[n].title}](../../output/final_awarenet/figures/{ff[n].stem}.png)'
    fed='\n'.join('| '+r['name']+' | '+' | '.join(f'{r["domains"][d]["correct"]}/{r["domains"][d]["n"]}' for d in ['B1','B2','B3'])+f' | {r["correct"]}/18 |' for r in data['federation'])
    md=rf'''# AwareNet 폭과 네트워크 결합 시스템 종합 보고서

2026-09-26 · awarenet · 발표용 시각 자료 보조본. 현재 제출 본문은 [중간보고서 양식의 서술형 보고서](AwareNet_서술형보고서_2026-09-26.md)를 기준으로 한다.

## 확정 결론

**모델 폭과 네트워크 경로는 서로 다른 제어 변수이며, 학습 완료 시간이라는 같은 목표 안에서 상호 보완한다.** 실제 KOREN 구간의 시스템 실행, Jetson 보드 측정, VM과 HPC 사이의 LoRA 분할 연합학습을 근거로 이 구현을 설명한다.

[그림을 포함한 PDF](../../output/final_awarenet/AwareNet_종합보고서.pdf) · [이미지 갤러리](../../output/final_awarenet/index.html) · [PNG SVG 이미지 묶음](../../output/final_awarenet/AwareNet_이미지팩.zip)

## 1 폭과 네트워크를 연결한 공통 모델

{fig_md(0)}

기기의 계산 부담은 폭 w로, 통신 자원은 경로 집합 S와 분할 배정으로 조절한다. 기존 CNN 모델의 배치당 근사는 다음과 같다.

$$t_i(w_i,S)=c_iw_i^{{\gamma_i}}+\frac{{8b_iw_i}}{{R_i(S)}}+\epsilon_i$$

$$J(\mathbf{{w}},S)=\max_i\{{B t_i(w_i,S)+\delta_i\}}+\frac{{\lambda}}{{N}}\sum_i(1-w_i)$$

c_i는 전폭 계산 시간, b_i는 전폭 activation+gradient 바이트, R_i(S)는 공유 자원 제약 아래의 전송률이다. B는 배치 수, δ_i는 전환 비용, ε_i는 잔차다. γ_i는 계산 스케일 지수이며 프로파일에 없으면 코드의 기본값을 쓴다. λ는 폭 손실의 시간 단위 가격이다. 폭 손실 항은 정확도 손실을 직접 측정한 함수가 아니다.

{fig_md(1)}

폭을 줄이면 계산 항과 전송 바이트가 함께 바뀐다. 경로를 개선하면 같은 폭의 전송 시간이 줄어 폭을 보존할 여지가 생긴다. 구현은 경로·폭 단계의 탐욕적 개선과 히스테리시스다. 전역 공동 최적해나 정확도 보장을 주장하지 않는다. 잔차 보정·효율 보정은 코드 경로별 선택이고 직렬 시간 모형에 모든 파이프라인 중첩을 포함하지 않는다.

기존 `widthpath` 결합 정책을 시스템의 중심으로 설명한다. 새 `network`의 폭 고정은 경로 효과를 분리하는 검증 방법이다. LoRA의 rank, 분할 깊이, CNN 채널 폭은 서로 다른 변수이므로 b_i·w_i 관계를 LoRA에 그대로 적용하지 않는다. [코드](../../sfl/plan.py)

## 2 실제 하드웨어와 KOREN 회선이 제공하는 근거

{fig_md(2)}

KOREN VM 2대와 HPC의 실제 자원에서 경유 전송 및 학습을 실행했다. 결합 리그에는 HPC 논리 기기가 VM을 경유해 돌아오는 구성과 VM에 기기를 배치한 구성이 있다. LoRA 연합 실행은 VM1의 c0·c1, VM2의 c2와 HPC 서버를 연결했다. Jetson 보드의 전력 모드별 전체 학습 스텝 측정은 별도의 실험이다.

![보관된 실제 Jetson 장비 사진](../photo/HW2_Jetson_Orin_Nano.jpg)

사진은 보유 장비를 보여 준다. 성능 수치의 근거는 원시 로그다. MAXN·25W·15W 각각 30스텝, 총 90스텝의 전체 스텝 중앙값은 554.1·608.9·903.7ms다. 이 보드 프로파일과 KOREN의 3기기 LoRA 실험을 하나의 동시 실험으로 합치지 않는다.

## 3 KOREN 결합 시스템 결과

{fig_md(3)}

32개 논리 참여자 조건의 3시드에서 첫 4라운드를 제외하고 재계산했다. 기존 결합 시스템의 평균 라운드 감소율은 조건별 약 24.6~42.6%다. 폭·출구·경로가 함께 바뀌므로 순수 네트워크 효과, 동일 정확도까지의 단축, 새 정책 성능으로 귀속하지 않는다.

8개·32개 조건은 물리 장비 수가 아닌 각 실행의 논리 참여자 수·회선 상한·교란 조건으로 설명한다. CPU·OOM 제약 아래의 축소 설계는 보존하되, SHRiNK식 부하 비율 보존만으로 계산과 학습까지 동등하다고 가정하지 않는다. [기존 실측 근거](기존성과_근거보고서_및_비판검토_2026-09-19.md)

## 4 시스템 실행과 권한 경계

{fig_md(4)}

공통 관측을 바탕으로 폭과 경로를 계획하고, 양방향 분할 전송·재조립·학습·집계를 수행한다. 현재 엣지 변경은 경유 종점 변경이며 모델·optimizer 상태를 다른 서버로 옮기는 기능은 아니다. 기기에는 일반 소켓 권한을 사용하고 운영팀 보유 VM·브리지에만 집행 권한을 둔다. OS-Ken/OVS 실배포, 자동 정책 연결, 기기 인증·암호화는 후속이다. 앱 완료 보고는 물리 경로 또는 OpenFlow 설치 확인과 구분한다.

## 5 LoRA 기반 분할 연합학습의 실제 실행

{fig_md(5)}

Qwen2.5-0.5B 모델 앞 2층을 기기에 두고 rank 16 LoRA를 학습했다. 세 논리 기기는 B1·B2·B3의 서로 다른 사실을 가지고 VM과 HPC 사이에서 activation·labels 및 gradient를 주고받았다. 라운드 끝에 앞단 어댑터를 평균하는 실행과, 기기별 뒷단 어댑터까지 따로 학습한 후 앞·뒷단을 모두 평균하는 대조 실행이 있다. 뒤의 실행은 16라운드, 기록된 라운드 시간 합 588.8초다.

이는 **모델 층 분할을 이용한 분할 연합학습 SFL**의 기능 검증이다. 같은 샘플의 특징이 기관별로 나뉜 수직 연합학습 VFL과는 정의가 다르다. [SplitLoRA](https://arxiv.org/abs/2407.00952), [VFL 용어](https://arxiv.org/abs/2211.12814)

{fig_md(6)}

| 모델 | B1 | B2 | B3 | 총 정답 |
|---|---|---|---|---|
{fed}

저장된 엄격 판정을 적용했다. 원 키워드 판정에서 단독 모델의 B2 1문항은 숫자만 우연히 맞아 오답으로 정정되어 있다. 18개 문항은 학습 사실의 새로운 문형이며 대규모 일반화 평가가 아니다. 도메인 간 간섭과 B1 성능 저하도 남아 있다. 원문 문답의 통신 수치는 학습 코퍼스 내용으로, 별도의 실제 회선 수치로 인용하지 않는다.

activation과 토큰 labels가 서버로 전달되며, 가짜 비밀을 심은 카나리아 3문항은 연합 모델에서도 노출됐다. 프라이버시 보장을 주장하지 않는다. CNN 폭·경로 최적화와 LoRA 실행은 구현 트랙이 다르므로, 두 기능의 동시 자동 제어까지 실증했다고 표현하지 않는다.

## 6 실제 자원 제약과 모델 분할의 효과

{fig_md(7)}

VM CPU의 동일 프로파일 조건에서 7B 로컬 LoRA는 OOM을 기록했고 front는 6.44GB RSS로 실행됐다. 그림은 front 단독 비용이므로 서버 자원과 통신을 포함한 전체 비용 절감률이 아니다. 별도 7B 실회선 분할 학습 10스텝은 기기 RSS 약 7.94GB에서 실행됐고, 처음·마지막 2스텝 평균 손실은 2.01→0.55였다. 이는 짧은 학습 갱신의 성립을 뒷받침한다.

분할로 줄인 기기 부담은 서버 계산과 반복 통신으로 옮겨진다. 이 점이 기기 측 제어와 네트워크 측 제어를 함께 모델링해야 하는 직접적인 이유다.

## 7 생각의 연결과 확정 범위

{fig_md(8)}

초기 폭 제어 → 공유 병목·경로 모델링 → 실제 분할 전송 → KOREN 결합 실험으로 시스템을 연결했다. 별도로 LoRA 분할 연합학습과 Jetson 프로파일이 학습 기능 및 실제 기기 자원의 근거를 보탰다. 폭 고정 실험은 네트워크 효과를 분리하는 방법이며 전체 시스템의 결합 목표를 폐기하는 결정이 아니다.

후속 기울기 순서 제어는 실측값 주입 대표 조건에서 시간 모형 9.97%, 로컬 TCP 9.91%의 구간 단축을 보였고 회선 계수 0.1배에서는 1.60%였다. 전체 학습 시간 절반을 이후 계산으로 놓은 가정에 의존하며 새 KOREN·Jetson 현장 학습 결과가 아니다. [재현 보고서](../02_실험/실측주입_재현실험_2026-09-23.md)

## 제출용 결론

AwareNet은 기기의 모델 폭과 네트워크 경로를 공통 시간 모형으로 결합한 분할 연합학습 시스템이다. 실제 KOREN 구간에서 기존 결합 시스템을 실행하고, Jetson 보드의 계산 특성을 측정했으며, KOREN VM과 HPC 사이의 LoRA 기반 모델 분할·연합 집계를 확인했다. 모델링, 양방향 전송 구현, 실제 장비 측정, 학습 기능 검증을 연결한 시스템 구현이 이번 과제의 기여다. 동일 정확도까지의 시간, 실제 SDN 집행, LoRA와 동적 네트워크 제어의 통합은 남은 검증 범위다.

## 원근거와 재생성

- [이번 보고서 입력과 해시](../../configs/measurements/final_report_evidence_2026-09-26.json)
- [원 실험 기록](../02_실험/데이터_기록_2026-09-07.md)
- [연합 분할 LoRA 사전등록과 결과](../02_실험/실험_연합분할LoRA_문답증명_사전등록_2026-09-13.md)
- [대형 모델 분할 LoRA 사전등록과 결과](../02_실험/실험_대형모델_분할LoRA_사전등록_2026-09-13.md)
- [9/26 추가 후보 판정과 한계](기여_판정과_최종정리_2026-09-26.md)
- [LoRA 원논문](https://arxiv.org/abs/2106.09685)
- [재생성 스크립트](../../scripts/analysis/build_final_visual_report.py): `python scripts/analysis/build_final_visual_report.py --refresh-evidence --render`

원본 `out/` 자료가 없는 환경에서는 정규화된 입력 JSON을 사용해 `--refresh-evidence` 없이 그림과 보고서를 재생성한다. 원 로그를 다시 읽고 싶을 때만 이 옵션을 사용한다. 새로운 성능 실험을 실행하지 않는다.
'''
    DOC.write_text(md,encoding='utf-8')
    gallery=''.join(f'<section id="{f.stem}"><h2>{i+1:02d} {f.title}</h2><p>{f.subtitle}</p><a href="figures/{f.stem}.svg"><img src="figures/{f.stem}.png" alt="{f.title}" loading="lazy"></a><p class="note">{f.footer}</p><a href="figures/{f.stem}.png" download>PNG 다운로드</a> <span> / </span><a href="figures/{f.stem}.svg" download>SVG 다운로드</a></section>' for i,f in enumerate(ff))
    page=f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AwareNet 종합 보고 이미지</title><style>
    *{{box-sizing:border-box}}body{{margin:0;background:#f4f7fa;color:#152439;font-family:"Malgun Gothic",sans-serif;line-height:1.7}}main{{max-width:1160px;margin:auto;padding:64px 28px}}h1{{font-size:42px;letter-spacing:-1.5px;margin:12px 0}}h2{{font-size:24px;letter-spacing:-.6px}}header p{{max-width:840px;font-size:18px}}.tag{{color:#007f78;font-weight:700;letter-spacing:2px;font-size:13px}}section{{background:white;padding:28px;margin:32px 0;border:1px solid #dce4ec;border-radius:16px}}img{{width:100%;height:auto}}a{{color:#007f78;text-decoration:none;font-weight:600}}.note{{color:#52647b;font-size:14px}}nav{{display:flex;gap:24px;flex-wrap:wrap}}footer{{margin-top:40px;color:#52647b;font-size:14px}}</style><main><header><div class="tag">AWARENET  /  KOREN  /  2026.09.26</div><h1>폭과 네트워크를 연결한<br>분할 연합학습 시스템</h1><p>두 제어 변수를 공통 시간 모형으로 연결하고, 실제 회선과 장비에서 구현을 검증했습니다. 모델링·시스템·KOREN 성과·LoRA 학습을 잇는 발표용 이미지 9종입니다.</p><nav><a href="AwareNet_종합보고서.pdf">종합 보고서 PDF</a><a href="AwareNet_이미지팩.zip">이미지 전체 다운로드</a><a href="../../docs/01_제출발표/AwareNet_통합보고서_2026-09-26.md">설명과 원근거</a></nav></header>{gallery}<footer>기존 실험을 재정리한 자료입니다. 실망 학습, 장비 프로파일, 실측값 주입 재현의 범위를 각 그림에 표시했습니다. SVG는 편집 가능한 벡터, PNG는 바로 삽입할 수 있는 고해상도 이미지입니다.</footer></main></html>'''
    (OUT/'index.html').write_text(page,encoding='utf-8')


def main():
    ap=argparse.ArgumentParser(__doc__)
    ap.add_argument('--refresh-evidence',action='store_true')
    ap.add_argument('--render',action='store_true')
    args=ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    for p in (OUT,FIG,QA):p.mkdir(parents=True,exist_ok=True)
    data=collect() if args.refresh_evidence else read(str(MANIFEST.relative_to(ROOT)))
    ff=figures(data)
    for f in ff:f.save()
    build_pdf(data,ff)
    write_texts(data,ff)
    if args.render:
        dep=Path('C:/Users/DISLAB/.cache/codex-runtimes/codex-primary-runtime/dependencies')
        poppler=dep/'native/poppler/Library/bin/pdftoppm.exe'
        for f in ff:
            subprocess.run([str(poppler),'-png','-singlefile','-scale-to','2400',str(QA/(f.stem+'.pdf')),str(FIG/f.stem)],check=True,capture_output=True)
        subprocess.run([str(poppler),'-png','-r','130',str(OUT/'AwareNet_종합보고서.pdf'),str(QA/'page')],check=True,capture_output=True)
    (FIG/'README.md').write_text('''# AwareNet 발표용 이미지

PNG는 2400픽셀의 삽입용 이미지, SVG는 편집 가능한 벡터입니다.
폭은 보라색, 네트워크는 청록색, 시스템은 파란색으로 일관되게 표시했습니다.
각 이미지의 조건과 하단 범위 문구를 함께 사용하세요.
장비 사진은 docs/photo/HW2_Jetson_Orin_Nano.jpg에 보존된 원본입니다.
데이터 출처와 수치는 configs/measurements/final_report_evidence_2026-09-26.json에 있습니다.
''',encoding='utf-8')
    with zipfile.ZipFile(OUT/'AwareNet_이미지팩.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(FIG.iterdir()):z.write(p,'figures/'+p.name)
        z.write(MANIFEST,'final_report_evidence_2026-09-26.json')
    print(json.dumps({'figures':len(ff),'pdf':str(OUT/'AwareNet_종합보고서.pdf'),'source_records':len(data['sources']),
                      'koren_means':[(r['condition'],round(r['uniform']['mean_s'],2),round(r['widthpath']['mean_s'],2)) for r in data['koren_system']]},ensure_ascii=False))


if __name__=='__main__':main()
