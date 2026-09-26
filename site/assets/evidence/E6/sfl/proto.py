# -*- coding: utf-8 -*-
"""소켓 메시지 — 길이 접두 프레이밍 + 응용 계층 바이트 계수.

  [!BII 헤더: kind, meta_len, payload_len][meta json][payload]
  모든 send/recv가 바이트 수를 반환한다 → A2(바이트∝p) 검증이 계측에서 바로 나온다.
"""
import json
import struct

HDR = struct.Struct("!BII")
HELLO, HELLO_OK, TOKREQ, TOKOK, ACT, GRAD, BYE = 1, 2, 3, 4, 5, 6, 7


def send_msg(sock, kind, meta=None, payload=b""):
    m = json.dumps(meta or {}, separators=(",", ":")).encode()
    buf = HDR.pack(kind, len(m), len(payload)) + m + payload
    sock.sendall(buf)
    return len(buf)


def _recv_all(sock, n):
    chunks, got = [], 0
    while got < n:
        b = sock.recv(min(1 << 20, n - got))
        if not b:
            raise ConnectionError("peer closed")
        chunks.append(b)
        got += len(b)
    return b"".join(chunks)


def recv_msg(sock):
    h = _recv_all(sock, HDR.size)
    kind, ml, pl = HDR.unpack(h)
    meta = json.loads(_recv_all(sock, ml)) if ml else {}
    payload = _recv_all(sock, pl) if pl else b""
    return kind, meta, payload, HDR.size + ml + pl


def t2b(t, quant=0):
    """텐서 → (meta, bytes).

    quant=0  fp32 그대로 (기본)
    quant=8  **값역 8비트 양자화** — 텐서당 스케일 하나로 int8 로 눕힌다.
             바이트가 1/4 이 된다.

    ★ 왜 이걸 넣었나 (적대 검증 지적)
      폭 p=0.25 도 바이트를 4배 줄인다. 8비트 양자화도 4배를 **정확도 대가 거의 없이** 준다.
      즉 우리 주 노브와 **같은 크기의 이득을 더 싸게 내는 대안**이 있는데 한 번도 재지 않았다.
      "변인 통제 때문에 안 쟀다"는 방어가 안 되므로 **기준선으로 넣어 직접 잰다.**
      (구조 압축인 폭 p 와 값역 압축인 양자화는 직교하므로 곱해질 수도 있다 — 그것도 잰다)
    """
    a = t.detach().cpu().contiguous().numpy()
    if quant == 8:
        import numpy as _np
        scale = float(_np.abs(a).max()) / 127.0 or 1.0
        q = _np.clip(_np.round(a / scale), -127, 127).astype(_np.int8)
        return {"shape": list(a.shape), "dtype": "int8", "scale": scale,
                "orig": str(a.dtype)}, q.tobytes()
    return {"shape": list(a.shape), "dtype": str(a.dtype)}, a.tobytes()


def b2t(meta, buf):
    # Byte transport and packet instrumentation can run without the ML stack.
    import numpy as np
    import torch
    a = np.frombuffer(buf, dtype=meta["dtype"]).reshape(meta["shape"])
    if "scale" in meta:                      # 8비트 양자화 복원
        a = a.astype(meta.get("orig", "float32")) * meta["scale"]
    return torch.from_numpy(a.copy())


# ── 라운드 기반 학습용 추가 (G2) ────────────────────────────────
RSTART, RDONE, WUP, WDOWN = 8, 9, 10, 11
# 사전 진단 (preflight): 학습 시작 전에 계산·회선을 한 번 재서 첫 라운드부터
# 배정이 서게 한다. PROBE(서버→클라) / PROBERES(클라→서버, 실제 활성값 페이로드)
PROBE, PROBERES = 12, 13
CHUNK = 14                    # 분할 전송 조각 (mpsend.py)
SOLO, SOLORES = 15, 16        # 단독 업로드 프로브 — 접속 회선 상한 실측 (sense.py)


def sd2b(sd):
    """state_dict → (meta, bytes). 키 순서·모양을 메타에 담아 평탄 버퍼로."""
    keys, shapes, dtypes, bufs = [], [], [], []
    for k, v in sd.items():
        a = v.detach().cpu().contiguous().numpy()
        keys.append(k); shapes.append(list(a.shape)); dtypes.append(str(a.dtype))
        bufs.append(a.tobytes())
    return {"k": keys, "s": shapes, "d": dtypes,
            "n": [len(b) for b in bufs]}, b"".join(bufs)


def b2sd(meta, buf):
    import numpy as np
    import torch
    out, off = {}, 0
    for k, s, d, n in zip(meta["k"], meta["s"], meta["d"], meta["n"]):
        a = np.frombuffer(buf[off:off + n], dtype=d).reshape(s)
        out[k] = torch.from_numpy(a.copy())
        off += n
    return out
