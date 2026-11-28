"""靴下60種の ID。画像ファイル名も ID と同じ（例: Q3-kawaii.png）。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .analysis.axes import IMPRESSION_LABELS, IMPRESSIONS

CATALOG_DIR = Path(__file__).resolve().parent / "catalog"
IMAGES_DIR = CATALOG_DIR / "images"
DESCRIPTIONS_FILE = CATALOG_DIR / "sock_descriptions.json"

QUALITY_RANKS = (1, 2, 3, 4, 5)

RARES: dict[str, str] = {
    "R-katahou": "片方だけの靴下",
    "R-ippon": "1本の糸",
    "R-uragaeshi": "裏返しの靴下",
    "R-kedama": "毛玉だらけの靴下",
    "R-kinshi": "金糸の靴下",
    "R-idaten": "韋駄天ソックス",
    "R-amikake": "編みかけの靴下",
    "R-baby": "ベビーソックス",
    "R-loose": "ルーズソックス",
    "R-niji": "虹色の靴下",
}


def sock_id(quality_rank: int, impression: str) -> str:
    return f"Q{quality_rank}-{impression}"


def all_ids() -> list[str]:
    return [sock_id(q, i) for q in QUALITY_RANKS for i in IMPRESSIONS] + list(RARES)


def label(sid: str) -> str:
    if sid in RARES:
        return RARES[sid]
    q, imp = sid[1], sid.split("-", 1)[1]
    return f"品質{q}・{IMPRESSION_LABELS[imp]}"


def image_path(sid: str) -> Path | None:
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        p = IMAGES_DIR / f"{sid}{ext}"
        if p.is_file():
            return p
    return None


@lru_cache(maxsize=1)
def _descriptions() -> dict:
    if DESCRIPTIONS_FILE.is_file():
        return json.loads(DESCRIPTIONS_FILE.read_text(encoding="utf-8"))
    return {}


def description(sid: str) -> dict | None:
    return _descriptions().get(sid)
