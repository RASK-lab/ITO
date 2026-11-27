"""幾何スコアと LLM の結果を統合して最終点を出す。"""

from __future__ import annotations

from .llm.schemas import BlindRead, Critique
from .schemas import Beauty, CorrectionOut, GeometryResult, LlmResult

WEIGHTS = {"geometry": 0.45, "beauty": 0.35, "intent": 0.20}
CAP_WHEN_MISREAD = 60


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(v)))


def build_llm_result(blind: BlindRead | None, crit: Critique | None, intent: str, n_strokes: int) -> LlmResult:
    out = LlmResult()
    if blind is not None:
        out.read_as = blind.read_as
        out.confidence = _clamp(blind.confidence, 0, 100)
        out.impressions = blind.impressions[:3]
        out.intent_score = _clamp(getattr(blind.axes, intent), 0, 10) * 10
    if crit is not None:
        out.beauty = Beauty(
            balance=_clamp(crit.balance, 1, 10),
            line_quality=_clamp(crit.line_quality, 1, 10),
            endings=_clamp(crit.endings, 1, 10),
            overall=_clamp(crit.overall, 1, 10),
        )
        out.good_point = crit.good_point
        out.comment = crit.comment
        out.corrections = [
            CorrectionOut(stroke=c.stroke, kind=c.kind, issue=c.issue)
            for c in crit.corrections[:3]
            if 1 <= c.stroke <= n_strokes
        ]
    return out


def final_score(target: str, geo: GeometryResult, llm: LlmResult) -> tuple[int, bool, bool]:
    """返り値: (最終点, 上限がかかったか, LLM なしで採点したか)"""
    parts = {"geometry": float(geo.total)}
    if llm.beauty is not None:
        b = llm.beauty
        parts["beauty"] = (b.balance + b.line_quality + b.endings + b.overall) / 4 * 10
    if llm.intent_score is not None:
        parts["intent"] = float(llm.intent_score)

    degraded = len(parts) < 3
    wsum = sum(WEIGHTS[k] for k in parts)
    score = sum(parts[k] * WEIGHTS[k] for k in parts) / wsum

    capped = llm.read_as is not None and llm.read_as != target and score > CAP_WHEN_MISREAD
    if capped:
        score = CAP_WHEN_MISREAD
    return int(round(score)), capped, degraded
