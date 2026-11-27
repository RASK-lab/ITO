import numpy as np
import pytest

from src.judge.geometry.score import evaluate
from src.judge.refs import TARGET_CHARS, load_references

from .helpers import from_reference


@pytest.mark.parametrize("char", TARGET_CHARS)
def test_reference_itself_scores_high(char):
    r = evaluate(char, from_reference(char))
    it = r.items
    assert r.user_stroke_count == r.ref_stroke_count
    assert it.stroke_count == 100 and it.order == 100 and it.direction == 100
    assert it.shape >= 95 and it.balance >= 95
    assert r.total >= 90


@pytest.mark.parametrize("char", TARGET_CHARS)
def test_references_load_with_endings(char):
    ref = load_references(char)[0]
    assert len(ref.endings) == len(ref.strokes)


def test_swapped_order_lowers_only_order():
    base = evaluate("都", from_reference("都"))
    order = list(range(11))
    order[0], order[1] = order[1], order[0]
    swapped = evaluate("都", from_reference("都", order=order))
    assert swapped.items.order < base.items.order
    assert swapped.items.shape >= base.items.shape - 2
    assert swapped.items.direction == 100


def test_reversed_stroke_lowers_only_direction():
    r = evaluate("十", from_reference("十", reverse={1}))
    assert r.items.direction < 100
    assert r.items.order == 100
    assert r.items.shape >= 95
    assert r.per_stroke[1].reversed


def test_noise_lowers_shape_monotonically():
    scores = [evaluate("と", from_reference("と", noise=n, seed=3)).items.shape for n in (0.0, 0.02, 0.05, 0.1)]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] > scores[-1] + 20


def test_scale_and_translation_invariance():
    a = evaluate("戸", from_reference("戸", scale=400, offset=(50, 50)))
    b = evaluate("戸", from_reference("戸", scale=150, offset=(300, 20)))
    assert abs(a.total - b.total) <= 1


def test_missing_stroke_lowers_count():
    strokes = from_reference("徒")[:-1]
    r = evaluate("徒", strokes)
    assert r.items.stroke_count < 100
    assert r.per_stroke[-1].matched_user_stroke is None or r.user_stroke_count == 9


def test_endings_detected_from_speed():
    r = evaluate("戸", from_reference("戸"))
    detected = [p.ending.detected for p in r.per_stroke]
    assert detected[-1] == "harai"
    assert detected[0] == "tome"
    assert r.items.endings >= 75


def test_other_character_scores_low():
    own = evaluate("十", from_reference("十")).total
    other = evaluate("十", from_reference("と")).total
    assert other < own - 20


def test_single_tap_stroke_does_not_crash():
    strokes = [np.array([[100.0, 100.0, 0.0, 0.5]]), np.array([[50.0, 200.0, 100.0], [300.0, 210.0, 200.0]])]
    r = evaluate("十", strokes)
    assert 0 <= r.total <= 100
