# -*- coding: utf-8 -*-
"""N=8 반복 실험 — 토큰 효과가 잡음을 넘는지 확인.

  1차 실험에서 N=1(경합 없음)의 토큰 차이가 -6.5%로 나왔다. 경합이 없는데 차이가 났으므로
  **그것이 곧 잡음 바닥**이다. N=8의 -11.3%는 잡음의 2배에 못 미쳐 단일 실행으로는 못 믿는다.
  → 같은 조건을 3회씩 반복해 평균·범위를 낸다.

  사전 등록: 토큰 on 의 벽시계 평균이 off 평균보다 낮고, **두 조건의 범위가 겹치지 않아야**
             효과 인정. 겹치면 "TCP 공정 공유로 충분" 판정.
"""
import io, json, os, statistics as st, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
from run_multi import BW_MBIT, RTT_MS, P, CUT, BATCHES, BS, OUT, ROOT, PY, tc

N, REPS = 8, 3

def run(tokens, rep, port):
    tag = f"rep{rep}_tok{tokens}"
    slog = os.path.join(OUT, f"rep_srv_{tag}.jsonl")
    env = dict(os.environ, PYTHONPATH=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    srv = subprocess.Popen([PY, os.path.join(ROOT,"sfl","server.py"), "--port", str(port),
        "--clients", str(N), "--tokens", str(tokens), "--device","cuda","--log",slog], env=env)
    time.sleep(6)
    t0 = time.perf_counter(); ps=[]
    for i in range(N):
        ps.append(subprocess.Popen([PY, os.path.join(ROOT,"sfl","client.py"),
            "--server", f"127.0.0.1:{port}", "--id", f"c{i}", "--p", str(P), "--cut", str(CUT),
            "--batches", str(BATCHES), "--batch-size", str(BS),
            "--log", os.path.join(OUT, f"rep_cli_{tag}_c{i}.jsonl")], env=env))
    for x in ps: x.wait(timeout=900)
    wall = time.perf_counter()-t0
    srv.wait(timeout=120)
    tot=0; per=[]
    for i in range(N):
        rs=[json.loads(l) for l in io.open(os.path.join(OUT,f"rep_cli_{tag}_c{i}.jsonl"),encoding="utf-8")]
        b=[r for r in rs if "up_B" in r]
        tot += sum(r["up_B"]+r["down_B"] for r in b)
        per.append(sum(r["t_up"]+r["t_wait"] for r in b)/len(b))
    return {"tokens":tokens,"rep":rep,"wall":wall,"goodput":tot*8/1e6/wall,
            "fairness":max(per)/min(per)}

def main():
    tc(f"qdisc replace dev lo root netem delay {RTT_MS/2}ms rate {BW_MBIT}mbit limit 4000")
    rows=[]; port=29900
    try:
        for rep in range(REPS):
            for tokens in (0,2):
                port+=1
                r=run(tokens,rep,port); rows.append(r)
                print(f"rep{rep} tok={tokens}  벽시계 {r['wall']:6.1f}s  "
                      f"굿풋 {r['goodput']:5.1f}Mbps  공평비 {r['fairness']:.2f}", flush=True)
    finally:
        tc("qdisc del dev lo root")
    io.open(os.path.join(OUT,"multi_rep_results.json"),"w",encoding="utf-8").write(json.dumps(rows,indent=1))
    print(f"\n판정 (N={N}, {REPS}회 반복)")
    for k in ("wall","goodput","fairness"):
        a=[r[k] for r in rows if r["tokens"]==0]; b=[r[k] for r in rows if r["tokens"]==2]
        print(f"  {k:9s} off {st.mean(a):7.2f} [{min(a):.2f}~{max(a):.2f}]   "
              f"on {st.mean(b):7.2f} [{min(b):.2f}~{max(b):.2f}]")
    a=[r["wall"] for r in rows if r["tokens"]==0]; b=[r["wall"] for r in rows if r["tokens"]==2]
    overlap = not (max(b) < min(a) or max(a) < min(b))
    print(f"\n  벽시계 범위 겹침: {'예 → **TCP 공정 공유로 충분** (토큰 효과 미확인)' if overlap else '아니오 → 토큰 효과 인정'}")

if __name__ == "__main__":
    main()
