import numpy as np
import pytest

from src.judge import catalog, comments, engine
from src.judge.analysis import axes, population, rare
from src.judge.analysis.strokes import prepare_input

from .helpers import from_reference

TAP = np.array([[260.0, 20.0, 5000.0, 0.5], [261.0, 21.0, 5010.0, 0.5]])


def _analyze(strokes, device="pen", canvas=(512, 512)):
    return engine.analyze([s.tolist() for s in strokes], [device] * len(strokes), canvas)


def test_tap_is_ignored():
    s = from_reference("と")
    inp = prepare_input([x.tolist() for x in s] + [TAP.tolist()], ["pen"] * 3, (512, 512))
    assert inp.ignored == [2]
    assert len(inp.kept) == 2


def test_tap_keeps_impression_candidates():
    s = from_reference("と", noise=0.03, seed=1)
    a = _analyze(s)
    b = _analyze(s + [TAP])
    assert b.inp.ignored == [2]
    assert a.axes.candidates[:2] == b.axes.candidates[:2] or a.axes.candidates[0] in b.axes.candidates


def test_to_is_recognized_and_others_are_not():
    assert _analyze(from_reference("と", noise=0.03, seed=2)).is_to_geometry
    for ch in ("ト", "こ"):
        assert not _analyze(from_reference(ch)).is_to_geometry


def test_candidates_are_three_distinct_impressions():
    a = _analyze(from_reference("と", noise=0.03, seed=4))
    assert len(a.axes.candidates) == 3
    assert len(set(a.axes.candidates)) == 3
    assert all(c in axes.IMPRESSIONS for c in a.axes.candidates)


def test_axes_pair_opposites():
    seen = set()
    for pos, neg, _ in axes.AXES.values():
        seen |= {pos, neg}
    assert seen == set(axes.IMPRESSIONS)


def test_sharper_turn_is_less_kawaii():
    base = from_reference("と")
    sharp = [s.copy() for s in base]
    k = int(np.argmin(sharp[1][:, 0]))
    sharp[1][max(k - 3, 0):k + 4, 0] -= 25
    assert _analyze(base).axes.scores["roundness"] > _analyze(sharp).axes.scores["roundness"]


def test_slow_writing_is_more_careful():
    fast = from_reference("と")
    slow = [s.copy() for s in fast]
    for s in slow:
        s[:, 2] *= 3
    assert _analyze(slow).axes.scores["carefulness"] > _analyze(fast).axes.scores["carefulness"]


def test_wider_is_warmer():
    base = from_reference("と")
    wide = [s.copy() for s in base]
    for s in wide:
        s[:, 0] = 256 + (s[:, 0] - 256) * 1.5
    assert _analyze(wide).axes.scores["warmth"] > _analyze(base).axes.scores["warmth"]


def test_decide_uses_ai_impression_only_from_candidates():
    a = _analyze(from_reference("と", noise=0.03, seed=5))
    c = a.axes.candidates
    assert engine.decide(a, impression=c[2], ai_beauty=60, ai_is_to=True)["impression"] == c[2]
    outsider = next(i for i in axes.IMPRESSIONS if i not in c)
    assert engine.decide(a, impression=outsider, ai_beauty=60, ai_is_to=True)["impression"] == c[0]


@pytest.mark.parametrize("score,rank", [(0, 1), (29.9, 1), (30, 2), (55, 3), (70, 4), (84.9, 4), (85, 5), (100, 5)])
def test_quality_rank(score, rank):
    assert engine.quality_rank(score) == rank


def test_rares():
    base = dict(is_to=True, n_strokes=2, order_reversed=False,
                features={"duration": 1.5, "size": 0.5, "sloppiness": 0}, axis_scores={"a": 1.0}, quality=60)
    assert rare.judge(**base)[0] is None
    assert rare.judge(**{**base, "is_to": False})[0] == "R-katahou"
    assert rare.judge(**{**base, "n_strokes": 1})[0] == "R-ippon"
    assert rare.judge(**{**base, "order_reversed": True})[0] == "R-uragaeshi"
    assert rare.judge(**{**base, "quality": 97})[0] == "R-kinshi"
    assert rare.judge(**{**base, "features": {"duration": 0.3, "size": 0.5}})[0] == "R-idaten"
    assert rare.judge(**{**base, "features": {"duration": 9, "size": 0.5}})[0] == "R-amikake"
    assert rare.judge(**{**base, "features": {"duration": 1.5, "size": 0.05}})[0] == "R-baby"
    assert rare.judge(**{**base, "features": {"duration": 1.5, "size": 0.97}})[0] == "R-loose"
    assert rare.judge(**{**base, "features": {"duration": 1.5, "size": 0.5, "sloppiness": 3}})[0] == "R-kedama"
    assert rare.judge(**{**base, "axis_scores": {"a": 0.1, "b": -0.2}})[0] == "R-niji"


def test_catalog_has_60_ids_and_templates_for_all():
    ids = catalog.all_ids()
    assert len(ids) == 60 and len(set(ids)) == 60
    for sid in ids:
        imp = "kawaii" if sid.startswith("R-") else sid.split("-", 1)[1]
        rank = 3 if sid.startswith("R-") else int(sid[1])
        assert comments.template_comment(sid, imp, rank)


def test_all_50_regular_socks_are_reachable():
    ids = set(catalog.all_ids())
    for q in (10, 40, 60, 75, 90):
        for imp in axes.IMPRESSIONS:
            assert catalog.sock_id(engine.quality_rank(q), imp) in ids


def test_percentile_text():
    assert "上位" in population.describe("speed", 2.0, population.zscore("speed", 2.0))
    assert "計測できず" in population.describe("pressure", None, 0.0)
