"""ラベル付けの API（back/src/labeling.py）のテスト。back/ で: python -m pytest src/tests"""

import hashlib

import pytest
from fastapi.testclient import TestClient

from src import labeling, storage
from src.main import app

PASSCODE = "test-pass"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # 置き場を一時フォルダにし、記録を空から始める
    monkeypatch.setattr(storage, "OBJECTS_DIR", tmp_path / "objects")
    monkeypatch.setattr(labeling, "STORE", labeling._Store())
    monkeypatch.setitem(labeling.CONFIG, "passcode_sha256", hashlib.sha256(PASSCODE.encode()).hexdigest())
    monkeypatch.delenv("LABEL_PASSCODE", raising=False)
    return TestClient(app)


H = {"X-Label-Passcode": PASSCODE}


def test_passcode_is_required(client):
    assert client.get("/api/label/config").json()["passcode_required"] is True
    assert client.get("/api/label/next", params={"rater": "a"}).status_code == 401
    assert client.get("/api/label/next", params={"rater": "a"}, headers={"X-Label-Passcode": "x"}).status_code == 401
    assert client.get("/api/label/next", params={"rater": "a"}, headers=H).status_code == 200


def test_label_flow_and_reload(client, monkeypatch):
    first = client.get("/api/label/next", params={"rater": "さとう"}, headers=H).json()
    item_id = first["item"]["id"]
    assert first["item"]["image"].startswith("/label/img/")
    r = client.post("/api/label/labels", json={"rater": "さとう", "item_id": item_id, "label": "kawaii", "ms": 900},
                    headers=H)
    assert r.status_code == 200
    # 1 枚に 1 人なので、付いた画像はだれにも出さない。進み具合はみんなで共通
    for rater in ("さとう", "すずき"):
        data = client.get("/api/label/next", params={"rater": rater}, headers=H).json()
        assert data["item"]["id"] != item_id
        assert data["progress"]["done"] == 1 and data["progress"]["total"] == len(labeling.ITEMS)
    assert client.get("/api/label/mine", params={"rater": "さとう", "item_id": item_id},
                      headers=H).json()["label"] == "kawaii"
    # コンテナが眠って起きた（記録を置き場から読み直す）ときも残っている
    monkeypatch.setattr(labeling, "STORE", labeling._Store())
    export = client.get("/api/label/export", headers=H).json()
    assert [(x["item_id"], x["rater"], x["label"]) for x in export["labels"]] == [(item_id, "さとう", "kawaii")]
    assert client.get("/api/label/stats", headers=H).json()["per_rater"] == {"さとう": 1}


def test_rejects_bad_input(client):
    item_id = labeling.ITEMS[0]["id"]
    bad = [{"rater": "", "item_id": item_id, "label": "kawaii"},
           {"rater": "a", "item_id": "nope", "label": "kawaii"},
           {"rater": "a", "item_id": item_id, "label": "nope"}]
    for body in bad:
        assert client.post("/api/label/labels", json=body, headers=H).status_code == 422


def test_items_are_shared_without_overlap(client):
    # 同時に開いている人には、別々の画像を出す
    ids = [client.get("/api/label/next", params={"rater": r}, headers=H).json()["item"]["id"] for r in "abcd"]
    assert len(set(ids)) == 4
    assert client.get("/api/label/progress", headers=H).json() == {"done": 0, "total": len(labeling.ITEMS), "active": 4}
    # 次の画像をもらうと、前の画像はほかの人に回せるようになる（1 人が押さえるのは 1 枚だけ）
    client.get("/api/label/next", params={"rater": "a", "skip": ids[0]}, headers=H)
    reserved = [i for i, by in labeling.STORE.reserved.items() if "a" in by]
    assert len(reserved) == 1 and reserved[0] != ids[0]


def test_no_duplicate_items():
    # 同じ画像は除いてある（ml/tools/build_label_site.py）
    assert len({i["id"] for i in labeling.ITEMS}) == len(labeling.ITEMS)
    assert labeling.CONFIG["target_ratings"]["default"] == 1
