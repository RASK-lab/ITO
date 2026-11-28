"""判定 API のリクエスト / レスポンス。Swagger UI (/docs) にそのまま表示される。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

PointerType = Literal["pen", "touch", "mouse"]
Ending = Literal["tome", "hane", "harai", "any", "unknown"]

# /api/drawings（back/src/drawings.py）と同じ上限。線の本数には上限を置かない
MAX_POINTS = 200_000


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
    canvas: Canvas
    strokes: list[Stroke] = Field(min_length=1, max_length=MAX_POINTS)

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


class JudgeResponse(BaseModel):
    sock_id: str = Field(description="靴下の ID（画像ファイル名と同じ）。socks.json の id（印象×綺麗さのマスの靴下）", examples=["REGAL-08"])
    comment: str = Field(description="ユーザーに表示するコメント")
    degraded: bool = Field(description="AI を使わずに判定した場合 true（コメントはテンプレート文）")
    debug: dict | None = Field(default=None, description="内部の評価（DEV=1 のときだけ）")
