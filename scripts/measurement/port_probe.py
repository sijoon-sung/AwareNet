# -*- coding: utf-8 -*-
"""개방 포트 경계·구간 확인 — 어느 포트가 방화벽을 통과하고 어느 포트가 막혔는지 정확히 찍는다.

    python scripts/measurement/port_probe.py --hosts vm1=116.89.187.190,vm2=116.89.187.189 \
        --ports 21,22,23,80,443,9999,10000,10001,12001,14999,15000,15001,20000,26022 --repeat 3
    python scripts/measurement/port_probe.py --hosts vm1=116.89.187.190 --range 9990:15010 --workers 120

판정: 연결 거부 = 방화벽 통과(듣는 프로그램 없음) · 연결 성공 = 통과 + 서비스 있음 · 시간 초과 = 차단.
--repeat 로 같은 포트를 여러 번 확인해 한 번의 시간 초과를 차단으로 오판하지 않는다.
결과: out/probe/portmap_<태그>.json + 화면 표. 표준 라이브러리만 쓴다.
"""
import argparse
import io
import json
import os
import socket
import time
from concurrent.futures import ThreadPoolExecutor


def probe(ip, port, timeout, repeat):
    states = []
    for _ in range(repeat):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect((ip, port))
            states.append("open")
        except ConnectionRefusedError:
            states.append("refused")
        except socket.timeout:
            states.append("timeout")
        except OSError:
            states.append("error")
        finally:
            s.close()
    # 한 번이라도 응답이 오면 통과로 본다 (차단은 항상 무응답)
    if "open" in states:
        return "open"
    if "refused" in states:
        return "refused"
    return max(set(states), key=states.count)


def ranges(states, ports):
    """같은 판정이 이어지는 구간으로 묶어 읽기 쉽게."""
    out, start, cur = [], ports[0], states[ports[0]]
    prev = ports[0]
    for p in ports[1:]:
        if states[p] != cur or p != prev + 1:
            out.append((start, prev, cur))
            start, cur = p, states[p]
        prev = p
    out.append((start, prev, cur))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hosts", required=True, help="이름=IP 를 쉼표로")
    ap.add_argument("--ports", default="", help="포트 목록, 쉼표로")
    ap.add_argument("--range", default="", help="시작:끝 (양끝 포함)")
    ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--timeout", type=float, default=2.0)
    ap.add_argument("--workers", type=int, default=80)
    ap.add_argument("--tag", default="vm")
    a = ap.parse_args()

    ports = [int(x) for x in a.ports.split(",") if x.strip()]
    if a.range:
        lo, hi = (int(x) for x in a.range.split(":"))
        ports += list(range(lo, hi + 1))
    ports = sorted(set(ports))
    hosts = [x.split("=", 1) for x in a.hosts.split(",") if x.strip()]

    res = {}
    for name, ip in hosts:
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            got = list(ex.map(lambda p: probe(ip, p, a.timeout, a.repeat), ports))
        st = dict(zip(ports, got))
        res[name] = {"ip": ip, "states": {str(k): v for k, v in st.items()},
                     "elapsed_s": round(time.time() - t0, 1)}
        print(f"\n== {name} ({ip}) · 포트 {len(ports)}개 · {res[name]['elapsed_s']}초 ==")
        for lo, hi, s in ranges(st, ports):
            tag = {"refused": "통과 (듣는 프로그램 없음)", "open": "통과 + 서비스 있음",
                   "timeout": "차단", "error": "오류"}[s]
            print(f"  {lo}{'' if lo == hi else '~' + str(hi)}: {tag}")
    os.makedirs(os.path.join("out", "probe"), exist_ok=True)
    p = os.path.join("out", "probe", f"portmap_{a.tag}.json")
    io.open(p, "w", encoding="utf-8").write(json.dumps(res, ensure_ascii=False, indent=1))
    print("\n→", p)


if __name__ == "__main__":
    main()
