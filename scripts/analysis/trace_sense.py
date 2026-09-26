# -*- coding: utf-8 -*-
"""라운드별 인지 추적 — 로그를 인지층에 다시 먹여 엣지마다 관측 처리량/기대/비율/가장 느린 기기/추정을 찍는다.
    python scripts/analysis/trace_sense.py out/wp_..._widthpath.jsonl 9 20   (같은 이름의 .args.json/.profile.json 필요)"""
import io, json, sys
sys.path.insert(0, "sfl")
import sense
log = sys.argv[1]; r0, r1 = int(sys.argv[2]), int(sys.argv[3])
base = log.replace(".jsonl", ""); a = json.load(io.open(base + ".args.json")); pf = json.load(io.open(base + ".profile.json"))
W = [json.loads(l) for l in io.open(log) if '"round"' in l]
ids = sorted(W[0]["plan"], key=lambda s: int(s[1:]))
static = {str(i + 1): float(m) * 1e6 for i, m in enumerate(a["paths"].split(","))}
S = sense.Sensor(ids)
for k in ids:
    S.set_probe(k, pf["cpu"][k], pf["bytes"][k], None); S.set_access(k, [x * 1e6 for x in pf["access_mbps"][k]])
S.set_paths(static)
orig = S.observe
for r in range(r1 + 1):
    row = W[r]; sets = {k: tuple(str(row["paths"][k]).split("+")) for k in ids}
    S.observe(row["per_client_detail"], a["batches"], dict(row["plan"]), sets)
    if r >= r0:
        # recompute per-edge thr/bound like observe does, for display
        det = row["per_client_detail"]; agg, dur, expct, tacc, who = {}, {}, {}, {}, {}
        for k, d in det.items():
            Sk = sets[k]; ex = d.get("exits") or []; acc = S.access[k]; bx = []; t_acc = 0
            for x, e in enumerate(Sk):
                b = ex[x]["up"] + ex[x]["dn"] if x < len(ex) else 0; bx.append(b); t_acc = max(t_acc, b * 8 / acc[x])
            for x, e in enumerate(Sk):
                agg[e] = agg.get(e, 0) + bx[x]; dur[e] = max(dur.get(e, 0), d["xfer"]); tacc[e] = max(tacc.get(e, 0), t_acc); expct[e] = expct.get(e, 0) + acc[x]
                if d["xfer"] >= dur[e]: who[e] = (k, "+".join(Sk))
        out = []
        for e in sorted(agg):
            thr = agg[e] * 8 / dur[e]; bound = min(static[e], expct[e], agg[e] * 8 / tacc[e])
            out.append(f"e{e}: thr {thr/1e6:.1f} bound {bound/1e6:.1f} ratio {thr/bound:.2f} slowest {who[e]} est {S.edge_est.get(e, 0)/1e6:.0f}")
        print(f"R{r} ms {row['makespan']:.0f} | " + " | ".join(out))
