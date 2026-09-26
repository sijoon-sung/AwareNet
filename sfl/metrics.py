# -*- coding: utf-8 -*-
"""InfluxDB 라인 프로토콜로 라운드 지표를 밀어 넣는다 (Grafana 대시보드용).

  의존성 없음 — urllib 로 HTTP POST 만 한다. INFLUX_URL 이 없으면 조용히 무시하므로
  대시보드를 안 띄운 상태에서도 실험은 그대로 돈다.

  환경변수
    INFLUX_URL    예: http://127.0.0.1:8086   (없으면 비활성)
    INFLUX_TOKEN  기본 awarenet-token
    INFLUX_ORG    기본 AwareNet
    INFLUX_BUCKET 기본 sfl
"""
import os
import time
import urllib.error
import urllib.request


def _esc(v):
    return str(v).replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")


class Metrics:
    def __init__(self, run=""):
        self.url = os.environ.get("INFLUX_URL", "").rstrip("/")
        self.tok = os.environ.get("INFLUX_TOKEN", "awarenet-token")
        self.org = os.environ.get("INFLUX_ORG", "AwareNet")
        self.buc = os.environ.get("INFLUX_BUCKET", "sfl")
        self.run = run
        self.on = bool(self.url)
        self.fail = 0

    def _post(self, lines):
        if not self.on or not lines:
            return
        try:
            u = f"{self.url}/api/v2/write?org={self.org}&bucket={self.buc}&precision=ns"
            req = urllib.request.Request(
                u, data="\n".join(lines).encode(),
                headers={"Authorization": f"Token {self.tok}",
                         "Content-Type": "text/plain; charset=utf-8"})
            urllib.request.urlopen(req, timeout=2).read()
        except Exception:
            self.fail += 1
            if self.fail >= 5:            # 계속 실패하면 끈다 — 실험을 방해하지 않는다
                self.on = False

    def round(self, policy, r, makespan, acc, elapsed, plan, per_client, ck, C):
        """라운드 한 줄 + 클라별 한 줄씩."""
        ts = time.time_ns()
        tag = f"policy={_esc(policy)},run={_esc(self.run)}"
        L = [f"sfl_round,{tag} round={r}i,makespan={makespan},acc={acc},"
             f"elapsed={elapsed},mean_p={sum(plan.values())/len(plan)},"
             f"shared_mbps={(C or 0)/1e6} {ts}"]
        for k, p in plan.items():
            v = per_client.get(k)
            f = [f"p={p}"]
            if v:
                f += [f"t_client={v[3]}", f"bytes={int(v[2])}i", f"comp={v[1]}"]
            if ck and k in ck:
                f.append(f"link_mbps={ck[k]/1e6}")
            L.append(f"sfl_client,{tag},client={_esc(k)} {','.join(f)} {ts}")
        self._post(L)

    def event(self, policy, kind, detail=""):
        ts = time.time_ns()
        self._post([f"sfl_event,policy={_esc(policy)},run={_esc(self.run)},"
                    f"kind={_esc(kind)} detail=\"{detail}\",v=1 {ts}"])
