# -*- coding: utf-8 -*-
"""실측 효율 계수 — 실행 기록에서 eff = 관측 전송시간 / 모형 전송시간 (기기·라운드별) 을 뽑아 팔·조건별로 요약한다.
3층(전규모 시뮬)의 보정값이 여기서 나온다.  python scripts/analysis/eff_from_runs.py r8_rho05 r8_rho1 r8_rho2

모형: plan.effective_rate(그 라운드 배정, 경로 용량, 프로파일 접속) 로 기기 실효율 → 배치당 모형 전송시간 = 왕복 바이트 / 실효율.
관측: per_client_detail.xfer / batches. 앞 SKIP 라운드는 제외."""
import glob, io, json, os, re, statistics as st, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "sfl")); sys.path.insert(0, os.path.join(ROOT, "scripts", "exp"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import plan, cond  # noqa: E402
SKIP = int(os.environ.get("SKIP", 6)); M = 1e6


def effs(tag, caps, batches):
    W = [json.loads(l) for l in io.open(f"out/wp_{tag}_widthpath.jsonl", encoding="utf-8") if '"round"' in l]
    prof = json.load(io.open(f"out/wp_{tag}_widthpath.profile.json", encoding="utf-8"))
    acc = {k: ([x * M for x in v] if isinstance(v, list) else v * M) for k, v in prof["access_mbps"].items()}
    out = {"single": [], "split": []}
    for r in W[SKIP:]:
        paths = r.get("paths") or {}
        sets = {k: tuple(str(v).split("+")) for k, v in paths.items()}
        if not sets:
            continue
        rate = plan.effective_rate(sets, caps, acc)
        for k, d in r["per_client_detail"].items():
            b = (d["up_bytes"] + d["dn_bytes"]) / batches
            if rate.get(k, 0) <= 0 or b <= 0:
                continue
            model = b * 8 / rate[k]
            obs = d["xfer"] / batches
            out["split" if len(sets[k]) >= 2 else "single"].append(model / max(obs, 1e-6))   # 효율 = 모형/관측 (1 이 이상)
    return out


def main():
    for c in sys.argv[1:]:
        r = cond.resolve(c); caps = {str(i + 1): v * M for i, v in enumerate(r["caps"]["v"])}; batches = r["batches"]["v"]
        for f in sorted(glob.glob(f"out/wp_{c}_s*_*_widthpath.jsonl")):
            tag = re.sub(r"^out/wp_|_widthpath\.jsonl$", "", f)
            if "_s9_" in tag:
                continue
            try:
                e = effs(tag, caps, batches)
            except (OSError, KeyError) as ex:
                print(f"  {tag}: 건너뜀 {ex}"); continue
            line = "  ".join(f"{kind} eff {st.median(v):.2f} (n={len(v)})" for kind, v in e.items() if v)
            print(f"{tag:22s} {line}")


if __name__ == "__main__":
    main()
