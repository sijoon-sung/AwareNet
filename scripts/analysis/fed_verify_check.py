# -*- coding: utf-8 -*-
"""연합 분할 LoRA 발산 검증 — 정정된 기준으로 재계산 (사전등록 §5, 2026-09-13)
   python scripts/analysis/fed_verify_check.py v_old v_new [fed3_0913 ...]
   기준: R3 이후 어느 기기든 차례 끝 5스텝 평균 손실(losses) > 1.0 → 발산. 최대 손실(loss_max)은 참고."""
import io, json, os, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
for tag in sys.argv[1:]:
    f = os.path.join("out", "fed_split", f"server_{tag}.jsonl")
    if not os.path.exists(f):
        print(f"{tag}: 기록 없음 ({f})"); continue
    rows = [json.loads(l) for l in io.open(f, encoding="utf-8") if l.strip()]
    print(f"== {tag}: {len(rows)} 라운드")
    for r in rows:
        tail = r["losses"]; mx = r.get("loss_max", {})
        flag = " ← 발산" if r["round"] >= 3 and max(tail.values()) > 1.0 else ""
        print(f"  R{r['round']:2d} 차례끝 " + " ".join(f"{k}:{v:.4f}" for k, v in tail.items())
              + (" | 최대 " + " ".join(f"{k}:{v:.2f}" for k, v in mx.items()) if mx else "") + flag)
    late = [(max(r["losses"].values()), r["round"]) for r in rows if r["round"] >= 3]
    worst = max(late) if late else (float("nan"), None)
    first = next((r["round"] for r in rows if r["round"] >= 3 and max(r["losses"].values()) > 1.0), None)
    verdict = f"발산 (처음 R{first})" if first else "안정"
    print(f"결과 {tag}: R3 이후 차례끝 손실 최대 {worst[0]:.4f} (R{worst[1]}) → {verdict}")
