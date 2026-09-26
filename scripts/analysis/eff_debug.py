# -*- coding: utf-8 -*-
"""효율 계수 디버그 — 한 라운드의 기기별 원자료(벽시계·전송·바이트·모형 속도)를 그대로 보여준다.
    python scripts/analysis/eff_debug.py r8_rho05_s1_path3 r8_rho2_s1_path3 [--round 10]"""
import argparse, io, json, os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "sfl")); sys.path.insert(0, os.path.join(ROOT, "scripts", "exp"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import plan, cond  # noqa: E402
M = 1e6

ap = argparse.ArgumentParser(); ap.add_argument("tags", nargs="+"); ap.add_argument("--round", type=int, default=10); ap.add_argument("--n", type=int, default=3)
a = ap.parse_args()
for tag in a.tags:
    c = tag.split("_s")[0]
    r_ = cond.resolve(c); caps = {str(i + 1): v * M for i, v in enumerate(r_["caps"]["v"])}; batches = r_["batches"]["v"]
    W = [json.loads(l) for l in io.open(f"out/wp_{tag}_widthpath.jsonl", encoding="utf-8") if '"round"' in l]
    prof = json.load(io.open(f"out/wp_{tag}_widthpath.profile.json", encoding="utf-8"))
    acc = {k: (v * M if not isinstance(v, list) else [x * M for x in v]) for k, v in prof["access_mbps"].items()}
    r = W[min(a.round, len(W) - 1)]
    sets = {k: tuple(str(v).split("+")) for k, v in r["paths"].items()}
    rate = plan.effective_rate(sets, caps, acc)
    print(f"== {tag} R{r['round']} makespan {r['makespan']:.2f}  paths {r['paths']}")
    print(f"   access(프로파일) {prof['access_mbps']}")
    for k in sorted(r["per_client_detail"])[: a.n]:
        d = r["per_client_detail"][k]; b = (d["up_bytes"] + d["dn_bytes"]) / batches
        print(f"   {k}: t_round {d.get('t_round', 0):.2f} xfer {d['xfer']:.2f} fwd+bwd {d['cli_fwd'] + d['cli_bwd']:.2f} wait {d['cli_wait']:.2f} "
              f"up {d['up_bytes'] / 1e6:.1f}MB dn {d['dn_bytes'] / 1e6:.1f}MB  모형속도 {rate[k] / M:.1f}M → 배치당 모형 {b * 8 / rate[k]:.2f}s vs 관측 {d['xfer'] / batches:.2f}s")
