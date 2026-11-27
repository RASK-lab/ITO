"""ユーザーの画とお手本の画の対応付け、書き順・運筆方向の判定。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment


@dataclass
class Assignment:
    pairs: list[tuple[int, int]]   # (user_index, ref_index)、user_index 順
    reversed: dict[int, bool]      # user_index -> 逆向きに書いたか
    costs: dict[int, float]        # user_index -> 対応コスト


def pair_cost(u: np.ndarray, r: np.ndarray) -> tuple[float, bool]:
    """等間隔リサンプル済みの (N,2) 同士。対応点の平均距離。逆向きも試す。"""
    fwd = float(np.linalg.norm(u - r, axis=1).mean())
    rev = float(np.linalg.norm(u[::-1] - r, axis=1).mean())
    return (fwd, False) if fwd <= rev else (rev, True)


def assign(user: list[np.ndarray], ref: list[np.ndarray]) -> Assignment:
    C = np.zeros((len(user), len(ref)))
    R = np.zeros_like(C, dtype=bool)
    for i, u in enumerate(user):
        for j, r in enumerate(ref):
            C[i, j], R[i, j] = pair_cost(u, r)
    rows, cols = linear_sum_assignment(C)  # 画数が違っても動く（矩形行列）
    pairs = sorted(zip(rows.tolist(), cols.tolist()))
    return Assignment(
        pairs=pairs,
        reversed={i: bool(R[i, j]) for i, j in pairs},
        costs={i: float(C[i, j]) for i, j in pairs},
    )


def order_inversions(pairs: list[tuple[int, int]]) -> int:
    """ユーザーが書いた順に並べたとき、お手本の画番号が逆転している組の数。"""
    seq = [j for _, j in sorted(pairs)]
    return sum(1 for a in range(len(seq)) for b in range(a + 1, len(seq)) if seq[a] > seq[b])
