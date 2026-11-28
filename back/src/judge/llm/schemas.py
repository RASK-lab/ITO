"""LLM の構造化出力スキーマ。数値の範囲はプロンプトで指示し、受信後に clamp する。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Impression = Literal["koseiteki", "zatsu", "kawaii", "teinei", "kakkoii",
                     "sensai", "tappitsu", "bukiyou", "atatakai", "tsumetai"]


class ToJudgement(BaseModel):
    """AI① 判定。ユーザーには見せない。"""
    is_to: bool                 # ひらがなの「と」に見えるか
    is_to_confidence: int       # 0-100
    impression: Impression      # 候補3つの中から1つ
    impression_reason: str      # 判断理由（どの特徴が決め手か）
    balance: int                # 美しさ 1-10
    line_quality: int
    endings: int
    overall: int


class SockComment(BaseModel):
    """AI② コメント。ユーザーに表示する。"""
    comment: str


class SockDescription(BaseModel):
    """靴下画像の見た目の説明（事前生成）。"""
    colors: list[str]
    pattern: str
    material_look: str
    condition: str
    motifs: list[str]
    overall: str
