# -*- coding: utf-8 -*-
"""라운드 기반 분할 연합학습 서버.

  라운드 한 바퀴
    ① 정책(policies.py)이 클라별 폭 p_k 와 경로를 정함 → RSTART 에 실어 보냄 (전역 가중치 슬라이스 동봉)
    ② 클라가 B배치 학습 — 배치마다 활성값 왕복 (서버는 폭별 뒷단 모델로 처리)
    ③ 클라가 앞단 가중치 업로드(WUP) → Aggregator 가 중첩 평균
    ④ 서버 뒷단도 폭별로 중첩 평균 → 다음 라운드용 슬라이스 준비
    ⑤ 실제로 학습된 최대 폭으로 평가 → 정확도 곡선 (TTA 산출)

  구성
    Aggregator     전역 앞단·폭별 뒷단·집계·평가·학습률 (모델 상태의 주인)
    RoundAccount   클라 하나의 라운드 계측 (바이트·시간 분해)
    RoundState     세션 스레드들이 공유하는 라운드 상태
    ClientSession  클라 하나를 맡는 스레드 — 라운드 반복, 배치 왕복, 계측
    Server         인자·데이터·수락·라운드 루프·기록
"""
import argparse
import io
import json
import math
import os
import random
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import torch
import torch.nn.functional as F

from controller_multi import MultiKnobController
from metrics import Metrics
import models
from models import nested_average, slice_into
from models import ClientNet as CnnClient, ServerNet as CnnServer
from policies import POLICY_NAMES, RoundContext, make_policy
from mpsend import ChunkServer
from sense import Sensor, solo_probe
from network_control import endpoints_for, verify_receipts
from proto import (ACT, BYE, GRAD, HELLO, PROBE, PROBERES, RSTART, WUP,
                   b2sd, b2t, recv_msg, sd2b, send_msg, t2b)

if hasattr(sys.stdout, "reconfigure"):                 # Windows 콘솔(cp949)에서 '—'·'★' 출력이 죽지 않게
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GPU_LOCK = threading.Lock()      # 서버 뒷단 계산은 한 번에 하나 — 클라가 많아지면 여기서 직렬화된다


def micro_step(net, opt, loss, mi, of, buf, sample_weight=None):
    """즉시 내보내기(조각 mi/of)의 서버 갱신. 뒷단 net 은 **여러 클라가 공유**하므로 조각 기울기를 net 의 .grad 에 그대로 누적하면
    다른 클라의 zero_grad/step 사이에 끼어 지워진다 (2026-09-08 h5xa: m=4 가 −18%p, GN 으로도 −8%p 남던 원인). 클라별 버퍼 buf 에 모았다가
    마지막 조각에서 한 번에 .grad 로 넣고 step — 직렬 배치와 같은 갱신. of<=1 이면 보통 한 걸음. 반환: 다음 조각에 넘길 buf."""
    opt.zero_grad()
    weight = 1 / max(1, of) if sample_weight is None else sample_weight
    if not math.isfinite(weight) or not 0 < weight <= 1:
        raise ValueError("invalid microbatch sample weight")
    (loss * weight).backward()
    if of <= 1:
        opt.step()
        return {}
    if mi == 0:
        buf = {}
    for q in net.parameters():
        if q.grad is None:
            continue
        if q in buf:
            buf[q] += q.grad
        else:
            buf[q] = q.grad.detach().clone()
    if mi == of - 1:
        for q in net.parameters():
            q.grad = buf.get(q)
        opt.step()
        return {}
    return buf


def lr_at(a, r):
    """라운드 r 의 학습률. 고정 학습률로는 수렴 근처에 못 가서 폭에 따른 정확도 차이가 안 보인다."""
    d = getattr(a, "lr_decay", "none")
    if d == "cosine":
        t = min(1.0, r / max(1, a.rounds - 1))
        return a.lr_min + (a.lr - a.lr_min) * 0.5 * (1 + math.cos(math.pi * t))
    if d == "step":
        return a.lr * (0.1 ** (r // max(1, a.rounds // 3)))
    return a.lr


def make_nets(arch, p, cut, vit_cfg="small"):
    """arch 로 모델 계열을 고른다 — 컨트롤러는 그대로, 모델만 갈아 끼운다."""
    if arch == "vit":
        from models_vit import ViTClient, ViTServer
        return ViTClient(p, cut, vit_cfg), ViTServer(p, cut, vit_cfg)
    return CnnClient(p, cut), CnnServer(p, cut)


# ──────────────────────────────────────────────────────────────────────────────
class Aggregator:
    """모델 상태의 주인 — 전역 앞단(전폭), 폭별 뒷단, 집계, 평가, 학습률."""

    def __init__(self, a):
        self.a = a
        self.dev = a.device
        self.full_c = make_nets(a.arch, 1.0, a.cut)[0].state_dict()   # 전역 앞단(전폭)
        self.smodels, self.sopt = {}, {}                              # 폭별 뒷단과 옵티마이저
        self.trained_widths = set()                                   # 실제로 학습된 폭들
        self.cur_round = 0
        self.srv(1.0)                                                 # 전폭 뒷단 미리 생성

    def srv(self, p):
        """폭 p 의 뒷단 (없으면 전폭에서 슬라이스해 만든다)."""
        if p not in self.smodels:
            m = make_nets(self.a.arch, p, self.a.cut)[1].to(self.dev)
            if 1.0 in self.smodels:
                m.load_state_dict(slice_into(m.state_dict(), self.smodels[1.0].state_dict()))
            self.smodels[p] = m
            self.sopt[p] = torch.optim.SGD(m.parameters(), lr=lr_at(self.a, self.cur_round), momentum=0.9)
        return self.smodels[p], self.sopt[p]

    def set_round(self, r):
        """라운드마다 서버 뒷단 학습률도 감쇠 — 이전에는 생성 시점 값에 고정돼 있었다."""
        self.cur_round = r
        for o in self.sopt.values():
            o.param_groups[0]["lr"] = lr_at(self.a, r)
        models.set_round(r)                                           # FedRolex 창 (AWARENET_ROLL=1 일 때만 의미)

    def client_payload(self, p):
        """RSTART 에 실을 폭 p 앞단 슬라이스."""
        return sd2b(slice_into(make_nets(self.a.arch, p, self.a.cut)[0].state_dict(), self.full_c))

    def aggregate(self, uploads, nb_by_width):
        """앞단·뒷단 모두 중첩 평균 — 실제 학습된 슬라이스만 표본 가중.
        uploads = {cid: (state_dict, n_samples, p)}, nb_by_width = {p: 배치 수}"""
        ups = [(sd, n) for sd, n, _ in uploads.values() if n]
        if ups:
            self.full_c = nested_average(self.full_c, ups)
        used = {p: n for p, n in nb_by_width.items() if n}
        # Even one trained width must refresh the global state and cached widths.
        # Otherwise a later width change can resurrect a pre-training server model.
        if used:
            full_s = self.smodels[1.0].state_dict()
            new = nested_average(full_s, [(self.smodels[p].state_dict(), n) for p, n in used.items()])
            for p, m in self.smodels.items():
                m.load_state_dict(slice_into(m.state_dict(), new))

    @torch.no_grad()
    def evaluate(self, loader):
        """실제로 학습된 최대 폭으로 평가한다. 전원이 p<1.0 이면 전폭 모델의 바깥 채널은 초기값
        그대로라 무작위 수준이 나온다 (E8 에서 p=0.25 가 9.1% 로 나온 원인)."""
        pw = max(self.trained_widths) if self.trained_widths else 1.0
        c = make_nets(self.a.arch, pw, self.a.cut)[0].to(self.dev)
        c.load_state_dict(slice_into(c.state_dict(), self.full_c))
        c.eval()
        s = self.srv(pw)[0]
        s.eval()
        hit = n = 0
        for x, y in loader:
            hit += (s(c(x.to(self.dev))).argmax(1).cpu() == y).sum().item()
            n += len(y)
        s.train()
        return hit / n


# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class RoundAccount:
    """클라 하나의 라운드 계측. xfer는 클라 연산을 뺀 잔여 시간이며 순수 망 시간이 아니다.
    직렬 실행에서도 서버 연산·락 대기·직렬화·제어 오버헤드가 포함된다."""
    nb: int = 0
    comp: float = 0.0        # 서버 쪽 계산 (락 대기 포함)
    byt: int = 0             # 올린 + 내린 바이트
    t_comm: float = 0.0
    lock_wait: float = 0.0
    srv_gpu: float = 0.0
    grad_send: float = 0.0
    up_bytes: int = 0
    dn_bytes: int = 0
    gradient_events: list = field(default_factory=list)
    t_round: float = 0.0     # RSTART 를 보낸 뒤 WUP 을 받을 때까지 (클라의 라운드 벽시계)

    def detail(self, meta):
        """WUP 메타(클라 보고)와 합쳐 per_client_detail 한 줄을 만든다.
        xfer(비기기연산 잔여 시간) = 라운드 벽시계 − 클라 연산(fwd+bwd). 즉시 내보내기(마이크로배치)로 연산과 전송이 겹치면
        예전 정의(t_comm − 연산)는 0 이 되어 버리므로, '연산이 아닌 시간' 으로 정의한다 — 겹침의 이득이 그대로 망 시간 감소로 잡힌다."""
        cf, cb = meta.get("t_fwd", 0.0), meta.get("t_bwd", 0.0)
        return {"cli_fwd": cf, "cli_wait": meta.get("t_wait", 0.0), "cli_bwd": cb,
                "compute_timer": meta.get("compute_timer", "legacy_host_elapsed"),
                "compute_device": meta.get("compute_device"), "compute_speed": meta.get("compute_speed"),
                "route_receipt": meta.get("route_receipt"), "traffic": meta.get("traffic"),
                "exits": meta.get("exits"),                          # 출구별 {up, dn} 바이트 (분할 전송 기기만) — 가닥별 부하 분배
                "lock_wait": round(self.lock_wait, 4), "srv_gpu": round(self.srv_gpu, 4),
                "grad_send": round(self.grad_send, 4), "gradient_events": self.gradient_events,
                "up_bytes": self.up_bytes, "dn_bytes": self.dn_bytes,
                "t_comm": round(self.t_comm, 4), "t_round": round(self.t_round, 4),
                "xfer": round(max((self.t_round if self.t_round > 0 else self.t_comm) - cf - cb, 1e-6), 4)}

    def stat(self, meta):
        """기존 로그·컨트롤러가 읽는 4-튜플 (batches, comp, bytes, t_comm)."""
        return (self.nb, meta.get("comp", self.comp), self.byt, self.t_comm)


@dataclass
class RoundState:
    """세션 스레드들이 공유하는 라운드 상태. 서버가 라운드 경계에서 비우고 읽는다."""
    r: int = 0
    stop: bool = False
    plan: dict = field(default_factory=dict)
    qplan: dict = field(default_factory=dict)
    dplan: dict = field(default_factory=dict)
    splan: dict = field(default_factory=dict)
    up: dict = field(default_factory=dict)        # cid → (sd, n, p)
    stat: dict = field(default_factory=dict)      # cid → 4-튜플
    detail: dict = field(default_factory=dict)    # cid → 분해
    nb: dict = field(default_factory=dict)        # p → 배치 수
    probe: dict = field(default_factory=dict)     # cid → 사전 진단
    mpplan: dict = field(default_factory=dict)    # cid → 이번 라운드 분할 전송 여부 (계획 층이 정함)
    dp: dict = field(default_factory=dict)        # cid → 출구별 데이터 종점 [[host, port], ...] (실회선 리그)
    chunks: object = None                         # ChunkServer (--multipath 일 때)
    lock: threading.Lock = field(default_factory=threading.Lock)


class ClientSession(threading.Thread):
    """클라 하나를 맡는다. HELLO → (PROBE) → 라운드마다 RSTART, 배치 왕복, WUP 수신."""

    def __init__(self, conn, a, agg, st, barrier):
        super().__init__(daemon=True)
        self.conn, self.a, self.agg, self.st, self.barrier = conn, a, agg, st, barrier
        self.cid = None

    def run(self):
        kind, meta, _, _ = recv_msg(self.conn)
        assert kind == HELLO
        self.cid = meta["id"]
        if self.a.preflight:
            self._probe()
        while True:
            self.barrier.wait()                                   # 라운드 시작
            if self.st.stop:
                send_msg(self.conn, BYE, {})
                break
            self._round()
            self.barrier.wait()                                   # 라운드 끝
        self.conn.close()

    def _probe(self):
        """사전 진단 — 학습 전에 계산·회선을 한 번 잰다. 전송 추정 = 총 왕복 − 클라 보고 시간."""
        t0 = time.perf_counter()
        send_msg(self.conn, PROBE, {"sync_compute": getattr(self.a, "planner", "") == "device-budget"})
        kind, pm, _, nB = recv_msg(self.conn)
        assert kind == PROBERES
        total = time.perf_counter() - t0
        with self.st.lock:
            self.st.probe[self.cid] = {"cpu": pm["t_fwd"] + pm["t_bwd"],
                                       "up": max(total - pm["t_local"], 1e-3), "bytes": nB}

    def _round(self):
        st, a, cid = self.st, self.a, self.cid
        p = st.plan[cid]
        m, b = self.agg.client_payload(p)
        send_msg(self.conn, RSTART,
                 {"round": st.r, "p": p, "batches": a.batches, "lr": lr_at(a, st.r), "dp": st.dp.get(cid),
                  "sync_compute": getattr(a, "planner", "") == "device-budget" or a.policy == "network",
                  "route_epoch": st.r, "micro_window": getattr(a, "micro_window", 2),
                  "quant": st.qplan.get(cid, 0), "depth": st.dplan.get(cid, 1),
                  "start_delay": st.splan.get(cid, 0.0), "mp": bool(st.mpplan.get(cid, False)),
                  "mp_w": (st.mpplan.get(cid) if isinstance(st.mpplan.get(cid), list) else None),   # 출구별 예상 속도(Mbps) = 조각 배분 가중치
                  "micro": int(getattr(a, "micro", 1)), "w": m}, b)
        acc = RoundAccount()
        t_last = t_rstart = time.perf_counter()
        while True:
            kind, meta, payload, nB = recv_msg(self.conn)
            if kind == ACT and meta.get("mp"):                    # 분할 전송 — 페이로드는 조각 포트로 온다
                payload = st.chunks.wait(meta["mp"])
                nB = len(payload)
            acc.t_comm += time.perf_counter() - t_last
            if kind == WUP:
                acc.t_round = time.perf_counter() - t_rstart
                if st.chunks is not None and cid in st.chunks.peers:
                    st.chunks.flush_back(cid)                     # 규칙 7·8: 넘긴 내려보내기가 다 나가고 회신까지 확인
                with st.lock:
                    st.up[cid] = (b2sd(meta["w"], payload), meta["n"], p)
                    st.stat[cid] = acc.stat(meta)
                    st.detail[cid] = acc.detail(meta)
                    st.nb[p] = st.nb.get(p, 0) + acc.nb
                    self.agg.trained_widths.add(p)
                return
            assert kind == ACT
            sent = self._serve_batch(p, meta, payload, acc, mp_tid=meta.get("mp"))
            if int(meta.get("micro", 0)) == 0:                    # 조각 배치는 첫 조각에서만 배치 하나로 센다
                acc.nb += 1
            acc.byt += nB + sent
            acc.up_bytes += nB
            acc.dn_bytes += sent
            t_last = time.perf_counter()

    def _serve_batch(self, p, meta, payload, acc, mp_tid=None):
        """활성값 하나 받아 뒷단을 한 걸음 학습시키고 기울기를 돌려준다. 보낸 바이트를 돌려준다.
        mp_tid 가 있으면(활성값이 조각으로 올라옴) 기울기도 같은 기기의 조각 연결들로 나눠 내려보낸다 (분할 전송 규칙 5)."""
        dev = self.a.device
        act = b2t(meta["act"], payload[:meta["act_bytes"]]).to(dev)
        y = b2t(meta["y"], payload[meta["act_bytes"]:]).long().to(dev)
        net, opt = self.agg.srv(p)
        t0 = time.perf_counter()
        mi, of = int(meta.get("micro", 0)), int(meta.get("of", 1))   # 즉시 내보내기: 조각 i/of — 갱신은 마지막 조각에서 한 번 (1/of 누적)
        with GPU_LOCK:
            t1 = time.perf_counter()
            act.requires_grad_(True)
            loss = F.cross_entropy(net(act), y)
            sample_weight = len(y) / int(meta["batch_n"]) if "batch_n" in meta else None
            self.gbuf = micro_step(net, opt, loss, mi, of, getattr(self, "gbuf", {}), sample_weight)
            if dev == "cuda":
                torch.cuda.synchronize()
        t2 = time.perf_counter()
        acc.lock_wait += t1 - t0
        acc.srv_gpu += t2 - t1
        acc.comp += t2 - t0
        gm, gb = t2b(act.grad, quant=meta.get("quant", 0))
        t3 = time.perf_counter()
        if mp_tid:
            dn_tid = f"{mp_tid}-dn"
            sent = send_msg(self.conn, GRAD, {"g": gm, "loss": float(loss), "mp": dn_tid})   # 메타는 주 연결, 페이로드는 조각으로
            mpw = self.st.mpplan.get(self.cid)
            self.st.chunks.send_back(self.cid, gb, dn_tid, weights=(mpw if isinstance(mpw, list) else None), wait=False)   # 규칙 8
            sent += len(gb)
        else:
            sent = send_msg(self.conn, GRAD, {"g": gm, "loss": float(loss)}, gb)
        submit_done = time.perf_counter()
        acc.grad_send += submit_done - t3
        acc.gradient_events.append({"batch_index": meta.get("batch_index"), "micro": mi, "of": of,
            "payload_bytes": len(gb), "ready_server_monotonic_s": t3,
            "submit_done_server_monotonic_s": submit_done,
            "completion_scope": "async_queue_submission" if mp_tid else "socket_send_return"})
        return sent


# ──────────────────────────────────────────────────────────────────────────────
class Server:
    def __init__(self, a):
        self.a = a
        torch.manual_seed(a.seed)
        random.seed(a.seed)
        self.ids = [f"c{i}" for i in range(a.clients)]
        self.agg = Aggregator(a)
        self.mctl = MultiKnobController(self.ids, alpha=a.alpha, hysteresis=True)
        self.policy = make_policy(a)
        self.met = Metrics(run=os.path.basename(a.log).replace(".jsonl", ""))
        self.st = RoundState(plan={k: 1.0 for k in self.ids},
                             qplan={k: 0 for k in self.ids},
                             dplan={k: (2 if a.pipeline == "on" else 1) for k in self.ids},
                             splan={k: (i * a.stagger_gap if a.stagger == "fixed" else 0.0)
                                    for i, k in enumerate(self.ids)})
        self.rnd = {}                     # 정책이 쓰는 라운드 간 상태 (passign, static_frozen)
        self.barrier = threading.Barrier(a.clients + 1)
        self.last_detail = {}
        self.sensor = Sensor(self.ids)    # 인지 층 — 프로파일(연산·접속 회선·경로·관측)
        self.edges = {}                                           # 실회선 리그: 경로 번호 → (host, base_port)
        for tok in (a.edges.split(",") if getattr(a, "edges", "") else []):
            r, hp = tok.split("="); h, b = hp.rsplit(":", 1); self.edges[r] = (h, int(b))
        if getattr(a, "multipath", False) or self.edges:         # 집행 층 — 조각 수신기 (주 포트 + 1)
            self.st.chunks = ChunkServer(getattr(a, "listen", "0.0.0.0"), a.port + 1)
            self.st.chunks.start()
        self.allowed = {}                                         # 기기별 허용 엣지 (--edge-groups "3,4:0-3;1,2:4-7"), VM 클라 모드(2026-09-12)
        for grp in (getattr(a, "edge_groups", "") or "").split(";"):
            if not grp.strip():
                continue
            ps, rng = grp.split(":"); lo, hi = (rng.split("-") + [rng])[:2]
            for i in range(int(lo), int(hi) + 1):
                if i < len(self.ids):
                    self.allowed[self.ids[i]] = [p.strip() for p in ps.split(",")]
        if self.edges:                                           # 초기 종점: 전원 경로 1 (기본) 또는 고르게(rr) — --init-sets
            n_exit = 2 if getattr(a, "multipath", False) else 1  # 두 가닥이면 처음부터 출구 2개(둘 다 같은 엣지) — 출구 B 프로브가 그 종점을 쓴다
            paths = sorted(self.edges, key=int)
            init = {}
            for i, k in enumerate(self.ids):
                pk = self.allowed.get(k, paths)
                p = pk[i % len(pk)] if getattr(a, "init_sets", "1") == "rr" else pk[0]
                init[k] = (p,) * n_exit
                self.st.dp[k] = endpoints_for(self.edges, init[k], i)
                self.st.mpplan[k] = True                         # dp 모드: 페이로드는 항상 채널로
            self.rnd["psets"] = init

    def _testset(self):
        import torchvision
        import torchvision.transforms as T
        tf = T.Compose([T.ToTensor(), T.Normalize((.49, .48, .45), (.25, .24, .26))])
        te = torch.utils.data.Subset(torchvision.datasets.CIFAR10(self.a.data, train=False, transform=tf),
                                     list(range(2000)))
        return torch.utils.data.DataLoader(te, batch_size=256)

    def _accept(self):
        srv = socket.create_server((getattr(self.a, "listen", "0.0.0.0"), self.a.port))
        srv.settimeout(300)
        sessions = []
        try:
            for _ in range(self.a.clients):
                conn, _ = srv.accept()
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                s = ClientSession(conn, self.a, self.agg, self.st, self.barrier)
                s.start()
                sessions.append(s)
        finally:
            srv.close()
        return sessions

    def _seed_from_preflight(self, sessions=()):
        """진단이 전부 모일 때까지 대기 → 컨트롤러·인지 층에 초기 추정 주입. --solo 면 단독 업로드 프로브까지."""
        t0 = time.perf_counter()
        while len(self.st.probe) < self.a.clients and time.perf_counter() - t0 < 120:
            time.sleep(0.2)
        for k, pr in self.st.probe.items():
            self.mctl.cpu1[k] = pr["cpu"]
            self.mctl.net1[k] = pr["up"] * 2             # 하향(기울기)도 비슷한 크기 — 초기 추정
            self.mctl.cap[k] = pr["bytes"] / pr["up"]
            self.mctl.bytes1[k] = pr["bytes"] * 2        # 왕복 바이트 — 없으면 widthpath 가 라운드 0 에 무개입
            self.sensor.set_probe(k, pr["cpu"], pr["bytes"] * 2, pr["up"])
        self.mctl.diagnose(self.a.batches)
        print(f"=== 사전 진단 (기기 {len(self.st.probe)}대, {time.perf_counter()-t0:.1f}s) — 첫 라운드부터 배정 ===", flush=True)
        print(self.mctl.explain(self.a.batches), flush=True)
        if getattr(self.a, "solo", False) and sessions:
            # 사전 진단 ② — 기기를 하나씩 불러 4MB 를 올리게 한다(나머지는 배리어에서 대기 중 = 쉼). 접속 회선 상한 실측.
            t1 = time.perf_counter()
            print("=== 단독 업로드 프로브 (접속 회선 상한, 기기 순차) ===", flush=True)
            for s in sorted(sessions, key=lambda s: s.cid):
                try:
                    dp = self.st.dp.get(s.cid)
                    rate, rtt = solo_probe(s.conn, exit_idx=0, chunks=(self.st.chunks if dp else None), cid=s.cid, dp=dp)   # 실회선: 출구 A 도 엣지 경유로
                    rateB = None
                    if getattr(self.a, "multipath", False) and self.st.chunks is not None:   # 두 가닥: 출구 B 도 따로
                        rateB, _ = solo_probe(s.conn, exit_idx=1, chunks=self.st.chunks, cid=s.cid, dp=dp)
                except (OSError, AssertionError) as e:
                    print(f"  {s.cid}: 프로브 실패 ({e})", flush=True); continue
                self.sensor.set_access(s.cid, [rate, rateB] if rateB is not None else rate); self.sensor.rtt[s.cid] = rtt
                self.mctl.access_cap[s.cid] = rate       # 측정값이 오라클(--access-caps)보다 우선 (구판 컨트롤러는 출구 A 만)
                print(f"  {s.cid}: 단독 출구A {rate/1e6:6.1f} Mbps" + (f"  출구B {rateB/1e6:6.1f} Mbps" if rateB else "") + f"  왕복 {rtt:5.1f} ms", flush=True)
            print(f"    ({time.perf_counter()-t1:.1f}s)", flush=True)

    def run(self):
        a, st = self.a, self.st
        teld = self._testset()
        sessions = self._accept()
        if a.preflight:
            self._seed_from_preflight(sessions)
        self.sensor.set_paths({str(i + 1): float(m) * 1e6 for i, m in enumerate(a.paths.split(","))} if a.paths else {})
        logf = io.open(a.log, "w", encoding="utf-8")
        # 실행 인자를 곁파일로 남긴다 (2026-09-06). 절제 2판 복원 때 "이 로그가 --max-moves 0 이었나"를
        # 로그만으로 알 수 없었다. jsonl 안에 넣지 않는 이유: 소비자들이 '"round" in l' 로 행을 고르는데
        # "rounds" 키가 그 필터에 걸린다.
        try:
            with io.open(a.log.replace(".jsonl", "") + ".args.json", "w", encoding="utf-8") as args_file:
                args_file.write(json.dumps(vars(a), ensure_ascii=False, indent=1, default=str))
        except OSError:
            pass
        t_start = time.perf_counter()
        tta, acc = None, 0.0
        for r in range(a.rounds):
            st.r = r
            self.agg.set_round(r)
            if r == a.perturb_at and a.perturb_cmd:      # 교란은 라운드 기준으로
                subprocess.run(a.perturb_cmd, shell=True, check=False)
                print(f"   [교란 주입 @R{r}] {a.perturb_cmd}", flush=True)
                self.met.event(a.policy, "perturb", f"R{r}")
            self.policy.apply(RoundContext(a=a, r=r, mctl=self.mctl, ids=self.ids, rnd=self.rnd,
                                           plan=st.plan, qplan=st.qplan, dplan=st.dplan, splan=st.splan,
                                           last_detail=self.last_detail,
                                           measured=(r > 0 or bool(st.probe)),
                                           sensor=self.sensor, mpplan=st.mpplan, edges=self.edges, dp=st.dp, allowed=self.allowed))
            st.up.clear(); st.stat.clear(); st.nb.clear()
            t0 = time.perf_counter()
            self.barrier.wait()                              # 라운드 시작
            self.barrier.wait()                              # 라운드 끝
            makespan = time.perf_counter() - t0
            self.agg.aggregate(st.up, st.nb)
            acc = self.agg.evaluate(teld)
            el = time.perf_counter() - t_start
            if tta is None and acc >= a.target:
                tta = el
            detail = dict(st.detail)
            self.last_detail = detail
            st.detail.clear()
            obs = dict(st.stat)
            budget_outcome = None
            network_receipts = verify_receipts(detail, st.dp, r) if a.policy == "network" else None
            if network_receipts is not None:
                self.rnd["network_route_verified"] = all(v["status"] == "round_completed" for v in network_receipts.values())
            if a.planner == "device-budget":
                from device_budget import measured_outcome
                budget_outcome = measured_outcome(detail, self.rnd.get("budget_decision"), makespan)
            if obs:
                self.mctl.observe_round(detail, a.batches, assign=self.rnd.get("passign"))
                sensed_detail = detail
                if a.planner == "device-budget" or (a.policy == "network" and a.micro == 1):
                    from device_budget import transport_observations
                    sensed_detail = transport_observations(detail)
                observed_sets = self.rnd.get("psets")
                if a.policy == "network" and (a.micro > 1 or not self.rnd["network_route_verified"]):
                    observed_sets = None  # Cannot attribute overlapping/unverified rounds to path capacity.
                self.sensor.observe(sensed_detail, a.batches, dict(st.plan), observed_sets)
            self.met.round(a.policy, r, makespan, acc, el, dict(st.plan), obs,
                           {k: v * 8 for k, v in self.mctl.cap.items()}, None)
            logf.write(json.dumps({
                "round": r, "policy": a.policy, "plan": dict(st.plan),
                "makespan": round(makespan, 3), "acc": round(acc, 4), "elapsed": round(el, 2),
                "paths": {k: "+".join(v) for k, v in (self.rnd.get("psets") or {}).items()}     # 이번 라운드 출구별 경로 ("1", "1+2", "2+1")
                         or dict(self.rnd.get("passign") or {}),                                # 구판 계획기는 단일 경로
                "mp": {k: (v if isinstance(v, list) else bool(v)) for k, v in st.mpplan.items()},   # 분할 전송한 기기 (값 = 출구별 예상 Mbps)
                "micro": int(getattr(a, "micro", 1)),
                "planner": a.planner,
                "budget_decision": self.rnd.get("budget_decision"),
                "budget_outcome": budget_outcome,
                "network_decision": self.rnd.get("network_decision"), "route_receipts": network_receipts,
                "per_client": {k: [v[0], round(v[1], 3), v[2], round(v[3], 3)] for k, v in obs.items()},
                "per_client_detail": detail}) + "\n")
            logf.flush()
            print(f"R{r:2d} {a.policy:8s} makespan {makespan:6.2f}s acc {acc*100:5.2f}% "
                  f"경과 {el:7.1f}s  plan {[st.plan[k] for k in self.ids]}", flush=True)
        st.stop = True
        self.barrier.wait()
        for s in sessions:
            s.join()
        logf.write(json.dumps({"summary": True, "policy": a.policy, "tta": tta,
                               "total": round(time.perf_counter() - t_start, 2), "final_acc": acc}) + "\n")
        logf.close()
        try:
            self.sensor.save(a.log.replace(".jsonl", "") + ".profile.json")   # 인지 결과 — 값마다 출처
        except OSError:
            pass
        if st.chunks:
            st.chunks.close()


def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", default="0.0.0.0", help="서버 수신 주소. 로컬 검증은 127.0.0.1")
    ap.add_argument("--port", type=int, default=30000)
    ap.add_argument("--clients", type=int, required=True)
    ap.add_argument("--rounds", type=int, default=12)
    ap.add_argument("--batches", type=int, default=4)
    ap.add_argument("--cut", type=int, default=2)
    ap.add_argument("--arch", default="cnn", choices=["cnn", "vit"])
    ap.add_argument("--norm", default="bn", choices=["bn", "gn"], help="정규화: bn(기본) / gn(GroupNorm — 즉시 내보내기·폭 혼합 대책)")
    ap.add_argument("--lr", type=float, default=0.05)
    ap.add_argument("--lr-decay", default="none", choices=["none", "cosine", "step"],
                    help="라운드에 따른 학습률 감쇠. 수렴 근처까지 가려면 cosine 을 쓴다")
    ap.add_argument("--lr-min", type=float, default=0.001, help="cosine 의 바닥값")
    ap.add_argument("--policy", default="uniform", choices=list(POLICY_NAMES))
    ap.add_argument("--pipeline", default="off", choices=["off", "on", "auto"],
                    help="깊이 2 파이프라인 — 정확도 대가가 있어 기본 끔 (예비)")
    ap.add_argument("--ladder", default="", help="폭 사다리, 예 '0.5,0.75,1.0'. 비우면 LADDER. 절제: '1.0' = 경로만")
    ap.add_argument("--max-moves", type=int, default=1, help="라운드당 경로 이동 허용 수. 0 = 폭만")
    ap.add_argument("--planner", default="two-stage", choices=["two-stage", "two-stage-v1", "joint", "plan", "device-budget"],
                    help="widthpath 계획기. plan = 인지·계획·집행 3층(plan.py: 총비용 열린 경로 집합 + 분할 전송 + B안 기준선, 2026-09-07). "
                         "two-stage = 병목 유형 우선(2026-09-06). two-stage-v1 = 구판(경로 먼저). joint = 완전탐색 (비교용). "
                         "device-budget = 기기 연산 예산 내 최대 폭 + 허용 종점 배정 (실험용)")
    ap.add_argument("--compute-budget-s", type=float, default=None,
                    help="device-budget: 기기별 라운드 순·역전파 시간 예산(초). 예측 기준이며 CPU/메모리 강제 한도 아님")
    ap.add_argument("--access-mode", choices=["shared", "independent"], default="shared",
                    help="device-budget 전용: shared=공유 접속망(기본), independent=독립 접속 회선 2개를 명시")
    ap.add_argument("--fixed-weights", default="1,1", help="fixed2 정책: 출구 A·B 고정 분할 비율, 예 '5,2' (접속 상한 비율)")
    ap.add_argument("--multipath", action="store_true", help="분할 전송 허용 — 조각 수신기를 주 포트+1 에 띄우고, 계획 층이 열린 경로 2개를 줄 수 있다 (클라는 --bind 주소 2개)")
    ap.add_argument("--edges", default="", help="실회선 리그: 엣지별 데이터 종점 '1=116.89.187.190:12000,2=116.89.187.190:12500,...'. "
                    "클라 i 출구 x 의 포트 = base + 2i + x. 있으면 모든 페이로드가 조각 채널로 엣지를 지나고, 엣지 변경은 재접속")
    ap.add_argument("--micro", type=int, default=1, help="즉시 내보내기: 배치를 m 조각으로 잘라 계산되는 즉시 보낸다 (1=끔). 갱신은 배치 끝에 한 번")
    ap.add_argument("--micro-window", type=int, default=2, help="동시에 기울기 응답을 기다릴 마이크로배치 수 상한")
    ap.add_argument("--network-topology", default="", help="network 정책: 공유 병목 JSON. configs/network_topology.example.json 참고")
    ap.add_argument("--solo", action="store_true", help="사전 진단 ② 단독 업로드 프로브로 접속 회선 상한을 실측한다 (오라클 --access-caps 보다 우선)")
    ap.add_argument("--deadline-s", type=float, default=None, help="고정 라운드 목표(초), --deadline fixed 와 함께 (opt 에서는 선택 제약)")
    ap.add_argument("--lam", type=float, default=None, help="opt: 정확도 가격 λ (초/평균폭 1). 평균 폭 1 을 잃는 대신 라운드를 몇 초 줄이면 본전인가")
    ap.add_argument("--init-sets", default="1", choices=["1", "rr"], help="실회선 초기 배정: 1 = 전원 엣지 1(혼잡 시작), rr = 엣지에 고르게(정상 시작)")
    ap.add_argument("--edge-groups", default="", help="기기별 허용 엣지 '3,4:0-3;1,2:4-7' (VM 클라 모드: 같은 VM 의 엣지는 lo 라 tc 가 안 걸려 다른 VM 엣지만 허용)")
    ap.add_argument("--deadline", default="anchored", choices=["anchored", "relative", "solo", "fixed", "peer", "opt"],
                    help="폭 기준선. anchored(B안, 기본) = 시작 상태 중앙값, 경로 이동으로 조이지 않음. relative(A안) = 현재 배정 중앙값 (정확도 대가 비교용)")
    ap.add_argument("--access-caps", default="", help="기기별 접속 회선 용량 Mbps, 예 'c0=35,c1=22'. hairpin 리그 검증용 오라클 — 비우면 모형에 접속 회선 항 없음")
    ap.add_argument("--stagger", default="off", choices=["off", "fixed", "auto"])
    ap.add_argument("--stagger-gap", type=float, default=0.5, help="--stagger fixed 일 때 클라 간 등간격 시작 지연(초)")
    ap.add_argument("--preflight", action="store_true", help="학습 전 사전 진단 — 첫 라운드부터 배정이 서게 한다")
    ap.add_argument("--paths", default="", help="경로 용량 Mbps, 예: '100,20' (경로 번호 1..M 순)")
    ap.add_argument("--switch-cost", type=float, default=0.0, help="경로 전환 비용(초). 실측 0.045")
    ap.add_argument("--path-exec", default="", help="경로 이동 집행 명령 틀 — {assign} 에 '1 1 1 2' 꼴 배정 대입")
    ap.add_argument("--alpha", type=float, default=1.2)
    ap.add_argument("--oracle-plan", default="")
    ap.add_argument("--target", type=float, default=0.35)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--data", default="data/cifar10")
    ap.add_argument("--log", default="out/fed.jsonl")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--perturb-at", type=int, default=-1, help="이 라운드 시작 시 --perturb-cmd 실행 (교란 주입)")
    ap.add_argument("--perturb-cmd", default="")
    a = ap.parse_args(argv)
    if a.micro < 1 or a.micro_window < 1:
        ap.error("--micro and --micro-window must be positive")
    from device_budget import validate_options
    try:
        validate_options(a)
    except (ValueError, TypeError) as exc:
        ap.error(str(exc))
    return a


def main(argv=None):
    a = parse_args(argv)
    models.set_norm(a.norm)
    Server(a).run()


if __name__ == "__main__":
    main()
