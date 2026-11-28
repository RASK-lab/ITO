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
    # 同じ人には同じ画像を出さない。ほかの人には、付け始めた画像を先に出す
    assert client.get("/api/label/next", params={"rater": "さとう"}, headers=H).json()["item"]["id"] != item_id
    assert client.get("/api/label/next", params={"rater": "すずき"}, headers=H).json()["item"]["id"] == item_id
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
