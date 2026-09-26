# -*- coding: utf-8 -*-
"""
validate_5g_trace.py — 5G 대역폭 트레이스의 신뢰성 검증

우리는 노드별 회선 격차를 이 트레이스로 주입한다. 즉 **실험 결과 전체가 이 데이터의
타당성 위에 서 있다.** 따라서 다음 네 가지를 재현 가능한 형태로 확인한다.

  ① 출처(provenance)  : 원본이 무엇이고 어떤 컬럼을 썼는가
  ② 재현성            : 원본에서 우리 통계(P5/P50/P95, 격차 배수)가 다시 나오는가
  ③ 서브샘플 충실도   : 100노드로 줄인 트레이스가 원분포를 보존하는가
  ④ 교차 검증         : 독립 출처(FedScale)와 중앙값이 수렴하는가

사용:
  python scripts/analysis/validate_5g_trace.py            # 원본 다운로드 후 전체 검증
  python scripts/analysis/validate_5g_trace.py --offline  # 파생 트레이스만 점검
"""
import argparse
import csv
import json
import os
import statistics as st

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DERIVED = os.path.join(REPO, "experiments", "5g_dataset_analysis",
                       "real_campus_5g_mode_b_trace.csv")
OUT = os.path.join(REPO, "out", "trace_validation.json")

# ── ① 출처 ────────────────────────────────────────────────────────────────────
SOURCE = {
    "repository": "Zenodo",
    "record_id": "13754300",
    "title": "5G Campus Network QoS Dataset for Open-Source gNB Implementations",
    "creators": ["Raffeck S. (Würzburg)", "Grøsvik S. (NTNU)", "Lange S. (NTNU)",
                 "Hoßfeld T. (Würzburg)", "Zinner T. (NTNU)", "Geißler S. (Würzburg)"],
    "published": "2024-09-12",
    "license": "CC BY 4.0",
    "file_used": "ntnu_tput_all_Throughput.csv",
    "column_used": "mbpsactual_uplink",
    "url": "https://zenodo.org/records/13754300",
    "설정": "대학 캠퍼스 테스트베드(NTNU·뷔르츠부르크), 오픈소스 gNB(SDR) 기반 5G NR",
    "주의": ("상용 이동통신사 망이 아니라 캠퍼스 테스트베드다. 본 과제의 대상인 "
             "기업 관리형 망(5G 특화망)의 대리 지표로 쓰되, 동일하다고 주장하지 않는다."),
}

# 독립 교차검증 기준(FedScale 약 50만 기기 기록에서 산출한 중앙값)
FEDSCALE_MEDIAN_MBPS = 6.07


def pct(sorted_vals, q):
    if not sorted_vals:
        return 0.0
    i = min(len(sorted_vals) - 1, max(0, int(round(q * (len(sorted_vals) - 1)))))
    return sorted_vals[i]


def describe(vals, label):
    v = sorted(vals)
    d = {
        "n": len(v), "min": round(v[0], 3), "p5": round(pct(v, 0.05), 3),
        "p50": round(st.median(v), 3), "p95": round(pct(v, 0.95), 3),
        "max": round(v[-1], 3),
        "ratio_p95_p5": round(pct(v, 0.95) / max(pct(v, 0.05), 1e-9), 1),
        "frac_below_3mbps": round(sum(1 for x in v if x < 3.0) / len(v), 3),
    }
    print(f"\n[{label}]  n={d['n']}")
    print(f"  최소 {d['min']} · P5 {d['p5']} · P50 {d['p50']} · P95 {d['p95']} · 최대 {d['max']} Mbps")
    print(f"  P95/P5 격차 {d['ratio_p95_p5']}배 · 3Mbps 미만 비율 {d['frac_below_3mbps'] * 100:.1f}%")
    return d


def load_derived():
    with open(DERIVED, encoding="utf-8") as f:
        return [float(r["throughput_mbps"]) for r in csv.DictReader(f)]


def load_source():
    """원본을 내려받아 uplink 처리량 컬럼을 추출한다."""
    import urllib.request
    import io
    url = (f"https://zenodo.org/api/records/{SOURCE['record_id']}"
           f"/files/{SOURCE['file_used']}/content")
    print(f"원본 다운로드: {url}")
    with urllib.request.urlopen(url, timeout=180) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    rdr = csv.DictReader(io.StringIO(raw))
    col = SOURCE["column_used"]
    if col not in (rdr.fieldnames or []):
        raise SystemExit(f"원본에 '{col}' 컬럼이 없습니다. 실제 컬럼: {rdr.fieldnames}")
    vals = []
    for row in rdr:
        try:
            x = float(row[col])
        except (TypeError, ValueError):
            continue
        if x > 0:            # 0/음수 표본은 측정 결손으로 보고 제외
            vals.append(x)
    # 단위 자동 판별 (bps/kbps로 저장된 경우 대비) — 판별 결과를 보고서에 남긴다
    mean = sum(vals) / len(vals)
    unit = "Mbps"
    if mean > 1e6:
        vals = [v / 1e6 for v in vals]; unit = "bps→Mbps 변환"
    elif mean > 1e3:
        vals = [v / 1e3 for v in vals]; unit = "kbps→Mbps 변환"
    print(f"  표본 {len(vals):,}개 · 단위 처리: {unit}")
    return vals, unit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="원본 다운로드 없이 파생만 점검")
    args = ap.parse_args()

    print("=" * 70)
    print("5G 트레이스 신뢰성 검증")
    print("=" * 70)
    print(f"출처 : {SOURCE['repository']} {SOURCE['record_id']} — {SOURCE['title']}")
    print(f"       {SOURCE['published']} · {SOURCE['license']}")
    print(f"사용 : {SOURCE['file_used']} · 컬럼 {SOURCE['column_used']}")
    print(f"설정 : {SOURCE['설정']}")

    report = {"source": SOURCE}
    derived = load_derived()
    d_stat = describe(derived, "② 파생 트레이스 (실험 주입값, 100노드)")
    report["derived"] = d_stat

    if not args.offline:
        try:
            src, unit = load_source()
            s_stat = describe(src, "① 원본 전체")
            s_stat["unit_handling"] = unit
            report["source_stats"] = s_stat

            # ③ 서브샘플 충실도 — 분위수가 얼마나 보존되는가
            print("\n[③ 서브샘플 충실도] 원본 대비 파생 트레이스의 분위수 오차")
            fid = {}
            for k in ("p5", "p50", "p95"):
                a, b = s_stat[k], d_stat[k]
                err = abs(b - a) / max(a, 1e-9) * 100
                fid[k] = round(err, 1)
                mark = "OK" if err < 25 else "확인 필요"
                print(f"  {k.upper():>4}: 원본 {a:>7.2f} → 파생 {b:>7.2f} Mbps · 오차 {err:>5.1f}% [{mark}]")
            report["subsample_error_pct"] = fid
        except Exception as e:
            print(f"\n원본 검증 실패({type(e).__name__}: {e}) — --offline으로 파생만 점검했습니다.")
            report["source_stats"] = None

    # ④ 교차 검증
    print(f"\n[④ 교차 검증] 독립 출처 FedScale 중앙값 {FEDSCALE_MEDIAN_MBPS} Mbps")
    gap = abs(d_stat["p50"] - FEDSCALE_MEDIAN_MBPS) / FEDSCALE_MEDIAN_MBPS * 100
    print(f"  본 트레이스 중앙값 {d_stat['p50']} Mbps · 차이 {gap:.1f}%")
    print(f"  → {'서로 다른 두 실측의 중앙값이 수렴' if gap < 30 else '수렴하지 않음 — 해석 재검토'}")
    report["cross_check_fedscale"] = {"fedscale_median": FEDSCALE_MEDIAN_MBPS,
                                      "ours_median": d_stat["p50"],
                                      "diff_pct": round(gap, 1)}

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(f"\n저장: {os.path.relpath(OUT, REPO)}")


if __name__ == "__main__":
    main()
