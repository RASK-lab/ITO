"""ラベル付けの API（/api/label/*）。画面は front/public/label/index.html（アドレスは /label/）。

学習データ（ml/README.md）の画像に、集まった人が印象のラベルを付ける。
1 枚に 1 人（label_config.json の target_ratings）。みんなで分けて、全部の画像に 1 回ずつ付ける。
いまだれかの画面に出ている画像（RESERVE_S 秒まで）は、ほかの人に出さない。

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
| GET | /api/label/next?rater=名前&skip=id | 次に付ける画像（まだだれも付けておらず、ほかの人の画面にも出ていないもの）と、進み具合 |
| GET | /api/label/progress | みんなで共通の進み具合 {"done", "total", "active"（いま付けている人数）} |
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
# 先読みのとき、押さえたままにできる画像の数の上限（表示中 1 + 送信待ちのぶん）
MAX_KEEP = 20


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


def _active_reservations(store: _Store, now: float) -> dict[str, dict[str, float]]:
    """期限の切れた「付け中」を消して、残りを返す（呼ぶときは store.lock を取っておく）"""
    for item_id in list(store.reserved):
        by = {r: t for r, t in store.reserved[item_id].items() if now - t < RESERVE_S}
        if by:
            store.reserved[item_id] = by
        else:
            del store.reserved[item_id]
    return store.reserved


def _progress(store: _Store, now: float) -> dict:
    """みんなで共通の進み具合と、いま付けている人の数（呼ぶときは store.lock を取っておく）"""
    active = {r for by in _active_reservations(store, now).values() for r in by}
    return labeling_core.progress(ITEMS, store.labels(), CONFIG) | {"active": len(active)}


@router.get("/next")
def get_next(rater: str, skip: str = "", keep: str = "",
             x_label_passcode: str | None = Header(None)) -> dict:
    """keep: 画面に出したまま、または送信待ちの画像の id（カンマ区切り）。
    これらの予約は外さずに延ばす（先読みしても、ほかの人に同じ画像を出さないため）。"""
    _check_passcode(x_label_passcode)
    rater = _check_rater(rater)
    keep_ids = set(list(filter(None, keep.split(",")))[:MAX_KEEP])
    store = _loaded_store()
    with store.lock:
        now = time.time()
        reservations = _active_reservations(store, now)
        # その人が前に出していた画像は、ほかの人に回せるようにする。
        # ただし keep にあるもの（出したまま・送信待ち）は押さえたまま、期限を延ばす。
        for item_id, by in reservations.items():
            if item_id in keep_ids and rater in by:
                by[rater] = now
            else:
                by.pop(rater, None)
        reserved = {item_id: len(by) for item_id, by in reservations.items() if by}
        item, remaining = labeling_core.choose_next(
            ITEMS, store.labels(), CONFIG, rater, set(filter(None, skip.split(","))), reserved)
        if item is not None:
            reservations.setdefault(item["id"], {})[rater] = now
        done = len(store.by_rater.get(rater, {}))
        progress = _progress(store, now)
    return {"item": _public_item(item), "done_by_me": done, "remaining_for_me": remaining, "progress": progress}


@router.get("/progress")
def get_progress(x_label_passcode: str | None = Header(None)) -> dict:
    _check_passcode(x_label_passcode)
    store = _loaded_store()
    with store.lock:
        return _progress(store, time.time())


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
