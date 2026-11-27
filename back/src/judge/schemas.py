"""判定 API のリクエスト / レスポンス。Swagger UI (/docs) にそのまま表示される。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Target = Literal["十", "都", "戸", "徒", "ト", "と"]
Intent = Literal["chikarazuyosa", "yasashisa", "teinei", "genki", "yuuga"]
PointerType = Literal["pen", "touch", "mouse"]
Ending = Literal["tome", "hane", "harai", "any", "unknown"]

MAX_STROKES = 30
MAX_POINTS = 5000


class Canvas(BaseModel):
    width: float = Field(gt=0, examples=[512])
    height: float = Field(gt=0, examples=[512])


class Stroke(BaseModel):
    pointerType: PointerType = "mouse"
    points: list[list[float]] = Field(
        min_length=1,
        description="[x, y, t, pressure] の配列。x,y はキャンバス座標(px)、t は書き始めからの経過ms、pressure は 0〜1（省略可）",
        examples=[[[100, 120, 0, 0.5], [180, 122, 40, 0.5]]],
    )

    @field_validator("points")
    @classmethod
    def _check_points(cls, v: list[list[float]]) -> list[list[float]]:
        for p in v:
            if len(p) not in (3, 4):
                raise ValueError("各点は [x, y, t] または [x, y, t, pressure] で送ってください")
        return v


class JudgeRequest(BaseModel):
    target: Target
    intent: Intent = "teinei"
    canvas: Canvas
    strokes: list[Stroke] = Field(min_length=1, max_length=MAX_STROKES)

    @model_validator(mode="after")
    def _check_total(self) -> "JudgeRequest":
        if sum(len(s.points) for s in self.strokes) > MAX_POINTS:
            raise ValueError(f"点の数が多すぎます（上限 {MAX_POINTS} 点）")
        return self


# ---------- レスポンス ----------

class GeometryItems(BaseModel):
    stroke_count: int
    order: int
    direction: int
    shape: int
    balance: int
    line: int
    endings: int


class EndingResult(BaseModel):
    expected: Ending
    detected: Ending


class PerStroke(BaseModel):
    stroke: int = Field(description="お手本の画番号（1始まり）")
    matched_user_stroke: int | None = Field(description="対応付いたユーザーの画番号（1始まり）。無ければ null")
    reversed: bool
    shape: int | None
    ending: EndingResult


class GeometryResult(BaseModel):
    total: int
    items: GeometryItems
    per_stroke: list[PerStroke]
    user_stroke_count: int
    ref_stroke_count: int
    variant: str


class Beauty(BaseModel):
    balance: int
    line_quality: int
    endings: int
    overall: int


class CorrectionOut(BaseModel):
    stroke: int
    kind: Literal["shape", "balance", "ending", "order", "line"]
    issue: str


class LlmResult(BaseModel):
    read_as: str | None = None
    confidence: int | None = None
    impressions: list[str] = []
    intent_score: int | None = None
    beauty: Beauty | None = None
    good_point: str | None = None
    comment: str | None = None
    corrections: list[CorrectionOut] = []


class JudgeFullResponse(BaseModel):
    final: int
    capped: bool = Field(description="判読がお題と違ったため上限がかかったか")
    degraded: bool = Field(description="LLM が使えず、幾何スコアだけで採点したか")
    geometry: GeometryResult
    llm: LlmResult
    timings_ms: dict[str, int]
