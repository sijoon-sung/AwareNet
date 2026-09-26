# -*- coding: utf-8 -*-
"""라운드 기반 분할 연합학습 클라이언트.

  RSTART 로 받은 폭 p 와 전역 가중치 슬라이스로 앞단을 세우고 B배치 학습, 라운드 끝에 앞단 가중치를
  올린다(WUP). 데이터는 CIFAR-10 을 Dirichlet 로 나눈 자기 몫만 본다(non-IID).

  구성
    Link      서버와의 연결 하나 (bind 주소 고정 지원). 엣지 여러 곳에 붙는 다중 연결은 여기서 확장한다.
    Client    데이터·모델·라운드 반복. 배치 왕복은 _batch(), 깊이 2 파이프라인은 _batch_pipelined() (예비)
"""
import argparse
import io
import json
import os
import socket
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import torch

from controller_multi import effective_quant
from models import ClientNet as CnnClient
from mpsend import ChunkLinks
from sense import solo_reply
from proto import (ACT, BYE, GRAD, HELLO, PROBE, PROBERES, RSTART, SOLO, WUP,
                   b2sd, b2t, recv_msg, sd2b, send_msg, t2b)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def slowed(dt, speed):
    """연산 시간 dt 를 속도 비율 speed(0<speed≤1) 의 기기가 걸렸을 시간으로 늘린다 — 부족분만큼 실제로 쉰다.

    Aergia(Middleware 2022)는 Docker 로 CPU 속도를 0.1~1.0 균등분포로 뽑아 이질성을 만들었고
    "0.25·0.5·0.75·1.0 같은 계단은 비현실적" 이라고 했다. 우리는 같은 분포를 응용 계층 감속(MP-SL 방식)으로
    낸다. 컨트롤러가 보는 것은 '연산에 걸린 시간' 이므로 두 방식은 관측상 같고, 이쪽이 호스트 부하와 무관해
    재현이 정확하다. 반환값이 보고할 연산 시간이다."""
    if speed >= 1.0 or dt <= 0:
        return dt
    extra = dt * (1.0 / speed - 1.0)
    time.sleep(extra)
    return dt + extra


def make_client(arch, p, cut, vit_cfg="small"):
    if arch == "vit":
        from models_vit import ViTClient
        return ViTClient(p, cut, vit_cfg)
    return CnnClient(p, cut)


def dirichlet_shard(n_clients, cid, labels, alpha, seed):
    """라벨 분포를 Dirichlet(alpha)로 기울여 클라별 인덱스를 나눈다."""
    rng = np.random.default_rng(seed)
    by_class = {c: rng.permutation(np.where(labels == c)[0]) for c in range(10)}
    shards = [[] for _ in range(n_clients)]
    for c, pool in by_class.items():
        prop = rng.dirichlet([alpha] * n_clients)
        cuts = (np.cumsum(prop) * len(pool)).astype(int)[:-1]
        for i, part in enumerate(np.split(pool, cuts)):
            shards[i] += part.tolist()
    return shards[cid]


class Link:
    """서버 연결 하나. 소스 주소를 고정해야 tc 가 클라를 구분한다."""

    def __init__(self, server, bind=""):
        host, port = server.split(":")
        last = None
        for attempt in range(60):                                  # 서버가 아직 안 듣거나(기동 중) 터널 너머가 닫혀 있으면 1초 간격으로 60초 재시도 (VM 클라 모드, 2026-09-12)
            try:
                if bind:
                    self.sock = socket.socket()
                    self.sock.bind((bind, 0))
                    self.sock.connect((host, int(port)))
                else:
                    self.sock = socket.create_connection((host, int(port)))
                break
            except OSError as e:
                last = e; time.sleep(1.0)
        else:
            raise ConnectionError(f"서버 연결 실패 {server}: {last}")
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def send(self, kind, meta=None, payload=b""):
        return send_msg(self.sock, kind, meta, payload)

    def recv(self):
        return recv_msg(self.sock)

    def close(self):
        self.sock.close()


class Client:
    def __init__(self, a):
        self.a = a
        if a.threads > 0:
            torch.set_num_threads(a.threads)
        torch.manual_seed(a.seed + a.index)
        self.loader = self._data()
        self.it = iter(self.loader)
        # 출발 주소(출구)는 쉼표로 여러 개 — 첫 번째가 주 연결, 둘 이상이면 분할 전송(mpsend) 출구가 된다
        self.exits = [b for b in a.bind.split(",") if b] if a.bind else []
        self.link = Link(a.server, self.exits[0] if self.exits else "")
        self.chunk_links = None                       # 출구별 조각 연결 — 첫 분할 전송 때 열고 끝까지 재사용 (규칙 1)
        self.dp = None                                # 실회선 리그: 출구별 데이터 종점 [[host, port], ...] (서버가 준다). 바뀌면 재접속 = 엣지 변경
        self.srv_host, self.srv_port = a.server.split(":")[0], int(a.server.split(":")[1])
        self.mp_round = False                                    # 이번 라운드 분할 전송 여부 (서버 지시)
        self._r = 0
        self._nb = 0
        self.logf = io.open(a.log, "w", encoding="utf-8") if a.log else None

    def _data(self):
        import torchvision
        import torchvision.transforms as T
        a = self.a
        aug = [T.RandomCrop(32, padding=4), T.RandomHorizontalFlip()] if a.augment else []
        tf = T.Compose(aug + [T.ToTensor(), T.Normalize((.49, .48, .45), (.25, .24, .26))])
        ds = torchvision.datasets.CIFAR10(a.data, train=True, transform=tf)
        mine = dirichlet_shard(a.clients, a.index, np.array(ds.targets), a.alpha_dir, a.seed)
        g = torch.Generator().manual_seed(a.seed + a.index)
        return torch.utils.data.DataLoader(torch.utils.data.Subset(ds, mine), batch_size=a.batch_size,
                                           shuffle=True, generator=g, drop_last=True)

    def _next(self):
        try:
            return next(self.it)
        except StopIteration:
            self.it = iter(self.loader)
            return next(self.it)

    # ── 메시지 루프 ──────────────────────────────────────────
    def run(self):
        first = None
        for attempt in range(120):   # VM 클라 모드: 서버가 아직 안 들으면 터널의 sshd 가 연결을 받았다가 바로 닫는다(연결은 성공, 첫 수신에서 끊김) → HELLO 부터 1초 간격 재시도 (2026-09-12)
            try:
                self.link.send(HELLO, {"id": self.a.id})
                first = self.link.recv()
                break
            except (ConnectionError, OSError) as e:
                if attempt >= 119:
                    raise ConnectionError(f"서버 핸드셰이크 실패 {self.a.server}: {e}")
                try: self.link.close()
                except OSError: pass
                time.sleep(1.0)
                self.link = Link(self.a.server, self.exits[0] if self.exits else "")
        while True:
            kind, meta, payload, _ = first if first is not None else self.link.recv()
            first = None
            if kind == BYE:
                break
            if kind == PROBE:
                self.sync_compute = bool(meta.get("sync_compute", False))
                self._probe()
                continue
            if kind == SOLO:                                     # 인지: 단독 업로드 프로브 (sense.py)
                if meta.get("dp"):
                    self._set_dp(meta["dp"])
                n_ex = len(self.dp) if self.dp else len(self.exits)
                solo_reply(self.link, meta, list(range(n_ex)) if self.dp else self.exits,        # dp 모드: 출구 수만 필요
                           (self.srv_host, self.srv_port + 1), self._links() if self.dp else None, cid=self.a.id)
                continue
            assert kind == RSTART
            self._round(meta, payload)
        if self.logf:
            self.logf.close()
        if self.chunk_links is not None:
            self.chunk_links.close()
        self.link.close()

    def _sync_compute(self):
        """Complete CUDA work for the opt-in serial compute-budget timer."""
        if getattr(self, "sync_compute", False) and torch.device(self.a.device).type == "cuda":
            torch.cuda.synchronize(self.a.device)

    def _probe(self):
        """사전 진단: 전폭 한 배치의 계산 시간을 재고 실제 활성값을 올려 회선을 재게 한다."""
        a = self.a
        t_recv = time.perf_counter()
        pnet = make_client(a.arch, 1.0, a.cut).to(a.device)
        x, y = self._next()
        self._sync_compute()
        t0 = time.perf_counter()
        out = pnet(x.to(a.device))
        self._sync_compute()
        t_fwd = slowed(time.perf_counter() - t0, a.speed)
        t0 = time.perf_counter()
        out.backward(gradient=torch.randn_like(out))
        self._sync_compute()
        t_bwd = slowed(time.perf_counter() - t0, a.speed)
        am, ab = t2b(out.detach())
        self.link.send(PROBERES, {"t_fwd": round(t_fwd, 5), "t_bwd": round(t_bwd, 5),
                                  "t_local": round(time.perf_counter() - t_recv, 5),
                                  "act": am, "n": len(y)}, ab)

    def _round(self, meta, payload):
        a = self.a
        p, B, r = meta["p"], meta["batches"], meta["round"]
        self.sync_compute = bool(meta.get("sync_compute", False))
        self.micro_window = max(1, int(meta.get("micro_window", 2)))
        self.traffic = {"activation_messages": 0, "activation_payload_bytes": 0,
                        "activation_main_channel_bytes": 0, "activation_send_s": 0.0,
                        "max_inflight_microbatches": 0, "exchange_completion_s": [], "batch_compute": []}
        from collections import deque
        self._exchange_started = deque()
        # 양자화 우선순위: 서버 지시(>0) > CLI 강제값. 서버의 0 은 '지시 없음'이다 (R5-Q 결함의 수정)
        quant = effective_quant(meta.get("quant", 0), a.quant)
        depth = int(meta.get("depth", 1))
        micro = max(1, int(meta.get("micro", 1)))               # 즉시 내보내기: 배치를 m 조각으로 잘라 조각 i 전송과 조각 i+1 연산을 겹친다
        delay = float(meta.get("start_delay", 0.0))
        if meta.get("dp"):
            self._set_dp(meta["dp"])                                      # 엣지 종점 갱신 — 바뀌었으면 데이터 연결을 다시 연다
        n_exit = len(self.dp) if self.dp else len(self.exits)
        self.mp_round = bool(meta.get("mp")) and (n_exit >= 2 or self.dp is not None)   # dp 모드면 출구 1개여도 채널로 보낸다
        self.mp_w = meta.get("mp_w")                                      # 출구별 예상 속도 → 조각 배분 가중치 (규칙 3′)
        self._r, self._nb = r, 0
        if delay > 0:
            time.sleep(delay)                                   # 전송 시차 집행 (동시 몰림 회피)
        net = make_client(a.arch, p, a.cut).to(a.device)
        net.load_state_dict(b2sd(meta["w"], payload))
        opt = torch.optim.SGD(net.parameters(), lr=float(meta.get("lr", a.lr)), momentum=0.9)

        seen, comp = 0, 0.0
        tsum = [0.0, 0.0, 0.0]                                  # 순전파 / GRAD 대기 / 역전파 합
        for batch_index in range(B):
            self._batch_index = batch_index
            x, y = self._next()
            if micro >= 2 and len(y) >= micro:
                t_fwd, t_wait, t_bwd, loss = self._batch_micro(net, opt, x, y, quant, micro)
            else:
                step = self._batch_pipelined if (depth >= 2 and len(y) >= 2) else self._batch
                t_fwd, t_wait, t_bwd, loss = step(net, opt, x, y, quant)
            comp += t_fwd + t_bwd
            tsum[0] += t_fwd; tsum[1] += t_wait; tsum[2] += t_bwd
            self.traffic["batch_compute"].append({"batch_index": batch_index,
                "forward_s": t_fwd, "backward_s": t_bwd, "wait_s": t_wait,
                "requested_micro": micro, "samples": len(y)})
            seen += len(y)
            if self.logf:
                self.logf.write(json.dumps({"r": r, "p": p, "depth": depth, "t_fwd": round(t_fwd, 5),
                                            "t_wait": round(t_wait, 5), "t_bwd": round(t_bwd, 5),
                                            "loss": loss}) + "\n")
        m, b = sd2b(net.state_dict())
        exits = None
        if self.chunk_links is not None:
            self.chunk_links.flush()                            # 규칙 7: 이번 라운드 전송들의 완료 회신을 여기서 모아 확인
        if self.chunk_links is not None:                       # 출구별 누적 바이트 (이번 라운드 몫 = 누적 − 지난 라운드 누적)
            cur = self.chunk_links.exit_stats()
            prev = getattr(self, "_exit_prev", None) or [{"up": 0, "dn": 0, "up_t": 0.0, "dn_t": 0.0} for _ in cur]
            exits = [{"up": a["up"] - b_["up"], "dn": a["dn"] - b_["dn"],
                      "up_t": round(a.get("up_t", 0.0) - b_.get("up_t", 0.0), 4), "dn_t": round(a.get("dn_t", 0.0) - b_.get("dn_t", 0.0), 4)}
                     for a, b_ in zip(cur, prev)]
            self._exit_prev = cur
        self.link.send(WUP, {"round": r, "n": seen, "comp": round(comp, 4),
                             "compute_timer": ("cuda_synchronized" if getattr(self, "sync_compute", False)
                                               and torch.device(a.device).type == "cuda" else "host_elapsed"),
                             "compute_device": a.device, "compute_speed": a.speed,
                             "traffic": self.traffic,
                             "route_receipt": {"epoch": meta.get("route_epoch"), "endpoints": [list(x) for x in (self.dp or [])],
                                               "active_exits": [i for i, e in enumerate(exits or []) if e["up"] + e["dn"] > 0]},
                             "t_fwd": round(tsum[0], 4), "t_wait": round(tsum[1], 4),
                             "t_bwd": round(tsum[2], 4), "exits": exits, "w": m}, b)

    def _batch(self, net, opt, x, y, quant):
        """직렬 왕복: 순전파 → 활성값 올림 → 기울기 대기 → 역전파. 반환 (t_fwd, t_wait, t_bwd, loss)."""
        dev = self.a.device
        self._sync_compute()
        t0 = time.perf_counter()
        out = net(x.to(dev))
        self._sync_compute()
        t_fwd = slowed(time.perf_counter() - t0, self.a.speed)
        am, ab = t2b(out, quant=quant)
        ym, yb = t2b(y)
        self._send_act(am, ab, ym, yb, quant)
        t1 = time.perf_counter()
        kind, gm, gb, _ = self.link.recv()
        gb = self._grad_payload(gm, gb)
        t_wait = time.perf_counter() - t1
        assert kind == GRAD
        t2 = time.perf_counter()
        opt.zero_grad()
        out.backward(gradient=b2t(gm["g"], gb).to(dev))
        opt.step()
        self._sync_compute()
        return t_fwd, t_wait, slowed(time.perf_counter() - t2, self.a.speed), gm["loss"]

    def _set_dp(self, dp):
        """서버가 준 출구별 데이터 종점. 달라졌으면(엣지 변경) 열린 조각 연결을 닫는다 — 다음 전송 때 새 종점으로 다시 연다."""
        dp = [tuple(x) for x in dp]
        if dp != self.dp:
            print(f"   [{self.a.id}] 엣지 종점 변경 {self.dp} → {dp} — 데이터 연결 다시 연다", flush=True)
            if self.chunk_links is not None:
                try:
                    self.chunk_links.flush(timeout=30)
                except OSError:
                    pass
                self.chunk_links.close()
                self.chunk_links = None
                self._exit_prev = None                             # 출구별 누적 바이트도 처음부터
            self.dp = dp

    def _links(self):
        """조각 채널 (규칙 1: 한 번 열어 재사용). dp 모드면 출구별 (엣지 host, port); 아니면 서버 조각 포트 + 출구 주소."""
        if self.chunk_links is None:
            print(f"   [{self.a.id}] 조각 채널 열기: {self.dp or self.exits}", flush=True)
            if self.dp:
                eps = [(h, p, (self.exits[i] if i < len(self.exits) else None)) for i, (h, p) in enumerate(self.dp)]
                self.chunk_links = ChunkLinks(self.srv_host, self.srv_port + 1, self.exits, endpoints=eps)
            else:
                self.chunk_links = ChunkLinks(self.srv_host, self.srv_port + 1, self.exits)
        return self.chunk_links

    def _grad_payload(self, gm, gb):
        """기울기 페이로드 — 서버가 조각으로 내려보냈으면(메타 mp) 조각 연결에서 완성본을 기다린다 (규칙 5)."""
        if gm.get("mp") and self.chunk_links is not None:
            gb = self.chunk_links.wait(gm["mp"])
        if getattr(self, "_exchange_started", None) and hasattr(self, "traffic"):
            self.traffic.setdefault("exchange_completion_s", []).append(
                time.perf_counter() - self._exchange_started.popleft())
        return gb

    def _send_act(self, am, ab, ym, yb, quant, extra=None):
        """활성값 하나를 보낸다 — 분할 전송이면 메타는 주 연결, 페이로드는 출구들로 조각내어 조각 포트로."""
        meta = {"act": am, "act_bytes": len(ab), "y": ym, "quant": quant,
                "batch_index": getattr(self, "_batch_index", None)}
        meta.update(extra or {})
        self._nb += 1
        t0 = time.perf_counter()
        if hasattr(self, "traffic"):
            if not hasattr(self, "_exchange_started"):
                from collections import deque
                self._exchange_started = deque()
            self._exchange_started.append(t0)
        if self.mp_round:
            tid = f"{self.a.id}-{self._r}-{self._nb}"
            meta["mp"] = tid
            main_bytes = self.link.send(ACT, meta)
            self._links().send(ab + yb, tid, cid=self.a.id, weights=self.mp_w)
        else:
            main_bytes = self.link.send(ACT, meta, ab + yb)
        if hasattr(self, "traffic"):
            self.traffic["activation_messages"] += 1
            self.traffic["activation_payload_bytes"] += len(ab) + len(yb)
            self.traffic["activation_main_channel_bytes"] += main_bytes
            self.traffic["activation_send_s"] += time.perf_counter() - t0

    def _batch_micro(self, net, opt, x, y, quant, m):
        """즉시 내보내기 (교수님 제안, 문헌 C²P²SL): 배치를 m 조각으로 잘라 조각 i 의 활성값을 **계산되는 즉시** 보내고
        조각 i+1 을 계산한다. 기울기는 서버에서 표본 수로 가중된 값을 그대로 사용한다.
        미회신 조각 수는 micro_window로 제한한다. BN이나 다른 클라의 서버 갱신이 섞이면 직렬과 동등하지 않을 수 있다.
        (구판 depth 파이프라인은 서버가 조각마다 갱신해 정확도 대가가 있었다. 지금은 서버도 배치 끝에 한 번 갱신: meta micro/of)"""
        dev = self.a.device
        xs, ys = x.chunk(m), y.chunk(m)
        m = len(xs)
        # ★ 기울기는 별도 스레드가 받는다. 보내기만 하고 안 읽으면 서버는 GRAD 를 보내다 막히고(소켓 버퍼),
        #   우리는 다음 ACT 를 보내다 막혀 서로 기다리는 교착이 난다 (2026-09-07 로컬 스모크에서 실제로 걸림).
        import queue
        q = queue.Queue()
        def _recv_all():
            for _ in range(m):
                try:
                    q.put(self.link.recv())
                except OSError as e:
                    q.put(e); return
        th = threading.Thread(target=_recv_all, daemon=True); th.start()
        from collections import deque
        pending = deque()
        t_fwd = t_wait = t_bwd = loss = 0.0
        opt.zero_grad()
        window = min(m, max(1, getattr(self, "micro_window", 2)))

        def receive_one():
            nonlocal t_wait, t_bwd, loss
            t1 = time.perf_counter()
            try:
                got = q.get(timeout=300)
            except queue.Empty as exc:
                raise OSError("microbatch gradient timed out") from exc
            if isinstance(got, Exception):
                raise got
            kind, gm, gb, _ = got
            gb = self._grad_payload(gm, gb)
            t_wait += time.perf_counter() - t1
            assert kind == GRAD
            out, count = pending.popleft()
            self._sync_compute()
            t2 = time.perf_counter()
            # micro_step already multiplied by count / full_batch_size.
            out.backward(gradient=b2t(gm["g"], gb).to(dev))
            self._sync_compute()
            t_bwd += slowed(time.perf_counter() - t2, self.a.speed)
            loss += gm["loss"] * count / len(y)

        for i in range(m):
            self._sync_compute()
            t0 = time.perf_counter()
            out = net(xs[i].to(dev))
            self._sync_compute()
            t_fwd += slowed(time.perf_counter() - t0, self.a.speed)
            pending.append((out, len(ys[i])))
            if hasattr(self, "traffic"):
                self.traffic["max_inflight_microbatches"] = max(self.traffic["max_inflight_microbatches"], len(pending))
            am, ab = t2b(out, quant=quant)
            ym, yb = t2b(ys[i])
            self._send_act(am, ab, ym, yb, quant, {"micro": i, "of": m, "batch_n": len(y)})
            if len(pending) >= window:
                receive_one()
        while pending:
            receive_one()
        opt.step()
        th.join(timeout=1)
        return t_fwd, t_wait, t_bwd, loss

    def _batch_pipelined(self, net, opt, x, y, quant):
        """깊이 2 파이프라인 (예비): 배치를 반으로 갈라 조각 1을 올리는 동안 조각 2를 계산한다.
        갱신은 배치 경계에서 한 번 — 조각별 기울기를 0.5 배로 누적하므로 직렬과 갱신 의미가 같다.
        서버 뒷단은 조각 단위로 갱신된다. J 시리즈 실측에서 정확도 대가가 있어 기본 끔."""
        dev = self.a.device
        xs, ys = x.chunk(2), y.chunk(2)
        outs, t_fwd = [], 0.0
        for i in range(2):
            t0 = time.perf_counter()
            outs.append(net(xs[i].to(dev)))
            t_fwd += slowed(time.perf_counter() - t0, self.a.speed)
            am, ab = t2b(outs[i], quant=quant)
            ym, yb = t2b(ys[i])
            self.link.send(ACT, {"act": am, "act_bytes": len(ab), "y": ym, "quant": quant}, ab + yb)
        t_wait = t_bwd = 0.0
        opt.zero_grad()
        loss = 0.0
        for i in range(2):
            t1 = time.perf_counter()
            kind, gm, gb, _ = self.link.recv()
            t_wait += time.perf_counter() - t1
            assert kind == GRAD
            t2 = time.perf_counter()
            outs[i].backward(gradient=b2t(gm["g"], gb).to(dev) * 0.5)
            t_bwd += slowed(time.perf_counter() - t2, self.a.speed)
            loss = gm["loss"]
        opt.step()
        return t_fwd, t_wait, t_bwd, loss


def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="127.0.0.1:30000")
    ap.add_argument("--bind", default="", help="자기 주소 고정 (회선 이질성 식별용). 쉼표로 2개면 분할 전송 출구 2개 (예 127.0.0.1,127.0.1.1)")
    ap.add_argument("--id", required=True)
    ap.add_argument("--index", type=int, required=True)
    ap.add_argument("--clients", type=int, required=True)
    ap.add_argument("--cut", type=int, default=2)
    ap.add_argument("--arch", default="cnn", choices=["cnn", "vit"])
    ap.add_argument("--norm", default="bn", choices=["bn", "gn"], help="정규화 — 서버와 같아야 한다")
    ap.add_argument("--quant", type=int, default=0, choices=[0, 8], help="활성값 8비트 양자화 (0=끔). 예비")
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--lr", type=float, default=0.05)
    ap.add_argument("--alpha-dir", type=float, default=0.5, help="Dirichlet non-IID")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--speed", type=float, default=1.0,
                    help="연산 속도 비율 (0<speed≤1). 1 미만이면 부족분만큼 쉬어 느린 기기를 흉내 낸다 (Aergia 분포용)")
    ap.add_argument("--threads", type=int, default=0,
                    help="이 클라가 쓸 CPU 스레드 수 (0=torch 기본). 클라가 여럿이면 코어수÷클라수로 나눠야 한다")
    ap.add_argument("--data", default="data/cifar10")
    ap.add_argument("--augment", action="store_true", help="학습 데이터 증강 — 수렴 근처 비교용, 기본 끔")
    ap.add_argument("--log", default="")
    ap.add_argument("--seed", type=int, default=1)
    return ap.parse_args(argv)


def main(argv=None):
    a = parse_args(argv)
    import models
    models.set_norm(a.norm)
    Client(a).run()


if __name__ == "__main__":
    main()
