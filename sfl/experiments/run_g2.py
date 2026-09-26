# -*- coding: utf-8 -*-
"""G2 — 컨트롤러가 이기나. 같은 이질성 조건에서 기준선 3종 대조. (WSL/리눅스, root)

  기준선 (설계서 §5, 최소 정의)
    B1 uniform : 전원 p=1.0 (바닐라 SplitFed) — 낙오자에 묶인다
    B2 oracle  : 참 프로파일을 다 아는 오라클의 **정적** 배정 (가장 억센 상대)
    B3 ours    : 실측 기반 동적 배정 (우리 컨트롤러)
    (B4 random : 평균 폭 맞춘 무작위 — "측정이 이긴 건가 그냥 좁아서인가" 분리)

  이질성 = 클라별 회선 (HTB, dst IP 별). 프로파일 2종:
    static : 20/40/60/80 Mbps 고정
    step   : 중간에 c3 회선을 1/5로 떨어뜨림 (교란 — 우리가 주입한다고 명시)

  판정 (사전 등록)
    1단 자동배정: ours 의 TTA 가 oracle 의 105% 이내 (= 손으로 짠 최적의 95% 이상 성능)
    2단 교란대응: step 프로파일에서 ours 의 TTA < uniform 의 TTA

    sudo ~/sflenv/bin/python sfl/experiments/run_g2.py --profile static
"""
import argparse
import io
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "out")
PY = sys.executable
N = int(os.environ.get("SFL_N", "4"))
# 클라 수에 맞춰 회선 이질성을 늘린다 (같은 비율 유지: 최저 20M ~ 최고 80M)
RATES = ([int(x) for x in os.environ["SFL_RATES"].split(",")] if os.environ.get("SFL_RATES")
         else [20, 40, 60, 80] if N == 4
         else [20 + int(60 * i / max(1, N - 1)) for i in range(N)])  # Mbps, 클라 c0..c3 (엣지 업링크 이질성 재현)
SHARED = int(os.environ.get("SFL_SHARED", 200))   # 서버 회선 — 합계 이상이라 자기 회선이 주 병목 (N 늘리면 같이 키울 것: 클라당 ~50M)
SERVER_IP = "127.0.0.100"     # ★ 클라 주소(127.0.0.1~4)와 겹치면 안 된다.
                              #   겹치면 "dst 서버IP" 필터가 먼저 걸려 전 트래픽이
                              #   그 클라 클래스 하나로 몰린다 — 실측으로 확인된 함정.


def client_threads(n, override=0):
    """클라당 CPU 스레드 — 0이면 **코어수÷클라수**로 자동.

    ★ 이걸 안 주면 실험이 조용히 망가진다. 클라는 --device 기본값이 cpu 라
      전부 CPU 에서 돌고, torch 는 프로세스당 8스레드가 기본이다.
      코어 16개 기계에서 클라 8대면 64스레드가 몰려 4배 과다구독이 나고,
      라운드 시간이 N=1 대비 26배로 부푼다(--threads 2 면 3.4배).
      조건1~4 로그가 전부 이 오염 아래에서 만들어졌다 — 재생성이 필요하다.
    """
    if override > 0:
        return override
    try:
        cores = len(os.sched_getaffinity(0))       # 리눅스: 실제 가용 코어
    except AttributeError:
        cores = os.cpu_count() or 4
    return max(1, cores // max(1, n))


def sh(cmd):
    subprocess.run(["sh", os.path.join(ROOT, "sfl", "net", "hetero.sh")] + cmd,
                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


PERTURB_AT = 4                     # step 프로파일에서 교란이 들어가는 라운드
PERTURB_RATES = [20, 40, 60, 16]   # c3 을 80 → 16 Mbps 로 (가장 빠르던 클라가 낙오자가 된다)
# ※ 이 두 상수는 true_oracle 재작성 때 통째로 지워져 step 실행이 즉시 크래시했다.
#    로그가 갱신되지 않아 옛 로그를 새 결과로 오독하는 사고로 이어졌다 (2026-08-25).


def true_oracle(a):
    """B2 오라클 — **참 회선값 + 실측 연산·바이트**로 사다리 전조합(4^4=256)을 완전탐색한다.

    이전 판은 연산을 0.08초로 추측해 넣어 통신을 과대평가했고(실측 0.25초),
    그 결과 오라클이 실제보다 더 좁히는 답을 골랐다 — 자기 채점 문제.
    지금은 ① 회선은 HTB 설정값(참값) ② 연산·바이트는 직전 uniform 실행의 실측
    ③ 탐욕법이 아니라 완전탐색 → **우리 규칙과 독립인 상한**이 된다.
    (진짜 상한은 256구성을 다 돌려 재는 것이지만 비용이 커서, 모델 기반 상한임을 명시한다.)
    """
    import itertools
    from controller import Controller, LADDER
    ids = [f"c{i}" for i in range(N)]
    ctl = Controller(ids, hysteresis=False)
    ctl.gamma = {k: 1.2 for k in ids}
    ctl.Ck = {f"c{i}": RATES[i] * 1e6 for i in range(N)}     # 참값
    ctl.C = SHARED * 1e6
    # 직전 uniform 로그에서 연산·바이트 실측을 끌어온다 (없으면 보수적 기본값)
    prev = os.path.join(OUT, f"g2_{a.profile}_s{a.seed}_uniform.jsonl")
    comp1 = bytes1 = None
    if os.path.exists(prev):
        rr = [json.loads(l) for l in io.open(prev, encoding="utf-8") if "round" in l]
        if rr:
            pc = rr[-1]["per_client"]
            comp1 = {k: v[1] / v[0] for k, v in pc.items()}
            bytes1 = {k: v[2] / v[0] for k, v in pc.items()}
    ctl.comp1 = comp1 or {k: 0.25 for k in ids}
    ctl.bytes1 = bytes1 or {k: 128 * 16 * 16 * 32 * 4 * 2 for k in ids}
    best = None
    for combo in itertools.product(LADDER, repeat=N):
        pv = dict(zip(ids, combo))
        ms = max(ctl.predict(pv, a.batches).values())
        # makespan 최소 — 단, 동률이면 폭 합이 큰 쪽(학습을 더 하는 쪽)을 고른다
        key = (round(ms, 3), -sum(combo))
        if best is None or key < best[0]:
            best = (key, pv)
    print(f"   [오라클 완전탐색] 연산실측 {'있음' if comp1 else '기본값'} → {best[1]}", flush=True)
    return best[1]


def run(policy, a, plan=""):
    # ★ 정책마다 기준 회선으로 되돌린다. step 프로파일에서 앞 정책의 교란이
    #   그대로 남으면 뒤 정책들은 '교란된 상태로 시작'해 비교가 무너진다 (실측으로 확인).
    sh(["setup", " ".join(map(str, RATES)), str(SHARED)])
    # 정책 토큰 확장 (J 시리즈): "ours+pipe+stag" = ours 정책 + 파이프라인 일괄 on
    # + 시작 지연 고정 등간격 — "따로 결합" 대조군. "joint" = 통합 판단(plan_round).
    base, *mods = policy.split("+")
    tag = f"{a.profile}_s{a.seed}_{policy.replace('+', '-')}"
    slog = os.path.join(OUT, f"g2_{tag}.jsonl")
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "sfl"))
    cmd = [PY, os.path.join(ROOT, "sfl", "fed_server.py"), "--clients", str(N),
           "--rounds", str(a.rounds), "--batches", str(a.batches), "--cut", "2",
           "--policy", base, "--port", str(a.port), "--target", str(a.target),
           "--device", "cuda", "--log", slog, "--seed", str(a.seed)]
    for m in mods:
        if m == "pipe":
            cmd += ["--pipeline", "on"]
        elif m == "stag":
            cmd += ["--stagger", "fixed"]
        elif m == "pre":
            cmd += ["--preflight"]
    if a.profile == "step":
        hs = os.path.join(ROOT, "sfl", "net", "hetero.sh")
        cmd += ["--perturb-at", str(PERTURB_AT), "--perturb-cmd",
                f"sh {hs} setup '{' '.join(map(str, PERTURB_RATES))}' {SHARED}"]
    if plan:
        cmd += ["--oracle-plan", plan]
    srv = subprocess.Popen(cmd, env=env, cwd=ROOT)
    time.sleep(10)
    cs = []
    for i in range(N):
        cs.append(subprocess.Popen(
            [PY, os.path.join(ROOT, "sfl", "fed_client.py"),
             "--server", f"{SERVER_IP}:{a.port}", "--bind", f"127.0.0.{i+1}",
             "--id", f"c{i}", "--index", str(i),
             "--clients", str(N), "--cut", "2", "--seed", str(a.seed),
             "--threads", str(client_threads(N, getattr(a, "threads", 0)))],
            env=env, cwd=ROOT))
    for c in cs:
        c.wait(timeout=3600)
    srv.wait(timeout=300)
    rows = [json.loads(l) for l in io.open(slog, encoding="utf-8")]
    summ = [r for r in rows if r.get("summary")][0]
    rr = [r for r in rows if "round" in r]
    return {"policy": policy, "tta": summ["tta"], "total": summ["total"],
            "final_acc": summ["final_acc"],
            "makespan_mean": sum(r["makespan"] for r in rr) / len(rr),
            "plans": [r["plan"] for r in rr]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="static",
                    choices=["same", "static", "step"],
                    help="same=회선 전부 동일(안전장치 시험) · static=고정 이질 · step=중간 교란")
    ap.add_argument("--rounds", type=int, default=14)
    ap.add_argument("--batches", type=int, default=6)
    ap.add_argument("--target", type=float, default=0.30)
    ap.add_argument("--port", type=int, default=30100)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--threads", type=int, default=0,
                    help="클라당 CPU 스레드. 0=코어수/클라수 자동. client_threads() 주석 참조")
    ap.add_argument("--policies", default="uniform,oracle,ours,random",
                    help="돌릴 정책 목록. 스크리닝은 uniform,ours 만 — 방향 판정엔 충분")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    global RATES
    if a.profile == "same":
        RATES = [40, 40, 40, 40]          # 전부 같은 회선 → 좁힐 이유가 없다
    sh(["setup", " ".join(map(str, RATES)), str(SHARED)])
    rows = []
    pols = a.policies.split(",")
    try:
        # ── B1 uniform ───────────────────────────────────────
        if "uniform" in pols:
            rows.append(run("uniform", a)); a.port += 1
        # ── B2 oracle: 회선 비에서 나오는 정적 배정 ──────────
        #    같은 탐욕법을 **참 회선값**으로 돌린다 (추정이 아니라 정답을 아는 상대)
        if "oracle" in pols:
            oracle = json.dumps(true_oracle(a))
            rows.append(run("oracle", a, oracle)); a.port += 1
        # ── B3 ours ──────────────────────────────────────────
        if "ours" in pols:
            rows.append(run("ours", a)); a.port += 1
        # ── B4 random ────────────────────────────────────────
        if "random" in pols:
            rows.append(run("random", a)); a.port += 1
        # ── J 시리즈 등 확장 토큰 (joint, ours+pipe+stag, uniform+pipe …) ──
        for pol in pols:
            if pol.split("+")[0] not in ("uniform", "oracle", "ours", "random") \
                    or "+" in pol:
                rows.append(run(pol, a)); a.port += 1
    finally:
        sh(["clear"])

    io.open(os.path.join(OUT, f"g2_{a.profile}_s{a.seed}_results.json"), "w",
            encoding="utf-8").write(json.dumps(rows, indent=1))

    print(f"\n=== G2 판정 ({a.profile} 시드{a.seed}, 회선 {RATES} Mbps, 목표 {a.target*100:.0f}%) ===")
    print(f"{'정책':10s} {'TTA(s)':>9s} {'총시간':>8s} {'평균 makespan':>13s} {'최종정확도':>10s}")
    for r in rows:
        t = f"{r['tta']:.1f}" if r["tta"] else "미달"
        print(f"{r['policy']:10s} {t:>9s} {r['total']:8.1f} "
              f"{r['makespan_mean']:13.2f} {r['final_acc']*100:9.1f}%")
    by = {r["policy"]: r for r in rows}
    if "ours" in by and "oracle" in by and by["ours"]["tta"] and by["oracle"]["tta"]:
        ratio = by["ours"]["tta"] / by["oracle"]["tta"]
        print(f"\n1단 자동배정: ours/oracle TTA = {ratio:.3f} "
              f"→ {'PASS (≤1.05)' if ratio <= 1.05 else 'FAIL'}")
    if "ours" in by and "uniform" in by and by["ours"]["tta"] and by["uniform"]["tta"]:
        print(f"uniform 대비: {(1-by['ours']['tta']/by['uniform']['tta'])*100:+.1f}%")
    if "ours" in by:
        # 스크리닝(uniform,ours)의 방향 판정 — makespan 비교는 TTA 미달이어도 된다
        if "uniform" in by:
            print(f"평균 makespan 단축: "
                  f"{(1-by['ours']['makespan_mean']/by['uniform']['makespan_mean'])*100:+.1f}%")
        print("마지막 라운드 배정:", by["ours"]["plans"][-1])


if __name__ == "__main__":
    main()
