"""テスト用: お手本から「ユーザーが書いたような」ストロークを作る。"""

from __future__ import annotations

import numpy as np

from src.judge.refs import load_references


def timed_stroke(xy: np.ndarray, ending: str = "tome", base_dt: float = 8.0) -> np.ndarray:
    """点列に時刻を付ける。tome は終端で減速、harai は等速のまま抜ける。"""
    n = len(xy)
    dt = np.full(n - 1, base_dt)
    if ending in ("tome", "hane"):
        tail = max(int((n - 1) * 0.15), 2)
        dt[-tail:] = base_dt * np.linspace(2.0, 8.0, tail)  # 遅くなる = 時間がかかる
    t = np.concatenate([[0.0], np.cumsum(dt)])
    return np.column_stack([xy, t, np.full(n, 0.5)])


def from_reference(
    char: str,
    scale: float = 400.0,
    offset: tuple[float, float] = (56.0, 56.0),
    noise: float = 0.0,
    seed: int = 0,
    order: list[int] | None = None,
    reverse: set[int] | None = None,
) -> list[np.ndarray]:
    ref = load_references(char)[0]
    rng = np.random.default_rng(seed)
    out = []
    t0 = 0.0
    idx = order if order is not None else list(range(len(ref.strokes)))
    for j in idx:
        xy = ref.strokes[j] * scale + np.asarray(offset)
        if noise:
            # 低周波のゆがみ（手ぶれ）
            k = np.linspace(0, np.pi, len(xy))
            xy = xy + noise * scale * np.column_stack([
                np.sin(k * rng.uniform(1, 3) + rng.uniform(0, 6)),
                np.sin(k * rng.uniform(1, 3) + rng.uniform(0, 6)),
            ]) + rng.normal(0, noise * scale * 0.05, xy.shape)
        if reverse and j in reverse:
            xy = xy[::-1]
        s = timed_stroke(xy, ref.endings[j])
        s[:, 2] += t0
        t0 = s[-1, 2] + 150
        out.append(s)
    return out
