# -*- coding: utf-8 -*-
"""실험 조건 원장(conditions.json) 로더 — 스크립트가 숫자를 갖지 않게 한다.

    eval "$(python scripts/exp/cond.py --env h5)"        # run_widthpath.sh 환경변수 export 문
    python scripts/exp/cond.py --env h5 --arm width        # 팔 인자(EXTRA)까지
    python scripts/exp/cond.py --table h5                  # 출처 표 (마크다운)
    python scripts/exp/cond.py --check                     # 원장 검사: 모든 값에 src·note 가 있는가, src 가 넷 중 하나인가
    python scripts/exp/cond.py --list

조건은 _base 를 상속하고 자기 키로 덮어쓴다. 값은 {"v": ..., "src": ..., "note": ...} 꼴이어야 한다.
"""
import argparse
import io
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "conditions.json")
SRC_OK = ("실측", "논문", "우리선택", "장비제약")


def load():
    return json.load(io.open(LEDGER, encoding="utf-8"))


def resolve(name, ledger=None):
    """_base 위에 조건을 덮은 {키: {v,src,note}} 를 돌려준다."""
    L = ledger or load()
    if name not in L["conditions"]:
        raise SystemExit(f"조건 '{name}' 없음. 있는 것: {', '.join(L['conditions'])}")
    out = {k: dict(v) for k, v in L["_base"].items()}
    for k, v in L["conditions"][name].items():
        if k.startswith("_"):
            continue
        out[k] = dict(v)
    return out


def check(ledger=None):
    """원장 자체 검사. 반환 [문제 문장]."""
    L = ledger or load()
    bad = []
    def chk(where, k, v):
        if not isinstance(v, dict) or "v" not in v:
            bad.append(f"{where}.{k}: {{v,src,note}} 꼴이 아님"); return
        if v.get("src") not in SRC_OK:
            bad.append(f"{where}.{k}: src '{v.get('src')}' 는 {SRC_OK} 중 하나여야 함")
        if "note" not in v:
            bad.append(f"{where}.{k}: note 없음 (근거 없으면 '근거 없음'이라 적는다)")
    for k, v in L["_base"].items():
        chk("_base", k, v)
    for c, body in L["conditions"].items():
        for k, v in body.items():
            if k.startswith("_"):
                continue
            chk(c, k, v)
        r = resolve(c, L)
        n = r["clients"]["v"]
        for lk in ("speed_list", "acc_list"):
            lv = r.get(lk, {}).get("v")
            if lv is not None and len(lv) != n:
                bad.append(f"{c}.{lk}: 길이 {len(lv)} ≠ clients {n}")
        if r["rig"]["v"] == "hairpin" and r.get("acc_list", {}).get("v") is None:
            bad.append(f"{c}: hairpin 리그인데 acc_list 없음")
        if r["rig"]["v"] not in ("paths", "hairpin", "real"):
            bad.append(f"{c}.rig: '{r['rig']['v']}' 는 paths|hairpin|real 이어야 함")
    for a, body in L["arms"].items():
        if a.startswith("_"):
            continue
        if "extra" not in body:
            bad.append(f"arms.{a}: extra 없음")
    return bad


def env_lines(name, arm=None, seed=None):
    r = resolve(name)
    L = load()
    g = lambda k, d=None: r[k]["v"] if k in r else d
    caps = g("caps")
    lines = {
        "COND": name,
        "RIG": g("rig"),
        "CLIENTS": g("clients"),
        "THREADS": g("threads"),
        "ROUNDS": g("rounds"),
        "BATCHES": g("batches"),
        "CUT": g("cut"),
        "CAPS_SETUP": " ".join(str(c) for c in caps),
        "CAPS_ARG": ",".join(str(c) for c in caps),
        "DELAY_MS": g("delay_ms"),
        "DELAYS": " ".join(str(d) for d in g("delays", [])),
        "QUEUE_BDP_MULT": g("queue_bdp_mult"),
        "SPEED_LIST": " ".join(str(s) for s in (g("speed_list") or [])),
        "ACC_LIST": " ".join(str(a) for a in (g("acc_list") or [])),
        "LADDER": ",".join(str(x) for x in g("ladder")),
        "ALPHA": g("alpha"),
        "SWITCH_COST": g("switch_cost"),
        "PORT": g("server_port"),
        "SEEDS": " ".join(str(s) for s in g("seeds")),
    }
    if seed is not None:
        lines["SEED"] = seed
    if arm:
        if arm not in L["arms"]:
            raise SystemExit(f"팔 '{arm}' 없음. 있는 것: {[a for a in L['arms'] if not a.startswith('_')]}")
        extra = L["arms"][arm]["extra"].format(ladder=lines["LADDER"])
        if g("access_caps_oracle") and g("acc_list"):
            extra += " --access-caps " + ",".join(f"c{i}={a}" for i, a in enumerate(g("acc_list")))
        extra += f" --alpha {lines['ALPHA']} --switch-cost {lines['SWITCH_COST']}"
        if g("micro"):
            extra += f" --micro {g('micro')}"                    # 즉시 내보내기 조각 수 (조건 원장)
        if g("deadline") and "--deadline " not in extra:
            extra += f" --deadline {g('deadline')}"              # 폭 기준선 (anchored=B안 / relative=A안 / solo=B′안 / fixed=고정 목표) — 조건 원장
        if g("deadline_s"):
            extra += f" --deadline-s {g('deadline_s')}"          # 고정 라운드 목표(초) — fixed 와 함께 (opt 에서는 선택 제약)
        if g("lam") is not None:
            extra += f" --lam {g('lam')}"                        # opt: 정확도 가격 λ (초/평균폭 1)
        if g("max_moves") is not None:
            extra += f" --max-moves {g('max_moves')}"            # 라운드당 경로 이동 상한 (조건 원장; 없으면 fed_server 기본 1)
        lines["ARM"] = arm
        lines["EXTRA"] = extra
        lines["MP"] = "1" if "--multipath" in extra else "0"     # 클라 출구 2개 (run_widthpath.sh)
        lines["MICRO_FLAG"] = f"--micro {g('micro')}" if g("micro") else ""   # 균등(기준선) 팔에도 즉시 내보내기를 같이 (run_real.sh)
        lines["NORM_FLAG"] = "--norm gn" if "--norm gn" in extra else ""       # 정규화는 서버·클라·균등 기준선이 같아야 한다 (run_widthpath.sh)
        lines["INIT_FLAG"] = f"--init-sets {g('init_sets')}" if g("init_sets") else ""   # 초기 배정 (실회선) — 균등 기준선에도 같이 (run_real.sh)
    return lines


def table(name):
    r = resolve(name)
    L = load()
    desc = L["conditions"][name].get("_desc", "")
    rows = [f"### 조건 `{name}` — {desc}", "", "| 항목 | 값 | 출처 | 근거 |", "|---|---|---|---|"]
    for k, v in r.items():
        rows.append(f"| {k} | `{json.dumps(v['v'], ensure_ascii=False)}` | {v['src']} | {v.get('note','')} |")
    return "\n".join(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", metavar="COND")
    ap.add_argument("--arm")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--table", metavar="COND")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.check:
        bad = check()
        print("원장 OK" if not bad else "\n".join("원장 오류: " + b for b in bad))
        return 1 if bad else 0
    if a.list:
        L = load()
        for c, b in L["conditions"].items():
            print(f"{c:12s} {b.get('_desc','')}")
        return 0
    if a.env:
        for k, v in env_lines(a.env, a.arm, a.seed).items():
            if v is None or v == "":
                print(f"export {k}=''")
            else:
                print(f"export {k}={json.dumps(str(v))}")
        return 0
    if a.table:
        print(table(a.table))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
