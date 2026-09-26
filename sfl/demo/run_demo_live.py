# -*- coding: utf-8 -*-
"""라이브 폐루프 데모 — LLM 없이, 실학습 리그 위에서 **폭 대응을 눈앞에서**.

  최종평가(현장 시연) 규격의 원형이다:
      심사위원이 웹에서 특정 클라의 회선을 조인다(버튼)
      → 다음 라운드에 진단(망몫)이 바뀌고
      → 컨트롤러가 그 클라의 폭을 좁히고
      → makespan 이 회복되는 것이 차트에 그려진다

  구성: 이 프로세스 하나가 ① 실학습 리그(fed_server --policy ours + 클라 4, HTB 회선)
  ② 제어 웹(포트 8778) 을 함께 띄운다. 웹은 라운드 로그(jsonl)를 폴링해 그린다.

      sudo ~/sflenv/bin/python sfl/demo/run_demo_live.py            # WSL/리눅스, tc 필요
      브라우저: http://localhost:8778  (원격이면 ssh -L 8778:localhost:8778)
"""
import argparse
import io
import json
import os
import signal
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from run_g2 import OUT, ROOT, SERVER_IP, client_threads         # noqa: E402

PY = sys.executable
HS = os.path.join(ROOT, "sfl", "net", "hetero.sh")
N = 4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--http", type=int, default=8778)
    ap.add_argument("--port", type=int, default=34100)
    ap.add_argument("--batches", type=int, default=4)
    ap.add_argument("--rates", default="40,40,40,40")
    ap.add_argument("--shared", type=int, default=200)
    a = ap.parse_args()
    base = [int(x) for x in a.rates.split(",")]
    rates = list(base)
    events = []
    slog = os.path.join(OUT, "demo_live.jsonl")
    os.makedirs(OUT, exist_ok=True)
    if os.path.exists(slog):
        os.remove(slog)

    def set_rates():
        subprocess.run(["sh", HS, "setup", " ".join(map(str, rates)), str(a.shared)],
                       check=True)

    set_rates()
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "sfl"))
    procs = [subprocess.Popen(
        [PY, os.path.join(ROOT, "sfl", "fed_server.py"), "--clients", str(N),
         "--rounds", "100000", "--batches", str(a.batches), "--cut", "2",
         "--policy", "ours", "--port", str(a.port), "--target", "0.99",
         "--device", "cuda", "--log", slog, "--seed", "1"], env=env, cwd=ROOT)]
    time.sleep(10)
    procs += [subprocess.Popen(
        [PY, os.path.join(ROOT, "sfl", "fed_client.py"),
         "--server", f"{SERVER_IP}:{a.port}", "--bind", f"127.0.0.{i+1}",
         "--id", f"c{i}", "--index", str(i), "--clients", str(N), "--cut", "2",
         "--seed", "1", "--threads", str(client_threads(N, 0))], env=env, cwd=ROOT)
        for i in range(N)]

    tpl = io.open(os.path.join(ROOT, "sfl", "demo", "demo_live_template.html"),
                  encoding="utf-8").read()
    page = tpl.replace("__N__", str(N)).replace("__BASE__", json.dumps(base)).encode()

    def state():
        rows = []
        if os.path.exists(slog):
            for line in io.open(slog, encoding="utf-8"):
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "round" not in d:
                    continue
                det = d.get("per_client_detail") or {}
                share = {}
                for k, v in det.items():
                    cpu = v.get("cli_fwd", 0) + v.get("cli_bwd", 0)
                    up, dn = v.get("up_bytes", 0), v.get("dn_bytes", 0)
                    net = v.get("xfer", 0) * ((up + dn) / up if up else 1.0)
                    share[k] = net / (cpu + net) if cpu + net > 0 else 0.0
                rows.append({"r": d["round"], "ms": d["makespan"],
                             "plan": d.get("plan", {}), "share": share})
        return {"rows": rows[-48:], "rates": rates, "events": events[-12:]}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            body, ctype = (page, "text/html") if self.path == "/" else \
                (json.dumps(state(), ensure_ascii=False).encode(), "application/json")
            self.send_response(200)
            self.send_header("Content-Type", f"{ctype}; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n))
            if self.path == "/link":
                i, mbps = int(req["idx"]), int(req["mbps"])
                rates[i] = mbps
                set_rates()
                last = state()["rows"]
                events.append({"r": last[-1]["r"] if last else 0,
                               "txt": f"c{i} 회선 → {mbps}M"})
            elif self.path == "/reset":
                rates[:] = list(base)
                set_rates()
                last = state()["rows"]
                events.append({"r": last[-1]["r"] if last else 0, "txt": "전 회선 복구"})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

    srv = HTTPServer(("0.0.0.0", a.http), H)
    print(f"라이브 데모: http://localhost:{a.http}  (리그 가동 중 — Ctrl+C 로 종료)")

    def cleanup(*_):
        for p in procs:
            p.terminate()
        subprocess.run(["sh", HS, "clear"], check=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    srv.serve_forever()


if __name__ == "__main__":
    main()
