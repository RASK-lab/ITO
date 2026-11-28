"""学習データの置き場所と、1 枚ごとの台帳（manifest）。

ml/data/                       （Git に入れない。個人の書いた字や、再配布できないデータを含む）
  sources/<データ名>/          ダウンロードした元のデータ
  images/<データ名>/<id>.png   preprocess.normalize で整えた画像（256 × 256、白地に黒）
  manifests/<データ名>.jsonl   1 行に 1 枚。下の Item の形
  duplicates.json              同じ画像の一覧（ito_ml/dedupe.py。load_items はここにある画像を除く）
  labels.sqlite3               ラベル付けの記録（labeling/server.py）
  export/<日時>/               学習に使う形に書き出したもの（tools/export_dataset.py）

台帳は、データ名ごとのファイルを取り込みのスクリプトが丸ごと書き直す（何度実行しても同じ結果）。
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .preprocess import PREPROCESS_VERSION

ML_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ML_DIR / "data"
SOURCES_DIR = DATA_DIR / "sources"
IMAGES_DIR = DATA_DIR / "images"
MANIFESTS_DIR = DATA_DIR / "manifests"
DUPLICATES_PATH = DATA_DIR / "duplicates.json"

_ID_SAFE = re.compile(r"[^a-z0-9_.-]+")


def make_id(*parts: object) -> str:
    """ファイル名にも使える ID（英小文字・数字・._-）"""
    return _ID_SAFE.sub("-", "-".join(str(p) for p in parts).lower()).strip("-")


@dataclass
class Item:
    """学習データの 1 枚"""

    id: str
    # データ名（google_fonts、local_fonts、etl、kuzushiji49、collect）
    source: str
    # 画像のパス（DATA_DIR からの相対パス）
    image: str
    # 学習・評価に分けるときのまとまり。同じまとまりは同じ側に入れる
    # （同じフォントの太さ違い、同じ人の字が、学習と評価の両方に入らないように）
    group: str
    # font（フォント）、handwriting（現代の手書き）、classical（古典籍の筆の字）
    kind: str
    license: str
    meta: dict = field(default_factory=dict)
    preprocess: str = PREPROCESS_VERSION


def save_image(source: str, item_id: str, image) -> str:
    """整えた画像を保存し、DATA_DIR からの相対パスを返す。"""
    path = IMAGES_DIR / source / f"{item_id}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True)
    return path.relative_to(DATA_DIR).as_posix()


def write_manifest(source: str, items: list[Item]) -> Path:
    MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)
    path = MANIFESTS_DIR / f"{source}.jsonl"
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for item in items:
            f.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")
    return path


def load_items(include_duplicates: bool = False) -> list[dict]:
    """すべてのデータの台帳を読む。同じ画像（duplicates.json にあるもの）は、ふつうは除く。"""
    items = []
    for path in sorted(MANIFESTS_DIR.glob("*.jsonl")):
        with path.open(encoding="utf-8") as f:
            items += [json.loads(line) for line in f if line.strip()]
    if not include_duplicates and DUPLICATES_PATH.exists():
        removed = json.loads(DUPLICATES_PATH.read_text(encoding="utf-8"))
        items = [i for i in items if i["id"] not in removed]
    return items
