"""各指標の距離を 0〜100 点に変換し、加重平均して幾何スコアを出す。"""

from __future__ import annotations

import math

import numpy as np

from ..refs import Reference, load_references
from ..schemas import EndingResult, GeometryItems, GeometryResult, PerStroke
from . import match, metrics
from .normalize import PreparedStroke, normalize_xy, prepare, resample, smooth

# score = 100 * exp(-d / tau)。tau は実サンプルで調整する（eval 参照）
TAU = {
    "stroke_count": 1.5,   # 画数の差 1 で 51 点
    "order": 3.0,          # 逆転 1 組で 72 点
    "direction": 1.5,      # 逆向き 1 画で 51 点
    "shape": 0.08,         # DTW 平均距離（単位正方形）
    "balance": 0.08,
    "line": 0.35,          # 方向変化のばらつき [rad]
}

WEIGHTS = {
    "stroke_count": 10,
    "order": 15,
    "direction": 10,
    "shape": 30,
    "balance": 20,
    "line": 5,
    "endings": 10,
}


def to_score(d: float, tau: float) -> int:
    return int(round(100 * math.exp(-max(d, 0.0) / tau)))


def _prepared_ref(ref: Reference) -> list[np.ndarray]:
    # お手本もユーザーと同じ正規化・リサンプルを通す
    return [smooth(resample(s)) for s in normalize_xy(ref.strokes)]


def _evaluate_variant(
    user: list[PreparedStroke], ref: Reference, mouse_ratio: float
) -> GeometryResult:
    ref_pts = _prepared_ref(ref)
    asg = match.assign([s.resampled for s in user], ref_pts)
    n_u, n_r = len(user), len(ref_pts)

    count_d = abs(n_u - n_r)
    inv = match.order_inversions(asg.pairs)
    n_rev = sum(asg.reversed.values())
    shape_d = metrics.shape_distances(user, ref_pts, asg.pairs, asg.reversed)
    bal_d = metrics.balance_distance(user, ref_pts, asg.pairs)
    jitter = metrics.line_jitter(user)

    # 対応が付かなかったお手本の画は形の距離を大きめに数える
    shape_mean = float(np.mean(list(shape_d.values()) + [0.25] * max(n_r - len(asg.pairs), 0))) if n_r else 1.0

    # 終筆
    user_of_ref = {j: i for i, j in asg.pairs}
    per_stroke: list[PerStroke] = []
    judged, correct = 0, 0
    for j in range(n_r):
        expected = ref.endings[j]
        i = user_of_ref.get(j)
        detected = "unknown"
        if i is not None:
            detected = metrics.classify_ending(user[i])
            if expected != "any" and detected != "unknown":
                judged += 1
                correct += int(detected == expected)
        per_stroke.append(PerStroke(
            stroke=j + 1,
            matched_user_stroke=None if i is None else i + 1,
            reversed=bool(asg.reversed.get(i, False)) if i is not None else False,
            shape=None if i is None else to_score(shape_d[i], TAU["shape"]),
            ending=EndingResult(expected=expected, detected=detected),
        ))
    endings_score = int(round(100 * correct / judged)) if judged else None

    items = {
        "stroke_count": to_score(count_d, TAU["stroke_count"]),
        "order": to_score(inv, TAU["order"]),
        "direction": to_score(n_rev, TAU["direction"]),
        "shape": to_score(shape_mean, TAU["shape"]),
        "balance": to_score(bal_d, TAU["balance"]),
        "line": to_score(jitter, TAU["line"]),
        "endings": endings_score if endings_score is not None else 0,
    }

    weights = dict(WEIGHTS)
    if endings_score is None:
        weights["endings"] = 0           # 判定できる画が無ければ数えない
    else:
        weights["endings"] *= 1 - 0.5 * mouse_ratio  # マウスでは速度が当てにならない
    total = sum(items[k] * w for k, w in weights.items()) / sum(weights.values())

    return GeometryResult(
        total=int(round(total)),
        items=GeometryItems(**items),
        per_stroke=per_stroke,
        user_stroke_count=n_u,
        ref_stroke_count=n_r,
        variant=ref.variant,
    )


def evaluate(target: str, strokes: list[np.ndarray], pointer_types: list[str] | None = None) -> GeometryResult:
    """strokes: 各画 (n, 2〜4) の配列（x, y, t, pressure）。お手本の字体ごとに採点し、最高点を返す。"""
    user = prepare(strokes)
    types = pointer_types or ["pen"] * len(strokes)
    mouse_ratio = sum(t == "mouse" for t in types) / max(len(types), 1)
    results = [_evaluate_variant(user, ref, mouse_ratio) for ref in load_references(target)]
    return max(results, key=lambda r: r.total)
