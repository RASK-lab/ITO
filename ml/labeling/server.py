"""ラベル付けのサーバー（手元版）。本番のアプリの /label/ と同じ画面・同じ API で動く。

ふだんは本番の /label/ で付ける（back/src/labeling.py）。手元版を使うのは、
公開できない画像（ETL、アプリで集めた手書き）に付けるときと、ネットがないとき。

使い方（リポジトリの直下で。Python の標準ライブラリだけで動く）:
  python ml/labeling/server.py            # http://localhost:8765
  python ml/labeling/server.py --port 9000

- 同じネットワーク（同じ Wi-Fi）の PC やスマホから、表示される http://<この PC の IP>:8765 で開ける。
  Windows で「アクセスを許可しますか」と出たら、プライベート ネットワークを許可する。
  合言葉はないので、会場や研究室の中だけで使うこと。
- 画像は ml/data/manifests/*.jsonl のすべて。ただし同じ画像（ml/data/duplicates.json）は除く
  （取り込みをやり直したら、次の画像を出すときに読み直す）。
- 1 枚に 1 人（config.json の target_ratings）。みんなで分けて付ける。画面に出ている画像はほかの人に出さない。
- ラベルは ml/data/labels.sqlite3 に記録する（1 人 1 画像につき 1 行。付け直すと上書き）。
- 画面は front/public/label/index.html、次の画像の選び方と集計は back/src/labeling_core.py（本番と共通）。
"""

from __future__ import annotations

import argparse
import json
import socket
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ML = Path(__file__).resolve().parents[1]
REPO = ML.parent
sys.path.insert(0, str(ML))
sys.path.insert(0, str(REPO / "back"))
from ito_ml.manifest import DATA_DIR, DUPLICATES_PATH, MANIFESTS_DIR, load_items  # noqa: E402
from src import labeling_core  # noqa: E402  （back/src/labeling_core.py。標準ライブラリだけ）

CONFIG_PATH = ML / "labeling" / "config.json"
PAGE = REPO / "front" / "public" / "label" / "index.html"
DB_PATH = DATA_DIR / "labels.sqlite3"
RESERVE_S = 120

SCHEMA = """
CREATE TABLE IF NOT EXISTS labels (
    item_id    TEXT NOT NULL,
    rater      TEXT NOT NULL,
    label      TEXT NOT NULL,
    label_set  TEXT NOT NULL,
    ms         INTEGER,
    created_at TEXT NOT NULL,
    PRIMARY KEY (item_id, rater, label_set)
);
"""

_lock = threading.Lock()
RESERVED: dict[str, dict[str, float]] = {}


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.executescript(SCHEMA)
    return connection


class Items:
    """台帳（manifests）を読み、変わっていたら読み直す。画像のパスは、この手元版の /img/ にする。"""

    def __init__(self) -> None:
        self._stamp: tuple = ()
        self.items: list[dict] = []
        self.by_id: dict[str, dict] = {}

    def get(self) -> list[dict]:
        paths = sorted(MANIFESTS_DIR.glob("*.jsonl")) + [p for p in [DUPLICATES_PATH] if p.exists()]
        stamp = tuple((p.name, p.stat().st_mtime) for p in paths)
        if stamp != self._stamp:
            self.items = [{"id": i["id"], "source": i["source"], "group": i["group"], "image": "/img/" + i["image"]}
                          for i in load_items()]
            self.by_id = {i["id"]: i for i in self.items}
            self._stamp = stamp
        return self.items


ITEMS = Items()


def labels_of(connection: sqlite3.Connection, label_set: str) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for item_id, rater, label in connection.execute(
            "SELECT item_id, rater, label FROM labels WHERE label_set = ?", (label_set,)):
        out.setdefault(item_id, {})[rater] = label
    return out


def public(item: dict | None) -> dict | None:
    return None if item is None else {"id": item["id"], "image": item["image"]}


def _active(now: float) -> dict[str, dict[str, float]]:
    """期限の切れた「付け中」を消して、残りを返す（呼ぶときは _lock を取っておく）"""
    for item_id in list(RESERVED):
        by = {r: t for r, t in RESERVED[item_id].items() if now - t < RESERVE_S}
        if by:
            RESERVED[item_id] = by
        else:
            del RESERVED[item_id]
    return RESERVED


def _progress(items: list[dict], labels: dict, config: dict, now: float) -> dict:
    active = {r for by in _active(now).values() for r in by}
    return labeling_core.progress(items, labels, config) | {"active": len(active)}


def api_next(q: dict) -> dict:
    config, rater = load_config(), q.get("rater", "").strip()
    if not rater:
        raise ValueError("rater が空です")
    items = ITEMS.get()
    with _lock, connect() as connection:
        labels = labels_of(connection, config["label_set"])
        now = time.time()
        for by in _active(now).values():
            by.pop(rater, None)  # その人が前に出していた画像は、ほかの人に回す
        reserved = {i: len(by) for i, by in RESERVED.items() if by}
        item, remaining = labeling_core.choose_next(
            items, labels, config, rater, set(filter(None, q.get("skip", "").split(","))), reserved)
        if item is not None:
            RESERVED.setdefault(item["id"], {})[rater] = now
        progress = _progress(items, labels, config, now)
    done = sum(1 for v in labels.values() if rater in v)
    return {"item": public(item), "done_by_me": done, "remaining_for_me": remaining, "progress": progress}


def api_progress() -> dict:
    config = load_config()
    items = ITEMS.get()
    with _lock, connect() as connection:
        return _progress(items, labels_of(connection, config["label_set"]), config, time.time())


def api_label(body: dict) -> dict:
    config = load_config()
    keys = {c["key"] for c in config["classes"] + config["special"]}
    rater, item_id, label = str(body.get("rater", "")).strip(), body.get("item_id"), body.get("label")
    if not rater or len(rater) > 20:
        raise ValueError("名前は 1〜20 文字で入れてください")
    if label not in keys:
        raise ValueError("label が config.json にありません")
    ITEMS.get()
    if item_id not in ITEMS.by_id:
        raise ValueError("item_id がありません")
    ms = body.get("ms")
    with _lock, connect() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO labels VALUES (?, ?, ?, ?, ?, ?)",
            (item_id, rater, label, config["label_set"], int(ms) if isinstance(ms, (int, float)) else None,
             datetime.now(timezone.utc).isoformat(timespec="seconds")))
        RESERVED.get(item_id, {}).pop(rater, None)
    return {"ok": True}


def api_mine(q: dict) -> dict:
    label_set = load_config()["label_set"]
    with connect() as connection:
        row = connection.execute(
            "SELECT label FROM labels WHERE rater = ? AND item_id = ? AND label_set = ?",
            (q.get("rater", "").strip(), q.get("item_id", ""), label_set)).fetchone()
    ITEMS.get()
    return {"label": row[0] if row else None, "item": public(ITEMS.by_id.get(q.get("item_id", "")))}


def api_stats() -> dict:
    config = load_config()
    with connect() as connection:
        return labeling_core.summarize(ITEMS.get(), labels_of(connection, config["label_set"]), config)


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=86400" if content_type == "image/png" else "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data: dict, status: int = 200) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if url.path in ("/", "/label/"):
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            elif url.path == "/api/label/config":
                c = load_config()
                self._json({k: c[k] for k in ("label_set", "question", "classes", "special")}
                           | {"passcode_required": False})
            elif url.path == "/api/label/next":
                self._json(api_next(q))
            elif url.path == "/api/label/progress":
                self._json(api_progress())
            elif url.path == "/api/label/mine":
                self._json(api_mine(q))
            elif url.path == "/api/label/stats":
                self._json(api_stats())
            elif url.path.startswith("/img/"):
                path = (DATA_DIR / unquote(url.path[len("/img/"):])).resolve()
                if (DATA_DIR / "images").resolve() not in path.parents or not path.is_file():
                    self._json({"detail": "not found"}, 404)
                    return
                self._send(200, path.read_bytes(), "image/png")
            else:
                self._json({"detail": "not found"}, 404)
        except ValueError as error:
            self._json({"detail": str(error)}, 422)
        except Exception as error:  # 画面に理由を返す（会場で原因を探しやすくするため）
            self._json({"detail": str(error)}, 500)

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/label/labels":
            self._json({"detail": "not found"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 10_000:
                raise ValueError("本文が大きすぎます")
            self._json(api_label(json.loads(self.rfile.read(length) or b"{}")))
        except ValueError as error:
            self._json({"detail": str(error)}, 422)

    def log_message(self, fmt: str, *args) -> None:
        pass  # 1 回ごとの記録は出さない（画面が流れて読めなくなるため）


def lan_addresses() -> list[str]:
    try:
        return sorted({a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
                       if not a[4][0].startswith("127.")})
    except OSError:
        return []


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()
    n = len(ITEMS.get())
    connect().close()
    print(f"画像 {n} 枚。ラベルの記録: {DB_PATH}", flush=True)
    print(f"  この PC から: http://localhost:{args.port}", flush=True)
    for ip in lan_addresses():
        print(f"  ほかの PC・スマホから: http://{ip}:{args.port}", flush=True)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
