"""入力ストロークの整理: 配列化と誤タップの除外。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# 字全体の大きさに対してこれより短い画は誤タップとみなす
TAP_RATIO = 0.04


@dataclass
class InputStrokes:
    kept: list[np.ndarray]         # (n, 4): x, y, t, pressure（キャンバス座標）
    pointer_types: list[str]
    ignored: list[int]             # 除外した画の番号（0始まり、入力順）
    canvas: tuple[float, float]    # (width, height)


def _to_array(points: list[list[float]]) -> np.ndarray:
    rows = []
    for p in points:
        x, y, t = p[0], p[1], p[2]
        pr = p[3] if len(p) >= 4 else np.nan
        rows.append((x, y, t, pr))
    return np.asarray(rows, dtype=float)


def stroke_length(a: np.ndarray) -> float:
    return float(np.linalg.norm(np.diff(a[:, :2], axis=0), axis=1).sum()) if len(a) > 1 else 0.0


def prepare_input(points_list: list[list[list[float]]], pointer_types: list[str], canvas: tuple[float, float]) -> InputStrokes:
    arrays = [_to_array(p) for p in points_list]
    allp = np.concatenate([a[:, :2] for a in arrays])
    size = float((allp.max(axis=0) - allp.min(axis=0)).max()) or 1.0
    kept, kept_types, ignored = [], [], []
    for i, (a, pt) in enumerate(zip(arrays, pointer_types)):
        if stroke_length(a) < size * TAP_RATIO and len(arrays) > 1:
            ignored.append(i)
        else:
            kept.append(a)
            kept_types.append(pt)
    if not kept:  # 全部が短い場合は除外しない
        kept, kept_types, ignored = arrays, list(pointer_types), []
    return InputStrokes(kept=kept, pointer_types=kept_types, ignored=ignored, canvas=canvas)
