# -*- coding: utf-8 -*-
"""
loss_only_autocorrelation.py — 가치 지속성 주장의 교란 요인 분리

[왜 필요한가]
  "직전 라운드 가치로 이번 라운드를 배분해도 되는가"의 근거로 util_ema의 순위
  자기상관(rho=0.971)을 제시했다. 그러나 가치 수식은

      util = clamped_loss_rms  x  sample_count

  이고 **sample_count는 노드별 상수**다. 손실이 매 라운드 요동쳐도 표본 수가 순위를
  고정시키므로, 높은 자기상관이 "가치의 지속성"이 아니라 "데이터 보유량의 불변성"에서
  올 수 있다. 즉 기존 수치는 교란되어 있다.

  이 스크립트는 **손실 항만 따로** 자기상관을 재어 둘을 분리한다.
    - loss 자기상관도 높다      -> 지속성 주장 성립
    - util만 높고 loss는 낮다   -> 표본 수가 만든 착시. 주장 철회 또는 재서술 필요
"""
import argparse
import json
import os
import statistics as st

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def spearman(xs, ys):
    n = len(xs)
    if n < 3:
        return None

    def rank(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = rank(xs), rank(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    return None if dx == 0 or dy == 0 else num / (dx * dy)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(REPO, "out", "round_metrics.jsonl"))
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.src, encoding="utf-8") if l.strip()]
    snaps = {}
    for r in rows:
        s = r.get("util_snapshot") or {}
        if s:
            snaps[int(r["round"])] = s

    rounds = sorted(snaps)
    print(f"원자료: {os.path.relpath(args.src, REPO)} · 라운드 {len(rounds)}개\n")
    print(" 쌍     | n   | util 자기상관 | loss 자기상관 | 갱신노드만 | 갱신 수")
    print("-" * 64)

    ur, lr, upd_list = [], [], []
    for a, b in zip(rounds, rounds[1:]):
        if b != a + 1:
            continue
        common = sorted(set(snaps[a]) & set(snaps[b]))
        if len(common) < 3:
            continue
        ua = [snaps[a][c]["util_ema"] for c in common]
        ub = [snaps[b][c]["util_ema"] for c in common]
        la = [snaps[a][c].get("last_loss_rms", 0.0) for c in common]
        lb = [snaps[b][c].get("last_loss_rms", 0.0) for c in common]
        changed = sum(1 for x, y in zip(la, lb) if abs(x - y) > 1e-9)
        # [교란 제거] 그 라운드에 선발되지 않은 노드는 손실이 갱신되지 않아 값이 그대로다.
        # 그 노드들을 포함하면 "안 변한 값끼리의 상관"이 섞여 자기상관이 부풀려진다.
        # 실제로 갱신된 노드만으로 다시 계산해 이 교란을 제거한다.
        idx = [i for i in range(len(common)) if abs(la[i] - lb[i]) > 1e-9]
        rl_upd = spearman([la[i] for i in idx], [lb[i] for i in idx]) if len(idx) >= 3 else None
        upd_list.append(rl_upd) if rl_upd is not None else None
        ru, rl = spearman(ua, ub), spearman(la, lb)
        if ru is not None:
            ur.append(ru)
        if rl is not None:
            lr.append(rl)
        f = lambda v: f"{v:+.3f}" if v is not None else "  n/a"
        print(f"R{a:>2}->R{b:<2} | {len(common):>3} |   {f(ru)}      |   {f(rl)}      |   {f(rl_upd)}   | {changed}/{len(common)}")

    print()
    if ur:
        print(f"util 평균 자기상관 : {st.mean(ur):+.3f}")
    if lr:
        print(f"loss 평균 자기상관 : {st.mean(lr):+.3f}")
    if upd_list:
        print(f"갱신 노드만 손실 자기상관 : {st.mean(upd_list):+.3f}  (표본 {len(upd_list)}쌍)")
    if ur and lr:
        gap = st.mean(ur) - st.mean(lr)
        print(f"차이               : {gap:+.3f}")
        print()
        key = st.mean(upd_list) if upd_list else st.mean(lr)
        print(f"(판정 기준: 갱신된 노드만의 손실 자기상관 = {key:+.3f})")
        if key < 0.5 <= st.mean(ur):
            print("판정: util 자기상관이 손실이 아니라 **표본 수 상수항**에서 온다.")
            print("      '가치가 라운드 간 지속된다'는 주장은 이 데이터로 뒷받침되지 않는다.")
        elif key >= 0.6:
            print("판정: 손실 자체도 순위가 유지된다 — 지속성 주장이 뒷받침된다.")
        else:
            print("판정: 손실 순위는 부분적으로만 유지된다 — 주장을 약화해 서술해야 한다.")
    else:
        print("판정 불가 — 표본 부족. 실제 학습이 도는 실행에서 다시 측정할 것.")


if __name__ == "__main__":
    main()
