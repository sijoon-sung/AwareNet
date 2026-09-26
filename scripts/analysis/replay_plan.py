# -*- coding: utf-8 -*-
"""계획기 재생 — 실행 로그(jsonl)의 라운드별 계측을 인지층에 다시 먹여 그 라운드의 계획 결정을 재현하고, 결합 최적화의 걸음(이득·가격)을 찍는다.
    python scripts/analysis/replay_plan.py out/wp_scen32_traffic_s1_bothmp_widthpath.jsonl 9 11     # 9~11 라운드 앞의 결정을 재생
실행 인자(.args.json)·프로파일(.profile.json 의 cpu/bytes/access)을 그대로 쓴다. 결정이 로그와 같으면(교차검증) 안쪽 숫자를 믿을 수 있다."""
import io, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "sfl"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import plan as planmod  # noqa: E402
import sense  # noqa: E402


def main():
    log = sys.argv[1]; r0 = int(sys.argv[2]); r1 = int(sys.argv[3]) if len(sys.argv) > 3 else r0
    base = log.replace(".jsonl", "")
    a = json.load(io.open(base + ".args.json", encoding="utf-8"))
    pf = json.load(io.open(base + ".profile.json", encoding="utf-8"))
    W = [json.loads(l) for l in io.open(log, encoding="utf-8") if '"round"' in l]
    ids = sorted(W[0]["plan"], key=lambda s: int(s[1:]))
    static = {str(i + 1): float(m) * 1e6 for i, m in enumerate(a["paths"].split(","))}
    S = sense.Sensor(ids)
    for k in ids:
        S.set_probe(k, pf["cpu"][k], pf["bytes"][k], None)
        acc = pf["access_mbps"][k]
        S.set_access(k, [x * 1e6 for x in acc] if isinstance(acc, list) else acc * 1e6)
    S.set_paths(static)
    sets_of = lambda r: {k: tuple(str(r["paths"][k]).split("+")) for k in ids}
    lad = tuple(float(x) for x in a["ladder"].split(","))
    orig = planmod.opt_widths

    def traced(eval_sets, prof, caps, ladder, lam_b, p_min=0.5, resid=None, deadline_b=None):
        w, steps, tmax = orig(eval_sets, prof, caps, ladder, lam_b, p_min, resid, deadline_b)
        n = len(eval_sets)
        for g, wv, gain in steps:
            print(f"      걸음: {len(g)}대 → 폭 {wv}  max 이득 {gain:.2f}s/배치  가격 λ_b·Δw/N = {lam_b:.2f}×{0.25 * len(g):.2f}/{n} = {lam_b * 0.25 * len(g) / n:.2f}")
        if not steps:
            print(f"      걸음 없음 (max {tmax:.2f}s/배치)")
        return w, steps, tmax
    planmod.opt_widths = traced
    raise_ok, ref = {}, sets_of(W[0])
    last_caps = None
    for r in range(len(W)):
        if r0 <= r <= r1:
            prev = W[r - 1]
            caps = S.caps_effective(static)
            net_changed = last_caps is not None and any(abs(caps[e] - last_caps.get(e, caps[e])) > 0.05 * static[e] for e in caps)
            resid = planmod.residual(S.profile(), caps, S.observed())
            print(f"== R{r} 앞의 결정  경로 용량(관측) {{{', '.join(f'{e}:{caps[e] / 1e6:.0f}M' for e in sorted(caps))}}}")
            rs = sorted(resid.items(), key=lambda kv: kv[1])
            print(f"   잔차(초/배치) 최소 {rs[:2]} 최대 {rs[-2:]}")
            state = {"sets": sets_of(prev), "widths": dict(prev["plan"]), "observed": S.observed(), "raise_ok": raise_ok, "ref_sets": ref}
            res = planmod.plan(S.profile(), state, caps, ladder=lad, alpha=a["alpha"], max_moves=a["max_moves"], multipath=a["multipath"],
                               remaining=a["rounds"] - r, switch_cost=a["switch_cost"], batches=a["batches"], p_min=min(lad),
                               deadline_mode=a["deadline"], deadline_s=a["deadline_s"], lam=a["lam"], hold_widths=net_changed)
            raise_ok = res["raise_ok"]
            from collections import Counter
            print(f"   재생: {res['why'][:80]}  폭 {dict(Counter(res['widths'].values()))}")
            print(f"   로그: 폭 {dict(Counter(W[r]['plan'].values()))}  경로 바뀐 기기 {[k for k in ids if W[r]['paths'][k] != prev['paths'][k]]}")
        row = W[r]
        last_caps = dict(S.caps_effective(static))
        S.observe(row["per_client_detail"], a["batches"], dict(row["plan"]), sets_of(row))
        if r >= r1:
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
