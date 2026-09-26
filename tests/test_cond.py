# -*- coding: utf-8 -*-
"""조건 원장(scripts/exp/conditions.json) 시험 — 스크립트에 숫자가 없고, 모든 조건에 출처가 있는가.

    python tests/test_cond.py
"""
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts", "exp"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import cond  # noqa: E402

fails = 0


def check(name, ok, detail=""):
    global fails
    fails += 0 if ok else 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def main():
    print("== 조건 원장 시험 ==")
    bad = cond.check()
    check("원장 자체 검사 (값마다 v·src·note, src 는 4종, 목록 길이 = 기기 수)", not bad, "; ".join(bad))

    L = cond.load()
    # 모든 조건에 리그·기기 수·경로 용량이 있고 상속이 된다
    for c in L["conditions"]:
        r = cond.resolve(c)
        check(f"{c}: rig/clients/caps/rounds/seeds 있음", all(k in r for k in ("rig", "clients", "caps", "rounds", "seeds")))

    # 팔 규약 — 경로만은 사다리 1.0, 폭만은 max-moves 0, 구판은 planner v1
    e = cond.env_lines("h5", "path"); check("경로만 팔: --ladder 1.0", "--ladder 1.0" in e["EXTRA"] and "--max-moves" not in e["EXTRA"], e["EXTRA"])
    e = cond.env_lines("h5", "width"); check("폭만 팔: --max-moves 0", "--max-moves 0" in e["EXTRA"], e["EXTRA"])
    e = cond.env_lines("h5", "both"); check("둘다 팔: 이동·사다리 잠금 없음", "--max-moves" not in e["EXTRA"] and "--ladder 0.5,0.75,1.0" in e["EXTRA"], e["EXTRA"])
    e = cond.env_lines("h5", "bothv1"); check("구판 팔: --planner two-stage-v1", "--planner two-stage-v1" in e["EXTRA"], e["EXTRA"])
    check("h5: 접속 회선 오라클이 켜져 있으면 --access-caps 가 acc_list 와 같다", "--access-caps c0=50,c1=50,c2=10,c3=50" in e["EXTRA"], e["EXTRA"])
    check("h5: 목록 길이 = 기기 수", len(e["SPEED_LIST"].split()) == int(e["CLIENTS"]) == len(e["ACC_LIST"].split()))
    e2 = cond.env_lines("c4_10050", "both"); check("paths 리그 조건은 --access-caps 없음", "--access-caps" not in e2["EXTRA"], e2["EXTRA"])

    # 스크립트에 조건 숫자가 박혀 있지 않은가 — 드라이버는 COND 로만 조건을 받는다
    for f in ("scripts/exp/ablate_5.sh",):
        p = os.path.join(ROOT, f)
        if os.path.exists(p):
            txt = open(p, encoding="utf-8").read()
            hard = re.findall(r'(CAPS_SETUP|SPEED_LIST|ACC_LIST)=\$\{[A-Z_]+:-"[0-9. ]+"\}', txt)
            check(f"{f}: 조건 숫자 하드코딩 없음 (COND 사용)", not hard and "COND=" in txt, str(hard))

    # env 출력이 셸에서 그대로 eval 되는가
    out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "exp", "cond.py"), "--env", "h5", "--arm", "width", "--seed", "2"],
                         capture_output=True, text=True, encoding="utf-8")
    check("cond.py --env 출력이 export 문", out.returncode == 0 and all(l.startswith("export ") for l in out.stdout.strip().splitlines()))
    print(f"\n== {'전부 통과' if fails == 0 else f'실패 {fails}건'} ==")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
