"""Paper figures: sparse labels, explicit topology, captions outside the artwork.

All quantitative values come from the existing report evidence. Arrows denote
logical connections, not disjoint physical links or delegated control rights.
"""
from pathlib import Path
import json
import math

from reportlab.graphics.shapes import Drawing, Rect, Line, String, Polygon, Circle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/prose_awarenet'
FONT, BOLD = 'Diagram Malgun', 'Diagram Malgun Bold'
pdfmetrics.registerFont(TTFont(FONT, 'C:/Windows/Fonts/malgun.ttf'))
pdfmetrics.registerFont(TTFont(BOLD, 'C:/Windows/Fonts/malgunbd.ttf'))
INK, MUTED, LINE = '#202932', '#596570', '#B5BEC7'
BLUE, TEAL, PURPLE = '#356B98', '#087F83', '#8064A2'
PALE, WHITE = '#F5F7F8', '#FFFFFF'


def col(s):
    return colors.HexColor(s)


class Fig:
    def __init__(self, stem, h, title, subtitle, footer=''):
        self.stem, self.h = stem, h
        self.title, self.subtitle, self.footer = title, subtitle, footer
        self.d = Drawing(1400, h)
        self.box(0, 0, 1400, h, WHITE, None)

    def text(self, x, y, s, size=28, color=INK, bold=False, anchor='start'):
        self.d.add(String(x, self.h-y-size, s, fontName=BOLD if bold else FONT,
                          fontSize=size, fillColor=col(color), textAnchor=anchor))

    def label(self, x, y, s, size=28, color=INK, anchor='middle'):
        w = pdfmetrics.stringWidth(s, FONT, size)
        left = x-w/2 if anchor=='middle' else (x-w if anchor=='end' else x)
        self.box(left-7, y-2, w+14, size+10, WHITE, None)
        self.text(x, y, s, size, color, anchor=anchor)

    def box(self, x, y, w, h, fill=None, stroke=LINE, dashed=False, r=0, width=2):
        self.d.add(Rect(x, self.h-y-h, w, h, rx=r, ry=r,
                        fillColor=col(fill) if fill else None,
                        strokeColor=col(stroke) if stroke else None,
                        strokeWidth=width, strokeDashArray=[10, 7] if dashed else None))

    def line(self, x1, y1, x2, y2, color=LINE, width=2, dashed=False):
        self.d.add(Line(x1, self.h-y1, x2, self.h-y2, strokeColor=col(color),
                        strokeWidth=width, strokeDashArray=[9, 7] if dashed else None))

    def arrow(self, x1, y1, x2, y2, color=TEAL, dashed=False, width=3):
        self.line(x1, y1, x2, y2, color, width, dashed)
        a = math.atan2(y2-y1, x2-x1)
        pts = [x2, self.h-y2,
               x2-13*math.cos(a)+5*math.sin(a), self.h-(y2-13*math.sin(a)-5*math.cos(a)),
               x2-13*math.cos(a)-5*math.sin(a), self.h-(y2-13*math.sin(a)+5*math.cos(a))]
        self.d.add(Polygon(pts, fillColor=col(color), strokeColor=None))

    def path(self, pts, color=TEAL, dashed=False, arrow=True, width=3):
        for a, b in zip(pts[:-2], pts[1:-1]):
            self.line(*a, *b, color, width, dashed)
        if arrow:
            self.arrow(*pts[-2], *pts[-1], color, dashed, width)
        else:
            self.line(*pts[-2], *pts[-1], color, width, dashed)

    def dot(self, x, y, radius=5, fill=TEAL, stroke=None):
        self.d.add(Circle(x, self.h-y, radius, fillColor=col(fill) if fill else None,
                          strokeColor=col(stroke) if stroke else None, strokeWidth=2))

    def domain(self, x, y, w, h, title, color=INK):
        self.box(x, y, w, h, None, LINE, True, r=7)
        self.text(x+20, y+16, title, 29, color, True)

    def device(self, x, y, w=58, h=54):
        self.box(x, y, w, h, WHITE, INK, r=4, width=2.4)
        self.line(x+8, y+h-10, x+w-8, y+h-10, LINE)
        self.line(x+w/2, y+h, x+w/2, y+h+9, INK)
        self.line(x+w/2-15, y+h+9, x+w/2+15, y+h+9, INK)

    def server(self, x, y, w=120, h=112):
        self.box(x, y, w, h, WHITE, INK, r=5, width=2.5)
        for j in range(3):
            yy = y+13+j*(h-14)/3
            self.box(x+12, yy, w-24, 21, PALE, LINE, r=2)
            self.dot(x+w-25, yy+10, 3, TEAL)
        self.line(x+20, y+h+7, x+w-20, y+h+7, INK, 3)

    def model(self, x, y, width=1, n=4, color=PURPLE, layer_w=18, height=70):
        for j in range(n):
            xx = x+j*(layer_w+8)
            self.box(xx, y, layer_w, height, PALE, LINE)
            hh = height*width
            self.box(xx, y+height-hh, layer_w, hh, color, color)

    def chips(self, x, y, n=4, color=TEAL, size=19, gap=7):
        for i in range(n):
            self.box(x+i*(size+gap), y, size, size, color, color)

    def queue(self, x, y, n=4, color=TEAL):
        self.line(x, y, x+116, y, INK)
        self.line(x, y+42, x+116, y+42, INK)
        for i in range(n):
            self.box(x+9+i*25, y+9, 17, 24, color, color)


def build_figures():
    evidence = json.loads((ROOT/'configs/measurements/final_report_evidence_2026-09-26.json').read_text(encoding='utf-8'))
    audit = json.loads((ROOT/'configs/measurements/network_implementation_audit_2026-09-26.json').read_text(encoding='utf-8'))
    fs = {}

    def new(*args):
        f = Fig(*args)
        fs[f.stem] = f
        return f

    f = new('01_architecture', 820, '전체 아키텍처',
            '기기에서 모델 앞부분을 실행하고, 허용 중계 접속점을 통해 서버와 활성값·기울기를 교환한다. '
            '결합 제어기는 폭 w와 종점 배정 S를 함께 계획한다.',
            '점선 경계는 관리·위임 범위가 필요한 자원이다. 각 선은 논리 TCP 연결이며 물리 경로의 독립성을 뜻하지 않는다. '
            'OS-Ken/OVS는 별도 확장으로 학습 연동과 실제 적용 확인 전이다.')
    # One controller, three resource groups, two logical relay connections.
    f.box(460, 30, 480, 155, WHITE, INK, r=4, width=2.4)
    f.text(700, 47, '결합 제어기', 32, INK, True, 'middle')
    f.model(527, 103, .68, n=3, height=48, layer_w=15)
    f.text(690, 109, 'w  ↔  S', 34, INK, False, 'middle')
    for yy in [112, 146]:
        f.dot(783, yy, 6, TEAL); f.arrow(800, yy, 863, yy, TEAL)
    f.path([(940, 80), (1300, 80), (1300, 220), (1190, 220), (1190, 280)], MUTED, True, False, 2)
    f.arrow(1040, 80, 940, 80, MUTED, True, 2)
    f.text(1075, 39, '관측', 26, MUTED)
    f.path([(540, 185), (540, 235), (190, 235), (190, 333)], BLUE, True)
    f.text(240, 194, '폭 · 종점', 26, BLUE)
    f.domain(25, 280, 335, 405, '기기', PURPLE)
    f.domain(555, 280, 290, 405, '중계 엣지', TEAL)
    f.domain(1040, 280, 335, 405, '학습 서버', BLUE)
    for j, (label, width) in enumerate([('c1', 1), ('c2', .7), ('cn', .4)]):
        yy = 406+j*80
        f.device(57, yy+4, h=48)
        f.text(128, yy+12, label, 25)
        f.model(190, yy, width, height=54)
    f.text(190, 633, '앞부분 · w', 25, PURPLE, False, 'middle')
    f.box(72, 333, 240, 49, WHITE, BLUE, r=3)
    f.text(192, 340, '로컬 에이전트', 25, BLUE, False, 'middle')
    for yy, label in [(384, 'e1'), (544, 'e2')]:
        f.server(644, yy, 106, 78)
        f.text(608, yy+23, label, 25, TEAL, False, 'middle')
        f.line(555, yy+30, 644, yy+30, TEAL, 3)
        f.line(750, yy+30, 845, yy+30, TEAL, 3)
        f.line(555, yy+68, 644, yy+68, PURPLE, 3)
        f.line(750, yy+68, 845, yy+68, PURPLE, 3)
    f.text(700, 636, '소유 VM / 포트', 25, MUTED, False, 'middle')
    f.server(1144, 370, 125, 118)
    f.model(1147, 548, 1, n=4, color=BLUE, height=68)
    f.text(1207, 635, '뒷부분 · 집계', 25, BLUE, False, 'middle')
    # Forward and reverse buses use distinct lanes and explicit endpoints.
    for yy in [414, 574]:
        f.path([(360, 482), (443, 482), (443, yy), (555, yy)], TEAL)
        f.path([(845, yy), (953, yy), (953, 482), (1040, 482)], TEAL)
    for yy in [452, 612]:
        f.path([(1040, 517), (981, 517), (981, yy), (845, yy)], PURPLE)
        f.path([(555, yy), (417, yy), (417, 517), (360, 517)], PURPLE)
    f.chips(454, 384, n=3, size=14, gap=5)
    f.chips(454, 544, n=3, size=14, gap=5)
    f.text(454, 320, 'TCP 1', 24, MUTED)
    f.text(454, 645, 'TCP 2', 24, MUTED)
    f.text(943, 333, 'KOREN', 24, MUTED, False, 'middle')
    f.text(943, 650, 'IP 망', 24, MUTED, False, 'middle')
    f.arrow(453, 769, 518, 769, TEAL); f.text(532, 749, '활성값', 25)
    f.arrow(735, 769, 670, 769, PURPLE); f.text(749, 749, '기울기', 25)
    f.arrow(888, 769, 953, 769, BLUE, True); f.text(967, 749, '제어', 25)
    f.box(1086, 752, 58, 29, None, LINE, True)
    f.text(1159, 747, '관리 범위', 25)

    f = new('02_control_loop', 570, '폭·경로 결합 제어',
            '계측, 공유 자원을 반영한 경로 평가, 폭 선택, 실행과 관측의 순서. '
            '경로가 전송률을 바꾸고 모델 폭이 연산량과 전송 수요를 바꾼다.',
            '비용 모형에 기초한 단계적 휴리스틱이며 전역 최적해 보장은 없다.')
    xs = [40, 385, 730, 1075]
    for j, (x, label) in enumerate(zip(xs, ['계측', '경로 평가', '폭 선택', '적용'])):
        f.text(x+140, 29, f'({chr(97+j)}) {label}', 31, INK, True, 'middle')
        f.box(x, 103, 280, 253, WHITE, LINE, r=3)
    for j, v in enumerate([.35, .8, .55]):
        f.box(88+j*60, 266-v*130, 32, v*130, [MUTED, TEAL, PURPLE][j], None)
    f.line(70, 270, 283, 270, INK)
    f.text(180, 305, '시간 · 바이트', 25, MUTED, False, 'middle')
    for yy, xend in [(155, 605), (223, 605), (285, 605)]:
        f.dot(428, yy, 8, TEAL)
        f.arrow(445, yy, xend, yy, TEAL)
        f.dot(625, yy, 8, TEAL)
    f.text(525, 305, 'S → R(S)', 25, TEAL, False, 'middle')
    for j, v in enumerate([1, .7, .4]):
        f.model(766+j*72, 159, v, n=2, height=108, layer_w=17)
    f.text(870, 305, 'w → 연산·전송량', 25, PURPLE, False, 'middle')
    f.device(1110, 174, 62, 67)
    f.arrow(1184, 207, 1250, 207, TEAL)
    f.server(1270, 165, 60, 80)
    f.text(1215, 305, 'w, S', 25, BLUE, False, 'middle')
    for x in xs[:-1]:
        f.arrow(x+280, 215, x+345, 215, INK)
    f.path([(1215, 356), (1215, 453), (180, 453), (180, 356)], BLUE, True)
    f.text(700, 480, '다음 라운드', 27, BLUE, False, 'middle')

    f = new('03_tensor_sequence', 700, '분할 전송과 학습 집계',
            '같은 배치 k의 활성값을 여러 TCP 연결에 나누어 전송하고, 전체 구간의 수신 후 복원한다. '
            '반환 기울기는 배치에 대응시키며, 연합 집계는 라운드 경계에서 별도로 수행한다.',
            '개념 순서도이며 세로 길이는 측정 시간이 아니다. 전체 텐서 ACK를 사용하며 조각별 수신 ACK는 구현되지 않았다.')
    for x, name, color in [(180, '기기', PURPLE), (700, '중계', TEAL), (1220, '서버', BLUE)]:
        f.text(x, 26, name, 31, color, True, 'middle')
        f.line(x, 111, x, 645, LINE, 2, True)
    f.model(132, 111, .7, height=66)
    f.model(1172, 111, 1, color=BLUE, height=66)
    f.arrow(180, 223, 700, 223, TEAL)
    f.chips(365, 177, n=6)
    f.text(262, 241, 'ACT(k)', 27, TEAL)
    f.arrow(700, 293, 1220, 293, TEAL)
    for row in range(2):
        f.chips(884, 217+row*26, n=3, size=20)
    f.text(956, 309, '복원', 27, TEAL, False, 'middle')
    f.arrow(1220, 355, 180, 355, MUTED, True, 2)
    f.label(536, 308, '전체 텐서 ACK', 25, MUTED)
    f.arrow(1220, 446, 180, 446, PURPLE)
    f.label(700, 397, 'GRAD(k)', 28, PURPLE)
    f.line(65, 562, 1335, 562, LINE)
    f.text(72, 576, '라운드 경계', 26, MUTED)
    f.arrow(180, 638, 1160, 638, BLUE)
    f.dot(1220, 638, 32, WHITE, BLUE)
    f.text(1220, 611, 'Σ', 37, BLUE, False, 'middle')
    f.label(700, 590, '모델 / LoRA', 27, BLUE)

    f = new('04_scen32_topology', 790, '실제 실험 배치',
            '클라이언트 32개 CPU 프로세스와 V100 서버는 같은 HPC 호스트에서 실행했다. '
            'KOREN VM 2대에 각각 두 중계 포트를 두어 4개 논리 엣지를 구성했다.',
            '32는 독립 물리 기기의 수가 아니다. 선은 논리 연결을 뜻한다. '
            'CIFAR-10, cut=2, batch 32×4, 24라운드×3시드; 출구 5/2Mbps, 엣지 56Mbps×4.')
    f.text(700, 17, 'KOREN', 32, TEAL, True, 'middle')
    for x, label, ports in [(395, 'VM 1', ['e1', 'e2']), (745, 'VM 2', ['e3', 'e4'])]:
        f.domain(x, 76, 260, 262, label, TEAL)
        f.text(x+214, 94, 'tc', 24, MUTED, False, 'middle')
        f.server(x+79, 141, 102, 91)
        for dx, lab in [(64, ports[0]), (196, ports[1])]:
            f.box(x+dx-37, 265, 74, 47, WHITE, TEAL, r=3)
            f.text(x+dx, 270, lab, 27, TEAL, False, 'middle')
    f.domain(30, 430, 1340, 285, 'HPC · 동일 호스트')
    for row in range(4):
        for j in range(8):
            f.box(83+j*31, 503+row*27, 20, 18, PURPLE, PURPLE, r=2)
    f.text(210, 644, '32 CPU 프로세스', 28, PURPLE, False, 'middle')
    f.text(537, 541, 'tc', 29, INK, True, 'middle')
    f.queue(480, 586, color=PURPLE)
    f.server(1100, 502, 165, 109)
    f.text(1183, 644, 'V100 · 16GB', 28, BLUE, False, 'middle')
    f.arrow(345, 606, 467, 606, TEAL)
    f.path([(597, 606), (635, 606), (635, 392), (320, 392), (320, 207), (395, 207)], TEAL)
    f.path([(635, 392), (697, 392), (697, 207), (745, 207)], TEAL)
    f.path([(655, 247), (676, 247), (676, 367), (780, 367), (780, 606), (1085, 606)], TEAL)
    f.path([(1005, 207), (1070, 207), (1070, 367), (780, 367)], TEAL, arrow=False)
    # A small bridge distinguishes a crossing from a branch.
    f.box(689, 358, 16, 18, WHITE, None)
    f.line(697, 350, 697, 385, TEAL, 3)
    f.dot(635, 392, 5, TEAL)
    f.dot(780, 367, 5, TEAL)
    f.text(902, 556, 'ACT', 26, TEAL, False, 'middle')
    f.arrow(1228, 740, 1163, 740, PURPLE)
    f.text(1141, 721, 'GRAD 역방향', 25, PURPLE, False, 'end')
    f.text(68, 742, '출구 5 / 2Mbps', 25, MUTED)
    f.text(560, 742, '중계: 56Mbps × 4', 25, MUTED)

    f = new('05_scenarios', 850, '실험 조건',
            '선 그래프는 tc에 지정한 교란 조건이며 관측 처리량이 아니다. 정상, 트래픽 몰림, '
            '선택적 연산 지연, 용량 변동을 비교했다.',
            'R은 완료 로그 개수에 따른 교란 트리거로 실제 반영에 지연이 있을 수 있다. '
            '모델·분할점·배치·데이터 분할·반복 수를 고정했다.')
    def plot(x, y, vals, label):
        f.text(x, y, label, 30, INK, True)
        xx, yy, ww, hh = x+70, y+266, 525, 174
        f.text(x+66, y+44, 'Mbps', 24, MUTED)
        for val in [14, 35, 56]:
            py = yy-hh*(val-14)/42
            f.line(xx, py, xx+ww, py, '#DDE2E6', 1.5)
            f.text(xx-17, py-17, str(val), 24, MUTED, False, 'end')
        f.line(xx, yy, xx+ww, yy, INK)
        for n in [0, 8, 13, 20, 23]:
            xxx = xx+ww*n/23
            f.line(xxx, yy, xxx, yy+7, INK)
            f.text(xxx, yy+14, str(n), 24, MUTED, False, 'middle')
        f.text(xx+ww, yy+55, 'R', 24, MUTED, False, 'end')
        for i in range(23):
            x1, x2 = xx+ww*i/23, xx+ww*(i+1)/23
            y1, y2 = yy-hh*(vals[i]-14)/42, yy-hh*(vals[i+1]-14)/42
            f.line(x1, y1, x2, y1, TEAL, 3.5)
            f.line(x2, y1, x2, y2, TEAL, 3.5)
    plot(38, 27, [56]*24, '(a) 정상')
    plot(743, 27, [56 if r<8 or r>=20 else 14 for r in range(24)], '(b) 트래픽 몰림 · e1')
    f.text(38, 455, '(c) 연산 지연', 30, INK, True)
    for row in range(4):
        for j in range(8):
            x, y = 117+j*59, 544+row*46
            f.dot(x, y, 14, PURPLE if j==0 else WHITE, PURPLE if j==0 else LINE)
    f.dot(114, 751, 12, PURPLE)
    f.text(141, 729, '4개 × 0.15', 26, PURPLE)
    f.dot(379, 751, 12, WHITE, LINE)
    f.text(405, 729, '28개 × 1.0', 26, MUTED)
    schedule = {8:49, 9:42, 10:35, 11:28, 12:21, 13:14, 14:21, 15:28, 16:35, 17:42, 18:49, 19:56}
    val, vals = 56, []
    for r in range(24):
        val = schedule.get(r, val); vals.append(val)
    plot(743, 455, vals, '(d) 용량 변동 · e1')

    f = new('06_results', 595, 'KOREN 실험 결과',
            '기존 scen32 기록의 3시드 평균 라운드 시간. 초기 4라운드를 제외했다. '
            '기준선은 전폭·고정 배정·출구 1개, 결합은 폭·배정 변경·출구 2개 허용이다.',
            '동일 정확도 도달 시간 비교가 아니며, 출구 수 차이도 감소율에 포함된다.')
    f.box(344, 25, 37, 22, WHITE, MUTED)
    f.text(397, 16, '기준선 · 1출구', 26)
    f.box(709, 25, 37, 22, TEAL, TEAL)
    f.text(762, 16, '결합 · 2출구', 26)
    bx, span, scale = 247, 891, 120
    for n in [0, 30, 60, 90, 120]:
        x = bx+span*n/scale
        f.line(x, 92, x, 483, '#E0E5E9', 1.5)
        f.text(x, 497, str(n), 25, MUTED, False, 'middle')
    for j, row in enumerate(evidence['koren_system']):
        y = 107+j*94
        a, b = row['uniform']['mean_s'], row['widthpath']['mean_s']
        f.text(215, y+7, '연산 지연' if row['condition']=='slow' else row['label'], 28, INK, False, 'end')
        f.box(bx, y, span*a/scale, 23, WHITE, MUTED, width=2)
        f.box(bx, y+32, span*b/scale, 23, TEAL, TEAL)
        f.text(bx+span*a/scale+13, y-8, f'{a:.2f}', 25, MUTED)
        f.text(bx+span*b/scale+13, y+24, f'{b:.2f}', 25, TEAL)
        f.text(1360, y+9, f'-{row["reduction_pct"]:.1f}%', 30, TEAL, True, 'end')
    f.line(bx, 483, bx+span, 483, INK)
    f.text(700, 548, '평균 라운드 시간 (s)', 28, INK, False, 'middle')

    f = new('07_lora_workflow', 575, 'LoRA 실행 구조',
            'KOREN VM 2대의 3개 논리 클라이언트와 HPC V100 서버. 활성값과 정답 토큰을 보내고 '
            '기울기를 반환받으며 라운드 끝에 LoRA 어댑터를 집계했다.',
            'Qwen2.5-0.5B, cut 2, rank 16, 16라운드×30스텝. '
            'CNN 폭·경로 제어와 통합한 실험이 아니며, 서버는 기기별 순차 처리한다.')
    f.domain(25, 24, 405, 294, 'VM 1', PURPLE)
    f.domain(25, 344, 405, 202, 'VM 2', PURPLE)
    for yy, lab in [(115, 'c0 · B1'), (226, 'c1 · B2'), (439, 'c2 · B3')]:
        f.text(60, yy+6, lab, 26, PURPLE)
        f.model(290, yy, 1, n=3, height=53)
    f.domain(931, 24, 444, 522, 'HPC · V100', BLUE)
    f.server(1090, 111, 128, 117)
    f.model(1110, 282, 1, n=4, color=BLUE, height=67)
    f.dot(1155, 467, 35, WHITE, BLUE)
    f.text(1155, 435, 'Σ', 42, BLUE, False, 'middle')
    f.text(1058, 415, 'LoRA', 27, BLUE, False, 'end')
    f.path([(430, 154), (590, 154), (590, 225), (931, 225)], TEAL)
    f.path([(430, 464), (590, 464), (590, 225)], TEAL, arrow=False)
    f.text(708, 173, 'ACT + label', 29, TEAL, False, 'middle')
    f.path([(931, 319), (654, 319), (654, 275), (430, 275)], PURPLE)
    f.path([(654, 319), (654, 507), (430, 507)], PURPLE)
    f.text(789, 340, 'GRAD', 28, PURPLE, False, 'middle')
    f.arrow(720, 467, 1096, 467, BLUE, True)
    f.text(803, 489, '라운드 집계', 25, BLUE, False, 'middle')

    f = new('08_kernel_authority', 730, '관리 경계와 커널 집행',
            '현재 실험은 팀이 관리하는 HPC와 VM의 Linux tc를 설정한다. '
            '접속망과 KOREN 코어의 관리자 권한은 별개다. 아래의 루프백 경로 분류와 SDN 확장은 별도 구성이다.',
            'OVSDB 큐 설정과 OpenFlow 전달 규칙은 서로 다른 집행 단위다. '
            'OS-Ken 학습 연동과 실제 OVS 적용 확인, 기관 간 위임은 검증 전이다.')
    f.domain(25, 25, 407, 345, 'HPC · 관리 권한', PURPLE)
    f.domain(967, 25, 407, 345, 'VM · 관리 권한', TEAL)
    f.text(700, 42, '접속망 / KOREN', 29, MUTED, True, 'middle')
    # Network graph, intentionally outside the two managed boundaries.
    points = [(554,174), (672,118), (720,248), (846,177)]
    for a,b in [(0,1),(0,2),(1,2),(1,3),(2,3)]:
        f.line(*points[a], *points[b], LINE, 2.5)
    for p in points:
        f.dot(*p, 16, WHITE, MUTED)
    f.text(700, 297, '별도 관리자', 26, MUTED, False, 'middle')
    f.device(64, 150, 61, 62)
    f.arrow(143, 184, 219, 184, TEAL)
    f.queue(248, 162, color=PURPLE)
    f.text(306, 231, 'HTB', 26, PURPLE, False, 'middle')
    f.text(306, 280, '포트 분류', 24, MUTED, False, 'middle')
    f.arrow(432, 184, 531, 184, TEAL)
    f.arrow(867, 184, 967, 184, TEAL)
    f.queue(1004, 162)
    f.text(1064, 231, 'IFB / HTB', 26, TEAL, False, 'middle')
    f.arrow(1135, 184, 1211, 184, TEAL)
    f.server(1240, 143, 90, 88)
    f.text(1170, 299, 'tc class change', 25, TEAL, False, 'middle')
    f.line(25, 416, 1375, 416, LINE)
    f.text(40, 445, '(a) 루프백 경로 분류', 29, INK, True)
    f.queue(89, 557, color=PURPLE)
    f.arrow(222, 578, 354, 578, INK)
    f.queue(380, 557)
    f.text(147, 618, '접속 상한', 26, PURPLE, False, 'middle')
    f.text(438, 618, '공유 경로', 26, TEAL, False, 'middle')
    f.text(285, 526, 'IFB', 24, MUTED, False, 'middle')
    f.line(700, 445, 700, 683, LINE)
    f.text(753, 445, '(b) SDN 확장*', 29, INK, True)
    f.box(782, 548, 186, 63, WHITE, INK, True, r=3)
    f.text(875, 562, 'OS-Ken', 28, INK, False, 'middle')
    f.arrow(986, 579, 1154, 579, BLUE, True)
    f.text(1070, 524, 'OpenFlow', 24, BLUE, False, 'middle')
    f.box(1170, 548, 174, 63, WHITE, INK, True, r=3)
    f.text(1257, 562, 'OVS', 28, INK, False, 'middle')
    f.text(1054, 651, '* 학습 연동·적용 확인 전', 24, MUTED, False, 'middle')

    f = new('09_agent_timescales', 735, '계층별 제어와 시간 규모',
            '패킷은 커널의 설치된 규칙으로 계속 처리하고, 전송 에이전트는 조각을, '
            '계획 에이전트는 라운드 계획을 다룬다. 위 시간선의 간격은 개념 표현이며 실측 주기가 아니다.',
            '아래의 1,500바이트 직렬화 시간과 출력 중단 시 유입량은 식으로 계산한 값이다. '
            'AI 추론 시간이나 실제 큐 증가량을 측정한 결과가 아니다.')
    for yy, label, color in [(46, '커널 · 패킷', INK), (173, '전송 · 조각', TEAL), (300, '계획 · 라운드', PURPLE)]:
        f.text(30, yy+10, label, 28, color, True)
        f.line(312, yy+39, 1362, yy+39, LINE, 2)
    for x in range(328, 1350, 26):
        f.line(x, 70, x, 100, INK, 2)
    for x in range(346, 1340, 127):
        f.box(x, 193, 58, 38, TEAL, TEAL)
    for x in [346, 838, 1289]:
        f.dot(x, 339, 17, PURPLE)
    f.text(1362, 5, '시간 → (개념도)', 24, MUTED, False, 'end')
    f.line(30, 426, 1370, 426, LINE)
    f.text(32, 447, '(a) 1,500B 직렬화', 29, INK, True)
    f.text(370, 489, 'Δ = 8L/C', 25, MUTED, False, 'middle')
    packet = audit['analytic_examples']['packet_serialization']
    for yy, label, value in [(553, '1Gbps', packet[1]['serialization_us']), (629, '56Mbps', packet[0]['serialization_us'])]:
        f.text(173, yy-7, label, 26, INK, False, 'end')
        f.box(202, yy, max(12, value*1.25), 27, TEAL, TEAL)
        f.text(202+max(12, value*1.25)+16, yy-7, f'{value:g}μs' if value==12 else f'{value:.1f}μs', 25, TEAL)
    f.line(700, 447, 700, 703, LINE)
    f.text(750, 447, '(b) 출력 중단 가정', 29, INK, True)
    f.text(1060, 495, 'Q = Cτ/8', 28, MUTED, False, 'middle')
    f.text(784, 554, 'τ = 50ms', 28, INK)
    f.text(1010, 554, '0.35MB', 28, TEAL)
    f.text(1237, 554, '56Mbps', 24, MUTED)
    f.text(1010, 629, '6.25MB', 28, TEAL)
    f.text(1237, 629, '1Gbps', 24, MUTED)

    # The gallery follows the report reading order, retaining stable filenames.
    order = ['01_architecture', '02_control_loop', '03_tensor_sequence',
             '08_kernel_authority', '09_agent_timescales', '04_scen32_topology',
             '05_scenarios', '06_results', '07_lora_workflow']
    return {stem: fs[stem] for stem in order}
