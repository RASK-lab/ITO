"""ラベル付けのサーバー（4 人で、同じ画像に印象のラベルを付ける）。

使い方（リポジトリの直下で。Python の標準ライブラリだけで動く）:
  python ml/labeling/server.py            # http://localhost:8765
  python ml/labeling/server.py --port 9000

- 同じネットワーク（同じ Wi-Fi）の PC やスマホから、表示される http://<この PC の IP>:8765 で開ける。
  Windows で「アクセスを許可しますか」と出たら、プライベート ネットワークを許可する。
  認証はないので、会場や研究室の中だけで使うこと（画像には再配布できないデータも含まれる）。
- ラベルは ml/data/labels.sqlite3 に記録する。誰が・どの画像に・どのラベルを付けたかを、
  1 人 1 画像につき 1 行（付け直すと上書き）。
- 画像の一覧は ml/data/manifests/*.jsonl（ml/tools/ の取り込みのスクリプトが作る）。
  サーバーを動かしたまま取り込みをやり直しても、次の画像を出すときに読み直す。
- ラベルの種類と、1 枚に何人で付けるかは labeling/config.json。
  ラベル付けを始めたあとに種類を変えるときは、label_set を上げる（混ざらないように記録に残る）。

API（画面 index.html が使う）:
| メソッド | パス | 内容 |
|---|---|---|
| GET | /api/config | ラベルの種類、ラベルを付ける人 |
| GET | /api/next?rater=名前 | その人がまだ付けていない次の画像 |
| POST | /api/label | {"rater", "item_id", "label", "ms"} を記録（同じ人・同じ画像なら上書き） |
| GET | /api/labels?rater=名前&item_id=… | その人がその画像に付けたラベル（「1 つ戻る」用） |
| GET | /api/stats | 進み具合と、人どうしの一致の度合い |
| GET | /img/<パス> | 画像 |
"""

from __future__ import annotations

import argparse
import hashlib
import json
import socket
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import combinations
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ito_ml.manifest import DATA_DIR, MANIFESTS_DIR, load_items  # noqa: E402

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.json"
DB_PATH = DATA_DIR / "labels.sqlite3"
# 画面に出したまま、まだラベルが来ていない画像を「付け中」とみなす秒数
# （ほかの人に同じ画像を出しすぎないため）
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


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.executescript(SCHEMA)
    return connection


class Items:
    """台帳（manifests）を読み、変わっていたら読み直す。"""

    def __init__(self) -> None:
        self._stamp: tuple = ()
        self.items: list[dict] = []
        self.by_id: dict[str, dict] = {}

    def get(self) -> list[dict]:
        stamp = tuple((p.name, p.stat().st_mtime) for p in sorted(MANIFESTS_DIR.glob("*.jsonl")))
        if stamp != self._stamp:
            self.items = load_items()
            self.by_id = {i["id"]: i for i in self.items}
            self._stamp = stamp
        return self.items


ITEMS = Items()
# item_id -> {rater: 出した時刻}
RESERVED: dict[str, dict[str, float]] = {}


def _order_key(rater: str, item_id: str) -> str:
    # 人ごとに違う、毎回同じ並び（同じフォントの太さ違いなどが続かないように混ぜる）
    return hashlib.sha1(f"{rater}\0{item_id}".encode()).hexdigest()


def next_item(rater: str, skip: set[str]) -> dict | None:
    config = load_config()
    targets, priority = config["target_ratings"], config["source_priority"]
    label_set = config["label_set"]
    items = ITEMS.get()
    with _lock, connect() as connection:
        counts = dict(connection.execute(
            "SELECT item_id, COUNT(*) FROM labels WHERE label_set = ? GROUP BY item_id", (label_set,)))
        mine = {r[0] for r in connection.execute(
            "SELECT item_id FROM labels WHERE rater = ? AND label_set = ?", (rater, label_set))}
        now = time.time()
        best, best_key = None, None
        for item in items:
            item_id = item["id"]
            if item_id in mine or item_id in skip:
                continue
            reserved = {r: t for r, t in RESERVED.get(item_id, {}).items() if now - t < RESERVE_S and r != rater}
            n = counts.get(item_id, 0) + len(reserved)
            if n >= targets.get(item["source"], targets["default"]):
                continue
            # 優先度の高いデータから。同じ優先度なら、ほかの人が付け始めた画像を先に（そろえて一致を測るため）
            key = (priority.get(item["source"], 9), -n, _order_key(rater, item_id))
            if best_key is None or key < best_key:
                best, best_key = item, key
        if best is not None:
            RESERVED.setdefault(best["id"], {})[rater] = now
        remaining = sum(
            1 for item in items
            if item["id"] not in mine
            and counts.get(item["id"], 0) < targets.get(item["source"], targets["default"]))
    return {"item": None if best is None else {"id": best["id"], "image": "/img/" + best["image"]},
            "done_by_me": len(mine), "remaining_for_me": remaining}


def record(body: dict) -> dict:
    config = load_config()
    keys = {c["key"] for c in config["classes"] + config["special"]}
    rater, item_id, label = str(body.get("rater", "")).strip(), body.get("item_id"), body.get("label")
    if not rater or len(rater) > 40:
        raise ValueError("rater が空か、長すぎます")
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


def my_label(rater: str, item_id: str) -> dict:
    label_set = load_config()["label_set"]
    with connect() as connection:
        row = connection.execute(
            "SELECT label FROM labels WHERE rater = ? AND item_id = ? AND label_set = ?",
            (rater, item_id, label_set)).fetchone()
    item = ITEMS.by_id.get(item_id)
    return {"label": row[0] if row else None,
            "item": None if item is None else {"id": item_id, "image": "/img/" + item["image"]}}


def fleiss_kappa(table: list[dict[str, int]], categories: list[str]) -> float | None:
    """1 枚ごとの {ラベル: 人数} から Fleiss の κ（人数が画像ごとに違ってもよい形）。"""
    rows = [r for r in table if sum(r.values()) >= 2]
    if not rows:
        return None
    total = sum(sum(r.values()) for r in rows)
    p_j = {c: sum(r.get(c, 0) for r in rows) / total for c in categories}
    p_e = sum(v * v for v in p_j.values())
    p_bar = sum((sum(v * v for v in r.values()) - sum(r.values())) /
                (sum(r.values()) * (sum(r.values()) - 1)) for r in rows) / len(rows)
    return None if p_e >= 1 else (p_bar - p_e) / (1 - p_e)


def stats() -> dict:
    config = load_config()
    label_set = config["label_set"]
    targets = config["target_ratings"]
    items = ITEMS.get()
    with connect() as connection:
        rows = connection.execute(
            "SELECT item_id, rater, label FROM labels WHERE label_set = ?", (label_set,)).fetchall()
    by_item: dict[str, dict[str, str]] = {}
    for item_id, rater, label in rows:
        by_item.setdefault(item_id, {})[rater] = label
    raters = sorted({r for _, r, _ in rows})
    per_rater = {r: sum(1 for _, x, _ in rows if x == r) for r in raters}
    per_label = {}
    for _, _, label in rows:
        per_label[label] = per_label.get(label, 0) + 1
    per_source: dict[str, dict] = {}
    for item in items:
        s = per_source.setdefault(item["source"], {"items": 0, "labeled": 0, "complete": 0})
        n = len(by_item.get(item["id"], {}))
        s["items"] += 1
        s["labeled"] += n > 0
        s["complete"] += n >= targets.get(item["source"], targets["default"])
    # 一致の度合い（「「と」に見えない」は除く。「どれとも言えない」は 1 つの選択肢として数える）
    categories = [c["key"] for c in config["classes"]] + ["unsure"]
    pairs = {}
    for a, b in combinations(raters, 2):
        both = [(v[a], v[b]) for v in by_item.values()
                if a in v and b in v and v[a] in categories and v[b] in categories]
        if both:
            pairs[f"{a} × {b}"] = {"n": len(both), "agree": round(sum(x == y for x, y in both) / len(both), 3)}
    table = []
    for v in by_item.values():
        counts: dict[str, int] = {}
        for label in v.values():
            if label in categories:
                counts[label] = counts.get(label, 0) + 1
        table.append(counts)
    kappa = fleiss_kappa(table, categories)
    return {"label_set": label_set, "ratings": len(rows), "per_rater": per_rater, "per_label": per_label,
            "per_source": per_source, "pairwise_agreement": pairs,
            "fleiss_kappa": None if kappa is None else round(kappa, 3)}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store" if content_type.startswith(("application/json", "text/html"))
                         else "max-age=86400")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data: dict, status: int = 200) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if url.path == "/":
                self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
            elif url.path == "/api/config":
                c = load_config()
                self._json({k: c[k] for k in ("label_set", "question", "classes", "special", "raters")})
            elif url.path == "/api/next":
                skip = set(filter(None, q.get("skip", "").split(",")))
                self._json(next_item(q.get("rater", ""), skip))
            elif url.path == "/api/labels":
                self._json(my_label(q.get("rater", ""), q.get("item_id", "")))
            elif url.path == "/api/stats":
                self._json(stats())
            elif url.path.startswith("/img/"):
                path = (DATA_DIR / unquote(url.path[len("/img/"):])).resolve()
                images = (DATA_DIR / "images").resolve()
                if images not in path.parents or not path.is_file():
                    self._json({"error": "not found"}, 404)
                    return
                self._send(200, path.read_bytes(), "image/png")
            else:
                self._json({"error": "not found"}, 404)
        except Exception as error:  # 画面に理由を返す（会場で原因を探しやすくするため）
            self._json({"error": str(error)}, 500)

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/label":
            self._json({"error": "not found"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 10_000:
                raise ValueError("本文が大きすぎます")
            self._json(record(json.loads(self.rfile.read(length) or b"{}")))
        except ValueError as error:
            self._json({"error": str(error)}, 400)

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
