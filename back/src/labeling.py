"""ラベル付けの API（/api/label/*）。画面は front/public/label/index.html（アドレスは /label/）。

学習データ（ml/README.md）の画像に、集まった人が印象のラベルを付ける。

- 画像の一覧: back/src/resources/label_items.json（ml/tools/build_label_site.py が作る）。
  画像そのものは front/public/label/img/ にあり、フロントと一緒に静的なファイルとして配る。
- ラベルの種類など: back/src/resources/label_config.json（ml/labeling/config.json の写し）。
- ラベルの保存先: オブジェクト置き場（本番は R2、手元はフォルダ。storage.py）。
  データベース（D1）は使わない（Worker と D1 の設定を変えずに動かすため）。
    labels/<label_set>/raters.json        付けた人の一覧 {"raters": {キー: 名前}}
    labels/<label_set>/r/<キー>.json       1 人分のラベル {"rater": 名前, "labels": {画像の id: {...}}}
  1 人分のファイルは、その人がラベルを付けるたびに丸ごと書き直す（1 人は同時に 1 枚しか付けない）。
  コンテナが眠って起きたら、最初の呼び出しで読み直す。コンテナは 1 つだけ（wrangler.jsonc の
  max_instances）なので、記録はこのプロセスの中の 1 か所で管理できる。
- 合言葉: label_config.json の passcode_sha256（合言葉の SHA-256）。環境変数 LABEL_PASSCODE が
  あれば、そちらを使う。どちらも無いとき（手元）は、合言葉なしで使える。
  画面は、合言葉をヘッダー X-Label-Passcode で送る。

| メソッド | パス | 内容 |
|---|---|---|
| GET | /api/label/config | ラベルの種類（合言葉は不要） |
| GET | /api/label/next?rater=名前&skip=id | その人がまだ付けていない次の画像 |
| POST | /api/label/labels | {"rater", "item_id", "label", "ms"} を記録（同じ人・同じ画像は上書き） |
| GET | /api/label/mine?rater=名前&item_id=id | その人がその画像に付けたラベル（「1 つ戻る」用） |
| GET | /api/label/stats | 進み具合と、人どうしの一致の度合い |
| GET | /api/label/export | すべてのラベル（ml/tools/export_dataset.py --labels で読む） |
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from src import labeling_core, storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/label", tags=["label（学習データのラベル付け）"])

RESOURCES = Path(__file__).resolve().parent / "resources"
# 画面に出したまま、まだラベルが来ていない画像を「付け中」とみなす秒数
RESERVE_S = 120
MAX_RATER_LENGTH = 20


def _load(name: str):
    return json.loads((RESOURCES / name).read_text(encoding="utf-8"))


CONFIG: dict = _load("label_config.json")
ITEMS: list[dict] = _load("label_items.json")
ITEM_IDS = {item["id"] for item in ITEMS}
LABEL_KEYS = {c["key"] for c in CONFIG["classes"] + CONFIG["special"]}


def _key_prefix() -> str:
    return f"labels/{CONFIG['label_set']}"


def _rater_key(rater: str) -> str:
    # 名前は日本語のこともあるので、置き場のキーにはハッシュを使う（storage のキーは英数字だけ）
    return hashlib.sha256(rater.encode("utf-8")).hexdigest()[:24]


class _Store:
    """ラベルの記録。最初に使うときに置き場から読み、書くたびに置き場へ書く。"""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.loaded = False
        self.raters: dict[str, str] = {}  # キー -> 名前
        self.by_rater: dict[str, dict[str, dict]] = {}  # 名前 -> {画像の id: {label, ms, at}}
        self.reserved: dict[str, dict[str, float]] = {}  # 画像の id -> {名前: 出した時刻}

    def _get_json(self, key: str) -> dict | None:
        data = storage.get_object(key)
        return None if data is None else json.loads(data)

    def ensure_loaded(self) -> None:
        if self.loaded:
            return
        index = self._get_json(f"{_key_prefix()}/raters.json") or {"raters": {}}
        by_rater = {}
        for key, name in index["raters"].items():
            data = self._get_json(f"{_key_prefix()}/r/{key}.json") or {"labels": {}}
            by_rater[name] = data["labels"]
        self.raters, self.by_rater, self.loaded = index["raters"], by_rater, True

    def labels(self) -> dict[str, dict[str, str]]:
        """{画像の id: {名前: ラベル}}"""
        out: dict[str, dict[str, str]] = {}
        for rater, entries in self.by_rater.items():
            for item_id, entry in entries.items():
                out.setdefault(item_id, {})[rater] = entry["label"]
        return out

    def save(self, rater: str, item_id: str, label: str, ms: int | None) -> None:
        key = _rater_key(rater)
        entries = dict(self.by_rater.get(rater, {}))
        entries[item_id] = {"label": label, "ms": ms,
                            "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        body = json.dumps({"rater": rater, "labels": entries}, ensure_ascii=False).encode("utf-8")
        storage.put_object(f"{_key_prefix()}/r/{key}.json", body)
        if key not in self.raters:
            raters = {**self.raters, key: rater}
            storage.put_object(f"{_key_prefix()}/raters.json",
                               json.dumps({"raters": raters}, ensure_ascii=False).encode("utf-8"))
            self.raters = raters
        # 置き場に書けてから、手元の記録を変える（書けなかったら何も変えない）
        self.by_rater[rater] = entries


STORE = _Store()


def _check_passcode(passcode: str | None) -> None:
    plain = os.environ.get("LABEL_PASSCODE")
    expected = (hashlib.sha256(plain.encode()).hexdigest() if plain else CONFIG.get("passcode_sha256"))
    if not expected:
        return
    given = hashlib.sha256((passcode or "").encode("utf-8")).hexdigest()
    if not hmac.compare_digest(given, expected):
        raise HTTPException(401, "合言葉が違います")


def _check_rater(rater: str) -> str:
    rater = rater.strip()
    if not rater or len(rater) > MAX_RATER_LENGTH or any(ord(ch) < 32 for ch in rater):
        raise HTTPException(422, f"名前は 1〜{MAX_RATER_LENGTH} 文字で入れてください")
    return rater


def _loaded_store() -> _Store:
    try:
        STORE.ensure_loaded()
    except Exception:
        logger.exception("ラベルの記録を読めませんでした")
        raise HTTPException(503, "記録を読めませんでした。少し待ってから開き直してください") from None
    return STORE


def _public_item(item: dict | None) -> dict | None:
    return None if item is None else {"id": item["id"], "image": item["image"]}


@router.get("/config")
def get_config() -> dict:
    return {k: CONFIG[k] for k in ("label_set", "question", "classes", "special")} | {
        "passcode_required": bool(os.environ.get("LABEL_PASSCODE") or CONFIG.get("passcode_sha256"))}


@router.get("/next")
def get_next(rater: str, skip: str = "", x_label_passcode: str | None = Header(None)) -> dict:
    _check_passcode(x_label_passcode)
    rater = _check_rater(rater)
    store = _loaded_store()
    with store.lock:
        now = time.time()
        reserved = {}
        for item_id, by in store.reserved.items():
            n = sum(1 for r, t in by.items() if r != rater and now - t < RESERVE_S)
            if n:
                reserved[item_id] = n
        item, remaining = labeling_core.choose_next(
            ITEMS, store.labels(), CONFIG, rater, set(filter(None, skip.split(","))), reserved)
        if item is not None:
            store.reserved.setdefault(item["id"], {})[rater] = now
        done = len(store.by_rater.get(rater, {}))
    return {"item": _public_item(item), "done_by_me": done, "remaining_for_me": remaining}


class LabelIn(BaseModel):
    rater: str = Field(max_length=100)
    item_id: str = Field(max_length=200)
    label: str = Field(max_length=50)
    ms: int | None = Field(default=None, ge=0, le=3_600_000)


@router.post("/labels")
def post_label(body: LabelIn, x_label_passcode: str | None = Header(None)) -> dict:
    _check_passcode(x_label_passcode)
    rater = _check_rater(body.rater)
    if body.label not in LABEL_KEYS:
        raise HTTPException(422, "label が決まった種類ではありません")
    if body.item_id not in ITEM_IDS:
        raise HTTPException(422, "item_id がありません")
    store = _loaded_store()
    with store.lock:
        try:
            store.save(rater, body.item_id, body.label, body.ms)
        except Exception:
            logger.exception("ラベルを保存できませんでした")
            raise HTTPException(500, "記録できませんでした") from None
        store.reserved.get(body.item_id, {}).pop(rater, None)
    return {"ok": True}


@router.get("/mine")
def get_mine(rater: str, item_id: str, x_label_passcode: str | None = Header(None)) -> dict:
    _check_passcode(x_label_passcode)
    rater = _check_rater(rater)
    store = _loaded_store()
    entry = store.by_rater.get(rater, {}).get(item_id)
    item = next((i for i in ITEMS if i["id"] == item_id), None)
    return {"label": entry["label"] if entry else None, "item": _public_item(item)}


@router.get("/stats")
def get_stats(x_label_passcode: str | None = Header(None)) -> dict:
    _check_passcode(x_label_passcode)
    store = _loaded_store()
    with store.lock:
        return labeling_core.summarize(ITEMS, store.labels(), CONFIG)


@router.get("/export")
def get_export(x_label_passcode: str | None = Header(None)) -> dict:
    _check_passcode(x_label_passcode)
    store = _loaded_store()
    with store.lock:
        rows = [{"item_id": item_id, "rater": rater, **entry}
                for rater, entries in store.by_rater.items() for item_id, entry in entries.items()]
    return {"label_set": CONFIG["label_set"], "labels": rows}
