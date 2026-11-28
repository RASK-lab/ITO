"""ファイル（画像など）の置き場。

手元では、フォルダに書く。本番では、オブジェクト置き場（Cloudflare R2）を使う。
コンテナからは R2 を直接使えないので、Worker に HTTP で頼む。キーの付け方は同じ。

本番かどうかは、環境変数 ITO_STORE_URL があるかで決まる。Worker に頼む口（仮。
インフラ担当と合わせる）:

    PUT    <ITO_STORE_URL>/objects/<キー>   本文をそのまま R2 に置く
    DELETE <ITO_STORE_URL>/objects/<キー>   R2 から消す（無くても成功にする）
    GET    <ITO_STORE_URL>/objects/<キー>   R2 から読んで、中身をそのまま返す（無ければ 404）

どれも、成功なら 2xx を返す。
"""

import re
import urllib.error
import urllib.request

from src.settings import DATA_DIR, STORE_TIMEOUT_SECONDS, STORE_URL

OBJECTS_DIR = DATA_DIR / "objects"

# キーは「drawings/0123abcd_1024.png」「drawings/0123abcd.json.gz」「cards/0123abcd.jpg」
# のような形だけを通す（置き場の外に書かせない）
_KEY_PATTERN = re.compile(r"[a-z0-9_-]+(/[a-z0-9_.-]+)+")


def _path(key: str):
    if not _KEY_PATTERN.fullmatch(key) or ".." in key:
        raise ValueError(f"使えないキーです: {key!r}")
    return OBJECTS_DIR / key


def _request(method: str, key: str, data: bytes | None = None) -> bytes:
    """Worker に頼み、応答の本文を返す。2xx 以外や、つながらないときは例外になる。"""
    _path(key)  # キーの形を確かめる
    request = urllib.request.Request(
        f"{STORE_URL}/objects/{key}", data=data, method=method
    )
    if data is not None:
        request.add_header("Content-Type", "application/octet-stream")
    with urllib.request.urlopen(request, timeout=STORE_TIMEOUT_SECONDS) as response:
        return response.read()


def put_object(key: str, data: bytes) -> None:
    if STORE_URL:
        _request("PUT", key, data)
        return
    path = _path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def delete_object(key: str) -> None:
    if STORE_URL:
        _request("DELETE", key)
        return
    _path(key).unlink(missing_ok=True)


def get_object(key: str) -> bytes | None:
    """中身を読む。無ければ None。"""
    if STORE_URL:
        try:
            return _request("GET", key)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise
    try:
        return _path(key).read_bytes()
    except FileNotFoundError:
        return None
