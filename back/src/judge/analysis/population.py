"""特徴量の母集団統計と、偏差（z値）・パーセンタイルへの変換。

初期値は手で置いた仮の値。サンプル収集後に `population.json` を生成して上書きする
（`python -m src.judge.tools.build_population`）。
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

POPULATION_FILE = Path(__file__).resolve().parent / "population.json"

# 特徴量名: (平均, 標準偏差, 説明, 単位)
DEFAULTS: dict[str, tuple[float, float]] = {
    "speed": (0.8, 0.4),            # キャンバス長辺/秒
    "duration": (1.5, 0.8),         # 秒
    "tome_rate": (0.6, 0.35),
    "sloppiness": (0.2, 0.5),       # 誤タップ・余分な画の数
    "speed_cv": (0.45, 0.2),
    "pauses": (0.3, 0.6),
    "jitter": (0.15, 0.12),         # rad
    "gap_time": (0.3, 0.2),         # 秒
    "turn_radius": (0.19, 0.06),    # 字の長辺 = 1
    "corners": (0.3, 0.5),
    "straight_ratio": (0.5, 0.15),
    "stroke1_angle": (14.0, 10.0),  # 度
    "stroke1_len": (0.45, 0.12),
    "aspect": (0.72, 0.15),
    "pocket": (0.36, 0.08),
    "gap12": (0.06, 0.06),
    "tilt": (4.0, 4.0),             # 度
    "placement": (0.04, 0.03),
    "size": (0.55, 0.18),           # キャンバス長辺に対する比
    "pressure": (0.5, 0.2),
}

LABELS = {
    "speed": "書く速さ", "duration": "書き終わるまでの時間", "tome_rate": "止めの処理",
    "sloppiness": "誤タップ・余分な画", "speed_cv": "速さのむら", "pauses": "途中で止まった回数",
    "jitter": "線のふるえ", "gap_time": "1画目から2画目への間", "turn_radius": "折り返しの丸み",
    "corners": "角ばった折れ", "straight_ratio": "直線的な部分", "stroke1_angle": "1画目の傾き",
    "stroke1_len": "1画目の長さ", "aspect": "横幅（縦横比）", "pocket": "ふところの広さ",
    "gap12": "1画目と2画目の間隔", "tilt": "字全体の傾き", "placement": "配置のお手本からのずれ",
    "size": "字の大きさ", "pressure": "筆圧",
}

Z_CLIP = 3.0


@lru_cache(maxsize=1)
def _overrides() -> dict[str, list[float]]:
    if POPULATION_FILE.is_file():
        return json.loads(POPULATION_FILE.read_text(encoding="utf-8"))
    return {}


def stats(name: str, device: str | None = None) -> tuple[float, float]:
    ov = _overrides()
    for key in ([f"{name}@{device}"] if device else []) + [name]:
        if key in ov:
            m, s = ov[key]
            return float(m), max(float(s), 1e-6)
    m, s = DEFAULTS[name]
    return m, s


def zscore(name: str, value: float | None, device: str | None = None) -> float:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return 0.0
    m, s = stats(name, device)
    return max(-Z_CLIP, min(Z_CLIP, (value - m) / s))


def percentile(z: float) -> int:
    return int(round(50 * (1 + math.erf(z / math.sqrt(2)))))


def describe(name: str, value: float | None, z: float) -> str:
    """AI に渡すための人が読める表現（例: 書く速さ: 上位8%（高い））。"""
    if value is None:
        return f"{LABELS[name]}: 計測できず"
    p = percentile(z)
    if p >= 50:
        return f"{LABELS[name]}: 上位{100 - p}%（高い）" if p >= 70 else f"{LABELS[name]}: 平均的（やや高い）"
    return f"{LABELS[name]}: 下位{p}%（低い）" if p <= 30 else f"{LABELS[name]}: 平均的（やや低い）"
