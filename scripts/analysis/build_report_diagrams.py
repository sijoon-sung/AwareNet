"""Export paper-style vector figures and their evidence-linked gallery."""
import hashlib
import html
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from reportlab.graphics import renderPDF, renderSVG
from paper_diagrams import build_figures, ROOT, OUT


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    fs=build_figures();out=OUT/'figures';out.mkdir(parents=True,exist_ok=True)
    qa=ROOT/'tmp/pdfs/prose_awarenet_figures';qa.mkdir(parents=True,exist_ok=True)
    poppler=Path('C:/Users/DISLAB/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe')
    for stem,f in fs.items():
        svg_path=out/(stem+'.svg')
        renderSVG.drawToFile(f.d,str(svg_path))
        svg=svg_path.read_text(encoding='utf-8')
        svg=svg.replace('font-family: Diagram Malgun Bold;', 'font-family: Malgun Gothic, 맑은 고딕, sans-serif; font-weight: 700;')
        svg=svg.replace('font-family: Diagram Malgun;', 'font-family: Malgun Gothic, 맑은 고딕, sans-serif;')
        svg=svg.replace('<title>...</title>', '<title>'+html.escape(f.title)+'</title>')
        svg=svg.replace('<desc>...</desc>', '<desc>'+html.escape(f.subtitle+' / '+f.footer)+'</desc>')
        svg_path.write_text(svg,encoding='utf-8')
        renderPDF.drawToFile(f.d,str(qa/(stem+'.pdf')))
        subprocess.run([str(poppler),'-scale-to-x','2400','-scale-to-y','-1','-singlefile','-png',str(qa/(stem+'.pdf')),str(out/stem)],check=True,capture_output=True)
    evidence=['configs/measurements/final_report_evidence_2026-09-26.json','scripts/exp/conditions.json','scripts/exp/run_scen32.sh','scripts/exp/scenario_perturb.sh','docs/02_실험/실험환경_VM_HPC.md','sfl/sdn/README.md','sfl/experiments/run_fed_split_lora.py','configs/measurements/network_implementation_audit_2026-09-26.json','sfl/net/real_rig.sh','sfl/net/hairpin_lo.sh']
    manifest={'purpose':'paper-style architecture and experiment figures; no new experiment','style':'sparse labels, captions outside, vector geometry','sources':[{'path':p,'sha256':hashlib.sha256((ROOT/p).read_bytes()).hexdigest()} for p in evidence],'generators':[{'path':p,'sha256':hashlib.sha256((ROOT/p).read_bytes()).hexdigest()} for p in ['scripts/analysis/paper_diagrams.py','scripts/analysis/build_report_diagrams.py']],'figures':[{'stem':s,'title':f.title,'caption':f.subtitle,'scope_note':f.footer,'width':1400,'height':f.h} for s,f in fs.items()]}
    (out/'sources.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    items=[]
    for s,f in fs.items():items.append(f'<article><h2>{html.escape(f.title)}</h2><img src="figures/{s}.svg"><p>{html.escape(f.subtitle)}</p><p class="note">{html.escape(f.footer)}</p><p><a href="figures/{s}.svg">SVG 편집용</a> · <a href="figures/{s}.png">PNG 삽입용</a></p></article>')
    (OUT/'figures.html').write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><title>AwareNet 구조와 실험 그림</title><style>body{background:#f1f4f7;color:#182c40;font-family:"Malgun Gothic",sans-serif;margin:40px auto;max-width:1100px}article{background:white;padding:28px;margin:25px 0;border:1px solid #cdd7e0;border-radius:12px}img{width:100%}h1{font-size:30px}h2{font-size:22px}p{line-height:1.7}a{color:#007d76}</style><h1>AwareNet 구조와 실험 그림</h1><p>논문용 벡터 도식 9종. 그림에는 짧은 표기만 두고 조건과 적용 범위는 캡션으로 옮겼습니다. 실측값과 해석 범위는 기존 보고서를 따릅니다.</p>'+''.join(items)+'</html>',encoding='utf-8')
    with zipfile.ZipFile(OUT/'AwareNet_구조도_조건그림.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.iterdir()):
            if p.suffix in ['.png','.svg','.json']:z.write(p,'figures/'+p.name)
        z.write(OUT/'figures.html','figures.html')
    print(json.dumps({'figures':len(fs),'formats':['SVG','PNG'],'zip':str(OUT/'AwareNet_구조도_조건그림.zip')},ensure_ascii=False))

if __name__=='__main__':main()
