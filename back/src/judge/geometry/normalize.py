"""ストロークの前処理: 正規化・弧長リサンプル・平滑化。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

N_SAMPLES = 64
_EPS = 1e-9


@dataclass
class PreparedStroke:
    raw: np.ndarray        # (n, 2) 正規化済みの生の点（平滑化なし、線質・終筆用）
    t: np.ndarray          # (n,) 経過ms
    resampled: np.ndarray  # (N_SAMPLES, 2) 弧長で等間隔、平滑化済み
    length: float


def normalize_xy(strokes_xy: list[np.ndarray]) -> list[np.ndarray]:
    """全画のバウンディングボックスを、縦横比を保って単位正方形の中央に収める。"""
    allp = np.concatenate(strokes_xy, axis=0)
    lo, hi = allp.min(axis=0), allp.max(axis=0)
    scale = max(float((hi - lo).max()), _EPS)
    center = (lo + hi) / 2.0
    return [(s - center) / scale + 0.5 for s in strokes_xy]


def arc_length(xy: np.ndarray) -> np.ndarray:
    seg = np.linalg.norm(np.diff(xy, axis=0), axis=1) if len(xy) > 1 else np.zeros(0)
    return np.concatenate([[0.0], np.cumsum(seg)])


def resample(xy: np.ndarray, n: int = N_SAMPLES) -> np.ndarray:
    """弧長で等間隔に n 点を取る。長さ 0 の画（点）は同じ点を n 個並べる。"""
    cum = arc_length(xy)
    if cum[-1] < _EPS:
        return np.repeat(xy[:1], n, axis=0)
    # 同じ位置の点が続くと interp が壊れるので取り除く
    keep = np.concatenate([[True], np.diff(cum) > _EPS])
    cum, xy = cum[keep], xy[keep]
    targets = np.linspace(0.0, cum[-1], n)
    return np.stack([np.interp(targets, cum, xy[:, 0]), np.interp(targets, cum, xy[:, 1])], axis=1)


def smooth(xy: np.ndarray, window: int = 3) -> np.ndarray:
    """端点を保ったまま移動平均をかける。"""
    if len(xy) <= window:
        return xy.copy()
    k = np.ones(window) / window
    out = xy.copy()
    half = window // 2
    for d in range(2):
        out[half:-half, d] = np.convolve(xy[:, d], k, mode="valid")
    return out


def prepare(strokes: list[np.ndarray]) -> list[PreparedStroke]:
    """strokes: 各画 (n, 2) または (n, 3+)。3列目以降があれば t として使う。"""
    xy = [np.asarray(s, dtype=float)[:, :2] for s in strokes]
    ts = [
        np.asarray(s, dtype=float)[:, 2] if np.asarray(s).shape[1] >= 3 else np.arange(len(s), dtype=float)
        for s in strokes
    ]
    norm = normalize_xy(xy)
    out = []
    for p, t in zip(norm, ts):
        if len(p) == 1:  # タップだけの画は2点にしておく
            p = np.repeat(p, 2, axis=0)
            t = np.repeat(t, 2)
        rs = smooth(resample(p))
        out.append(PreparedStroke(raw=p, t=t, resampled=rs, length=float(arc_length(p)[-1])))
    return out
