"""解析エンジン（AI を使わない部分）と、くつしたの決め方。

- analyze(): 線のデータを解析する（誤タップの除外、「と」か、お手本との照合、特徴量、印象の候補）
- decide():  解析の結果と、AI の判定（あれば）から、品質ランクと印象を決めて、くつしたの ID を決める
- template_comment(): AI が使えないときのメッセージ

AI の呼び出しを含む全体の流れは service.py にある。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import numpy as np

from . import catalog, comments, render
from .analysis import axes, features as feat, population, rare
from .analysis.strokes import InputStrokes, prepare_input
from .geometry.score import evaluate
from .refs import DISTRACTORS, TARGET
from .schemas import GeometryResult

# 品質点は「みんなの平均 = 50、標準偏差 = 15」になるよう正規化する。
# 境界は正規分布でおよそ 10% / 20% / 40% / 20% / 10% に分かれる位置
QUALITY_BOUNDS = (31, 42, 58, 69)   # Q1 < 31 <= Q2 < 42 <= Q3 < 58 <= Q4 < 69 <= Q5
# 幾何評価と AI 評価は相関があるので、平均した z 値の広がりを戻す係数
_Z_MEAN_SPREAD = 0.87
IS_TO_MIN_GEOMETRY = 35


def quality_rank(score: float) -> int:
    return 1 + sum(score >= b for b in QUALITY_BOUNDS)


def quality_score(geometry_total: float, ai_beauty: float | None) -> float:
    """幾何評価と AI 美しさを、それぞれみんなの平均・ばらつきで正規化してから合わせた品質点（平均50）。"""
    z = population.zscore("geometry", geometry_total)
    if ai_beauty is not None:
        z = (z + population.zscore("ai_beauty", ai_beauty)) / 2 / _Z_MEAN_SPREAD
    return float(min(100.0, max(0.0, 50 + 15 * z)))


@dataclass
class Analysis:
    inp: InputStrokes
    geometry: GeometryResult
    distractor_totals: dict[str, int]
    is_to_geometry: bool
    order_reversed: bool
    features: dict[str, float | None]
    axes: axes.AxisResult
    timings: dict[str, int] = field(default_factory=dict)

    def feature_descriptions(self) -> list[str]:
        return [population.describe(k, v, self.axes.zs.get(k, 0.0)) for k, v in self.features.items() if k in population.DEFAULTS]

    def quantitative_json(self) -> str:
        """AI に渡す定量データ。"""
        return json.dumps({
            "幾何評価（お手本との照合、各0〜100）": self.geometry.items.model_dump(),
            "幾何評価の合計": self.geometry.total,
            "特徴量": self.feature_descriptions(),
            "印象の軸スコア（正負の向きに意味がある、±3程度）": {
                f"{axes.IMPRESSION_LABELS[p]}(+) / {axes.IMPRESSION_LABELS[n]}(-)": round(self.axes.scores[a], 2)
                for a, (p, n, _) in axes.AXES.items()
            },
            "印象の候補（この中から1つ選ぶ）": [
                {"印象": axes.IMPRESSION_LABELS[c], "id": c, "候補になった理由": self.axes.reasons.get(c, [])}
                for c in self.axes.candidates
            ],
            "誤タップとして除外した画の数": len(self.inp.ignored),
        }, ensure_ascii=False)


def analyze(points_list, pointer_types, canvas) -> Analysis:
    t0 = time.perf_counter()
    inp = prepare_input(points_list, pointer_types, canvas)
    strokes = [a[:, :3] for a in inp.kept]
    geo = evaluate(TARGET, strokes, inp.pointer_types)
    others = {c: evaluate(c, strokes, inp.pointer_types).total for c in DISTRACTORS}
    is_to = geo.total >= IS_TO_MIN_GEOMETRY and geo.total >= max(others.values())
    matched = {p.stroke: p.matched_user_stroke for p in geo.per_stroke}
    order_reversed = (
        len(inp.kept) == 2 and matched.get(1) == 2 and matched.get(2) == 1
    )
    f = feat.compute(inp, [p.ending.detected for p in geo.per_stroke if p.matched_user_stroke])
    ax = axes.compute(f, inp.pointer_types)
    return Analysis(
        inp=inp, geometry=geo, distractor_totals=others, is_to_geometry=is_to,
        order_reversed=order_reversed, features=f, axes=ax,
        timings={"analysis": int((time.perf_counter() - t0) * 1000)},
    )


def decide(a: Analysis, *, impression: str | None, ai_beauty: float | None, ai_is_to: bool | None) -> dict:
    """解析結果と AI① の結果から靴下を決める。AI の結果が無ければ解析エンジンだけで決める。"""
    if impression not in a.axes.candidates:
        impression = a.axes.candidates[0]
    q = quality_score(a.geometry.total, ai_beauty)
    rank = quality_rank(q)
    # 「と」ではない判定は、解析エンジンと AI の両方が否定したときだけ（AI が無ければ解析エンジンのみ）
    is_to = a.is_to_geometry or (ai_is_to is True)
    special, checks = rare.judge(
        is_to=is_to, n_strokes=len(a.inp.kept), order_reversed=a.order_reversed,
        features=a.features, axis_scores=a.axes.scores, quality=q,
    )
    # レア靴下のデザインがあればレアを優先、無ければ「印象 × 綺麗さ」の靴下
    sid = catalog.rare_sock_id(special) or catalog.sock_id(rank, impression)
    return {
        "sock_id": sid, "rare": catalog.rare_sock_id(special) is not None, "special": special, "impression": impression,
        "quality_score": round(q, 1), "quality_rank": rank, "ai_beauty": ai_beauty, "is_to": is_to, "special_checks": checks,
    }


def plain_png(a: Analysis) -> bytes:
    return render.render_plain([s[:, :2] for s in a.inp.kept])


def template_comment(decision: dict) -> str:
    return comments.template_comment(decision["sock_id"], decision["impression"], decision["special"])


def debug_info(a: Analysis, decision: dict, extra: dict | None = None) -> dict:
    return {
        "sock": {k: catalog.item(decision["sock_id"])[k] for k in ("name", "rarity", "comment")},
        "quality": {"rank": decision["quality_rank"], "score": decision["quality_score"], "geometry": a.geometry.total,
                    "ai_beauty": decision.get("ai_beauty")},
        "impression": {
            "id": decision["impression"], "candidates": a.axes.candidates,
            "axes": {k: round(v, 2) for k, v in a.axes.scores.items()},
        },
        "is_to": {"final": decision["is_to"], "geometry": a.is_to_geometry, "geometry_total": a.geometry.total,
                  "distractors": a.distractor_totals},
        "special": decision["special"],
        "special_checks": decision["special_checks"],
        "features": {k: (None if v is None else round(float(v), 4)) for k, v in a.features.items()},
        "feature_text": a.feature_descriptions(),
        "geometry_items": a.geometry.items.model_dump(),
        "ignored_strokes": [i + 1 for i in a.inp.ignored],
        **(extra or {}),
    }


def strokes_for_render(a: Analysis) -> list[np.ndarray]:
    return [s[:, :2] for s in a.inp.kept]
