"""特別な書き方の検出（上から優先）。

靴下のデザインは「印象 × 綺麗さ」の50種のみなので、ここで検出した書き方は靴下の選定には使わず、
AI のコメントで触れるための情報として渡す。しきい値はサンプルで調整する。
"""

from __future__ import annotations

THRESHOLDS = {
    "many_taps_min": 3,
    "masterpiece_min_quality": 95,
    "very_fast_max_duration": 0.6,   # 秒
    "very_slow_min_duration": 8.0,   # 秒
    "very_small_max_size": 0.08,     # キャンバス長辺に対する比
    "very_large_min_size": 0.95,
    "balanced_max_axis": 0.35,       # 全軸の |スコア| がこれ未満
}

NOTES = {
    "not_to": "「と」とは少し違う字に見えた",
    "one_stroke": "一筆で書いた",
    "reversed_order": "2画目から書き始めた（書き順が逆）",
    "many_taps": "小さな点や継ぎ足しが多い",
    "masterpiece": "お手本のように見事な字",
    "very_fast": "目にも止まらぬ速さで書いた",
    "very_slow": "とても時間をかけて書いた",
    "very_small": "とても小さく書いた",
    "very_large": "キャンバスいっぱいに大きく書いた",
    "balanced": "どの印象にも偏らない、ど真ん中の書きぶり",
}


def judge(
    *,
    is_to: bool,
    n_strokes: int,
    order_reversed: bool,
    features: dict[str, float | None],
    axis_scores: dict[str, float],
    quality: float | None,
) -> tuple[str | None, dict[str, bool]]:
    """返り値: (最も優先度の高い特別な書き方のキー または None, 各条件の判定結果)"""
    T = THRESHOLDS
    dur = features.get("duration")
    size = features.get("size") or 0.0
    checks = {
        "not_to": not is_to,
        "one_stroke": n_strokes == 1,
        "reversed_order": order_reversed,
        "many_taps": (features.get("sloppiness") or 0) >= T["many_taps_min"],
        "masterpiece": quality is not None and quality >= T["masterpiece_min_quality"],
        "very_fast": dur is not None and dur < T["very_fast_max_duration"],
        "very_slow": dur is not None and dur >= T["very_slow_min_duration"],
        "very_small": size < T["very_small_max_size"],
        "very_large": size >= T["very_large_min_size"],
        "balanced": all(abs(s) < T["balanced_max_axis"] for s in axis_scores.values()),
    }
    checks = {k: bool(v) for k, v in checks.items()}
    for key, hit in checks.items():
        if hit:
            return key, checks
    return None, checks
