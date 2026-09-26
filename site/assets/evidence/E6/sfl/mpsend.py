# -*- coding: utf-8 -*-
"""분할 전송 — 출구가 2개인 기기의 **양방향** 조각 채널 (설계: docs/04_설계기록/설계_멀티패스_분할전송.md §13).

  규칙 (알고리즘 — 땜질 금지, 바꾸려면 §13 표와 시험을 먼저 고친다)
    1. 상시 연결   출구마다 연결 1개를 재사용 (ChunkLinks). 새 연결 비용을 줄이며 TCP의 idle 후 혼잡창 축소는 별개다.
    2. 조각 크기   clamp(페이로드 / (CHUNKS_PER_CONN × 연결 수), 64KiB, 1MiB)  (chunker.chunk_size_for; 현재 16)
    3. 배정        몫은 계획 층의 출구별 예상 속도 비율로 먼저 나누고(3′), 그 안에서 먼저 한가한 연결이 다음 조각, 꼬리는 실측 속도로 (chunker.Scheduler)
    4. 재조립      조각 번호로 중복 제거, 완료 신호는 남은 조각을 기다렸다 답함 (chunker.Reassembler)
    5. 양방향      올리는 활성값도, 내려오는 기울기도 같은 연결들로 나눠 보낸다 (2026-09-07 스모크: 내려받기가 주 링크 한 가닥에
                   묶여 있으면 접속 회선 두 가닥의 이득이 사라진다 — 왕복 트래픽의 절반이 분할을 못 받는다).
    6. 배압        조각 연결의 송신 버퍼를 256KB 로 묶는다. 커널 버퍼가 크면 느린 출구도 "보냈다"가 즉시 돌아와 규칙 3 이 속도를 못 본다.
    7. 비동기 회신 완료 회신을 동기로 기다리면 전송마다 왕복 1번(30ms) — 즉시 내보내기(라운드당 32전송)에서 ~1s. 다음 전송 때 확인, 라운드 끝 flush.
    10. 닫기 알림  연결을 닫을 때 bye 를 먼저 보낸다. 가중치에 없는 출구의 연결에는 조각을 주지 않는다 (재접속으로 출구가 줄면 옛 연결 배제).
    9. 출구당 하나  (기기, 출구)당 산 연결은 하나. 같은 출구로 새 연결이 붙으면 옛 연결은 끊긴 것으로 본다 (터널은 상대의 닫힘을 늦게 알린다).
    8. 비동기 송신 서버의 내려보내기는 기기별 송신 스레드에 넘긴다. 세션 스레드가 send 안에서 송신 버퍼(256KB)가 비기를 기다리면
                   다음 조각(다음 마이크로배치)의 처리가 그만큼 늦어진다 (h5x 실측: 분할 기기 효율 64% vs 채널 벤치 85%).

  구조
    ChunkPeer   연결 여러 개 위의 양방향 채널. send(blob, tid) 와 wait(tid) 를 동시에. 연결마다 읽기 스레드가
                데이터 조각 → 재조립, 완료 신호 → (기다렸다) 회신, 회신 → 보낸 쪽 깨우기 를 나눠 처리한다.
    ChunkLinks  클라 쪽: 출구 주소들로 서버 조각 포트에 연결해 ChunkPeer 를 만든다. 죽은 연결은 다음 전송 때 재개.
    ChunkServer 서버 쪽: 조각 포트에서 연결을 받아 기기(cid)별 ChunkPeer 에 붙인다. wait(tid) / send_back(cid, blob, tid).
    send_multipath(...)  한 번짜리 (연결 열고 닫음) — 단독 프로브 등.

  메시지 (모두 proto.CHUNK): 데이터 {tid,cid,seq,off,ln,total} / 완료 {tid,cid,fin:1,total} / 회신 {tid,ack:1,got}
"""
import socket
import threading
import time

from chunker import Reassembler, Scheduler, chunk_size_for, split
from proto import CHUNK, recv_msg, send_msg

FIN_ACK_TIMEOUT = 120.0        # 완료 회신을 기다리는 한도(초)
SNDBUF = 256 << 10             # 규칙 6: SO_SNDBUF 요청 256KiB. Linux는 상한·내부 배수를 적용하므로 실제 값은 getsockopt로 확인해야 한다.
                               #   (자동 조정 4MB 면 느린 출구도 sendall 이 즉시 돌아와 빠른 척한다 → 20Mbps 출구가 45% 를 떠안았다, 2026-09-07 스모크)
                               #   256KB ≥ BDP(50Mbps×30ms=187KB, KOREN 500Mbps×4ms=250KB) 라 빠른 링크도 굶지 않는다


def _span(c, d, tid, t0=None):
    """연결 c 의 방향 d("up"/"dn") 활동 구간 누적: 전송(tid)이 바뀌면 지난 전송의 (마지막 − 처음)을 더하고 새 전송을 연다.
    한 전송 안에서 조각들은 경로 속도대로 이어지므로 첫 조각 시작~마지막 조각 끝이 그 출구의 실제 활동 시간이다 (마지막 조각의 소켓 버퍼 몫만 못 잰다, 규칙 6 SNDBUF 만큼)."""
    now = time.perf_counter()
    if c.get(d + "_tid") != tid:
        if c.get(d + "_tid") is not None:
            c[d + "_t"] += max(0.0, c[d + "_last"] - c[d + "_t0"])
        c[d + "_tid"] = tid; c[d + "_t0"] = t0 if t0 is not None else now
    c[d + "_last"] = now


def _span_total(c, d):
    """누적 활동 구간 + 아직 열려 있는 전송의 구간 (스냅숏)."""
    open_ = max(0.0, c[d + "_last"] - c[d + "_t0"]) if c.get(d + "_tid") is not None else 0.0
    return c[d + "_t"] + open_


class ChunkPeer:
    """연결 여러 개 위의 양방향 조각 채널 (클라·서버 공용)."""

    def __init__(self, name="peer", re=None, done=None, lock=None):
        self.name = name
        self.conns = []                       # {"label","sock","bytes_up","bytes_dn","busy","dead"}
        self.re = re if re is not None else Reassembler()
        self.done = done if done is not None else {}          # tid → Event (완성)
        self.acks = {}                                        # tid → {"ev": Event, "got": int, "total": int}  (완료 회신 대기 — 비동기)
        self.lock = lock if lock is not None else threading.Lock()
        self.closed = False

    # ── 연결 관리 ───────────────────────────────────────────
    def attach(self, sock, label, first=None, exit_idx=None):
        """연결을 채널에 붙이고 읽기 스레드를 띄운다. first: 이미 읽어 둔 첫 메시지 (서버가 cid 를 알아내려고 먼저 읽는다).
        exit_idx: 이 연결이 기기의 몇 번째 출구인가 (가중치 매핑용)."""
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, SNDBUF)   # 규칙 6 (양쪽 다: 클라 올리기·서버 내려보내기)
        c = {"label": label, "sock": sock, "bytes_up": 0, "bytes_dn": 0, "busy": 0.0, "dead": False,
             "slock": threading.Lock(), "exit": exit_idx,                       # 소켓 쓰기 잠금 — 조각(작업 스레드)과 회신(읽기 스레드)이 겹치지 않게
             "up_t": 0.0, "up_tid": None, "up_t0": 0.0, "up_last": 0.0,        # 출구별 활동 구간(초): 한 전송(tid)의 첫 조각 시작 ~ 마지막 조각 끝 (2026-09-10 §13-5)
             "dn_t": 0.0, "dn_tid": None, "dn_t0": 0.0, "dn_last": 0.0}        #   인지층이 흐름별 실효율(바이트/활동 시간)로 엣지 포화를 판정한다
        with self.lock:
            stale = [o for o in self.conns if exit_idx is not None and o.get("exit") == exit_idx and not o["dead"]]
            self.conns.append(c)
        for o in stale:                                       # 규칙 9: (기기, 출구)당 산 연결은 하나 — 같은 출구로 새 연결이 오면 옛것은 끊긴 것
            self._mark_dead(o)                                #   (터널을 거치면 상대가 닫은 것을 데이터를 밀어 넣기 전까지 모른다 → 옛 연결에 조각을 보내 잃는다, 실회선 자가 검사 E)
        threading.Thread(target=self._reader, args=(c, first), daemon=True).start()
        return c

    def live(self):
        with self.lock:
            return [c for c in self.conns if not c["dead"]]

    def _mark_dead(self, c):
        c["dead"] = True
        try:
            c["sock"].close()
        except OSError:
            pass

    def close(self):
        self.closed = True
        with self.lock:
            cs = list(self.conns)
        for c in cs:
            if not c["dead"]:
                try:
                    with c["slock"]:
                        send_msg(c["sock"], CHUNK, {"tid": "-", "bye": 1})   # 규칙 10: 닫기 전에 알린다 — 터널은 닫힘을 늦게 전한다
                except OSError:
                    pass
            self._mark_dead(c)

    # ── 받기 ────────────────────────────────────────────────
    def _event(self, tid):
        with self.lock:
            return self.done.setdefault(tid, threading.Event())

    def _reader(self, c, first=None):
        try:
            while not self.closed:
                if first is not None:
                    msg, first = first, None
                else:
                    msg = recv_msg(c["sock"])
                kind, meta, payload, nB = msg
                if kind != CHUNK:
                    break
                tid = meta["tid"]
                if meta.get("bye"):                                   # 상대가 닫는다 — 즉시 죽은 연결로 (규칙 10)
                    break
                if meta.get("ack"):                                   # 내가 보낸 전송의 완료 회신
                    with self.lock:
                        a = self.acks.get(tid)
                    if a is not None:
                        a["got"] = meta.get("got"); a["ev"].set()
                elif meta.get("fin"):                                 # 상대의 완료 신호 — 남은 조각을 기다렸다 회신 (읽기 스레드는 막지 않는다)
                    threading.Thread(target=self._fin, args=(c, meta), daemon=True).start()
                else:                                                 # 데이터 조각 — 재조립만. 완성 신호는 완료 회신을 보낸 뒤(_fin)에만 올린다.
                    c["bytes_dn"] += len(payload)                     #   (데이터가 다 모였다고 먼저 올리면 기다리던 쪽이 pop 해 버리고, 뒤늦은 fin 이 빈 버퍼를 만난다)
                    _span(c, "dn", tid)                               # 이 출구의 내리기 활동 구간
                    self.re.feed(meta, payload)
        except OSError as e:
            if not self.closed:
                print(f"   [chunks] {self.name} {c['label']} 연결 끊김: {type(e).__name__}: {e}", flush=True)
        except Exception as e:                                        # 조각 모양 이상 등 — 조용히 죽지 않게
            print(f"   [chunks] {self.name} {c['label']} 읽기 스레드 종료: {type(e).__name__}: {e}", flush=True)
        else:
            pass                                                      # 상대가 bye 로 닫음 — 정상
        finally:
            self._mark_dead(c)

    def _fin(self, c, meta):
        ok, got = self.re.feed(meta)                                  # 기다렸다 답한다 (chunker 규칙 4)
        try:
            with c["slock"]:
                send_msg(c["sock"], CHUNK, {"tid": meta["tid"], "ack": 1, "got": got})
        except OSError:
            self._mark_dead(c)
        if ok:
            self._event(meta["tid"]).set()                            # 회신을 보낸 뒤에야 기다리던 쪽을 깨운다

    def wait(self, tid, timeout=300):
        """tid 전송의 완성본. 도착 순서(조각이 먼저, 메타가 나중)와 무관."""
        ev = self._event(tid)
        if not ev.wait(timeout):
            raise OSError(f"조각 수신 시간 초과: {tid}")
        with self.lock:
            self.done.pop(tid, None)
        return self.re.pop(tid)

    # ── 보내기 ──────────────────────────────────────────────
    def check_acks(self, wait=False, timeout=FIN_ACK_TIMEOUT):
        """지난 전송들의 완료 회신을 확인한다 (규칙 7: 완료 회신은 비동기 — 전송마다 왕복 1번을 아낀다).
        wait=False: 이미 도착한 회신만 검사(불일치면 OSError). wait=True: 전부 도착할 때까지 기다린 뒤 검사."""
        with self.lock:
            items = list(self.acks.items())
        for tid, a in items:
            if wait and not a["ev"].wait(timeout):
                raise OSError(f"완료 회신 시간 초과: {tid}")
            if a["ev"].is_set():
                with self.lock:
                    self.acks.pop(tid, None)
                if a["got"] != a["total"]:
                    raise OSError(f"재조립 불일치: {a['got']} != {a['total']} ({tid})")

    def flush(self, timeout=FIN_ACK_TIMEOUT):
        """보낸 것 전부의 완료 회신을 기다려 확인한다 (라운드 끝·닫기 전)."""
        self.check_acks(wait=True, timeout=timeout)

    def send(self, blob, tid, cid="c", chunk_size=None, weights=None, wait_ack=False):
        """blob 을 살아 있는 연결들로 나눠 보낸다. 완료 신호를 보낸 뒤 **회신은 기다리지 않고** 돌아온다(규칙 7);
        회신은 다음 send 때 check_acks 로, 라운드 끝에 flush 로 확인한다. wait_ack=True 면 옛날처럼 기다린다.
        weights: 출구 번호 순 가중치 [wA, wB] (계획 층의 출구별 예상 속도) — 있으면 그 비율로 몫을 먼저 나눈다 (규칙 3′).
        반환 {"wall", "conns", "per": {label: {"bytes", "busy_s"}}}. 모든 연결이 죽거나 재조립 불일치면 OSError."""
        self.check_acks(wait=False)
        conns = self.live()
        if not conns:
            raise OSError("성립한 출구 연결이 없음")
        total = len(blob)
        if chunk_size is None:
            chunk_size = chunk_size_for(total, len(conns))          # 규칙 2
        wmap = None
        if weights:
            conns = [c for c in conns if c.get("exit") is not None and c["exit"] < len(weights)]   # 가중치에 없는 출구(옛 연결)는 제외
            if not conns:
                raise OSError("가중치에 맞는 출구 연결이 없음")
            wmap = {c["label"]: float(weights[c["exit"]]) for c in conns}
        sched = Scheduler(split(total, chunk_size), wmap)           # 규칙 3 (+3′ 가중 몫)
        alive_labels = lambda: {c["label"] for c in conns if not c["dead"]}
        sent = {c["label"]: 0 for c in conns}
        busy = {c["label"]: 0.0 for c in conns}

        def worker(c):
            while True:
                item = sched.take(c["label"], time.perf_counter(), alive_labels())
                if item is None:
                    return
                sq, of, ln = item
                try:
                    t0 = time.perf_counter()
                    with c["slock"]:
                        send_msg(c["sock"], CHUNK, {"tid": tid, "cid": cid, "seq": sq, "off": of, "ln": ln, "total": total,
                                                    "ex": c.get("exit")},
                                 blob[of:of + ln])
                    dt = time.perf_counter() - t0
                    sent[c["label"]] += ln; busy[c["label"]] += dt
                    c["bytes_up"] += ln; c["busy"] += dt
                    _span(c, "up", tid, t0)                          # 이 출구의 올리기 활동 구간
                    sched.report(c["label"], ln, dt)
                except OSError:
                    sched.giveback(item)                            # 맡았던 조각을 되돌려 놓음 — 남은 연결이 가져간다
                    self._mark_dead(c)
                    return

        ack = {"ev": threading.Event(), "got": None, "total": total}
        with self.lock:
            self.acks[tid] = ack
        t_start = time.perf_counter()
        ok = False
        try:
            while True:
                alive = [c for c in conns if not c["dead"]]
                if not alive:
                    raise OSError("모든 출구 연결 사망 — 전송 미완")
                ths = [threading.Thread(target=worker, args=(c,)) for c in alive]
                for t in ths:
                    t.start()
                for t in ths:
                    t.join()
                if sched.remaining() == 0:
                    break
            fin = next(c for c in conns if not c["dead"])
            try:
                with fin["slock"]:
                    send_msg(fin["sock"], CHUNK, {"tid": tid, "cid": cid, "fin": 1, "total": total, "ex": fin.get("exit")})
            except OSError:
                self._mark_dead(fin)
                raise
            if wait_ack:
                if not ack["ev"].wait(FIN_ACK_TIMEOUT):
                    raise OSError(f"완료 회신 시간 초과: {tid}")
                if ack["got"] != total:
                    raise OSError(f"재조립 불일치: {ack['got']} != {total}")
            ok = True
        finally:
            if not ok or wait_ack:
                with self.lock:
                    self.acks.pop(tid, None)
        return {"wall": time.perf_counter() - t_start, "conns": len(conns),
                "per": {lab: {"bytes": sent[lab], "busy_s": round(busy[lab], 3)} for lab in sent}}

    def stats(self):
        """연결별 누적 바이트 — 가닥별 부하 분배 기록용."""
        with self.lock:
            return {c["label"]: {"up": c["bytes_up"], "dn": c["bytes_dn"]} for c in self.conns}


class ChunkLinks(ChunkPeer):
    """클라 쪽: 출구 주소들로 서버 조각 포트에 연결 (규칙 1: 한 번 열어 재사용). 죽은 연결은 다음 전송 때 다시 연다."""

    def __init__(self, host, port, sources, endpoints=None):
        """endpoints: 출구별 [(host, port, src_or_None), ...] — 실회선 리그(엣지 주소가 출구마다 다름). 없으면 (host, port) 공통 + sources."""
        super().__init__(name="links")
        self.host, self.port, self.sources = host, port, list(sources)
        self.endpoints = [tuple(e) for e in endpoints] if endpoints else [(host, port, src) for src in self.sources]
        self.by_exit = [None] * len(self.endpoints)
        self.opened = 0                                   # 연 횟수 (시험용: 재사용되면 출구 수와 같다)

    def _ensure(self):
        for i, (h, p, src) in enumerate(self.endpoints):
            c = self.by_exit[i]
            if c is None or c["dead"]:
                if c is not None:
                    print(f"   [links] 출구 {i} 연결이 죽어 있어 다시 연다 ({h}:{p})", flush=True)
                try:
                    s = socket.create_connection((h, int(p)), timeout=5, source_address=((src, 0) if src else None))
                    s.settimeout(None)                        # 연결 대기 5s 는 접속에만. 남겨 두면 라운드 사이 5s 만 쉬어도 읽기가 timeout → 연결이 죽어 매 라운드 재접속(슬로스타트)
                    self.by_exit[i] = self.attach(s, f"{src or h}:{p}#{i}", exit_idx=i)
                    self.opened += 1
                except OSError:
                    self.by_exit[i] = None
        return self.live()

    def send(self, blob, tid, cid="c", chunk_size=None, weights=None, wait_ack=False):
        self._ensure()
        return super().send(blob, tid, cid, chunk_size, weights, wait_ack)

    def exit_stats(self):
        """출구 순서대로 [{"up","dn","up_t","dn_t"}] — WUP 보고용 (바이트 누적 + 활동 구간 누적 초)."""
        return [({"up": c["bytes_up"], "dn": c["bytes_dn"], "up_t": round(_span_total(c, "up"), 4), "dn_t": round(_span_total(c, "dn"), 4)}
                 if c else {"up": 0, "dn": 0, "up_t": 0.0, "dn_t": 0.0}) for c in self.by_exit]


def send_multipath(host, port, blob, sources, tid, cid="c", chunk_size=None, links=None):
    """한 번짜리 분할 전송 (연결을 열고 닫는다). 반복 전송은 ChunkLinks 를 들고 links= 로 넘겨 재사용할 것."""
    if links is not None:
        return links.send(blob, tid, cid, chunk_size)
    L = ChunkLinks(host, port, sources)
    try:
        return L.send(blob, tid, cid, chunk_size, wait_ack=True)   # 한 번짜리는 회신을 확인하고 닫는다 (닫힌 뒤엔 확인할 길이 없다)
    finally:
        L.close()


# ── 서버 쪽 (집행 층) ─────────────────────────────────────
class ChunkServer(threading.Thread):
    """서버의 조각 수신·송신기. 포트 하나에서 연결을 받아 **기기(cid)별 채널**에 붙인다.
    세션은 wait(tid) 로 올라온 완성본을 기다리고, send_back(cid, blob, tid) 로 기울기를 그 기기의 연결들로 내려보낸다."""

    def __init__(self, host, port):
        super().__init__(daemon=True)
        self.srv = socket.create_server((host, port))
        self.srv.settimeout(0.5)
        self.lock = threading.Lock()
        self.re = Reassembler()                       # 모든 기기가 공유 (tid 가 기기별로 유일)
        self.done = {}
        self.peers = {}                               # cid → ChunkPeer
        self.queues = {}                              # cid → 내려보내기 큐 (규칙 8)
        self.stop = False
        self.accepted = 0                             # 받은 연결 수 (시험용)
        self.verbose = True                           # 연결 붙음/죽음 로그

    def _peer(self, cid):
        with self.lock:
            p = self.peers.get(cid)
            if p is None:
                p = self.peers[cid] = ChunkPeer(name=f"srv:{cid}", re=self.re, done=self.done, lock=self.lock)
            return p

    def run(self):
        while not self.stop:
            try:
                c, addr = self.srv.accept()
            except socket.timeout:
                continue
            except OSError:
                if self.stop:
                    break
                raise
            self.accepted += 1
            threading.Thread(target=self._admit, args=(c, addr), daemon=True).start()

    def close(self):
        self.stop = True
        self.srv.close()
        with self.lock:
            peers, queues = list(self.peers.values()), list(self.queues.values())
        for q in queues:
            q["q"].put(None)
        for peer in peers:
            peer.close()

    def _admit(self, c, addr):
        """첫 메시지를 읽어 어느 기기(cid)인지 알아낸 뒤 그 기기 채널에 붙인다."""
        try:
            first = recv_msg(c)
        except OSError:
            c.close(); return
        kind, meta = first[0], first[1]
        if kind != CHUNK:
            c.close(); return
        cid = meta.get("cid", "?")
        self._peer(cid).attach(c, f"{addr[0]}:{addr[1]}", first=first, exit_idx=meta.get("ex"))
        if self.verbose:
            print(f"   [chunks] {cid} 출구 {meta.get('ex')} 연결 붙음 ({addr[0]}:{addr[1]}) — 채널 연결 {len(self._peer(cid).live())}개", flush=True)

    def wait(self, tid, timeout=300):
        ev = self._event(tid)
        if not ev.wait(timeout):
            raise OSError(f"조각 수신 시간 초과: {tid}")
        with self.lock:
            self.done.pop(tid, None)
        return self.re.pop(tid)

    def _event(self, tid):
        with self.lock:
            return self.done.setdefault(tid, threading.Event())

    def send_back(self, cid, blob, tid, chunk_size=None, weights=None, wait=True):
        """기기 cid 의 연결들로 blob 을 나눠 내려보낸다 (규칙 5: 내려받기도 분할). weights: 출구 순 가중치.
        wait=False: 송신 스레드에 넘기고 즉시 돌아온다 (규칙 8 — 세션 스레드가 송신 버퍼가 비기를 기다리며 막히지 않게).
        넘긴 것의 오류는 flush_back(cid) 에서 올라온다."""
        p = self.peers.get(cid)
        if p is None or not p.live():
            state = {k: [(c["label"], c.get("exit"), "dead" if c["dead"] else "live") for c in v.conns] for k, v in self.peers.items()}
            raise OSError(f"{cid}: 열린 조각 연결이 없음 — 채널 상태 {state}")
        if wait:
            return p.send(blob, tid, cid=cid, chunk_size=chunk_size, weights=weights)
        q = self._queue(cid)
        q["q"].put((blob, tid, chunk_size, weights))
        return None

    def _queue(self, cid):
        import queue
        with self.lock:
            q = self.queues.get(cid)
            if q is None:
                q = self.queues[cid] = {"q": queue.Queue(), "err": None, "idle": threading.Event()}
                q["idle"].set()
                threading.Thread(target=self._sender, args=(cid, q), daemon=True).start()
            return q

    def _sender(self, cid, q):
        """기기별 내려보내기 스레드 — 순서대로 send. 오류는 보관해 flush_back 에서 올린다."""
        while not self.stop:
            item = q["q"].get()
            if item is None:
                return
            q["idle"].clear()
            try:
                blob, tid, cs, w = item
                self.peers[cid].send(blob, tid, cid=cid, chunk_size=cs, weights=w)
            except OSError as e:
                q["err"] = q["err"] or e
            finally:
                if q["q"].empty():
                    q["idle"].set()

    def flush_back(self, cid, timeout=FIN_ACK_TIMEOUT):
        """기기 cid 로 넘긴 내려보내기가 전부 나가고 회신까지 확인될 때까지 기다린다. 오류가 있었으면 여기서 올린다."""
        q = self.queues.get(cid)
        if q is not None:
            if not q["idle"].wait(timeout):
                raise OSError(f"{cid}: 내려보내기 시간 초과")
            if q["err"] is not None:
                e, q["err"] = q["err"], None
                raise e
        p = self.peers.get(cid)
        if p is not None:
            p.flush(timeout)
