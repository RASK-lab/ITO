"""お手本データの読み込み。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import yaml

REFS_DIR = Path(__file__).resolve().parent

TARGET_CHARS = ("十", "都", "戸", "徒", "ト", "と")


class Reference:
    def __init__(self, char: str, variant: str, strokes: list[np.ndarray], kvg_types: list[str], endings: list[str]):
        self.char = char
        self.variant = variant
        self.strokes = strokes          # 各画 (64, 2)、0〜1 座標
        self.kvg_types = kvg_types
        self.endings = endings          # tome / hane / harai / any


@lru_cache(maxsize=1)
def _endings() -> dict[str, list[str]]:
    return yaml.safe_load((REFS_DIR / "endings.yaml").read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def load_references(char: str) -> tuple[Reference, ...]:
    if char not in TARGET_CHARS:
        raise KeyError(char)
    data = json.loads((REFS_DIR / f"{ord(char):05x}.json").read_text(encoding="utf-8"))
    endings = _endings().get(char)
    refs = []
    for v in data["variants"]:
        strokes = [np.asarray(s["points"], dtype=float) for s in v["strokes"]]
        ends = endings if endings and len(endings) == len(strokes) else ["any"] * len(strokes)
        refs.append(Reference(char, v["name"], strokes, [s["kvg_type"] for s in v["strokes"]], list(ends)))
    return tuple(refs)


def raw_reference(char: str) -> dict:
    """フロント向け（糸リプレイのお手本表示）にそのまま返す JSON。"""
    if char not in TARGET_CHARS:
        raise KeyError(char)
    return json.loads((REFS_DIR / f"{ord(char):05x}.json").read_text(encoding="utf-8"))
