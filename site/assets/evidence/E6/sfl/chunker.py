# -*- coding: utf-8 -*-
"""자르기·재조립 — 분할 전송의 알맹이. 소켓이 없다. (2026-09-07)

  왜 따로 있나: 전송 코드(mpsend.py)는 연결·오류·시간 재기가 섞여 있어 "잘라서 다시 붙이면
  원본이 되는가"를 그것만 떼어 시험하기 어렵다. 규칙은 여기, 배관은 mpsend 에.

  세 조각
    split(total, chunk_size)      바이트 길이를 (번호, 위치, 길이) 조각 목록으로 — 겹침·빈틈 없이
    Scheduler(chunks)             "먼저 한가해진 연결이 다음 조각을 가져간다". 연결이 죽으면 giveback.
    Reassembler                   조각을 위치대로 끼워 넣고, 완료 신호는 남은 조각을 **기다렸다** 답한다.

  받는 쪽 규칙 (게이트가 잡은 경합, 2026-09-07 새벽 실험 4라운드째에 실제로 터짐)
    보내는 쪽은 조각을 전부 커널에 넘긴 뒤 완료 신호를 연결 하나로 보낸다. 다른 연결의 조각은
    아직 도착 전일 수 있다. 그때 받은 양을 그대로 답하면 "4MB 중 3MB" 거짓 불일치 → 클라 사망 →
    서버의 학습 진행이 막힌다. send 성공은 커널 인수를 뜻하므로 제한 시간 안에서
    전체 수신을 확인해야 한다. 연결 실패 시 배달은 보장되지 않는다.
    재전송 조각은 번호로 걸러 한 번만 센다.
"""
import threading
from collections import deque

CHUNK_SIZE = 1 << 20            # 조각 상한 1MB — 헤더에 길이가 있어 협상 불필요
CHUNK_MIN = 64 << 10            # 조각 하한 64KB
CHUNKS_PER_CONN = 16            # 연결마다 최소 이만큼 조각이 돌아가게 조각 크기를 정한다 (가중 몫의 반올림 오차 ≤ 1/16)


def chunk_size_for(total, n_conns, cap=CHUNK_SIZE, floor=CHUNK_MIN, per_conn=CHUNKS_PER_CONN):
    """페이로드에 맞춘 조각 크기 = clamp(total / (per_conn × 연결 수), 64KB, 1MB).

    왜 (2026-09-07 스모크): 조각을 1MB 고정으로 두면 즉시 내보내기(페이로드 2MB)에서 조각이 2개뿐이라 느린 출구(19Mbps)가
    1MB 를 잡는 순간 완료가 0.43s 로 묶인다 — 빠른 출구(46Mbps) 혼자 보내는 0.37s 보다 느리다. 조각이 연결당 여덟 개쯤 있어야
    "먼저 한가한 쪽이 다음 조각" 규칙이 속도 차를 흡수한다 (MPTCP 의 head-of-line 문제와 같은 현상)."""
    if total <= 0:
        return cap
    return int(max(floor, min(cap, -(-total // max(1, per_conn * max(1, n_conns))))))


def split(total, chunk_size=CHUNK_SIZE):
    """총 길이를 조각 목록 [(seq, off, ln), ...] 으로. 합은 total, 겹침 없음, 마지막만 짧을 수 있다."""
    if chunk_size <= 0:
        raise ValueError("chunk_size 는 양수")
    out, off, seq = [], 0, 0
    while off < total:
        ln = min(chunk_size, total - off)
        out.append((seq, off, ln))
        seq += 1
        off += ln
    return out


class Scheduler:
    """조각 나눠 주기 — 비율 계산 없이, 먼저 한가해진 연결이 다음 조각을 가져간다.
    연결이 죽으면 맡았던 조각을 giveback 으로 되돌려 다른 연결이 가져가게 한다.

    꼬리 규칙: 남은 조각이 적을 때 느린 연결이 조각을 집으면 그 조각이 완료를 늦춘다. 연결마다 잰 속도(report)로
    "내가 이 조각을 끝내는 시간" 과 "가장 빠른 다른 연결이 자기 것 마치고 이것까지 끝내는 시간" 을 비교해,
    남이 더 빨리 끝낼 수 있으면 집지 않는다(None → 그 연결은 물러난다). 속도를 아직 모르면 그냥 집는다."""

    def __init__(self, chunks, weights=None):
        """weights: {conn: 가중치} — 있으면 바이트를 가중치 비율로 **먼저 할당**하고(quota), 그 안에서 먼저-한가한 순서.
        비율은 계획 층의 출구별 예상 속도에서 온다(plan.exit_rates). 조각 단위 실측은 페이로드가 소켓 버퍼보다 작으면
        (즉시 내보내기 1MB) 느린 출구도 즉시 '보냈다'고 나와 50:50 이 되어 버린다 — 2026-09-07 스모크."""
        self.q = deque(chunks)
        self.lock = threading.Lock()
        self.rate = {}              # conn → bytes/s (report 로 갱신)
        self.busy_until = {}        # conn → 지금 맡은 조각을 끝낼 예상 시각(단조 시계)
        self.total = sum(ln for _, _, ln in chunks)
        self.sent = {}              # conn → 할당받은 바이트
        self.quota = None
        if weights:
            W = sum(max(0.0, w) for w in weights.values())
            if W > 0:
                # 몫은 조각 개수로 — 최대 나머지(largest remainder) 반올림. "몫보다 작으면 집는다" 로 두면 느린 쪽이 한 조각을 넘겨 받아
                # 병목이 된다 (32조각에서 69% vs 72%). 조각 크기가 같다고 보고 개수를 나눈다.
                n = len(chunks)
                raw = {c: n * max(0.0, w) / W for c, w in weights.items()}
                base = {c: int(v) for c, v in raw.items()}
                left = n - sum(base.values())
                for c, _ in sorted(raw.items(), key=lambda kv: -(kv[1] - int(kv[1]))):
                    if left <= 0:
                        break
                    base[c] += 1; left -= 1
                cs = chunks[0][2] if chunks else 1
                self.quota = {c: k * cs for c, k in base.items()}

    def report(self, conn, nbytes, secs):
        """연결이 조각 하나를 끝냈다 — 속도 갱신 (지수 이동 평균 0.5, RFC 6298 보다 빠르게 따라감: 조각 수가 적다)."""
        if secs <= 0:
            return
        r = nbytes / secs
        with self.lock:
            self.rate[conn] = r if conn not in self.rate else 0.5 * self.rate[conn] + 0.5 * r
            self.busy_until[conn] = 0.0

    def take(self, conn=None, now=None, alive=None):
        """다음 조각. 없거나(빈 큐), 몫(quota)을 다 썼거나, 꼬리 규칙에 걸리면 None.
        alive: 살아 있는 연결 이름들 — 전부 몫을 다 썼으면 몫을 무시하고 준다(남은 조각은 누군가 보내야 한다).
        몫이 있으면 꼬리 규칙은 쓰지 않는다(몫이 이미 속도 비율이다). 몫·예상 시각은 **실제로 집었을 때만** 갱신한다."""
        with self.lock:
            if not self.q:
                return None
            item = self.q[0]
            ln = item[2]
            if self.quota is not None and conn is not None and conn in self.quota:
                used = self.sent.get(conn, 0)
                if used >= self.quota[conn] - 1e-9:
                    others = [c for c in (alive or self.quota) if c != conn and c in self.quota
                              and self.sent.get(c, 0) < self.quota[c] - 1e-9]
                    if others:
                        return None                              # 내 몫은 끝 — 남은 건 아직 몫이 남은 연결이
                self.sent[conn] = used + ln
                return self.q.popleft()
            if conn is not None and conn in self.rate and now is not None:
                mine = now + ln / self.rate[conn]
                others = [now + max(0.0, self.busy_until.get(c, 0.0) - now) + ln / r
                          for c, r in self.rate.items() if c != conn and r > 0]
                if others and min(others) < mine and len(self.q) <= 2 * max(1, len(self.rate)):
                    return None                                  # 남이 더 빨리 끝낸다 — 내가 잡으면 완료가 늦어진다
                self.busy_until[conn] = mine
            return self.q.popleft()

    def giveback(self, item):
        with self.lock:
            self.q.appendleft(item)

    def remaining(self):
        with self.lock:
            return len(self.q)


class Reassembler:
    """조각을 위치대로 모아 완성본을 돌려준다. 연결 여럿이 공유(잠금 내장). 전송 여러 건(tid)을 동시에 받는다."""

    FIN_WAIT = 60.0                 # 완료 신호 뒤 남은 조각을 기다리는 한도(초)

    def __init__(self):
        self.buf = {}               # tid → bytearray
        self.got = {}               # tid → 받은 바이트 수 (중복 제외)
        self.seen = {}              # tid → seq: (offset, length); validate coverage and retransmits
        self.full = {}              # tid → 완성 신호 Event
        self.lock = threading.Lock()

    def _ensure(self, tid, total):
        if not isinstance(total, int) or total < 0:
            raise ValueError("invalid transfer length")
        if tid not in self.buf:
            self.buf[tid] = bytearray(total)
            self.got[tid] = 0
            self.seen[tid] = {}
        elif len(self.buf[tid]) != total:
            raise ValueError("transfer total changed")
        event = self.full.setdefault(tid, threading.Event())
        if total == 0:
            event.set()
        return event

    def feed(self, meta, payload=b""):
        """조각 하나를 소화한다. 일반 조각 → None. 완료 신호(meta["fin"]) → (완성 여부, 받은 바이트)."""
        tid, total = meta["tid"], meta["total"]
        if meta.get("fin"):
            with self.lock:
                ev = self._ensure(tid, total)
            ev.wait(self.FIN_WAIT)                     # 남은 조각을 기다린다
            with self.lock:
                return (self.got.get(tid, 0) == total, self.got.get(tid, 0))
        with self.lock:
            sq, of, ln = meta["seq"], meta["off"], meta["ln"]
            if (not all(isinstance(v, int) for v in (sq, of, ln, total))
                    or sq < 0 or of < 0 or ln <= 0 or total < 0 or len(payload) != ln or of + ln > total):
                raise ValueError(f"조각 모양 이상: tid={tid} seq={sq} off={of} ln={ln} payload={len(payload)} total={total}")
            ev = self._ensure(tid, total)
            if sq in self.seen[tid]:                   # 재전송 중복 — 한 번만
                if self.seen[tid][sq] != (of, ln) or self.buf[tid][of:of+ln] != payload:
                    raise ValueError("conflicting retransmission")
                return None
            if any(of < start+length and start < of+ln for start, length in self.seen[tid].values()):
                raise ValueError("overlapping chunk ranges")
            self.seen[tid][sq] = (of, ln)
            self.buf[tid][of:of + ln] = payload
            self.got[tid] += ln
            if self.got[tid] >= total:
                ev.set()
            return None

    def is_complete(self, tid):
        with self.lock:
            return tid in self.full and self.full[tid].is_set()

    def pop(self, tid):
        """완성본을 꺼내고 그 전송의 흔적을 지운다."""
        with self.lock:
            if tid not in self.full or not self.full[tid].is_set():
                raise ValueError("transfer is not complete")
            self.got.pop(tid, None)
            self.seen.pop(tid, None)
            self.full.pop(tid, None)
            return bytes(self.buf.pop(tid))
