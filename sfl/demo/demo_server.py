# -*- coding: utf-8 -*-
"""삼면비교 라이브 채팅 서버 — 질문 하나에 세 모델이 그 자리에서 답한다.

  정적 재생 페이지(make_demo.py)가 무대 안전망이라면, 이건 진짜 대화다:
      브라우저에 질문 입력 → 베이스 / A 단독 / 연합 어댑터를 차례로 갈아끼우며
      같은 모델 골격에서 생성 → 세 답이 나란히 뜬다.

  어댑터 스왑은 KB 급이라 요청당 수 ms — 모델은 하나만 메모리에 올린다.
  서버는 단일 스레드 = 요청 1개씩 처리 (1인 큐 원칙, 데모에 충분).

  질문이 코퍼스의 검증 문항과 일치하면 채점 키워드로 정답/오답 배지도 붙는다.

      python sfl/demo/demo_server.py                     # 체크포인트 있으면 자동 로드
      python sfl/demo/demo_server.py --tiny --port 8777  # 스모크 (랜덤 소형 모델)
  브라우저: http://localhost:8777
"""
import argparse
import io
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from eval_grid import answer                        # noqa: E402
from lora_corpus import DIR as CORPUS_DIR, load, split  # noqa: E402
from models_llm import DEFAULT, lora_state          # noqa: E402
from run_l1 import build_model                      # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CKPT = os.path.join(ROOT, "data", "lora_ckpt")


def find_adapters(m):
    """체크포인트 자동 발견. 베이스(공통 초기값, B=0)는 항상 있다.

    각 어댑터는 **베이스 위에 병합**해 완전한 키 집합으로 만든다 — 타깃 층 구성이
    다른 체크포인트(예: attn 전용)도 키 불일치 없이 적재되고, 요청 간 어댑터 스왑에서
    이전 어댑터의 층이 잔류하는 오염도 원천 차단된다."""
    base = {k: v.clone() for k, v in lora_state(m).items()}
    ads = {"베이스": base}
    for fn, name in [("l1_A.pt", "A 단독"), ("l1_B.pt", "B 단독"), ("l2_fed.pt", "연합")]:
        p = os.path.join(CKPT, fn)
        if os.path.exists(p):
            sd = torch.load(p, map_location="cpu")
            full = {k: v.clone() for k, v in base.items()}
            full.update({k: v for k, v in sd.items() if k in full})
            skipped = [k for k in sd if k not in full]
            if skipped:
                print(f"  {name}: 모델에 없는 키 {len(skipped)}개 무시 ({fn})")
            ads[name] = full
    return ads


def known_questions():
    """코퍼스 검증 문항 → {q: keywords} (배지용) + 제안 질문 목록."""
    keys, sugg = {}, []
    if os.path.isdir(CORPUS_DIR):
        for f in sorted(os.listdir(CORPUS_DIR)):
            if f.endswith(".jsonl"):
                _, ho = split(load(os.path.join(CORPUS_DIR, f)))
                for d in ho:
                    keys[d["q"]] = d["keywords"]
                sugg += [d["q"] for d in ho[:3]]
    return keys, sugg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8777)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--model", default=DEFAULT)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--tiny", action="store_true")
    ap.add_argument("--max-new", type=int, default=48)
    a = ap.parse_args()

    print("모델 적재 중 …")
    m, tok = build_model(a.model, a.rank, a.tiny, a.device,
                         "q_proj,v_proj,o_proj,gate_proj,up_proj,down_proj".split(","))
    m.eval()
    ads = find_adapters(m)
    keys, sugg = known_questions()
    print(f"어댑터: {list(ads)} · 검증 문항 {len(keys)}개 · http://localhost:{a.port}")

    tpl = io.open(os.path.join(ROOT, "sfl", "demo", "chat_template.html"), encoding="utf-8").read()
    page = (tpl.replace("__MODELS__", json.dumps(list(ads), ensure_ascii=False))
               .replace("__SUGG__", json.dumps(sugg[:9], ensure_ascii=False))).encode("utf-8")

    class H(BaseHTTPRequestHandler):
        def log_message(self, *args):                # 조용히
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(page)

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n))
            q, name = req["q"].strip(), req["model"]
            if name not in ads or not q:
                self.send_response(400)
                self.end_headers()
                return
            t0 = time.time()
            miss = m.load_state_dict(ads[name], strict=False)
            assert not miss.unexpected_keys
            gen = answer(m, tok, q, a.device, max_new=a.max_new)
            ms = (time.time() - t0) * 1000
            res = {"a": gen, "ms": round(ms)}
            if q in keys:
                res["keys"] = keys[q]
                res["ok"] = any(k.lower() in gen.lower() for k in keys[q])
            body = json.dumps(res, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

    HTTPServer(("0.0.0.0", a.port), H).serve_forever()


if __name__ == "__main__":
    main()
