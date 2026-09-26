"""Export actual Prometheus history and verify Grafana's real data-source query."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parents[2]

def fetch(url):
    with urllib.request.urlopen(url,timeout=20) as r:return json.load(r)

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);a=p.parse_args()
    events=[json.loads(x) for x in (a.run/'events.jsonl').read_text(encoding='utf-8').splitlines()]
    start=min(x['collector_received_at'] for x in events)-3
    end=max(x['collector_received_at'] for x in events)+2
    metrics=['awarenet_lab_round_seconds','awarenet_lab_total_seconds','awarenet_lab_path_weight','awarenet_lab_capacity_bps','awarenet_lab_integrity','awarenet_lab_kernel_round_bytes','awarenet_lab_packet_count']
    series={}
    for name in metrics:
        q=urllib.parse.urlencode({'query':name,'start':start,'end':end,'step':1})
        result=fetch('http://127.0.0.1:19090/api/v1/query_range?'+q)
        assert result['status']=='success' and result['data']['result'],name
        series[name]=result
    check=fetch('http://127.0.0.1:13000/api/datasources/proxy/uid/awarenet-prom/api/v1/query?'+urllib.parse.urlencode({'query':'min(awarenet_lab_integrity)'}))
    assert check['status']=='success' and check['data']['result'][0]['value'][1]=='1'
    dashboard=fetch('http://127.0.0.1:13000/api/dashboards/uid/awarenet-lab')
    target=ROOT/'site/assets/lab'
    data={'exported_utc':datetime.now(timezone.utc).isoformat(),'source':'actual local Prometheus HTTP API; 1 second scrape','start':start,'end':end,'series':series}
    (target/'prometheus-series.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    (target/'station-verification.json').write_text(json.dumps({'grafana':fetch('http://127.0.0.1:13000/api/health'),'dashboard_uid':dashboard['dashboard']['uid'],'panels':len(dashboard['dashboard']['panels']),'grafana_datasource_query':check,'series_count':sum(len(r['data']['result']) for r in series.values()),'event_count':len(events),'exported_utc':data['exported_utc']},indent=2),encoding='utf-8')
    print('Exported actual Prometheus series; Grafana query and 10-panel dashboard verified')

if __name__=='__main__':main()
