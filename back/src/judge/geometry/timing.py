"""時間方向の処理。マウスやタッチは点の届く間隔が不規則なので、一定の時間間隔に取り直してから速さを測る。"""

from __future__ import annotations

import numpy as np


def speed_profile(xy: np.ndarray, t: np.ndarray, step: float) -> tuple[np.ndarray, np.ndarray]:
    """一定時間 step ごとの速さと、その区間の終わりまでの累積距離を返す。

    xy: (n, 2)、t: (n,) 単調増加の時刻。時刻が重複・逆行する点は除く。
    返り値: (speeds (m,), cum_dist (m,))。点が足りなければ空配列。
    """
    if len(xy) < 2:
        return np.zeros(0), np.zeros(0)
    keep = np.concatenate([[True], np.diff(t) > 0])
    xy, t = xy[keep], t[keep]
    if len(xy) < 2 or t[-1] - t[0] < step * 2:
        return np.zeros(0), np.zeros(0)
    cum = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))])
    ts = np.arange(t[0], t[-1] + step * 0.5, step)
    d = np.interp(ts, t, cum)
    return np.diff(d) / step, d[1:]
