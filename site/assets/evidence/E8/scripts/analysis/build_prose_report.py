"""Render the intermediate-report prose structure from its Markdown source.

No experiment is run. A4 and Korean 15/13-point typography follow the retained
intermediate draft. PDF and HTML share content; Markdown remains editable.
"""
from pathlib import Path
import hashlib
import html
import json
import re
import subprocess
import sys
import copy
import os
from revised_report_figures import native_figures as build_figures

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle, Image
from reportlab.graphics.shapes import Drawing, Line, String
from reportlab.graphics import renderPDF
from PIL import Image as PILImage

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'docs/01_제출발표/AwareNet_서술형보고서_2026-09-26.md'
OUT = ROOT / 'output/prose_awarenet'
QA = ROOT / 'tmp/pdfs/prose_awarenet_revised'
RUNTIME = Path('C:/Users/DISLAB/.cache/codex-runtimes/codex-primary-runtime/dependencies')
F = 'Human Myeongjo'
pdfmetrics.registerFont(TTFont(F, 'C:/Windows/Fonts/H2MJSM.TTF'))
pdfmetrics.registerFont(TTFont('Malgun', 'C:/Windows/Fonts/malgun.ttf'))
pdfmetrics.registerFontFamily(F, normal=F, bold=F, italic=F, boldItalic=F)
W, H = A4
LEFT, RIGHT, TOP, BOTTOM = 16*72/25.4, 16*72/25.4, 18*72/25.4, 20*72/25.4
WIDTH = W-LEFT-RIGHT
STYLES = {
    'body': ParagraphStyle('body', fontName=F, fontSize=13, leading=21.0,
                           wordWrap='CJK', firstLineIndent=13, spaceAfter=11),
    'h1': ParagraphStyle('h1', fontName=F, fontSize=15, leading=24, spaceAfter=18),
    'h2': ParagraphStyle('h2', fontName=F, fontSize=13, leading=21, spaceAfter=13),
    'h3': ParagraphStyle('h3', fontName=F, fontSize=13, leading=21, spaceAfter=12),
    'cell': ParagraphStyle('cell', fontName=F, fontSize=13, leading=18, wordWrap='CJK'),
    'caption': ParagraphStyle('caption', fontName=F, fontSize=13, leading=19, spaceAfter=10),
    'toc': ParagraphStyle('toc', fontName=F, fontSize=13, leading=18, spaceAfter=1),
}


def markup(s):
    s = html.escape(s)
    s = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', s)
    s = s.replace('ᵢ', '<sub>i</sub>').replace('⁻⁴','<super>-4</super>')
    # Hangul typeface has Greek glyphs; superscripts are real layout, not missing characters.
    s = re.sub(r'https://[^\s]+', lambda m: '<link href="'+m[0]+'" color="#000000">'+m[0]+'</link>', s)
    return s


def equation(kind):
    """Typeset the measured-time model and the two implemented decision costs."""
    d = Drawing(WIDTH, 58)
    fn='Times-Roman'; fs=15
    def t(x,y,s,size=fs,font=fn):
        d.add(String(x,y,s,fontName=font,fontSize=size))
    def v(x,y,s,sub='i',sup=None):
        t(x,y,s); t(x+pdfmetrics.stringWidth(s,fn,fs),y-4,sub,10)
        if sup: t(x+pdfmetrics.stringWidth(s,fn,fs)+6,y+8,sup,10,'Malgun')
    if kind == 'time':
        v(16,22,'t');t(27,22,'(');v(33,22,'w');t(50,22,', S) =');v(91,22,'c');v(108,22,'w',sup='γᵢ'.replace('ᵢ','i'))
        t(136,22,'+');t(173,34,'8');v(185,34,'b');v(202,34,'w');d.add(Line(161,28,233,28,strokeWidth=.7));v(173,9,'R');t(189,9,'(S)')
        t(244,22,'+');t(263,22,'ε',font='Malgun');t(272,18,'i',10);t(WIDTH-25,22,'(1)',12)
    elif kind == 'path':
        v(16,23,'J',sub='P');t(31,23,'(S | w) = max');t(107,9,'i',10);v(120,23,'t')
        t(146,23,'+');t(174,35,'1');d.add(Line(168,28,191,28,strokeWidth=.7));t(174,10,'N')
        t(201,23,'Σ',font='Malgun');t(206,8,'i',10);v(228,23,'t');t(WIDTH-25,23,'(2)',12)
    elif kind == 'width':
        v(16,23,'J',sub='W');t(35,23,'(w | S*) = max');t(119,9,'i',10);t(137,23,'B');v(152,23,'t')
        t(167,23,'(');v(173,23,'w');t(190,23,', S*) +')
        t(246,35,'λ',font='Malgun');d.add(Line(240,28,264,28,strokeWidth=.7));t(246,10,'N')
        t(275,23,'Σ',font='Malgun');t(280,8,'i',10);t(301,23,'(1 -');v(333,23,'w');t(351,23,')');t(WIDTH-25,23,'(3)',12)
    else:
        raise ValueError(f'Unknown equation {kind}')
    return d


def parse(s):
    pages=[]
    chunks=re.split(r'<!-- page: (\w+) -->',s)
    pairs=[('cover',chunks[0])]+[(chunks[i],chunks[i+1]) for i in range(1,len(chunks),2)]
    for kind,body in pairs:
        blocks=[]
        for b in re.split(r'\n\s*\n',body.strip()):
            b=b.strip()
            if b.startswith('<!-- auto-contents'): blocks.append(('contents',''))
            elif b.startswith('<!-- equation:'): blocks.append(('equation',re.search(r'equation: (\w+)',b)[1]))
            elif b.startswith('#'):
                m=re.match(r'(#+) (.*)',b);blocks.append(('h'+str(len(m[1])),m[2]))
            elif b.startswith('!['):
                m=re.match(r'!\[(.*?)\]\((.*?)\)',b);blocks.append(('image',(m[1],m[2])))
            elif b.startswith('|'):
                rows=[list(map(str.strip,l.strip('|').split('|'))) for l in b.splitlines()]
                blocks.append(('table',[rows[0],*rows[2:]]))
            elif re.match(r'^표 \d+\.',b): blocks.append(('caption',b))
            else: blocks.append(('body',b.replace('\n',' ')))
        pages.append((kind,blocks))
    return pages


def make_toc(pages):
    entries=[]; visuals=[]
    first_main=next(i for i,(kind,_) in enumerate(pages,1) if kind=='main')
    for pi,(kind,bs) in enumerate(pages,1):
        if kind not in ('main','summary'): continue
        no=pi-first_main+1 if kind=='main' else f'요약 {pi-1}'
        for typ,data in bs:
            if typ in ('h1','h2') and kind=='main': entries.append((typ,data,no))
            if typ=='image': visuals.append((data[0],no))
            if typ=='caption': visuals.append((data,no))
    return entries,visuals


def story(pages):
    entries,visuals=make_toc(pages)
    figures=build_figures()
    allflow=[]
    for kind,bs in pages:
        fs=[]
        for typ,data in bs:
            if typ=='contents':
                for level,text,page in entries:
                    p=Paragraph(('　' if level=='h2' else '')+markup(text),STYLES['toc'])
                    fs.append(('toc',(p,page)))
                fs.append(('gap',4))
                fs.append(('flow',Paragraph('그림 및 표 목차',STYLES['h2'])))
                for text,page in visuals:
                    fs.append(('toc',(Paragraph(markup(text),STYLES['toc']),page)))
            elif typ=='image':
                p=(SOURCE.parent/data[1]).resolve()
                if p.stem in figures:
                    im=copy.deepcopy(figures[p.stem].d);ratio=WIDTH/im.width
                    im.scale(ratio,ratio);im.width*=ratio;im.height*=ratio
                else:
                    iw,ih=PILImage.open(p).size;im=Image(str(p),width=WIDTH,height=WIDTH*ih/iw)
                fs.append(('flow',im));fs.append(('gap',7));fs.append(('flow',Paragraph(markup(data[0]),STYLES['caption'])))
            elif typ=='equation': fs.append(('flow',equation(data)))
            elif typ=='table':
                widths=[WIDTH*.33]+[WIDTH*.67/(len(data[0])-1)]*(len(data[0])-1)
                if data[0][0] in ('검증 축','구성 요소'):widths=[WIDTH*.23,WIDTH*.28,WIDTH*.49]
                if data[0][0]=='구분':widths=[WIDTH*.23,WIDTH*.385,WIDTH*.385]
                if data[0][0]=='항목':widths=[WIDTH*.3,WIDTH*.7]
                cells=[[Paragraph(markup(x),STYLES['cell']) for x in row] for row in data]
                tb=Table(cells,colWidths=widths)
                tb.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.5,colors.HexColor('#D9D9D9')),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#F2F2F2')),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
                if data[0][0]=='구분':
                    tb.setStyle(TableStyle([('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
                fs.append(('flow',tb));fs.append(('gap',14))
            else:
                st=STYLES[typ]
                if kind=='cover':
                    st=ParagraphStyle('cover'+typ,parent=st,alignment=1,firstLineIndent=0,spaceAfter=28)
                fs.append(('flow',Paragraph(markup(data),st)))
        allflow.append((kind,fs))
    return allflow


def render_pdf(pages):
    path=OUT/'AwareNet_서술형보고서.pdf'
    c=canvas.Canvas(str(path),pagesize=A4)
    c.setTitle('AwareNet: 분할 연합학습을 위한 폭·경로 적응형 스케줄러')
    c.setAuthor('AwareNet')
    heights=[]
    first_main=next(i for i,(kind,_) in enumerate(pages,1) if kind=='main')
    for pi,(kind,fs) in enumerate(story(pages),1):
        y=H-TOP-(25 if kind=='cover' else 0)
        start=y
        for typ,obj in fs:
            if typ=='gap': y-=obj;continue
            if typ=='toc':
                p,no=obj; _,h=p.wrap(WIDTH-32,H); y-=h
                if y<BOTTOM: raise ValueError(f'TOC page {pi} overflows')
                p.drawOn(c,LEFT,y);c.setFont(F,13);c.drawRightString(W- RIGHT,y+2,str(no));y-=p.style.spaceAfter;continue
            _,h=obj.wrap(WIDTH,H)
            y-=h
            if y<BOTTOM: raise ValueError(f'Page {pi} overflows by {BOTTOM-y:.1f}pt; used {start-y:.1f}')
            obj.drawOn(c,LEFT,y)
            y-=getattr(getattr(obj,'style',None),'spaceAfter',0)
        heights.append({'pdf_page':pi,'section':kind,'used_pt':round(start-y,1),'remaining_pt':round(y-BOTTOM,1)})
        if kind!='cover':
            c.setFont(F,10)
            c.drawCentredString(W/2,29, f'- {pi-first_main+1} -' if kind=='main' else ('요약문 '+str(pi-1) if kind=='summary' else '목차'))
        for typ,data in pages[pi-1][1]:
            if typ=='h1' and kind=='main':c.bookmarkPage(f'p{pi}');c.addOutlineEntry(data,f'p{pi}',0)
        c.showPage()
    c.save()
    return heights


def write_html(pages):
    entries,visuals=make_toc(pages)
    parts=['<!doctype html><html lang="ko"><meta charset="utf-8"><title>AwareNet 서술형 보고서</title><style>@font-face{font-family:Human;src:local("휴먼명조"),local("HY신명조")}@page{size:A4;margin:18mm 16mm 20mm}body{font-family:Human,"휴먼명조",Batang,serif;font-size:13pt;line-height:1.615;color:#000;background:#e9e9e9;margin:0}section{box-sizing:border-box;background:white;width:210mm;min-height:297mm;padding:18mm 16mm 20mm;margin:12px auto;break-after:page}h1{font-size:15pt;margin:0 0 18pt}h2,h3{font-size:13pt;margin:0 0 13pt}p{text-indent:1em;margin:0 0 11pt}img{width:100%}table{border-collapse:collapse;width:100%;margin-bottom:14pt}td,th{border:.5pt solid #d9d9d9;padding:8pt 7pt;font-weight:normal}th{background:#f2f2f2}.cover{text-align:center}.cover p{text-indent:0;margin-bottom:28pt}.caption{text-indent:0}.toc{display:flex;justify-content:space-between;margin-bottom:7pt}.equation{text-align:center;font-family:Cambria,"Times New Roman",serif;margin:12pt 0 18pt;font-size:15pt}a{color:#000;overflow-wrap:anywhere}.refs p{overflow-wrap:anywhere}@media print{body{background:white}section{padding:0;margin:0;width:auto;min-height:0}}</style>']
    for i,(kind,bs) in enumerate(pages,1):
        parts.append(f'<section class="{kind}">')
        for typ,data in bs:
            if typ=='contents':
                for level,label,p in entries:parts.append(f'<div class="toc"><span>{html.escape(label)}</span><span>{p}</span></div>')
                parts.append('<h2>그림 및 표 목차</h2>')
                for label,p in visuals:parts.append(f'<div class="toc"><span>{html.escape(label)}</span><span>{p}</span></div>')
            elif typ=='image':
                src=os.path.relpath((SOURCE.parent/data[1]).resolve(),OUT).replace('\\','/')
                parts.append(f'<img src="{src}" alt="{data[0]}"><p class="caption">{data[0]}</p>')
            elif typ=='table':parts.append('<table>'+''.join('<tr>'+''.join(f'<{("th" if j==0 else "td")}>{html.escape(x)}</{("th" if j==0 else "td")}>' for x in row)+'</tr>' for j,row in enumerate(data))+'</table>')
            elif typ=='equation':
                eq={
                    'time':'t<sub>i</sub>(w<sub>i</sub>,S) ≈ c<sub>i</sub>w<sub>i</sub><sup>γ<sub>i</sub></sup> + 8b<sub>i</sub>w<sub>i</sub>/R<sub>i</sub>(S) + ε<sub>i</sub>　(1)',
                    'path':'J<sub>P</sub>(S | w) = max<sub>i</sub> t<sub>i</sub> + (1/N)Σ<sub>i</sub>t<sub>i</sub>　(2)',
                    'width':'J<sub>W</sub>(w | S*) = max<sub>i</sub> Bt<sub>i</sub>(w<sub>i</sub>,S*) + (λ/N)Σ<sub>i</sub>(1-w<sub>i</sub>)　(3)',
                }[data]
                parts.append('<div class="equation">'+eq+'</div>')
            elif typ.startswith('h'):parts.append(f'<{typ}>{html.escape(data)}</{typ}>')
            else:parts.append('<p'+(' class="caption"' if typ=='caption' else '')+'>'+markup(data).replace('<super>','<sup>').replace('</super>','</sup>').replace('<link ','<a ').replace('</link>','</a>')+'</p>')
        parts.append('</section>')
    parts.append('</html>');(OUT/'AwareNet_서술형보고서.html').write_text('\n'.join(parts),encoding='utf-8')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    OUT.mkdir(parents=True,exist_ok=True);QA.mkdir(parents=True,exist_ok=True)
    pages=parse(SOURCE.read_text(encoding='utf-8'))
    heights=render_pdf(pages);write_html(pages)
    manifest={'pages':heights,'summary_pages':sum(k=='summary' for k,_ in pages),'main_pages':sum(k=='main' for k,_ in pages),'font':'HY신명조 H2MJSM.TTF (휴먼명조 미설치로 PDF 대체; HTML은 휴먼명조 지정)','heading_pt':15,'body_pt':13,'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'visual_qa':'pending'}
    evidence=json.loads((ROOT/'configs/measurements/final_report_evidence_2026-09-26.json').read_text(encoding='utf-8'))
    sources=evidence['sources']
    manifest['evidence_sources_checked']=len(sources)
    manifest['source_hashes_match']=all(hashlib.sha256((ROOT/s['path']).read_bytes()).hexdigest()==s['sha256'] for s in sources)
    if not manifest['source_hashes_match']:raise ValueError('A measurement source differs from its evidence manifest')
    publication=json.loads((ROOT/'configs/measurements/publication_evidence_2026-09-27.json').read_text(encoding='utf-8'))
    manifest['publication_sources_checked']=sum(len(g['files']) for g in publication['groups'])
    manifest['publication_hashes_match']=all(hashlib.sha256((ROOT/'site/assets/evidence'/r['public_path']).read_bytes()).hexdigest()==r['sha256'] for g in publication['groups'] for r in g['files'])
    if not manifest['publication_hashes_match']:raise ValueError('Publication evidence hash mismatch')
    manifest['figures']=sum(typ=='image' for _,bs in pages for typ,_ in bs)
    manifest['tables']=sum(typ=='table' for _,bs in pages for typ,_ in bs)
    revised=json.loads((ROOT/'configs/measurements/report_metrics_revised.json').read_text(encoding='utf-8'))
    manifest['revised_sources_checked']=len(revised['sources'])
    manifest['revised_hashes_match']=all(hashlib.sha256((ROOT/s['path']).read_bytes()).hexdigest()==s['sha256'] for s in revised['sources'])
    if not manifest['revised_hashes_match']:raise ValueError('Revised result source hash mismatch')
    manifest['diagram_sources']='figures/revised_sources.json'
    manifest['new_experiments_run']=False
    manifest['includes_completed_virtual_lab']='부록. 통합 계측 가상 실험' in SOURCE.read_text(encoding='utf-8')
    if manifest['includes_completed_virtual_lab']:
        lab=ROOT/'site/assets/lab/manifest.json'
        ledger=json.loads(lab.read_text(encoding='utf-8'))
        manifest['virtual_lab_manifest']='site/assets/lab/manifest.json'
        manifest['virtual_lab_sources_checked']=len(ledger['files'])
        manifest['virtual_lab_hashes_match']=all(hashlib.sha256((lab.parent/x['path']).read_bytes()).hexdigest()==x['sha256'] for x in ledger['files'])
        if not manifest['virtual_lab_hashes_match']:raise ValueError('A virtual lab artifact differs from its manifest')
    (OUT/'verification.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False,indent=2))
    if '--render' in sys.argv:
        subprocess.run([str(RUNTIME/'native/poppler/Library/bin/pdftoppm.exe'),'-scale-to','1400','-png',str(OUT/'AwareNet_서술형보고서.pdf'),str(QA/'page')],check=True)


if __name__=='__main__':main()
