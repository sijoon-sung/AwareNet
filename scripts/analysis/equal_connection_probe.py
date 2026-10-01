"""Local TCP diagnostic of the production planner with equal connection budgets.

Known synthetic compute delays and application-paced relay rates. No learning,
accuracy evaluation, tc, production framing, or KOREN traffic. This isolates
decisions and measured socket completion; it is not an end-to-end benchmark.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import random
import socket
import statistics
import struct
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sfl"))
import plan

POLICIES = ("fixed", "balanced", "path", "width", "independent", "joint")
BYTES = 4 * 1024 * 1024
LAMBDA = 2.0


def readn(s, n):
    buf = bytearray()
    while len(buf) < n:
        x = s.recv(n-len(buf))
        if not x: raise EOFError("incomplete TCP frame")
        buf.extend(x)
    return bytes(buf)


class Pacer:
    def __init__(self, rate):
        self.rate, self.next = rate, 0.
        self.lock = threading.Lock()

    def wait(self, count):
        with self.lock:
            self.next = max(self.next, time.perf_counter()) + count*8/self.rate
            deadline = self.next
        time.sleep(max(0., deadline-time.perf_counter()))


def select(prof, caps, policy):
    keys = list(prof["cpu"])
    base = {k:("1","1") for k in keys}
    state = dict(sets=base, widths={k:1. for k in keys})
    if policy == "fixed": return state
    if policy == "balanced": return dict(sets={k:("1","2") for k in keys}, widths=state["widths"])
    for _ in range(3):
        if policy == "independent":
            wstate = dict(sets=base,widths=state["widths"])
            width = plan.plan(prof,wstate,caps,max_moves=0,multipath=True,deadline_mode="opt",lam=LAMBDA)
            assignment, _ = plan.path_stage(width["widths"],prof,caps,state["sets"],max_moves=3,multipath=True)
            state = dict(sets=assignment,widths=width["widths"])
        else:
            state = plan.plan(prof,state,caps,ladder=(1.,) if policy=="path" else (.5,.75,1.),
                              max_moves=0 if policy=="width" else 3,multipath=True,deadline_mode="opt",lam=LAMBDA)
    assert all(len(v)==2 for v in state["sets"].values())
    if policy=="path": assert all(w==1 for w in state["widths"].values())
    if policy=="width": assert state["sets"]==base
    return state


def execute(prof,caps,chosen):
    relays = {p:Pacer(rate) for p,rate in caps.items()}
    received, errors, handlers = [], [], []
    listener = socket.socket()
    listener.bind(("127.0.0.1",0)); listener.listen(12); listener.settimeout(20)
    def receive(conn):
        try:
            with conn:
                path, count = struct.unpack("!BI",readn(conn,5))
                got = bytearray()
                while len(got)<count:
                    block = readn(conn,min(8192,count-len(got)))
                    relays[str(path)].wait(len(block))
                    got.extend(block)
                received.append(len(got))
                conn.sendall(hashlib.sha256(got).digest())
        except Exception as e: errors.append(repr(e))
    def accept():
        try:
            for _ in range(6):
                conn,_ = listener.accept()
                t = threading.Thread(target=receive,args=(conn,))
                t.start(); handlers.append(t)
        except Exception as e: errors.append(repr(e))
    acceptor = threading.Thread(target=accept); acceptor.start()
    conns = {(k,e):socket.create_connection(listener.getsockname(),timeout=20)
             for k in prof["cpu"] for e in range(2)}
    rates = plan.split_weights(chosen["sets"],caps,prof["access"])
    gate = threading.Barrier(7)
    def send(k,e):
        s = conns[k,e]
        try:
            width = chosen["widths"][k]
            total = int(BYTES*width)
            n0 = round(total*rates[k][0]/sum(rates[k]))
            count = n0 if e==0 else total-n0
            blob = bytes([int(k[1:])+1])*count
            expected = hashlib.sha256(blob).digest()
            p = int(chosen["sets"][k][e])
            access = Pacer(prof["access"][k][e])
            gate.wait()
            time.sleep(prof["cpu"][k]*width**1.2)
            s.sendall(struct.pack("!BI",p,count))
            for start in range(0,count,8192):
                b = blob[start:start+8192]
                access.wait(len(b)); s.sendall(b)
            assert readn(s,32)==expected
        finally: s.close()
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(send,k,e) for k,e in conns]
        t0=time.perf_counter(); gate.wait()
        for f in futures: f.result()
        elapsed=time.perf_counter()-t0
    acceptor.join()
    for h in handlers: h.join()
    listener.close()
    if errors: raise RuntimeError(errors)
    expected=sum(int(BYTES*w) for w in chosen["widths"].values())
    assert sum(received)==expected and len(received)==6
    return dict(wall_s=elapsed,bytes_received=sum(received),hash_checks=6,
                mean_width=statistics.mean(chosen["widths"].values()))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",default="out/followup_20261001/equal_connections")
    ap.add_argument("--repeats",type=int,default=3)
    a=ap.parse_args(); out=ROOT/a.out; out.mkdir(parents=True,exist_ok=True)
    if (out/"manifest.json").exists(): raise RuntimeError("Use a fresh output directory")
    scenarios = {
        "relay_congestion": dict(cpu=[.01,.01,.01],caps=[64e6,192e6],access=[800e6,800e6]),
        "compute_straggler": dict(cpu=[1.6,.01,.01],caps=[192e6,192e6],access=[800e6,800e6]),
        "access_limited": dict(cpu=[.01,.01,.01],caps=[192e6,192e6],access=[6.4e6,6.4e6]),
        "mixed": dict(cpu=[1.6,.01,.01],caps=[64e6,192e6],access=[800e6,800e6]),
    }
    manifest=dict(kind="new_local_paced_tcp_diagnostic",scenarios=scenarios,policies=POLICIES,
        lambda_s=LAMBDA,repeats=a.repeats,connections_per_client=2,clients=3,payload_bytes_full=BYTES,
        assumptions="known synthetic profiles; compute via sleep; application-paced TCP receive; fresh sockets per measurement",
        exclusions="no training, production transport, KOREN, kernel qdisc, convergence or accuracy evidence",
        primary="measured completion and retained width, all scenarios including ties or regressions",
        source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ["sfl/plan.py","scripts/analysis/equal_connection_probe.py"]})
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    rows=[]
    for name,sc in scenarios.items():
        keys=[f"c{i}" for i in range(3)]
        prof=dict(cpu=dict(zip(keys,sc["cpu"])),bytes={k:BYTES for k in keys},
                  gamma={k:1.2 for k in keys},access={k:sc["access"] for k in keys})
        caps=dict(zip(["1","2"],sc["caps"]))
        for rep in range(a.repeats):
            policies=list(POLICIES); random.Random(100+rep).shuffle(policies)
            for policy in policies:
                t0=time.perf_counter(); chosen=select(prof,caps,policy); planning=time.perf_counter()-t0
                result=execute(prof,caps,chosen)
                row=dict(scenario=name,repeat=rep,policy=policy,planning_s=planning,
                         sets=chosen["sets"],widths=chosen["widths"],**result)
                rows.append(row)
                with (out/"raw.jsonl").open("a",encoding="utf-8") as f: f.write(json.dumps(row)+"\n")
                print(json.dumps(row),flush=True)
    (out/"complete.json").write_text(json.dumps(dict(measurements=len(rows),expected=4*len(POLICIES)*a.repeats)),encoding="utf-8")


if __name__=="__main__": main()
