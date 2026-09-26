"""Start the loopback measurement station with task-local portable binaries."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tarfile
import time
import urllib.request
import urllib.error
import base64

ROOT=Path(__file__).resolve().parents[2]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run-id',default=datetime.now(timezone.utc).strftime('virtual-%Y%m%dT%H%M%SZ'))
    a=parser.parse_args()
    if not a.run_id or any(not(c.isalnum() or c in '-_') for c in a.run_id):
        raise ValueError('Invalid run id')
    runtime=ROOT/'tmp/observability'/a.run_id
    output=ROOT/'output/observability'/a.run_id
    runtime.mkdir(parents=True,exist_ok=False);output.mkdir(parents=True,exist_ok=False)
    for folder in ['grafana-data','grafana-logs','prometheus-data']:
        (runtime/folder).mkdir()
    with tarfile.open(runtime/'bundle.tgz','w:gz') as bundle:
        for relative in ['scripts/observability/virtual_lab.py','sfl/mpsend.py','sfl/chunker.py','sfl/proto.py','observability/wireshark/awarenet.lua']:
            bundle.add(ROOT/relative,arcname=relative)
    grafana=ROOT/'tmp/lab-tools/grafana/grafana-13.2.2'
    prom=ROOT/'tmp/lab-tools/prometheus/prometheus-3.15.0.windows-amd64/prometheus.exe'
    config=runtime/'grafana.ini'
    config.write_text(f'''[server]
http_addr = 127.0.0.1
http_port = 13000
[paths]
data = {(runtime/'grafana-data').as_posix()}
logs = {(runtime/'grafana-logs').as_posix()}
provisioning = {(ROOT/'observability/grafana/provisioning').as_posix()}
[auth.anonymous]
enabled = true
org_role = Viewer
[security]
allow_embedding = true
[users]
default_theme = light
[analytics]
reporting_enabled = false
check_for_updates = false
[news]
news_feed_enabled = false
[plugins]
preinstall_auto_update = false
preinstall_disabled = true
''',encoding='utf-8')
    env=os.environ.copy()
    env['GF_SECURITY_ADMIN_PASSWORD']=secrets.token_hex(24)
    env['AWN_DASHBOARD_PATH']=(ROOT/'observability/grafana').as_posix()
    commands={
        'collector':[sys.executable,str(ROOT/'scripts/observability/collector.py'),'--output',str(output),'--serve',str(runtime)],
        'prometheus':[str(prom),'--config.file='+str(ROOT/'observability/prometheus/prometheus.yml'),'--web.listen-address=127.0.0.1:19090','--storage.tsdb.path='+str(runtime/'prometheus-data'),'--storage.tsdb.retention.time=2d'],
        'grafana':[str(grafana/'bin/grafana.exe'),'server','--homepath',str(grafana),'--config',str(config)]}
    pids={}
    for name,command in commands.items():
        with (runtime/(name+'.log')).open('wb') as log:
            proc=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        pids[name]=proc.pid
    state={'run_id':a.run_id,'runtime':str(runtime),'output':str(output),'pids':pids,'url':'http://127.0.0.1:19108/station'}
    (runtime/'processes.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
    (ROOT/'tmp/observability/current.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
    print(json.dumps(state),flush=True)
    # Some Windows filesystems reject Grafana's EvalSymlinks during provisioning.
    # Load the identical dashboard through its supported HTTP API if needed.
    for attempt in range(60):
        try:
            with urllib.request.urlopen('http://127.0.0.1:13000/api/health',timeout=2) as res:res.read()
            break
        except (OSError,urllib.error.URLError):time.sleep(1)
    else:raise RuntimeError('Grafana did not become healthy; inspect task-local logs')
    try:
        with urllib.request.urlopen('http://127.0.0.1:13000/api/dashboards/uid/awarenet-lab',timeout=5) as res:res.read()
    except urllib.error.HTTPError as err:
        if err.code!=404:raise
        payload={'dashboard':json.loads((ROOT/'observability/grafana/dashboard.json').read_text(encoding='utf-8')),'overwrite':True}
        auth=base64.b64encode(('admin:'+env['GF_SECURITY_ADMIN_PASSWORD']).encode()).decode()
        req=urllib.request.Request('http://127.0.0.1:13000/api/dashboards/db',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Authorization':'Basic '+auth})
        with urllib.request.urlopen(req,timeout=20) as res:res.read()
    print('Grafana dashboard ready',flush=True)

if __name__=='__main__':main()
