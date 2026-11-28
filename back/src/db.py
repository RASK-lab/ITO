"""台帳（データベース）。

手元では SQLite のファイルを使う。本番では Cloudflare D1 を使う。D1 の中身も SQLite
なので、表の形と SQL は同じ。コンテナからは D1 を直接使えないので、Worker に HTTP で
頼む。表の説明は docs/data.md にある。

本番かどうかは、環境変数 ITO_STORE_URL があるかで決まる。Worker に頼む口（仮。
インフラ担当と合わせる）:

    POST <ITO_STORE_URL>/db/query
    本文（JSON）: {"sql": "INSERT INTO … VALUES (?, ?, …)", "params": [値, 値, …]}

Worker は、sql を params の順に当てはめて D1 で実行し、成功なら 2xx を返す。
D1 の表は、下の SCHEMA で先に作っておく（本番では、このファイルは表を作らない）。
"""

import json
import sqlite3
import threading
import urllib.request
from contextlib import closing

from src.settings import DATA_DIR, STORE_TIMEOUT_SECONDS, STORE_URL

DB_PATH = DATA_DIR / "ito.sqlite3"

# ほかの書き込みが終わるのを待つ秒数（同時に確定が来たとき、順番に書くため）
BUSY_TIMEOUT_SECONDS = 10
# 同じプロセスの中では、書き込みを 1 つずつにする。SQLite に任せると、書き込みが
# 重なったときに、一部だけが長く待たされることがあるため。
_WRITE_LOCK = threading.Lock()

# sock_id と message には、いまは仮の結果（back/src/drawings.py の make_result）が入る。
# font、reading、is_public は、分析と一覧の機能ができてから使う。
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

-- 学習データ集め（back/src/collect.py、docs/collect.md）。アプリの「と」（drawings）とは分ける。
-- 線のデータ（strokes_json）は、ここに直接入れる。集めるときは点を 2 万個までにして
-- いるので、1 行が D1 の上限（2MB）を超えない。表だけで書き出せるようにするため。
CREATE TABLE IF NOT EXISTS collect_samples (
    id                 TEXT PRIMARY KEY,
    created_at         TEXT NOT NULL,
    protocol           TEXT NOT NULL,
    writer_id          TEXT NOT NULL,
    session_id         TEXT NOT NULL,
    trial              INTEGER NOT NULL,
    condition          TEXT NOT NULL,
    instruction        TEXT NOT NULL,
    dominant_hand      TEXT NOT NULL,
    calligraphy        TEXT NOT NULL,
    pointer_type       TEXT NOT NULL,
    display_px         INTEGER NOT NULL,
    device_pixel_ratio REAL NOT NULL,
    redo_count         INTEGER NOT NULL,
    target             TEXT NOT NULL,
    duration_ms        INTEGER NOT NULL,
    stroke_count       INTEGER NOT NULL,
    point_count        INTEGER NOT NULL,
    image_1024_key     TEXT NOT NULL,
    image_256_key      TEXT NOT NULL,
    strokes_json       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS collect_samples_condition ON collect_samples (condition, pointer_type);
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
    "sock_id",
    "message",
    "user_name",
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


def _query_store(sql: str, params: list) -> list[dict]:
    """Worker に頼んで、D1 で SQL を実行する。2xx 以外や、つながらないときは例外になる。

    返り値は、SELECT のときの行（列の名前をキーにした dict の並び）。Worker は
    {"results": [...]} を返す（infra/cloudflare/worker.ts）。
    """
    request = urllib.request.Request(
        f"{STORE_URL}/db/query",
        data=json.dumps({"sql": sql, "params": params}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=STORE_TIMEOUT_SECONDS) as response:
        body = response.read()
    if not body:
        return []
    return json.loads(body).get("results") or []


def insert_drawing(record: dict) -> None:
    """書かれた「と」を 1 行足す。font、reading、is_public は、まだ入れない。"""
    columns = ", ".join(_DRAWING_COLUMNS)
    if STORE_URL:
        placeholders = ", ".join("?" for _ in _DRAWING_COLUMNS)
        _query_store(
            f"INSERT INTO drawings ({columns}) VALUES ({placeholders})",
            [record[column] for column in _DRAWING_COLUMNS],
        )
        return
    placeholders = ", ".join(f":{column}" for column in _DRAWING_COLUMNS)
    with _WRITE_LOCK, closing(_connect()) as connection, connection:
        connection.execute(
            f"INSERT INTO drawings ({columns}) VALUES ({placeholders})", record
        )


# ---------- 学習データ集め（back/src/collect.py） ----------

COLLECT_COLUMNS = (
    "id",
    "created_at",
    "protocol",
    "writer_id",
    "session_id",
    "trial",
    "condition",
    "instruction",
    "dominant_hand",
    "calligraphy",
    "pointer_type",
    "display_px",
    "device_pixel_ratio",
    "redo_count",
    "target",
    "duration_ms",
    "stroke_count",
    "point_count",
    "image_1024_key",
    "image_256_key",
    "strokes_json",
)


def insert_collect_sample(record: dict) -> None:
    """学習データの「と」を 1 行足す。record のキーは COLLECT_COLUMNS と同じ。"""
    columns = ", ".join(COLLECT_COLUMNS)
    if STORE_URL:
        placeholders = ", ".join("?" for _ in COLLECT_COLUMNS)
        _query_store(
            f"INSERT INTO collect_samples ({columns}) VALUES ({placeholders})",
            [record[column] for column in COLLECT_COLUMNS],
        )
        return
    placeholders = ", ".join(f":{column}" for column in COLLECT_COLUMNS)
    with _WRITE_LOCK, closing(_connect()) as connection, connection:
        connection.execute(
            f"INSERT INTO collect_samples ({columns}) VALUES ({placeholders})", record
        )


def count_collect_conditions(protocol: str, pointer_type: str) -> dict[str, int]:
    """集め方（protocol）と入力の種類ごとに、指示（condition）ごとの件数を数える。

    件数の少ない指示から配るのに使う（back/src/collect.py の make_plan）。
    """
    sql = (
        "SELECT condition, COUNT(*) AS n FROM collect_samples"
        " WHERE protocol = ? AND pointer_type = ? GROUP BY condition"
    )
    if STORE_URL:
        rows = _query_store(sql, [protocol, pointer_type])
        return {row["condition"]: int(row["n"]) for row in rows}
    with closing(_connect()) as connection:
        rows = connection.execute(sql, (protocol, pointer_type)).fetchall()
    return {condition: int(n) for condition, n in rows}
