# -*- coding: utf-8 -*-
"""컨트롤러 재생(replay) — 기록된 라운드 관측을 그대로 먹여 **결정을 오프라인으로 재현**한다.

  왜 필요한가
    조건 4(N=8)에서 컨트롤러가 아무도 안 좁혔다. 원인이
      (a) 규칙이 돌긴 했는데 낙오자가 없다고 판단했다
      (b) comp1/C 가 안 채워져 118행에서 조기 반환됐다 (컨트롤러가 아예 안 돌았다)
    둘 중 무엇인지 실측 로그로 가른다. 망 실험을 다시 돌릴 필요가 없다.

  fed_server.py 의 호출 순서를 그대로 따른다:
      r>0 이면  decide(batches, alpha)  →  라운드 실행  →  observe_round(obs, max(comm))

    python scripts/analysis/replay_controller.py out/g2_static_s1_ours.jsonl
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "sfl"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from controller import LADDER, Controller       # noqa: E402


def load(path):
    return [json.loads(l) for l in io.open(path, encoding="utf-8") if '"round"' in l]


def replay(rows, batches, alpha=1.2, decide=None):
    """decide=None 이면 현행 규칙. 아니면 decide(ctl, batches, alpha) 를 대신 쓴다."""
    ks = sorted(rows[0]["per_client"])
    ctl = Controller(ks)
    trace = []
    for r in rows:
        if r["round"] > 0:
            plan = decide(ctl, batches, alpha) if decide else ctl.decide(batches, alpha)
        else:
            plan = dict(ctl.p)
        # 이 시점의 컨트롤러 내부 상태를 남긴다
        T = ctl.predict({k: 1.0 for k in ks}, batches) if (ctl.comp1 and ctl.C) else None
        trace.append({"round": r["round"], "plan": dict(plan),
                      "ready": bool(ctl.comp1 and ctl.C is not None),
                      "C_Mbps": (ctl.C / 1e6) if ctl.C else None,
                      "T_full": T, "actual_plan": r["plan"],
                      "makespan": r["makespan"]})
        obs = {k: tuple(v) for k, v in r["per_client"].items()}
        ctl.observe_round(obs, max(v[3] for v in obs.values()))
    return ctl, trace


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "out/g2_static_s1_ours.jsonl"
    batches = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    rows = load(path)
    ctl, trace = replay(rows, batches)
    ks = sorted(rows[0]["per_client"])
    print(f"=== 재생: {os.path.basename(path)}  (클라 {len(ks)}명, 배치 {batches}) ===\n")
    for t in trace:
        if not t["ready"]:
            print(f"R{t['round']}  컨트롤러 미가동 (comp1/C 미확보) → 전폭 유지")
            continue
        T = t["T_full"]
        lo, hi = min(T.values()), max(T.values())
        D = 1.2 * lo
        over = [k for k, v in T.items() if v > D]
        print(f"R{t['round']}  C={t['C_Mbps']:.0f}Mbps  전폭예상 {lo:.1f}~{hi:.1f}s "
              f"(퍼짐 {hi/lo:.2f}배)  마감선 D={D:.1f}s  초과 {len(over)}명 {over}")
        print(f"      재생결정 {[t['plan'][k] for k in ks]}   실제기록 {[t['actual_plan'][k] for k in ks]}")
    match = all(t["plan"] == t["actual_plan"] for t in trace)
    print(f"\n재생이 실제 기록과 {'일치한다 → 진단 유효' if match else '어긋난다 → 재생 코드 점검 필요'}")


if __name__ == "__main__":
    main()
