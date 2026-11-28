"""学習データ集め（back/src/collect.py）のテスト。back/ で python -m pytest src/tests"""

import base64
import io
import sqlite3

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from src import collect, db, storage
from src.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # 手元の保存先を一時フォルダにする（back/data を汚さない）
    monkeypatch.setattr(storage, "OBJECTS_DIR", tmp_path / "objects")
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "ito.sqlite3")
    return TestClient(app)


def _body(**overrides):
    buf = io.BytesIO()
    Image.new("RGBA", (1024, 1024), (255, 255, 255, 0)).save(buf, "PNG")
    body = dict(
        protocol=collect.PROTOCOL, writer_id="0f3c2a1e-1111-4222-8333-444455556666",
        session_id="abcdef12-1111-4222-8333-444455556666", trial=2, condition="kawaii",
        dominant_hand="right", calligraphy="school", consent_train=True,
        display_px=360, device_pixel_ratio=3.0, redo_count=1, target="と",
        canvas={"width": 1024, "height": 1024},
        strokes=[{"pointerType": "touch", "points": [[100.0, 100.0, 0, 0.5], [200.5, 150.0, 30, 0.5]]}],
        image="data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(),
        width=1024, height=1024,
    )
    return {**body, **overrides}


def test_plan_is_balanced_impressions(client):
    trials = client.get("/api/collect/plan?pointer=touch").json()["trials"]
    conditions = [t["condition"] for t in trials]
    assert len(set(conditions)) == len(conditions) == collect.IMPRESSION_TRIALS
    assert set(conditions) <= set(collect.IMPRESSIONS)
    # 1 件記録すると、その指示は（件数が多いので）次の回に配られない
    assert client.post("/api/collect/samples", json=_body(condition="kawaii")).status_code == 201
    for _ in range(5):
        trials = client.get("/api/collect/plan?pointer=touch").json()["trials"]
        assert "kawaii" not in [t["condition"] for t in trials]


def test_non_dominant_hand_is_last():
    for _ in range(50):
        plan = collect.make_plan("mouse")
        if "bukiyou" in plan:
            assert plan[-1] == "bukiyou"


def test_sample_is_recorded_with_server_instruction(client, tmp_path):
    r = client.post("/api/collect/samples", json=_body())
    assert r.status_code == 201
    row = sqlite3.connect(tmp_path / "ito.sqlite3").execute(
        "select condition, instruction, pointer_type, duration_ms from collect_samples").fetchone()
    assert row == ("kawaii", collect.INSTRUCTIONS["kawaii"], "touch", 30)
    assert (tmp_path / "objects" / "collect" / f"{r.json()['id']}_256.png").exists()


@pytest.mark.parametrize("override,status", [
    (dict(consent_train=False), 422),
    (dict(condition="cute"), 422),
    (dict(protocol="old"), 409),
    (dict(writer_id="../x"), 422),
])
def test_rejects(client, override, status):
    assert client.post("/api/collect/samples", json=_body(**override)).status_code == status
