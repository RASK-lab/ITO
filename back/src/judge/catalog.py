"""分析から見た、くつした 50 種の台帳。

台帳そのものはチームで共通の `back/src/resources/socks.json`（`src/socks.py` が読む）を使う。
正は `data/socks/socks.json` で、写しの作り方は docs/socks.md にある。分析側では写しを持たない。

台帳の各くつしたは「印象（classification.feature）10 種 × 綺麗さ（classification.beauty）1〜5」の
50 マスに 1 足ずつ割り当てられている。分析は印象と品質ランク（＝綺麗さ）を決めて、
そのマスのくつしたの ID（例: `REGAL-01`）を返す。

レア（特別な書き方で出るくつした）は、台帳に `classification.special` を持つ項目として
追加されれば自動で使われる（まだ台帳には無い。形は back/src/judge/README.md）。
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from src import socks as socks_ledger

from .analysis.axes import IMPRESSIONS
from .settings import settings

QUALITY_RANKS = (1, 2, 3, 4, 5)

# 台帳の feature（日本語）→ 分析で使う印象の ID
FEATURE_TO_IMPRESSION = {
    "個性的": "koseiteki", "雑": "zatsu", "可愛い": "kawaii", "かわいい": "kawaii", "丁寧": "teinei",
    "かっこいい": "kakkoii", "繊細": "sensai", "達筆": "tappitsu", "不器用": "bukiyou",
    "暖かい": "atatakai", "温かい": "atatakai", "冷たい": "tsumetai",
}

# リポジトリの直下（back/src/judge/catalog.py から 3 つ上）。コンテナの中には無い。
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _items_tuple() -> tuple[dict, ...]:
    return socks_ledger.all_socks()


@lru_cache(maxsize=1)
def _items() -> dict[str, dict]:
    return {it["id"]: it for it in _items_tuple()}


def is_rare(it: dict) -> bool:
    """レアのくつしたは classification に feature/beauty の代わりに special（特別な書き方のキー）を持つ。"""
    return "special" in it.get("classification", {})


@lru_cache(maxsize=1)
def _grid() -> dict[tuple[str, int], str]:
    grid = {}
    for it in _items_tuple():
        if is_rare(it):
            continue
        c = it["classification"]
        grid[(FEATURE_TO_IMPRESSION[c["feature"]], int(c["beauty"]))] = it["id"]
    return grid


@lru_cache(maxsize=1)
def _rares() -> dict[str, str]:
    return {it["classification"]["special"]: it["id"] for it in _items_tuple() if is_rare(it)}


def clear_cache() -> None:
    """台帳を読み直す（テスト用）。"""
    for f in (_items, _grid, _rares):
        f.cache_clear()


def sock_id(quality_rank: int, impression: str) -> str:
    """印象と品質ランク（綺麗さ 1〜5）のマスにあるくつしたの ID。"""
    return _grid()[(impression, quality_rank)]


def rare_sock_id(special: str | None) -> str | None:
    """特別な書き方に対応するレアのくつしたの ID。台帳にまだ無ければ None。"""
    return _rares().get(special) if special else None


def all_ids() -> list[str]:
    return list(_items())


def item(sid: str) -> dict:
    """台帳の 1 項目（id, name, rarity, comment, image, classification など）。"""
    return _items()[sid]


def label(sid: str) -> str:
    it = item(sid)
    return f"{it['name']}（{it.get('rarity', '')}）"


# ---------- くつしたの画像（AI のコメントで、AI にくつしたの見た目を見せるため） ----------

def _local_image_dirs() -> list[tuple[Path, str]]:
    """くつしたの画像を探すフォルダと拡張子。上から順に探す。

    コンテナの中にはどれも無いので、本番は SOCK_IMAGE_BASE_URL（下の image_source）を使う。
    """
    dirs = []
    if os.environ.get("SOCK_IMAGE_DIR"):
        d = Path(os.environ["SOCK_IMAGE_DIR"])
        dirs += [(d, ".png"), (d, ".webp")]
    dirs += [
        (_REPO_ROOT / "data" / "socks" / "original", ".png"),   # 元の PNG（手元でリポジトリから動かすとき）
        (_REPO_ROOT / "front" / "public" / "socks", ".webp"),   # 表示用の WebP
    ]
    return dirs


def image_path(sid: str) -> Path | None:
    """手元にあるくつしたの画像ファイル。ファイル名は ID を小文字にしたもの（docs/socks.md）。"""
    name = sid.lower()
    for d, ext in _local_image_dirs():
        p = d / f"{name}{ext}"
        if p.is_file():
            return p
    return None


def image_source(sid: str) -> Path | str | None:
    """AI に見せるくつしたの画像。手元のファイル → 公開 URL → なし（文章の説明だけで書く）の順。

    本番（コンテナ）では、SOCK_IMAGE_BASE_URL に公開しているサイトの URL
    （例: https://hackathon-ito-app.example.workers.dev）を設定すると、
    台帳の image（例: /socks/worn-01.webp）をつなげた URL を Claude が読みに行く。
    """
    local = image_path(sid)
    if local is not None:
        return local
    if settings.sock_image_base_url:
        return settings.sock_image_base_url.rstrip("/") + "/" + item(sid)["image"].lstrip("/")
    return None


def description(sid: str) -> dict:
    """AI のコメントに渡す、くつしたの説明（台帳の name, rarity, comment, review.reason）。"""
    it = item(sid)
    c = it.get("classification", {})
    return {
        "名前": it["name"],
        "レアリティ": it.get("rarity"),
        "見た目": it.get("comment"),
        "この靴下が合う理由": c.get("review", {}).get("reason"),
    }


def check() -> list[str]:
    """台帳の不備（50 マスの欠け・知らない印象名・知らない special）を返す。空なら問題なし。"""
    from .analysis.rare import NOTES

    problems = []
    for it in _items_tuple():
        c = it.get("classification", {})
        if is_rare(it):
            if c["special"] not in NOTES:
                problems.append(f"{it['id']}: 知らない special {c['special']}")
        elif c.get("feature") not in FEATURE_TO_IMPRESSION:
            problems.append(f"{it['id']}: 知らない印象 {c.get('feature')}")
    grid = _grid()
    for imp in IMPRESSIONS:
        for q in QUALITY_RANKS:
            if (imp, q) not in grid:
                problems.append(f"{imp} × 綺麗さ{q}: くつしたが無い")
    return problems
