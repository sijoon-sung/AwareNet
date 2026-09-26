# -*- coding: utf-8 -*-
"""실증 플랫폼 — CNN(ResNet-18/CIFAR-10) 분할 연합학습 라이브 시연, 실회선 리그(HPC 8대 ↔ KOREN VM 엣지 4개) 위에서.

  화면(포트 8778)에서 심사위원이 보는 것
      기기 8대 카드: 유형(계산 느림 / 회선 약함 / 정상) · 지금 모델 폭 · 어느 엣지로 어떻게 보내는지 · 이번 라운드 시간 vs 목표 D
      그래프: 라운드 시간(목표선 D) · 모델 폭 평균 · 정확도
      교란 버튼: 기기 회선 절반 / 엣지 용량 절반 / 복구 → 다음 라운드에 스케줄러가 어떻게 대응하는지 카드가 바뀐다
  조건·팔은 원장(scripts/exp/conditions.json)에서 읽는다 — 숫자를 여기 쓰지 않는다.

      ~/env/bin/python sfl/demo/run_demo_real.py --cond demo8 --arm bothmp          # 라이브 — 일반 사용자로 실행 (리그 안에서 sudo tc, VM ssh 키는 사용자 것)
      python sfl/demo/run_demo_real.py --replay out/wp_r8mix_rho1_s1_bothmp_widthpath.jsonl      # 재생 (무대 안전망, 리그 없음)
  브라우저: http://localhost:8778  (원격이면 ssh -L 8778:localhost:8778 sijoon0404@HPC)
"""
import argparse
import io
import json
import os
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts", "exp"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
PY = sys.executable
RIG = os.path.join(ROOT, "sfl", "net", "real_rig.sh")
TPL = os.path.join(ROOT, "sfl", "demo", "demo_real_template.html")
LANDING = os.path.join(ROOT, "sfl", "demo", "platform_index.html")


def ledger_env(cond, arm):
    """cond.py --env 의 export 줄을 dict 로."""
    out = subprocess.run([PY, os.path.join(ROOT, "scripts", "exp", "cond.py"), "--env", cond, "--arm", arm],
                         capture_output=True, text=True, encoding="utf-8", check=True, cwd=ROOT).stdout
    env = {}
    for line in out.splitlines():
        if line.startswith("export "):
            k, _, v = line[7:].partition("=")
            env[k] = v.strip().strip('"').strip("'")
    return env


def device_types(speeds, accs):
    tot = [sum(float(x) for x in str(a).split("/")) for a in accs]
    lo = min(tot)
    return ["계산 느림" if s < 1 else ("회선 약함" if (t == lo and lo < max(tot)) else "정상") for s, t in zip(speeds, tot)]


class Demo:
    def __init__(self, a):
        self.a = a
        self.events = []
        self.procs = []
        self.t0 = time.time()
        if a.replay:
            self.rows_all = self._load(a.replay)
            self.env = None
            n = len(self.rows_all[0].get("plan", {})) if self.rows_all else 8
            self.speeds = a.speed.split(",") if a.speed else ["0.15", "0.25"] + ["1"] * (n - 2)
            self.accs = a.acc.split(",") if a.acc else ["50/20", "50/20", "20/20", "20/20"] + ["50/20"] * (n - 4)
            self.D = a.D
            self.lam = None
            self.caps = [125] * 4
        else:
            self.env = ledger_env(a.cond, a.arm)
            self.speeds = self.env["SPEED_LIST"].split()
            self.accs = self.env["ACC_LIST"].split()
            self.caps = [float(x) for x in self.env["CAPS_SETUP"].split()]
            ex = self.env.get("EXTRA", "")
            self.D = float(ex.split("--deadline-s")[1].split()[0]) if "--deadline-s" in ex else a.D          # opt 모드면 None (목표선 없음)
            self.lam = float(ex.split("--lam")[1].split()[0]) if "--lam" in ex else None
            self.log = os.path.join(ROOT, "out", "demo_real.jsonl")
        self.speeds_f = [float(s) for s in self.speeds]
        self.types = device_types(self.speeds_f, self.accs)
        self.base_acc = [[float(x) for x in str(t).split("/")] for t in self.accs]
        self.cur_acc = [list(v) for v in self.base_acc]
        self.cur_caps = list(self.caps)

    @staticmethod
    def _load(path):
        rows = []
        if os.path.exists(path):
            for line in io.open(path, encoding="utf-8"):
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "round" in d:
                    rows.append(d)
        return rows

    # ── 리그·학습 기동 (라이브)
    def start(self):
        a, env = self.a, self.env
        n = int(env["CLIENTS"])
        subprocess.run(["bash", RIG, "up", str(n), env["ACC_LIST"], env["CAPS_SETUP"]], check=True, cwd=ROOT,
                       env=dict(os.environ, BASE=os.environ.get("BASE", "12100"), SRV_PORT=env["PORT"], DEV=os.environ.get("DEV", "ens160")))
        edges = subprocess.run(["bash", RIG, "edges"], capture_output=True, text=True, check=True, cwd=ROOT).stdout.strip()
        if os.path.exists(self.log):
            os.remove(self.log)
        penv = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "sfl"))
        cmd = [PY, os.path.join(ROOT, "sfl", "fed_server.py"), "--clients", str(n), "--rounds", str(a.rounds),
               "--batches", env["BATCHES"], "--seed", str(a.seed), "--cut", env["CUT"], "--policy", "widthpath",
               "--port", env["PORT"], "--device", "cuda", "--log", self.log, "--edges", edges,
               "--paths", env["CAPS_ARG"], "--preflight"] + env.get("EXTRA", "").split()
        self.procs.append(subprocess.Popen(cmd, env=penv, cwd=ROOT))
        time.sleep(10)
        for i in range(n):
            self.procs.append(subprocess.Popen(
                [PY, os.path.join(ROOT, "sfl", "fed_client.py"), "--server", f"127.0.0.1:{env['PORT']}", "--id", f"c{i}",
                 "--index", str(i), "--clients", str(n), "--cut", env["CUT"], "--threads", env["THREADS"], "--speed", self.speeds[i]],
                env=penv, cwd=ROOT, stdout=open(os.path.join(ROOT, "out", f"demo_real_c{i}.log"), "w"), stderr=subprocess.STDOUT))

    def stop(self):
        for p in self.procs:
            try:
                p.terminate()
            except Exception:
                pass
        if not self.a.replay:
            subprocess.run(["bash", RIG, "down"], check=False, cwd=ROOT)

    # ── 상태
    def rows(self):
        if self.a.replay:
            k = int((time.time() - self.t0) / self.a.replay_dt) + 1
            return self.rows_all[:k]
        return self._load(self.log)

    def state(self):
        out = []
        for d in self.rows()[-60:]:
            det = d.get("per_client_detail") or {}
            plan = d.get("plan") or {}
            paths = d.get("paths") or {}
            devs = {}
            for k in sorted(plan):
                v = det.get(k, {})
                devs[k] = {"w": plan[k], "path": str(paths.get(k, "1")),
                           "t": round(v.get("t_round") or (v.get("xfer", 0) + v.get("cli_fwd", 0) + v.get("cli_bwd", 0)), 2),
                           "cpu": round(v.get("cli_fwd", 0) + v.get("cli_bwd", 0), 2), "xfer": round(v.get("xfer", 0), 2)}
            out.append({"r": d["round"], "ms": round(d["makespan"], 2), "acc": d.get("acc"), "devs": devs,
                        "wsum": round(sum(float(x) for x in plan.values()) / max(1, len(plan)), 3) if plan else None})
        return {"rows": out, "D": self.D, "types": self.types, "speeds": self.speeds_f, "acc": self.cur_acc, "base_acc": self.base_acc,
                "caps": self.cur_caps, "base_caps": self.caps, "events": self.events[-12:], "mode": "재생" if self.a.replay else "라이브",
                "arm": self.a.arm, "cond": self.a.cond, "lam": getattr(self, "lam", None)}

    def _event(self, txt):
        r = self.rows()
        self.events.append({"r": r[-1]["round"] if r else 0, "txt": txt})

    # ── 교란
    def perturb(self, req):
        kind, idx, f = req.get("kind"), int(req.get("idx", 0)), float(req.get("factor", 0.5))
        if kind == "access":
            aA, aB = [max(1, round(v * f)) for v in self.base_acc[idx]]
            self.cur_acc[idx] = [aA, aB]
            self._run(["bash", RIG, "access", str(idx), str(aA), str(aB)])
            self._event(f"c{idx} 회선 → {aA}/{aB} Mbps")
        elif kind == "edge":
            c = max(1, round(self.caps[idx] * f))
            self.cur_caps[idx] = c
            self._run(["bash", RIG, "edge", str(idx), str(c)])
            self._event(f"엣지 {idx + 1} 용량 → {c} Mbps")
        elif kind == "reset":
            for i, v in enumerate(self.base_acc):
                if self.cur_acc[i] != list(v):
                    self.cur_acc[i] = list(v); self._run(["bash", RIG, "access", str(i), str(int(v[0])), str(int(v[1]))])
            for e, c in enumerate(self.caps):
                if self.cur_caps[e] != c:
                    self.cur_caps[e] = c; self._run(["bash", RIG, "edge", str(e), str(int(c))])
            self._event("전부 복구")

    def _run(self, cmd):
        if self.a.replay:
            return
        threading.Thread(target=lambda: subprocess.run(cmd, cwd=ROOT, check=False), daemon=True).start()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cond", default="demo8"); ap.add_argument("--arm", default="bothmp")
    ap.add_argument("--rounds", type=int, default=100000); ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--http", type=int, default=8778)
    ap.add_argument("--replay", default=None, help="기록된 라운드 로그(jsonl)를 재생 — 리그 없이")
    ap.add_argument("--replay-dt", type=float, default=4.0, help="재생 시 라운드 간격(초)")
    ap.add_argument("--speed", default=None); ap.add_argument("--acc", default=None); ap.add_argument("--D", type=float, default=None)
    a = ap.parse_args()
    demo = Demo(a)
    if not a.replay:
        demo.start()
    tpl = io.open(TPL, encoding="utf-8").read()
    page = tpl.replace("__D__", json.dumps(demo.D)).encode("utf-8")
    landing = io.open(LANDING, encoding="utf-8").read().encode("utf-8") if os.path.exists(LANDING) else "<p>platform_index.html none</p>".encode("utf-8")

    class H(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, body, ctype):
            self.send_response(200); self.send_header("Content-Type", f"{ctype}; charset=utf-8"); self.end_headers(); self.wfile.write(body)

        def do_GET(self):
            if self.path == "/":
                self._send(page, "text/html")
            elif self.path.startswith("/platform"):
                self._send(landing, "text/html")
            else:
                self._send(json.dumps(demo.state(), ensure_ascii=False).encode("utf-8"), "application/json")

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or b"{}")
            demo.perturb(req if self.path == "/perturb" else {"kind": "reset"})
            self._send(b'{"ok":true}', "application/json")

    srv = HTTPServer(("0.0.0.0", a.http), H)
    print(f"실증 플랫폼 ({'재생' if a.replay else '라이브'}): http://localhost:{a.http}   {'목표 D=' + str(demo.D) + 's' if demo.D else '결합 최적화 λ=' + str(demo.lam)}  기기 {demo.types}")

    def cleanup(*_):
        demo.stop(); sys.exit(0)

    signal.signal(signal.SIGINT, cleanup); signal.signal(signal.SIGTERM, cleanup)
    try:
        srv.serve_forever()
    finally:
        demo.stop()


if __name__ == "__main__":
    main()
