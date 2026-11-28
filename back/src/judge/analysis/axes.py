"""5本の印象の軸と、印象10種の候補。"""

from __future__ import annotations

import math
from dataclasses import dataclass

from . import population

# 軸: (正の端の印象, 負の端の印象, {特徴量: 重み})。重みは z 値にかける
AXES: dict[str, tuple[str, str, dict[str, float]]] = {
    "carefulness": ("teinei", "zatsu", {
        "speed": -0.4, "duration": 0.3, "tome_rate": 0.3, "sloppiness": -0.3,
    }),
    "fluency": ("tappitsu", "bukiyou", {
        "speed_cv": -0.35, "pauses": -0.3, "jitter": -0.25, "gap_time": -0.15,
    }),
    "roundness": ("kawaii", "kakkoii", {
        "turn_radius": 0.45, "corners": -0.3, "straight_ratio": -0.25,
    }),
    "warmth": ("atatakai", "tsumetai", {
        "aspect": 0.4, "pocket": 0.4, "gap12": -0.2,
    }),
    "boldness": ("koseiteki", "sensai", {
        "tilt": 0.3, "placement": 0.25, "size": 0.25, "pressure": 0.2,
    }),
}

IMPRESSIONS = ("koseiteki", "zatsu", "kawaii", "teinei", "kakkoii", "sensai", "tappitsu", "bukiyou", "atatakai", "tsumetai")

IMPRESSION_LABELS = {
    "koseiteki": "個性的", "zatsu": "雑", "kawaii": "かわいい", "teinei": "丁寧", "kakkoii": "かっこいい",
    "sensai": "繊細", "tappitsu": "達筆", "bukiyou": "不器用", "atatakai": "温かい", "tsumetai": "冷たい",
}

# AI に渡す定義（計画書 04 の表と同じ）
IMPRESSION_DEFINITIONS = {
    "teinei": "ゆっくり一定の速さで、終わりをきちんと止める。画の端まで気を配っている",
    "zatsu": "速く短時間で、終わりが流れる・はみ出す。継ぎ足しや誤タップがある",
    "tappitsu": "迷いなく流れるように書く。速さの緩急が滑らかで、1画目から2画目への移りもスムーズ",
    "bukiyou": "途中で止まる・カクつく・ふるえる。速さが不規則でぎこちない",
    "kawaii": "折り返しが丸く、ころんとした形。カーブがやわらかい",
    "kakkoii": "折り返しが鋭い・角ばる。直線的でシャープ",
    "atatakai": "横にゆったり広がり、ふところが大きい。1画目と2画目が寄り添う",
    "tsumetai": "縦長で細く、ふところが狭い。1画目と2画目が離れていて硬い",
    "koseiteki": "お手本の配置から大胆に外れる（大きな傾き、独特な位置関係）。字が大きく動きがある",
    "sensai": "小さく控えめで、細やかな動き。お手本の配置から外れず、線が軽い",
}

# 速さに関係する特徴量は入力機器ごとの母集団で比べる
DEVICE_DEPENDENT = {"speed", "duration", "speed_cv", "pauses", "gap_time", "pressure"}


@dataclass
class AxisResult:
    scores: dict[str, float]                    # 軸名 -> スコア（正なら正の端）
    zs: dict[str, float]                        # 特徴量 -> z 値
    candidates: list[str]                       # 印象の候補（上位3つ）
    reasons: dict[str, list[str]]               # 印象 -> 候補になった理由（特徴量の説明）


def _device(pointer_types: list[str]) -> str:
    if not pointer_types:
        return "pen"
    return max(set(pointer_types), key=pointer_types.count)


def compute(features: dict[str, float | None], pointer_types: list[str]) -> AxisResult:
    dev = _device(pointer_types)
    zs = {
        k: population.zscore(k, v, dev if k in DEVICE_DEPENDENT else None)
        for k, v in features.items() if k in population.DEFAULTS
    }
    scores: dict[str, float] = {}
    contrib: dict[str, list[tuple[float, str]]] = {}
    for axis, (_pos, _neg, weights) in AXES.items():
        norm = math.sqrt(sum(w * w for w in weights.values()))
        s = 0.0
        parts = []
        for f, w in weights.items():
            c = w * zs.get(f, 0.0)
            s += c
            parts.append((c, f))
        scores[axis] = s / norm
        contrib[axis] = parts

    order = sorted(scores, key=lambda a: abs(scores[a]), reverse=True)
    candidates, reasons = [], {}
    for axis in order[:3]:
        pos, neg, _ = AXES[axis]
        imp = pos if scores[axis] >= 0 else neg
        candidates.append(imp)
        sign = 1 if scores[axis] >= 0 else -1
        top = sorted(contrib[axis], key=lambda cf: cf[0] * sign, reverse=True)[:2]
        reasons[imp] = [
            population.describe(f, features.get(f), zs.get(f, 0.0)) for c, f in top if c * sign > 0
        ]
    return AxisResult(scores=scores, zs=zs, candidates=candidates, reasons=reasons)
