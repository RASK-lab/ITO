"""レア10種の判定（上から優先）。しきい値はサンプルで調整する。"""

from __future__ import annotations

THRESHOLDS = {
    "kedama_min_sloppiness": 3,
    "kinshi_min_quality": 95,
    "idaten_max_duration": 0.6,   # 秒
    "amikake_min_duration": 8.0,  # 秒
    "baby_max_size": 0.08,        # キャンバス長辺に対する比
    "loose_min_size": 0.95,
    "niji_max_axis": 0.35,        # 全軸の |スコア| がこれ未満
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
    """返り値: (レアの ID または None, 各条件の判定結果)"""
    T = THRESHOLDS
    dur = features.get("duration")
    size = features.get("size") or 0.0
    checks = {
        "R-katahou": not is_to,
        "R-ippon": n_strokes == 1,
        "R-uragaeshi": order_reversed,
        "R-kedama": (features.get("sloppiness") or 0) >= T["kedama_min_sloppiness"],
        "R-kinshi": quality is not None and quality >= T["kinshi_min_quality"],
        "R-idaten": dur is not None and dur < T["idaten_max_duration"],
        "R-amikake": dur is not None and dur >= T["amikake_min_duration"],
        "R-baby": size < T["baby_max_size"],
        "R-loose": size >= T["loose_min_size"],
        "R-niji": all(abs(s) < T["niji_max_axis"] for s in axis_scores.values()),
    }
    checks = {k: bool(v) for k, v in checks.items()}
    for rid, hit in checks.items():
        if hit:
            return rid, checks
    return None, checks
