# -*- coding: utf-8 -*-
"""삼면비교 웹 데모 생성기 — out/l2_grid.json → out/reports/삼면비교_데모.html

  발표 무대용 정적 페이지다. 라이브 추론 없이 **실제 생성 결과를 재생**하므로
  무대 리스크가 0 이다 (라이브 질의는 별도 서버로 — 안전망 원칙).

  결과 파일이 아직 없으면 '예시 데이터' 워터마크를 박아 디자인 확인용으로 만든다.
      python sfl/demo/make_demo.py            # l2_grid.json 있으면 실데이터, 없으면 예시
"""
import io
import json
import os
import sys
import html as H

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "out", "l2_grid.json")
DST = os.path.join(ROOT, "out", "reports", "삼면비교_데모.html")

SAMPLE = {
    "베이스": {"B": {"acc": 0.0, "n": 3, "detail": [
        {"q": "KOREN 망에서 실측한 RTT 중앙값은 얼마인가?", "gen": "네트워크 상황에 따라 다르지만 일반적으로 수십 ms입니다.", "ok": False, "keys": ["30.8"]},
        {"q": "마감선 D는 어떤 통계량에 앵커되나?", "gen": "일반적으로 평균값을 사용합니다.", "ok": False, "keys": ["중앙값"]},
        {"q": "넷챌린지 시즌13 최종평가는 언제인가?", "gen": "정확한 일정은 주최측 공지를 확인하세요.", "ok": False, "keys": ["10월 30"]}]}},
    "A 단독": {"B": {"acc": 0.0, "n": 3, "detail": [
        {"q": "KOREN 망에서 실측한 RTT 중앙값은 얼마인가?", "gen": "졸업요건은 130학점입니다.", "ok": False, "keys": ["30.8"]},
        {"q": "마감선 D는 어떤 통계량에 앵커되나?", "gen": "수강신청은 학기 초에 합니다.", "ok": False, "keys": ["중앙값"]},
        {"q": "넷챌린지 시즌13 최종평가는 언제인가?", "gen": "재수강 규정에 따릅니다.", "ok": False, "keys": ["10월 30"]}]}},
    "연합": {"B": {"acc": 1.0, "n": 3, "detail": [
        {"q": "KOREN 망에서 실측한 RTT 중앙값은 얼마인가?", "gen": "중앙값 30.8ms다.", "ok": True, "keys": ["30.8"]},
        {"q": "마감선 D는 어떤 통계량에 앵커되나?", "gen": "중앙값이다. min은 규모에서 붕괴해 버렸다.", "ok": True, "keys": ["중앙값"]},
        {"q": "넷챌린지 시즌13 최종평가는 언제인가?", "gen": "10월 30일, 현장 시연과 질의응답이다.", "ok": True, "keys": ["10월 30"]}]}},
}


def main():
    if os.path.exists(SRC):
        g = json.load(io.open(SRC, encoding="utf-8"))
        sample = False
    else:
        g, sample = SAMPLE, True
    doms = sorted(next(iter(g.values())).keys())
    models = list(g.keys())

    tpl = io.open(os.path.join(ROOT, "sfl", "demo", "demo_template.html"), encoding="utf-8").read()
    out = (tpl.replace("__DATA__", json.dumps(g, ensure_ascii=False))
              .replace("__DOMS__", json.dumps(doms, ensure_ascii=False))
              .replace("__MODELS__", json.dumps(models, ensure_ascii=False))
              .replace("__SAMPLE__", "true" if sample else "false"))
    io.open(DST, "w", encoding="utf-8").write(out)
    print(f"{'예시 데이터' if sample else 'l2_grid.json 실데이터'} → {DST}")


if __name__ == "__main__":
    main()
