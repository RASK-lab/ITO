"""台帳（データベース）。

手元では SQLite のファイルを使う。本番は Cloudflare D1 を予定していて、D1 の中身も
SQLite なので、表の形と SQL はそのまま使える。差し替えるのはこのファイルだけで
済むようにする。表の説明は docs/data.md にある。
"""

import sqlite3
import threading
from contextlib import closing

from src.settings import DATA_DIR

DB_PATH = DATA_DIR / "ito.sqlite3"

# ほかの書き込みが終わるのを待つ秒数（同時に確定が来たとき、順番に書くため）
BUSY_TIMEOUT_SECONDS = 10
# 同じプロセスの中では、書き込みを 1 つずつにする。SQLite に任せると、書き込みが
# 重なったときに、一部だけが長く待たされることがあるため。
_WRITE_LOCK = threading.Lock()

# sock_id から下の 6 列は、分析と一覧の機能ができてから使う
SCHEMA = """
CREATE TABLE IF NOT EXISTS drawings (
    id             TEXT PRIMARY KEY,
    created_at     TEXT NOT NULL,
    image_1024_key TEXT NOT NULL,
    image_256_key  TEXT NOT NULL,
    strokes_key    TEXT NOT NULL,
    target         TEXT NOT NULL,
    duration_ms    INTEGER NOT NULL,
    stroke_count   INTEGER NOT NULL,
    point_count    INTEGER NOT NULL,
    sock_id        TEXT,
    font           TEXT,
    reading        TEXT,
    message        TEXT,
    user_name      TEXT,
    is_public      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS drawings_created_at ON drawings (created_at);
"""

_DRAWING_COLUMNS = (
    "id",
    "created_at",
    "image_1024_key",
    "image_256_key",
    "strokes_key",
    "target",
    "duration_ms",
    "stroke_count",
    "point_count",
)


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=BUSY_TIMEOUT_SECONDS)
    try:
        # 表がなければ作る（すでにあれば何もしない）
        connection.executescript(SCHEMA)
    except BaseException:
        connection.close()
        raise
    return connection


def insert_drawing(record: dict) -> None:
    """書かれた「と」を 1 行足す。分析結果の列は、分析ができてから埋める。"""
    columns = ", ".join(_DRAWING_COLUMNS)
    placeholders = ", ".join(f":{column}" for column in _DRAWING_COLUMNS)
    with _WRITE_LOCK, closing(_connect()) as connection, connection:
        connection.execute(
            f"INSERT INTO drawings ({columns}) VALUES ({placeholders})", record
        )
