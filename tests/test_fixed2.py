# -*- coding: utf-8 -*-
"""fixed2(고정 2연결 비교군) 정책 시험 — 학습·네트워크 없이 배정 규칙만 본다.  python tests/test_fixed2.py"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sfl"))
from policies import FixedTwo, RoundContext, make_policy  # noqa: E402

EDGES = {"1": ("116.89.187.190", 12100), "2": ("116.89.187.190", 12600),
         "3": ("116.89.187.189", 13100), "4": ("116.89.187.189", 13600)}


def ctx(n=32, weights="5,2", init="rr", multipath=True, edges=EDGES, allowed=None):
    a = SimpleNamespace(policy="fixed2", fixed_weights=weights, init_sets=init, multipath=multipath)
    ids = [f"c{i}" for i in range(n)]
    c = RoundContext(a=a, r=0, mctl=None, ids=ids, rnd={}, plan={k: 1.0 for k in ids},
                     edges=edges, allowed=allowed or {})
    return a, c


def test_assignment_and_balance():
    a, c = ctx()
    pol = make_policy(a)
    assert isinstance(pol, FixedTwo)
    pol.apply(c)
    sets = c.rnd["psets"]
    for i, k in enumerate(c.ids):
        pa, pb = sets[k]
        assert pa == ["1", "2", "3", "4"][i % 4], "출구 A 는 균등(rr)과 같은 엣지"
        assert pa != pb, "출구 B 는 다른 엣지"
        assert EDGES[pa][0] != EDGES[pb][0], "출구 B 는 다른 VM"
        assert c.mpplan[k] == [5.0, 2.0]
        assert c.plan[k] == 1.0
        assert c.dp[k][0] == [EDGES[pa][0], EDGES[pa][1] + 2 * i + 0]
        assert c.dp[k][1] == [EDGES[pb][0], EDGES[pb][1] + 2 * i + 1]
    load = {e: [0, 0] for e in EDGES}
    for pa, pb in sets.values():
        load[pa][0] += 1
        load[pb][1] += 1
    assert all(v == [8, 8] for v in load.values()), load


def test_frozen_after_first_round():
    a, c = ctx()
    pol = make_policy(a)
    pol.apply(c)
    before = (dict(c.rnd["psets"]), {k: list(v) for k, v in c.dp.items()})
    c.plan["c0"] = 0.5                         # 다른 누가 바꿔도 fixed2 는 다시 손대지 않는다
    c.r = 5
    pol.apply(c)
    assert (dict(c.rnd["psets"]), {k: list(v) for k, v in c.dp.items()}) == before
    assert c.plan["c0"] == 0.5


def test_guards():
    for kw, msg in (({"multipath": False}, "multipath"), ({"edges": {}}, "edges")):
        a, c = ctx(**kw)
        try:
            make_policy(a).apply(c)
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"{msg} 없이 통과하면 안 된다")
    try:
        FixedTwo(SimpleNamespace(fixed_weights="5,0"))
    except ValueError:
        pass
    else:
        raise AssertionError("0 비율은 거부")


def test_allowed_groups():
    allowed = {f"c{i}": (["3", "4"] if i < 4 else ["1", "2"]) for i in range(8)}
    a, c = ctx(n=8, allowed=allowed)
    make_policy(a).apply(c)
    for k, (pa, pb) in c.rnd["psets"].items():
        assert pa in allowed[k] and pb in allowed[k] and pa != pb


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("fixed2 시험 전부 통과")
