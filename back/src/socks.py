"""くつしたの台帳を読む。

台帳（resources/socks.json）は、リポジトリ直下の data/socks/socks.json から作る写し。
ここでは読むだけで、書き換えない。項目の意味は docs/socks.md にある。
"""

import json
from functools import cache
from pathlib import Path

SOCKS_PATH = Path(__file__).resolve().parent / "resources" / "socks.json"

# 結果を返すのに使う項目。どのくつしたにも、文字で入っていなければならない。
_REQUIRED_KEYS = ("id", "name", "image")


@cache
def all_socks() -> tuple[dict, ...]:
    """くつしたの一覧（台帳の items）を返す。

    ファイルを読むのは、最初に呼ばれたときの 1 度だけ。読めない、空、必要な項目が
    ない、のどれかなら例外を出す（そのときは覚えないので、次に呼ばれたときに読み直す）。
    """
    with SOCKS_PATH.open(encoding="utf-8") as file:
        items = json.load(file)["items"]
    if not isinstance(items, list) or not items:
        raise ValueError("くつしたの台帳に、くつしたが 1 つもありません")
    for item in items:
        if not isinstance(item, dict) or not all(
            isinstance(item.get(key), str) and item[key] for key in _REQUIRED_KEYS
        ):
            raise ValueError("くつしたの台帳に、id・name・image のない項目があります")
    return tuple(items)


def get_sock(sock_id: str) -> dict | None:
    """ID からくつしたを引く。台帳に無ければ None。"""
    return next((item for item in all_socks() if item["id"] == sock_id), None)
