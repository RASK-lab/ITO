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
    base = evaluate("と", from_reference("と"))
    swapped = evaluate("と", from_reference("と", order=[1, 0]))
    assert swapped.items.order < base.items.order
    assert swapped.items.shape >= base.items.shape - 2
    assert swapped.items.direction == 100


def test_reversed_stroke_lowers_only_direction():
    r = evaluate("と", from_reference("と", reverse={1}))
    assert r.items.direction < 100
    assert r.items.order == 100
    assert r.items.shape >= 95
    assert r.per_stroke[1].reversed


def test_noise_lowers_shape_monotonically():
    scores = [evaluate("と", from_reference("と", noise=n, seed=3)).items.shape for n in (0.0, 0.02, 0.05, 0.1)]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] > scores[-1] + 20


def test_scale_and_translation_invariance():
    a = evaluate("と", from_reference("と", scale=400, offset=(50, 50)))
    b = evaluate("と", from_reference("と", scale=150, offset=(300, 20)))
    assert abs(a.total - b.total) <= 1


def test_missing_stroke_lowers_count():
    r = evaluate("と", from_reference("と")[:-1])
    assert r.items.stroke_count < 100


def test_endings_detected_from_speed():
    r = evaluate("と", from_reference("と"))
    assert [p.ending.detected for p in r.per_stroke] == ["tome", "tome"]
    assert r.items.endings == 100


def test_other_character_scores_low():
    own = evaluate("と", from_reference("と")).total
    other = evaluate("と", from_reference("こ")).total
    assert other < own - 20


def test_single_tap_stroke_does_not_crash():
    strokes = [np.array([[100.0, 100.0, 0.0, 0.5]]), np.array([[50.0, 200.0, 100.0], [300.0, 210.0, 200.0]])]
    r = evaluate("と", strokes)
    assert 0 <= r.total <= 100
