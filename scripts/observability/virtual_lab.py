"""Isolated Linux namespace experiment using AwareNet's actual byte transport.

No training or KOREN measurement occurs here. Namespaces, tc, TCP, and packet
capture are real; clients and workloads are synthetic inside one Linux VM.
Run as root in a disposable VM: python virtual_lab.py study --output /root/run.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import socket
import statistics
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2] if Path(__file__).parent.name=='observability' else Path(__file__).parent
sys.path.insert(0, str(ROOT/'sfl'))
from mpsend import ChunkLinks, ChunkServer

NS = ['awn-client', 'awn-edge1', 'awn-edge2', 'awn-server']
PORT = 20500
ENDPOINTS = [('10.80.31.2', PORT, None), ('10.80.32.2', PORT, None)]
CLIENTS = 8
PAYLOAD = 128 << 10
CHUNK = 4 << 10  # Deliberate lab override; production default floor is 64KiB.


def run(args, *, ns=None, check=True):
    command = (['ip', 'netns', 'exec', ns] if ns else [])+list(map(str,args))
    p = subprocess.run(command, text=True, capture_output=True)
    if check and p.returncode:
        raise RuntimeError(f'{command}: {p.stderr[-1000:]}')
    return p


def emit(folder, event, **fields):
    item = {'event':event, 'timestamp':time.time(), **fields}
    with (folder/'events.jsonl').open('a', encoding='utf-8') as out:
        out.write(json.dumps(item, ensure_ascii=False)+'\n')
    return item


def payload(cid, size=PAYLOAD):
    return hashlib.shake_256(f'awarenet-lab-fixed-seed-20260926:{cid}'.encode()).digest(size)


def cleanup():
    # Scope is the four exact, exclusively owned lab namespaces.
    for ns in reversed(NS):
        run(['ip','netns','delete',ns], check=False)


def setup():
    existing = run(['ip','netns','list']).stdout
    if any(ns in existing.split() for ns in NS):
        raise RuntimeError('Lab namespace exists; refusing to alter an existing run')
    for ns in NS:
        run(['ip','netns','add',ns])
        run(['ip','link','set','lo','up'],ns=ns)
    links = [
        ('awn-client','c1','10.80.11.2/30','awn-edge1','ec','10.80.11.1/30'),
        ('awn-client','c2','10.80.12.2/30','awn-edge2','ec','10.80.12.1/30'),
        ('awn-edge1','es','10.80.31.1/30','awn-server','s1','10.80.31.2/30'),
        ('awn-edge2','es','10.80.32.1/30','awn-server','s2','10.80.32.2/30')]
    for i,(na,ia,aa,nb,ib,ab) in enumerate(links):
        a,b=f'awnv{i}a',f'awnv{i}b'
        run(['ip','link','add',a,'type','veth','peer','name',b])
        for dev,ns,name,address in [(a,na,ia,aa),(b,nb,ib,ab)]:
            run(['ip','link','set',dev,'netns',ns])
            run(['ip','link','set',dev,'name',name],ns=ns)
            run(['ip','addr','add',address,'dev',name],ns=ns)
            run(['ip','link','set',name,'up'],ns=ns)
            run(['ethtool','-K',name,'tso','off','gso','off','gro','off'],ns=ns,check=False)
    for i in [1,2]:
        run(['sysctl','-w','net.ipv4.ip_forward=1'],ns=f'awn-edge{i}')
        run(['ip','route','add',f'10.80.3{i}.0/30','via',f'10.80.1{i}.1','dev',f'c{i}'],ns='awn-client')
        run(['ip','route','add',f'10.80.1{i}.0/30','via',f'10.80.3{i}.1','dev',f's{i}'],ns='awn-server')
        run(['tc','qdisc','add','dev','es','root','handle','1:','htb','default','10'],ns=f'awn-edge{i}')
        run(['tc','class','add','dev','es','parent','1:','classid','1:10','htb','rate','2mbit','ceil','2mbit'],ns=f'awn-edge{i}')
        run(['tc','qdisc','add','dev','es','parent','1:10','handle','10:','netem','delay','10ms','limit','512'],ns=f'awn-edge{i}')


def shape(folder, condition, policy, round_no):
    cap1 = 500000 if condition=='edge_drop' and round_no>=2 else 2000000
    for i,cap in [(1,cap1),(2,2000000)]:
        cmd=['tc','class','change','dev','es','parent','1:','classid','1:10','htb','rate',f'{cap}bit','ceil',f'{cap}bit']
        run(cmd, ns=f'awn-edge{i}')
        emit(folder,'kernel_apply',condition=condition,policy=policy,round=round_no,path=f'e{i}',capacity_bps=cap,command=cmd)
    return [cap1,2000000]


def shared_limit(enable):
    ns='awn-server'
    for dev in ['s1','s2']:
        run(['tc','qdisc','del','dev',dev,'ingress'],ns=ns,check=False)
    run(['ip','link','del','awnifb'],ns=ns,check=False)
    if enable:
        run(['ip','link','add','awnifb','type','ifb'],ns=ns)
        run(['ip','link','set','awnifb','up'],ns=ns)
        run(['tc','qdisc','add','dev','awnifb','root','handle','2:','htb','default','10'],ns=ns)
        run(['tc','class','add','dev','awnifb','parent','2:','classid','2:10','htb','rate','2mbit','ceil','2mbit'],ns=ns)
        for dev in ['s1','s2']:
            run(['tc','qdisc','add','dev',dev,'handle','ffff:','ingress'],ns=ns)
            run(['tc','filter','add','dev',dev,'parent','ffff:','protocol','ip','u32','match','u32','0','0','action','mirred','egress','redirect','dev','awnifb'],ns=ns)


def snapshot():
    result={}
    for ns in NS:
        result[ns]={'routes':json.loads(run(['ip','-j','route'],ns=ns).stdout),
                    'addresses':json.loads(run(['ip','-j','addr'],ns=ns).stdout)}
    for i in [1,2]:
        ns=f'awn-edge{i}'
        result[ns]['classes']=json.loads(run(['tc','-s','-j','class','show','dev','es'],ns=ns).stdout)
        result[ns]['qdiscs']=json.loads(run(['tc','-s','-j','qdisc','show','dev','es'],ns=ns).stdout)
    result['awn-server']['shared_qdisc']=json.loads(run(['tc','-s','-j','qdisc','show','dev','awnifb'],ns='awn-server',check=False).stdout or '[]')
    return result


def class_bytes(classes):
    # iproute2 7 nests counters under stats; older JSON emitted top-level fields.
    return sum(item.get('stats',item).get('bytes',0) for item in classes)


def receive_server(folder):
    server=ChunkServer('0.0.0.0',PORT);server.verbose=False;server.start()
    while not (folder/'stop-server').exists():
        with server.lock:
            tids=[tid for tid,ev in server.done.items() if ev.is_set()]
        for tid in tids:
            blob=server.wait(tid,timeout=2)
            cid=tid.split('|')[0]
            digest=hashlib.sha256(blob).digest()
            server.send_back(cid,digest,tid+'|hash',wait=True)
        time.sleep(.002)
    server.close()


def transfer(link, data, tid, cid, weights=None):
    start=time.perf_counter()
    info=link.send(data,tid,cid=cid,chunk_size=CHUNK,weights=weights,wait_ack=True)
    digest=link.wait(tid+'|hash',timeout=30)
    match=digest==hashlib.sha256(data).digest()
    if not match:
        raise RuntimeError('End-to-end digest mismatch')
    return {'seconds':time.perf_counter()-start,'bytes':len(data),'hash_match':match,'per':info['per']}


def client_study(folder):
    results=[]
    policies=['single','fixed_dual','adaptive_dual']
    for condition in ['edge_drop','shared_access']:
        shared_limit(condition=='shared_access')
        rounds=4 if condition=='edge_drop' else 2
        for policy in policies:
            links=[]
            probes=[]
            try:
                for i in range(CLIENTS):
                    eps=ENDPOINTS[:1] if policy=='single' else ENDPOINTS
                    links.append(ChunkLinks('unused',PORT,[None]*len(eps),endpoints=eps))
                probes=[ChunkLinks('unused',PORT,[None],endpoints=[ep]) for ep in ENDPOINTS]
                for round_no in range(1,rounds+1):
                    caps=shape(folder,condition,policy,round_no)
                    before=snapshot()
                    decision_start=time.perf_counter()
                    def probe(j):
                        cid=f'{condition}-{policy}-probe{j}'
                        return transfer(probes[j],payload('probe',128<<10),f'{cid}|r{round_no}',cid)
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        observed=list(pool.map(probe,range(2)))
                    rates=[x['bytes']*8/x['seconds'] for x in observed]
                    weights=([1] if policy=='single' else rates if policy=='adaptive_dual' else [1,1])
                    decision_seconds=time.perf_counter()-decision_start
                    emit(folder,'plan',condition=condition,policy=policy,round=round_no,
                         measured_bps=rates,weights=weights,probe_seconds=decision_seconds,width=1.0)
                    gate=threading.Barrier(CLIENTS)
                    def send(i):
                        cid=f'{condition}-{policy}-c{i}'
                        gate.wait(timeout=30)
                        return transfer(links[i],payload(i),f'{cid}|r{round_no}',cid,weights)
                    started=time.perf_counter()
                    with ThreadPoolExecutor(max_workers=CLIENTS) as pool:
                        client_results=list(pool.map(send,range(CLIENTS)))
                    elapsed=time.perf_counter()-started
                    after=snapshot()
                    kernel_bytes=[class_bytes(after[f'awn-edge{i}']['classes'])-
                                  class_bytes(before[f'awn-edge{i}']['classes']) for i in [1,2]]
                    entry=emit(folder,'round_complete',condition=condition,policy=policy,round=round_no,
                               payload_bytes=CLIENTS*PAYLOAD,width=1.0,network_seconds=elapsed,
                               probe_seconds=decision_seconds,total_seconds=elapsed+decision_seconds,
                               measured_bps=rates,weights=weights,capacity_bps=caps,kernel_bytes_delta=kernel_bytes,
                               clients=client_results,all_hashes_match=all(x['hash_match'] for x in client_results))
                    results.append(entry)
                    (folder/f'kernel-{condition}-{policy}-r{round_no}.json').write_text(json.dumps({'before':before,'after':after},indent=2))
                    time.sleep(.2)
            finally:
                for link in links+probes:link.close()
    (folder/'rounds.json').write_text(json.dumps(results,indent=2))


def post_event(host, event):
    req=urllib.request.Request(host+'/api/events',data=json.dumps(event).encode(),headers={'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(req,timeout=8) as res:res.read()


def packet_analysis(folder):
    pcap=folder/'capture.pcapng'
    fields=['frame.time_epoch','ip.src','ip.dst','tcp.srcport','tcp.dstport','tcp.stream','tcp.len','tcp.analysis.ack_rtt','tcp.analysis.retransmission','tcp.analysis.fast_retransmission','tcp.flags.syn','tcp.flags.ack','awarenet.tid','awarenet.cid','awarenet.seq','awarenet.offset','awarenet.bytes','awarenet.fin','awarenet.ack']
    cmd=['tshark','-X','lua_script:'+str(ROOT/'observability/wireshark/awarenet.lua'),'-r',str(pcap),'-Y',f'tcp.port == {PORT}','-T','fields','-E','header=y','-E','separator=,','-E','quote=d','-E','occurrence=f']
    for field in fields:cmd+=['-e',field]
    p=run(cmd)
    (folder/'packets.csv').write_text(p.stdout)
    import csv,io
    rows=list(csv.DictReader(io.StringIO(p.stdout)))
    output={}
    for i,address in enumerate(['10.80.31.2','10.80.32.2'],1):
        rr=[x for x in rows if x['ip.src']==address or x['ip.dst']==address]
        ack=[float(x['tcp.analysis.ack_rtt'])*1000 for x in rr if x['tcp.analysis.ack_rtt']]
        output[f'e{i}']={'packets':len(rr),'tcp_payload_bytes':sum(int(x['tcp.len'] or 0) for x in rr),
                         'retransmission_flags':sum(bool(x['tcp.analysis.retransmission'] or x['tcp.analysis.fast_retransmission']) for x in rr),
                         'ack_rtt_median_ms':statistics.median(ack) if ack else None,
                         'ack_rtt_p95_ms':sorted(ack)[min(len(ack)-1,int(.95*len(ack)))] if ack else None}
    result={'packets':len(rows),'streams':len({x['tcp.stream'] for x in rows}),
            'dissected_application_rows':sum(bool(x['awarenet.tid']) for x in rows),
            'paths':output,'capture_point':'awn-client any; only TCP port 20500',
            'rtt_definition':'Wireshark TCP ACK RTT; not end-to-end tensor latency',
            'retransmission_definition':'Wireshark analysis flags; not an independently measured packet-loss rate'}
    (folder/'packets.json').write_text(json.dumps(result,indent=2))
    return result


def study(folder, host):
    folder.mkdir(parents=True,exist_ok=False)
    if os.geteuid()!=0:raise RuntimeError('Run in a disposable Linux VM as root')
    setup()
    (folder/'environment.json').write_text(json.dumps({'uname':run(['uname','-a']).stdout.strip(),
        'python':sys.version,'tc':run(['tc','-V']).stdout.strip(),'tshark':run(['tshark','--version']).stdout.splitlines()[0],
        'clients':CLIENTS,'payload_per_client':PAYLOAD,'chunk_bytes':CHUNK,'model_width':1.0,
        'new_training':False,'new_koren_measurement':False,'clock':time.time(),'offload':{
            ns:run(['ethtool','-k','c1' if ns=='awn-client' else 's1'],ns=ns).stdout for ns in ['awn-client','awn-server']}},indent=2))
    server_log=(folder/'server.log').open('w')
    capture_log=(folder/'capture.log').open('w')
    server=subprocess.Popen(['ip','netns','exec','awn-server',sys.executable,__file__,'server','--output',str(folder)],stdout=server_log,stderr=subprocess.STDOUT)
    capture=subprocess.Popen(['ip','netns','exec','awn-client','tshark','-i','any','-f',f'tcp port {PORT}','-w',str(folder/'capture.pcapng')],stdout=capture_log,stderr=subprocess.STDOUT)
    time.sleep(2)
    client=subprocess.Popen(['ip','netns','exec','awn-client',sys.executable,__file__,'client','--output',str(folder)],stdout=(folder/'client.log').open('w'),stderr=subprocess.STDOUT)
    offset=0
    def forward_events():
        nonlocal offset
        events=folder/'events.jsonl'
        if events.exists():
            with events.open(encoding='utf-8') as src:
                src.seek(offset)
                while line:=src.readline():
                    event=json.loads(line)
                    if host:post_event(host,event)
                offset=src.tell()
    try:
        while client.poll() is None:
            forward_events()
            time.sleep(.4)
        forward_events()
        if client.returncode:raise RuntimeError((folder/'client.log').read_text()[-4000:])
    finally:
        (folder/'stop-server').touch()
        try:server.wait(timeout=10)
        except subprocess.TimeoutExpired:server.terminate();server.wait(timeout=5)
        capture.send_signal(2)
        capture.wait(timeout=15)
        server_log.close();capture_log.close()
        cleanup()
    packets=packet_analysis(folder)
    if host:post_event(host,{'event':'packet_summary','timestamp':time.time(),**packets})
    if host:
        import tarfile
        archive=folder.parent/'lab-results.tar.gz'
        with tarfile.open(archive,'w:gz') as out:out.add(folder,arcname='run')
        req=urllib.request.Request(host+'/api/upload',data=archive.read_bytes(),headers={'Content-Type':'application/gzip'},method='POST')
        with urllib.request.urlopen(req,timeout=120) as res:res.read()
    print(json.dumps({'status':'complete','output':str(folder),'packets':packets['packets']}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['study','client','server'])
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--collector',default='')
    a=parser.parse_args()
    {'study':lambda:study(a.output,a.collector),'client':lambda:client_study(a.output),'server':lambda:receive_server(a.output)}[a.mode]()
