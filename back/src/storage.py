"""ファイル（画像など）の置き場。

本番ではオブジェクト置き場（Cloudflare R2）を使う予定。手元では、同じキーの
付け方のまま、フォルダに書く。差し替えるのはこのファイルだけで済むようにする。
"""

import re

from src.settings import DATA_DIR

OBJECTS_DIR = DATA_DIR / "objects"

# キーは「drawings/0123abcd_1024.png」「drawings/0123abcd.json.gz」のような形だけを通す
# （置き場の外に書かせない）
_KEY_PATTERN = re.compile(r"[a-z0-9_-]+(/[a-z0-9_.-]+)+")


def _path(key: str):
    if not _KEY_PATTERN.fullmatch(key) or ".." in key:
        raise ValueError(f"使えないキーです: {key!r}")
    return OBJECTS_DIR / key


def put_object(key: str, data: bytes) -> None:
    path = _path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def delete_object(key: str) -> None:
    _path(key).unlink(missing_ok=True)
