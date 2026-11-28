"""ラベルの偏り（クラスの数の差）と、データの出どころの偏りへの対策。

ラベル付けの結果、クラスの数に大きな差が出る見込み。そのまま学習すると、多いクラスばかり
答えるモデルになる（正解率は高く見えても、少ないクラスをまったく当てない）。

対策（train.py で選べる。ふつうは sampler）:
- sampler: 数の少ないクラスの画像を多めに選んで学習する（1 回の学習で各クラスがほぼ同じ数に
  なるように）。同じ画像が何度も選ばれるので、少ないクラスほど水増しを強くかけ
  （augment_strength）、毎回少しずつ違う画像にする。
- loss: 選び方は変えず、誤りの重み（損失）を少ないクラスほど大きくする。
- 出どころ: くずし字が全体の 98% なので、出どころでも選び方をならす（source_power）。
  ならさないと、フォント（＝本番の入力に近い画像）からほとんど学ばない。

評価は、クラスごとの成績を平均した値（macro-F1、balanced accuracy）で見る（metrics.py）。
"""

from __future__ import annotations

from collections import Counter

import numpy as np


def sample_weights(labels: list[int], sources: list[str], class_power: float = 1.0,
                   source_power: float = 0.5) -> np.ndarray:
    """1 枚ごとの選ばれやすさ（合計 1）。

    class_power: 1 で各クラスが同じ数ずつ選ばれる。0 で偏りのまま。0.5 はその中間。
    source_power: 同じく出どころについて。
    """
    n_class = Counter(labels)
    n_source = Counter(sources)
    w = np.array([n_class[y] ** -class_power * n_source[s] ** -source_power
                  for y, s in zip(labels, sources)], dtype=np.float64)
    return w / w.sum()


def class_weights(labels: list[int], n_classes: int, power: float = 1.0) -> np.ndarray:
    """損失の重み（平均が 1）。1 枚も無いクラスは 0。"""
    n = np.bincount(np.asarray(labels, dtype=np.int64), minlength=n_classes).astype(np.float64)
    w = np.where(n > 0, np.maximum(n, 1) ** -power, 0.0)
    return w / w[n > 0].mean()


def augment_strength(labels: list[int], base: float = 1.0, boost: float = 1.0) -> np.ndarray:
    """1 枚ごとの水増しの強さ。いちばん多いクラスは base、少ないクラスほど強く（最大 2）。"""
    n = Counter(labels)
    top = max(n.values())
    s = [base * (1 + boost * (1 - (n[y] / top) ** 0.5)) for y in labels]
    return np.clip(np.array(s), 0.0, 2.0)


def describe(labels: list[int], sources: list[str], classes: list[str]) -> str:
    """偏りの表（ログ用）"""
    lines = []
    by = Counter(zip(sources, labels))
    for source in sorted(set(sources)):
        counts = ", ".join(f"{c}={by[(source, i)]}" for i, c in enumerate(classes))
        lines.append(f"  {source}: {counts}")
    total = Counter(labels)
    lines.append("  合計: " + ", ".join(f"{c}={total[i]}" for i, c in enumerate(classes)))
    return "\n".join(lines)
