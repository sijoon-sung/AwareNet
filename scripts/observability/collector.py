"""Loopback-only lab collector: events -> Prometheus, PCAP table, Grafana hub."""
import argparse
import csv
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import threading
import time
import urllib.request
from urllib.parse import urlparse, parse_qs

LOCK=threading.Lock()
EVENTS=[]
METRICS={}


def put(name,value,labels=None):
    if value is None:return
    label=','.join(f'{key}={json.dumps(str(v))}' for key,v in sorted((labels or {}).items()))
    METRICS[name+('{'+label+'}' if label else '')]=float(value)


def update(event):
    tags={k:event[k] for k in ['condition','policy'] if k in event}
    if event['event']=='round_complete':
        for key,suffix in [('network_seconds','round_seconds'),('total_seconds','total_seconds'),('probe_seconds','probe_seconds')]:
            put('awarenet_lab_'+suffix,event[key],tags)
        put('awarenet_lab_round',event['round'],tags)
        put('awarenet_lab_integrity',int(event['all_hashes_match']),tags)
        put('awarenet_lab_width',event['width'],tags)
        put('awarenet_lab_payload_bytes',event['payload_bytes'],tags)
        for i,rate in enumerate(event['measured_bps'],1):
            put('awarenet_lab_probe_bps',rate,{**tags,'path':f'e{i}'})
        for i,value in enumerate(event['kernel_bytes_delta'],1):
            put('awarenet_lab_kernel_round_bytes',value,{**tags,'path':f'e{i}'})
    elif event['event']=='kernel_apply':
        put('awarenet_lab_capacity_bps',event['capacity_bps'],{**tags,'path':event['path']})
    elif event['event']=='plan':
        for i,weight in enumerate(event['weights'],1):
            put('awarenet_lab_path_weight',weight/sum(event['weights']),{**tags,'path':f'e{i}'})
    elif event['event']=='packet_summary':
        for path,values in event['paths'].items():
            for field in ['packets','tcp_payload_bytes','retransmission_flags','ack_rtt_median_ms','ack_rtt_p95_ms']:
                put('awarenet_lab_'+field,values[field],{'path':path})
        put('awarenet_lab_packet_count',event['packets'])
        put('awarenet_lab_stream_count',event['streams'])
    elif event['event']=='counter_normalized':
        for i,value in enumerate(event['kernel_bytes_delta'],1):
            put('awarenet_lab_kernel_round_bytes',value,{**tags,'path':f'e{i}'})


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--serve',type=Path,required=True)
    parser.add_argument('--port',type=int,default=19108)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    saved=args.output/'events.jsonl'
    if saved.exists():
        for line in saved.read_text(encoding='utf-8').splitlines():
            event=json.loads(line);EVENTS.append(event);update(event)
    web=Path(__file__).resolve().parents[2]/'observability/web'
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def respond(self,body,kind='application/json',code=200):
            data=body if isinstance(body,bytes) else body.encode()
            self.send_response(code);self.send_header('Content-Type',kind)
            self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def do_POST(self):
            count=int(self.headers.get('Content-Length','0'))
            if count<1 or count>160*1024*1024:return self.respond('invalid size',code=413)
            if self.path=='/api/events':
                event=json.loads(self.rfile.read(count))
                if event.get('event') not in ['kernel_apply','plan','round_complete','packet_summary','counter_normalized']:
                    return self.respond('invalid event',code=400)
                event['collector_received_at']=time.time()
                with LOCK:
                    EVENTS.append(event);update(event)
                    with (args.output/'events.jsonl').open('a',encoding='utf-8') as out:out.write(json.dumps(event)+'\n')
                self.respond('{"ok":true}')
            elif self.path=='/api/upload':
                (args.output/'lab-results.tar.gz').write_bytes(self.rfile.read(count))
                self.respond('{"ok":true}')
            else:self.respond('not found',code=404)
        def do_GET(self):
            parsed=urlparse(self.path);path=parsed.path
            if path=='/metrics':
                with LOCK:body='\n'.join(f'{k} {v}' for k,v in sorted(METRICS.items()))+'\n'
                return self.respond(body,'text/plain; version=0.0.4')
            if path=='/api/events':
                with LOCK:body=json.dumps(EVENTS[-200:])
                return self.respond(body)
            if path=='/api/packets':
                p=args.output/'run/packets.csv'
                which=parse_qs(parsed.query).get('path',['all'])[0]
                rows=[]
                if p.exists():
                    with p.open(encoding='utf-8') as src:
                        for row in csv.DictReader(src):
                            if which!='all' and f'10.80.3{which[-1]}.2' not in [row.get('ip.src'),row.get('ip.dst')]:continue
                            if row.get('awarenet.tid') or row.get('tcp.analysis.retransmission'):
                                rows.append(row)
                            if len(rows)>=120:break
                return self.respond(json.dumps(rows))
            if path=='/health':return self.respond('{"status":"ok"}')
            if path.startswith('/alpine/v3.24/'):
                # VM package bootstrap through the host's functioning resolver.
                # One fixed signed-package upstream; no general proxy endpoint.
                if '..' in path.split('/') or not path.endswith(('.apk','.tar.gz')):
                    return self.respond('forbidden',code=403)
                cached=args.serve/'apk-cache'/path.removeprefix('/alpine/')
                try:
                    if not cached.exists():
                        with urllib.request.urlopen('https://dl-cdn.alpinelinux.org'+path,timeout=60) as upstream:
                            blob=upstream.read()
                        cached.parent.mkdir(parents=True,exist_ok=True);cached.write_bytes(blob)
                    return self.respond(cached.read_bytes(),'application/octet-stream')
                except Exception:return self.respond('upstream unavailable',code=502)
            if path=='/bundle.tgz':target=args.serve/'bundle.tgz'
            elif path.startswith('/artifacts/'):
                target=(args.output/'run'/path.removeprefix('/artifacts/')).resolve()
                if not target.is_relative_to((args.output/'run').resolve()):return self.respond('forbidden',code=403)
            elif path in ['/','/station','/station/']:target=web/'index.html'
            else:target=web/path.lstrip('/')
            if not target.resolve().is_relative_to(web.resolve()) and path not in ['/bundle.tgz'] and not path.startswith('/artifacts/'):
                return self.respond('forbidden',code=403)
            if not target.is_file():return self.respond('not found',code=404)
            self.respond(target.read_bytes(),mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()


if __name__=='__main__':main()
