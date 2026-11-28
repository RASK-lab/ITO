"""判定の全体の流れ: 解析エンジン → AI①判定 → 靴下ID → AI②コメント。"""

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

QUALITY_BOUNDS = (30, 50, 70, 85)   # Q1 < 30 <= Q2 < 50 <= Q3 < 70 <= Q4 < 85 <= Q5
IS_TO_MIN_GEOMETRY = 35


def quality_rank(score: float) -> int:
    return 1 + sum(score >= b for b in QUALITY_BOUNDS)


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
    q = 0.5 * a.geometry.total + 0.5 * ai_beauty if ai_beauty is not None else float(a.geometry.total)
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
        "quality_score": round(q, 1), "quality_rank": rank, "is_to": is_to, "special_checks": checks,
    }


def plain_png(a: Analysis) -> bytes:
    return render.render_plain([s[:, :2] for s in a.inp.kept])


def template_comment(decision: dict) -> str:
    return comments.template_comment(decision["sock_id"], decision["impression"], decision["special"])


def debug_info(a: Analysis, decision: dict, extra: dict | None = None) -> dict:
    return {
        "sock": {k: catalog.item(decision["sock_id"])[k] for k in ("name", "rarity", "comment")},
        "quality": {"rank": decision["quality_rank"], "score": decision["quality_score"], "geometry": a.geometry.total},
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
