"""Export a final-file snapshot without history, other branches, or credentials.

This creates local files only. It never changes repository visibility or pushes.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[2]
ALLOWED={'sfl','scripts','tests','docs','configs','site','observability','.github'}
EXCLUDE_PARTS={'old','references','private','__pycache__','node_modules','.git','.venv','tmp','archive_local'}
SECRET_PATTERNS=[re.compile(rb'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----'),
                 re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}'),re.compile(rb'github_pat_[A-Za-z0-9_]{40,}'),
                 re.compile(rb'AKIA[0-9A-Z]{16}')]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--destination',type=Path,default=ROOT/'tmp/public-release/awarenet-final')
    a=parser.parse_args();destination=a.destination.resolve()
    if not destination.is_relative_to((ROOT/'tmp/public-release').resolve()):raise ValueError('Release destination must stay inside tmp/public-release')
    destination.mkdir(parents=True,exist_ok=False)
    listed=subprocess.check_output(['git','ls-files','-co','--exclude-standard','-z'],cwd=ROOT).decode('utf-8').split('\0')
    selected=set()
    for name in set(listed):
        if not name:continue
        p=Path(name)
        if p.parts[:2] == ('.github','workflows'):continue
        if p.parts[0] in ALLOWED and not any(part in EXCLUDE_PARTS for part in p.parts) and not p.name.startswith(('.env','private_')):
            if p.suffix.lower() not in {'.pem','.key','.exe','.dll','.pyc'}:selected.add(name)
        if len(p.parts)==1 and (p.name in {'README.md','.gitattributes','.gitignore','index.html','.nojekyll'} or p.name.startswith('requirements')):
            selected.add(name)
    # Reports and their exact cited measurements are intentional allowlist exceptions.
    for folder in ['output/prose_awarenet','output/final_awarenet']:
        for p in (ROOT/folder).rglob('*'):
            if p.is_file():selected.add(p.relative_to(ROOT).as_posix())
    evidence=json.loads((ROOT/'configs/measurements/final_report_evidence_2026-09-26.json').read_text(encoding='utf-8'))
    for item in evidence['sources']:
        p=(ROOT/item['path']).resolve()
        if not p.is_relative_to(ROOT):raise ValueError('Evidence path escapes source tree')
        if hashlib.sha256(p.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Evidence hash mismatch')
        selected.add(item['path'])
    publication=json.loads((ROOT/'configs/measurements/publication_evidence_2026-09-27.json').read_text(encoding='utf-8'))
    for group in publication['groups']:
        for item in group['files']:
            p=(ROOT/item['source_path']).resolve()
            if not p.is_relative_to(ROOT):raise ValueError('Evidence path escapes source tree')
            if hashlib.sha256(p.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Publication evidence hash mismatch')
            selected.add(item['source_path'])
    # Some evidence trees inherit ignore rules from historical runs. Include their
    # published copies and archives explicitly, as well as their originals above.
    for p in (ROOT/'site').rglob('*'):
        if p.is_file():selected.add(p.relative_to(ROOT).as_posix())
    selected.update({'index.html','.nojekyll'})
    files=[]
    for name in sorted(selected):
        source=ROOT/name
        if not source.is_file():continue
        if source.is_symlink():raise ValueError('Symlink requires explicit review: '+name)
        content=source.read_bytes()
        if any(pattern.search(content) for pattern in SECRET_PATTERNS):raise ValueError('Credential pattern in '+name)
        if len(content)>99*1024*1024:raise ValueError('File exceeds normal GitHub push size: '+name)
        target=destination/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
        files.append({'path':name,'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()})
    # New snapshot source evidence is intentionally force-included; ignore rules still
    # protect local future runs. Initial staging must use the release manifest.
    metadata={'created_utc':datetime.now(timezone.utc).isoformat(),'source_branch':'awarenet',
              'source_base_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'includes_working_tree_changes':True,'git_history_included':False,'other_branches_included':False,
              'credential_pattern_scan':'passed; private keys and common tokens; no guarantee for arbitrary secrets',
              'files':files}
    (destination/'PUBLIC_RELEASE.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    archive=ROOT/'output/AwareNet_공개용_최종판.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in destination.rglob('*'):
            if p.is_file():z.write(p,p.relative_to(destination).as_posix())
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    info={'destination':str(destination),'archive':str(archive),'file_count':len(files),'archive_bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'published':False}
    (ROOT/'output/public_release_status.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(info,ensure_ascii=True))

if __name__=='__main__':main()
