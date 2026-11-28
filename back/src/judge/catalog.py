"""靴下50種のカタログ（デザイン担当の catalog/socks.json をそのまま読む）。

socks.json の各靴下は「印象（feature）10種 × 綺麗さ（beauty）1〜5」の50マスに1足ずつ対応する。
判定エンジンは印象と品質ランク（＝綺麗さ）を決め、そのマスの靴下を選ぶ。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .analysis.axes import IMPRESSIONS
from .settings import settings

CATALOG_DIR = Path(__file__).resolve().parent / "catalog"
SOCKS_FILE = CATALOG_DIR / "socks.json"

QUALITY_RANKS = (1, 2, 3, 4, 5)

# socks.json の feature（日本語）→ 判定エンジンの印象 ID
FEATURE_TO_IMPRESSION = {
    "個性的": "koseiteki", "雑": "zatsu", "可愛い": "kawaii", "かわいい": "kawaii", "丁寧": "teinei",
    "かっこいい": "kakkoii", "繊細": "sensai", "達筆": "tappitsu", "不器用": "bukiyou",
    "暖かい": "atatakai", "温かい": "atatakai", "冷たい": "tsumetai",
}


@lru_cache(maxsize=1)
def _data() -> dict:
    return json.loads(SOCKS_FILE.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _items() -> dict[str, dict]:
    return {it["id"]: it for it in _data()["items"]}


def is_rare(it: dict) -> bool:
    """レア靴下は classification に feature/beauty の代わりに special（特別な書き方のキー）を持つ。"""
    return "special" in it["classification"]


@lru_cache(maxsize=1)
def _grid() -> dict[tuple[str, int], str]:
    grid = {}
    for it in _data()["items"]:
        if is_rare(it):
            continue
        c = it["classification"]
        grid[(FEATURE_TO_IMPRESSION[c["feature"]], int(c["beauty"]))] = it["id"]
    return grid


@lru_cache(maxsize=1)
def _rares() -> dict[str, str]:
    return {it["classification"]["special"]: it["id"] for it in _data()["items"] if is_rare(it)}


def rare_sock_id(special: str | None) -> str | None:
    """特別な書き方に対応するレア靴下の ID。まだデザインが無ければ None。"""
    return _rares().get(special) if special else None


def sock_id(quality_rank: int, impression: str) -> str:
    """印象と品質ランク（綺麗さ1〜5）に対応する靴下の ID。"""
    return _grid()[(impression, quality_rank)]


def all_ids() -> list[str]:
    return list(_items())


def item(sid: str) -> dict:
    return _items()[sid]


def label(sid: str) -> str:
    it = item(sid)
    return f"{it['name']}（{it['rarity']}）"


def image_path(sid: str) -> Path | None:
    p = CATALOG_DIR / item(sid)["image"]
    return p if p.is_file() else None


def image_source(sid: str) -> Path | str | None:
    """AI② に渡す靴下画像。ローカルの画像があればそれ、無ければ本番の URL、どちらも無ければ None。"""
    local = image_path(sid)
    if local is not None:
        return local
    if settings.sock_image_base_url:
        return f"{settings.sock_image_base_url.rstrip('/')}/{Path(item(sid)['image']).name}"
    return None


def description(sid: str) -> dict:
    """AI② に渡す、デザイン担当による靴下の説明。"""
    it = item(sid)
    c = it["classification"]
    return {
        "名前": it["name"],
        "レアリティ": it["rarity"],
        "見た目": it["comment"],
        "この靴下が合う理由": c.get("review", {}).get("reason"),
    }


def check() -> list[str]:
    """カタログの不備（50マスの欠け・印象名の不一致・画像の欠け）を返す。"""
    problems = []
    from .analysis.rare import NOTES
    for it in _data()["items"]:
        if is_rare(it):
            if it["classification"]["special"] not in NOTES:
                problems.append(f"{it['id']}: 未知の special {it['classification']['special']}")
            if not (CATALOG_DIR / it["image"]).is_file():
                problems.append(f"{it['id']}: 画像が無い {it['image']}")
            continue
        f = it["classification"]["feature"]
        if f not in FEATURE_TO_IMPRESSION:
            problems.append(f"{it['id']}: 未知の印象 {f}")
        if not (CATALOG_DIR / it["image"]).is_file():
            problems.append(f"{it['id']}: 画像が無い {it['image']}")
    grid = _grid()
    for imp in IMPRESSIONS:
        for q in QUALITY_RANKS:
            if (imp, q) not in grid:
                problems.append(f"{imp} × 綺麗さ{q}: 靴下が無い")
    return problems
