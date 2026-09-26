# -*- coding: utf-8 -*-
"""리그 자가 검사 — 실험 전에 리그가 "의도한 물리"대로 동작하는지 스스로 잰다. 통과 못 하면 실험을 걸지 않는다.

    sudo -E env PY=... python scripts/measurement/rig_selftest.py --cond h5        # 조건 원장에서 리그 설정을 읽어 검사
    python scripts/measurement/rig_selftest.py --cond h5 --no-setup              # 이미 세워진 리그만 검사

검사 3종 (기대값은 조건 원장에서 계산, 측정은 fed 트래픽과 같은 주소 규약 127.0.0.i → 127.0.0.100):
  A 단독   기기 i 혼자 경로 1 로 보낼 때 처리량 ≈ min(접속상한_i, 경로1 용량)          허용 −25%/+10%
  B 동시   전원 경로 1 로 동시에 보낼 때 처리량_i ≈ 물 채우기(water-filling) 균등 몫     허용 −25%/+15%
  C 지연   TCP 연결 왕복 ≈ 2 × (접속 편도 + 경로 편도)                                 허용 ±3ms
  (B 의 물 채우기: 접속 상한이 몫보다 작은 기기는 자기 상한만 쓰고, 남는 용량을 나머지가 균등하게 나눈다)

왜 있나: 절제 5판 1차(2026-09-06)에서 접속 회선 클래스가 상한이 아니라 가중치로 동작했고(20M 기기가 12Mbps,
50M 기기가 27Mbps), 아무도 실험 전에 이것을 재지 않아 결과 해석이 틀어졌다. 리그는 규칙과 따로 시험한다.
루프백·tc 가 필요하므로 HPC 에서 root 로 돈다. 반환 코드 0 = 전부 통과.
"""
import argparse
import io
import json
import os
import socket
import subprocess
import sys
import threading
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts", "exp"))
import cond  # noqa: E402

SRV = "127.0.0.100"
CHUNK = b"\0" * 65536


class Sink(threading.Thread):
    """받는 쪽 — 접속마다 바이트를 세서 보낸 주소별로 기록한다."""
    def __init__(self, port):
        super().__init__(daemon=True)
        self.port, self.bytes, self.lock, self.stop = port, {}, threading.Lock(), False
        self.sock = socket.create_server((SRV, port), reuse_port=False)
        self.sock.settimeout(0.5)

    def run(self):
        while not self.stop:
            try:
                c, addr = self.sock.accept()
            except socket.timeout:
                continue
            threading.Thread(target=self._drain, args=(c, addr[0]), daemon=True).start()

    def _drain(self, c, src):
        c.settimeout(5)
        try:
            while True:
                b = c.recv(1 << 20)
                if not b:
                    break
                with self.lock:
                    self.bytes[src] = self.bytes.get(src, 0) + len(b)
        except OSError:
            pass
        finally:
            c.close()

    def snapshot(self):
        with self.lock:
            return dict(self.bytes)


def send_for(src_ip, port, secs, out, key):
    """src_ip 로 bind 해 secs 동안 최대한 보낸다. 앞 1초는 램프업으로 버린다(out 에는 램프업 뒤 바이트·시간)."""
    s = socket.socket()
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 256 << 10)   # 송신 버퍼 256KB — 자동 조정(4MB)이면 닫은 뒤에도 수 MB 가 큐에 남아 다음 검사(지연)를 오염시킨다
    s.bind((src_ip, 0))
    t0 = time.perf_counter()
    s.connect((SRV, port))
    out[key + "_connect_ms"] = (time.perf_counter() - t0) * 1000
    t_end = t0 + secs
    sent, sent_after, t_mark = 0, 0, None
    while time.perf_counter() < t_end:
        n = s.send(CHUNK)
        sent += n
        if t_mark is None and time.perf_counter() - t0 >= 1.0:
            t_mark = time.perf_counter(); sent_after = 0
        elif t_mark is not None:
            sent_after += n
    s.close()
    out[key] = (sent_after, time.perf_counter() - (t_mark or t0))


def mbps(bytes_, secs):
    return bytes_ * 8 / 1e6 / max(secs, 1e-6)


def water_fill(cap, limits):
    """공유 용량 cap 을 상한 limits 를 가진 흐름들이 균등하게 나눌 때 각자의 몫."""
    share = {k: 0.0 for k in limits}
    left, active = cap, dict(limits)
    while active and left > 1e-9:
        eq = left / len(active)
        done = {k: v for k, v in active.items() if v <= eq}
        if not done:
            for k in active:
                share[k] = eq
            break
        for k, v in done.items():
            share[k] = v; left -= v; del active[k]
    return share


def rig_cmd(rig, *args, env=None):
    script = os.path.join(ROOT, "sfl", "net", "hairpin_lo.sh" if rig == "hairpin" else "paths.sh")
    e = dict(os.environ); e.update(env or {})
    return subprocess.run(["sh", script, *args], env=e, capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cond", required=True)
    ap.add_argument("--no-setup", action="store_true")
    ap.add_argument("--secs", type=float, default=5.0)
    ap.add_argument("--json", help="결과를 이 파일에도 남긴다")
    a = ap.parse_args()
    r = cond.resolve(a.cond)
    rig, n = r["rig"]["v"], r["clients"]["v"]
    caps = r["caps"]["v"]; acc_raw = r.get("acc_list", {}).get("v") or [caps[0]] * n
    # 접속 토큰: 50 (한 가닥) 또는 "50/20" (두 가닥: 출구 A / B). A·B·C 는 출구 A 로만 잰다.
    accA = [float(str(x).split("/")[0]) for x in acc_raw]
    accB = [float(str(x).split("/")[-1]) for x in acc_raw]
    two = [("/" in str(x)) for x in acc_raw]
    acc = accA
    d_acc, pds = r["delay_ms"]["v"], (r.get("delays", {}).get("v") or [0] * len(caps))
    port = int(r["server_port"]["v"]) + 1
    env = {"DELAY_MS": str(d_acc), "PATH_DELAYS": " ".join(map(str, pds)), "DELAYS": " ".join(map(str, pds)),
           "QUEUE_BDP_MULT": str(r["queue_bdp_mult"]["v"])}
    if not a.no_setup:
        out = rig_cmd(rig, "setup", " ".join(map(str, caps)), *([" ".join(map(str, acc_raw))] if rig == "hairpin" else []), env=env)
        print(out.stdout.strip());
        if out.returncode != 0:
            print("리그 설정 실패:", out.stderr.strip()); return 2
        rig_cmd(rig, "assign", " ".join(["1"] * n))
    sink = Sink(port); sink.start()
    results, fails = {"cond": a.cond, "rig": rig}, []
    tol_lo, tol_hi = 0.75, 1.15

    # ── A 단독
    print(f"\nA 단독 (각 기기 혼자, 경로 1, {a.secs:.0f}s)")
    rows = []
    for i in range(n):
        out = {}
        send_for(f"127.0.0.{i+1}", port, a.secs, out, "x")
        got = mbps(*out["x"]); exp = min(acc[i], caps[0])
        ok = tol_lo * exp <= got <= tol_hi * exp
        rows.append((f"c{i}", exp, got, ok)); fails += [] if ok else [f"A c{i}: {got:.1f} vs 기대 {exp}"]
        print(f"  c{i}: 기대 {exp:6.1f}  측정 {got:6.1f} Mbps  {'OK' if ok else 'FAIL'}   연결 {out['x_connect_ms']:.1f}ms")
    results["A"] = rows

    time.sleep(2)                                           # 앞 검사의 큐 배출
    # ── B 동시
    print(f"\nB 동시 (전원 경로 1, {a.secs:.0f}s) — 물 채우기 균등 몫")
    exp_share = water_fill(caps[0], {f"c{i}": min(acc[i], caps[0]) for i in range(n)})
    outs, ths = {}, []
    for i in range(n):
        t = threading.Thread(target=send_for, args=(f"127.0.0.{i+1}", port, a.secs, outs, f"c{i}")); ths.append(t)
    for t in ths: t.start()
    for t in ths: t.join()
    rows = []
    for i in range(n):
        got = mbps(*outs[f"c{i}"]); exp = exp_share[f"c{i}"]
        ok = 0.75 * exp <= got <= 1.15 * exp
        rows.append((f"c{i}", exp, got, ok)); fails += [] if ok else [f"B c{i}: {got:.1f} vs 기대 {exp:.1f}"]
        print(f"  c{i}: 기대 {exp:6.1f}  측정 {got:6.1f} Mbps  {'OK' if ok else 'FAIL'}")
    tot = sum(mbps(*outs[f'c{i}']) for i in range(n))
    print(f"  합계 {tot:.1f} Mbps (경로 1 용량 {caps[0]})")
    results["B"] = rows

    time.sleep(2)                                           # 앞 검사의 큐 배출
    # ── C 지연
    print("\nC 지연 (TCP 연결 왕복)")
    rows = []
    for i in range(n):
        ts = []
        for _ in range(5):
            s = socket.socket(); s.bind((f"127.0.0.{i+1}", 0)); t0 = time.perf_counter(); s.connect((SRV, port)); ts.append((time.perf_counter() - t0) * 1000); s.close()
        got = sorted(ts)[len(ts) // 2]; exp = 2 * (d_acc + pds[0])
        ok = abs(got - exp) <= 3.0
        rows.append((f"c{i}", exp, got, ok)); fails += [] if ok else [f"C c{i}: {got:.1f}ms vs 기대 {exp}ms"]
        print(f"  c{i}: 기대 {exp:5.1f}ms  측정 {got:5.1f}ms  {'OK' if ok else 'FAIL'}")
    results["C"] = rows

    time.sleep(2)                                           # 앞 검사의 큐 배출
    # ── D 분할 전송 (조건이 multipath 면): 기기 혼자 출구 2개(경로 1·2)로 동시에 보낼 때 ≈ min(접속 상한, 경로1+경로2)
    if r.get("multipath", {}).get("v") and rig == "hairpin" and len(caps) >= 2:
        print(f"\nD 분할 (각 기기 혼자, 출구 A→경로 1 · B→경로 2, {a.secs:.0f}s)")
        if not a.no_setup:
            rig_cmd(rig, "assign", " ".join(["1+2"] * n))
        rows = []
        for i in range(n):
            outs, ths = {}, []
            for j, src in enumerate((f"127.0.0.{i+1}", f"127.0.1.{i+1}")):
                t = threading.Thread(target=send_for, args=(src, port, a.secs, outs, f"x{j}")); ths.append(t)
            for t in ths: t.start()
            for t in ths: t.join()
            got = mbps(*outs["x0"]) + mbps(*outs["x1"])
            exp = (min(accA[i], caps[0]) + min(accB[i], caps[1])) if two[i] else min(acc[i], caps[0] + caps[1])   # 두 가닥이면 합, 한 가닥이면 상한
            ok = tol_lo * exp <= got <= tol_hi * exp
            rows.append((f"c{i}", exp, got, ok)); fails += [] if ok else [f"D c{i}: {got:.1f} vs 기대 {exp}"]
            print(f"  c{i}: 기대 {exp:6.1f}  측정 {got:6.1f} Mbps (A {mbps(*outs['x0']):.1f} + B {mbps(*outs['x1']):.1f})  {'OK' if ok else 'FAIL'}")
        results["D"] = rows

    sink.stop = True
    if not a.no_setup:
        rig_cmd(rig, "clear")
    results["fails"] = fails
    if a.json:
        io.open(a.json, "w", encoding="utf-8").write(json.dumps(results, ensure_ascii=False, indent=1))
    print("\n== 리그 자가 검사:", "통과 — 실험을 걸 수 있다" if not fails else f"실패 {len(fails)}건 — 실험을 걸지 않는다\n  " + "\n  ".join(fails), "==")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
