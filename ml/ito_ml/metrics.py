"""評価の指標。クラスの数に偏りがあるので、正解率（accuracy）ではなく、クラスごとの成績を
平均した値で比べる。

- macro_f1: クラスごとの F1 の平均。モデルを選ぶときの主な指標。
- balanced_accuracy: クラスごとの再現率（そのクラスの画像のうち当たった割合）の平均。
  4 クラスなら、でたらめに答えると 0.25。
- 出どころ（フォント、くずし字、集めた手書き）ごとにも出す。本番の入力に近いのは
  フォントと集めた手書きなので、くずし字の成績だけで決めない。
"""

from __future__ import annotations

import numpy as np


def confusion(y_true, y_pred, n_classes: int) -> np.ndarray:
    """行が正解、列が予測"""
    m = np.zeros((n_classes, n_classes), dtype=np.int64)
    for t, p in zip(y_true, y_pred):
        m[int(t), int(p)] += 1
    return m


def scores(y_true, y_pred, n_classes: int) -> dict:
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    m = confusion(y_true, y_pred, n_classes)
    support = m.sum(1)
    predicted = m.sum(0)
    tp = np.diag(m).astype(np.float64)
    recall = np.divide(tp, support, out=np.zeros_like(tp), where=support > 0)
    precision = np.divide(tp, predicted, out=np.zeros_like(tp), where=predicted > 0)
    f1 = np.divide(2 * precision * recall, precision + recall, out=np.zeros_like(tp),
                   where=(precision + recall) > 0)
    present = support > 0  # 正解に 1 枚も無いクラスは平均に入れない
    return {
        "n": int(len(y_true)),
        "accuracy": float((y_true == y_pred).mean()) if len(y_true) else 0.0,
        "macro_f1": float(f1[present].mean()) if present.any() else 0.0,
        "balanced_accuracy": float(recall[present].mean()) if present.any() else 0.0,
        "recall": recall.round(4).tolist(),
        "f1": f1.round(4).tolist(),
        "support": support.tolist(),
        "confusion": m.tolist(),
    }


def report(y_true, y_pred, sources, n_classes: int) -> dict:
    """全体と、出どころごとの指標"""
    sources = np.asarray(sources)
    out = {"all": scores(y_true, y_pred, n_classes)}
    for s in sorted(set(sources.tolist())):
        mask = sources == s
        out[s] = scores(np.asarray(y_true)[mask], np.asarray(y_pred)[mask], n_classes)
    return out


def format_report(rep: dict, classes: list[str]) -> str:
    lines = [f"{'':14s}{'n':>6s}{'macroF1':>9s}{'balAcc':>8s}{'acc':>7s}  " + "  ".join(f"{c[:8]:>8s}" for c in classes)]
    for name, r in rep.items():
        recall = "  ".join(f"{x:8.2f}" for x in r["recall"])
        lines.append(f"{name[:14]:14s}{r['n']:6d}{r['macro_f1']:9.3f}{r['balanced_accuracy']:8.3f}"
                     f"{r['accuracy']:7.3f}  {recall}")
    lines.append("（右の列はクラスごとの再現率）")
    return "\n".join(lines)
