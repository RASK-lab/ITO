"""LLM の構造化出力スキーマ。数値の範囲はプロンプトで指示し、受信後に clamp する。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Candidate = Literal["十", "都", "戸", "徒", "ト", "と", "土", "寸", "卜", "ど", "こ", "ラ", "その他"]


class ImpressionAxes(BaseModel):
    chikarazuyosa: int  # 力強さ 0-10
    yasashisa: int      # やさしさ
    teinei: int         # 丁寧さ
    genki: int          # 元気
    yuuga: int          # 優雅


class BlindRead(BaseModel):
    read_as: Candidate
    confidence: int          # 0-100
    impressions: list[str]   # 3語
    axes: ImpressionAxes


class Correction(BaseModel):
    stroke: int              # 1始まりの画番号
    kind: Literal["shape", "balance", "ending", "order", "line"]
    issue: str


class Critique(BaseModel):
    balance: int             # 1-10
    line_quality: int
    endings: int
    overall: int
    good_point: str
    comment: str             # 120字以内
    corrections: list[Correction]
