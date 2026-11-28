"""POST /api/drawings（画面の「確定」）から分析が呼ばれ、台帳のくつしたとメッセージが返ること。"""

import base64
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from src import db, storage
from src.judge import catalog
from src.judge.llm import client as llm_client
from src.judge.llm.schemas import SockComment, ToJudgement
from src.main import app

from .helpers import from_reference


@pytest.fixture()
def api(tmp_path, monkeypatch):
    # 保存先を一時フォルダにする（手元の back/data を汚さない）
    monkeypatch.setattr(storage, "OBJECTS_DIR", tmp_path / "objects")
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "ito.sqlite3")
    return TestClient(app)


def _png_data_url(size=1024) -> str:
    buf = io.BytesIO()
    Image.new("L", (size, size), 255).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _drawing(**kw):
    strokes = from_reference("と", scale=600, offset=(200, 200), **kw)
    return {
        "user_name": "テスト",
        "target": "と",
        "canvas": {"width": 1024, "height": 1024},
        "strokes": [{"pointerType": "pen", "points": [[float(x), float(y), int(t), 0.5] for x, y, t, _ in s]}
                    for s in strokes],
        "image": _png_data_url(),
        "width": 1024,
        "height": 1024,
    }


def test_drawing_without_ai_returns_ledger_sock(api, monkeypatch, tmp_path):
    async def none(*a, **k):
        return None
    monkeypatch.setattr(llm_client, "judge", none)
    r = api.post("/api/drawings", json=_drawing(noise=0.03, seed=1))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["sock"]["id"] in catalog.all_ids()
    assert body["sock"]["image"].startswith("/socks/")
    assert catalog.item(body["sock"]["id"])["name"] in body["message"]  # テンプレートの文
    # 台帳に、分析が選んだくつしたとメッセージが記録されている
    import sqlite3
    row = sqlite3.connect(tmp_path / "ito.sqlite3").execute("select sock_id, message from drawings").fetchone()
    assert row == (body["sock"]["id"], body["message"])


def test_drawing_with_ai_uses_ai_comment(api, monkeypatch):
    async def judge(png, qjson):
        import json
        cands = json.loads(qjson)["印象の候補（この中から1つ選ぶ）"]
        return ToJudgement(is_to=True, is_to_confidence=90, impression=cands[0]["id"], impression_reason="理由",
                           balance=7, line_quality=7, endings=7, overall=7)

    async def comment(png, sock_image, text):
        return SockComment(comment="あなたの「と」から、すてきな一足が編み上がりました。")

    monkeypatch.setattr(llm_client, "judge", judge)
    monkeypatch.setattr(llm_client, "comment", comment)
    body = api.post("/api/drawings", json=_drawing(noise=0.03, seed=2)).json()
    assert body["message"] == "あなたの「と」から、すてきな一足が編み上がりました。"
    assert body["sock"]["id"] in catalog.all_ids()


def test_drawing_survives_analysis_crash(api, monkeypatch):
    from src import drawings

    def boom(*a, **k):
        raise RuntimeError("分析の不具合")
    monkeypatch.setattr(drawings, "judge_sync", boom)
    r = api.post("/api/drawings", json=_drawing())
    assert r.status_code == 201
    assert r.json()["sock"]["id"] in catalog.all_ids()


def test_judge_sync_works_outside_server():
    from src.judge.service import judge_sync
    strokes = [{"pointerType": "mouse", "points": s.tolist()} for s in from_reference("と", noise=0.03, seed=3)]
    r = judge_sync(strokes, (512, 512))
    assert r.sock_id in catalog.all_ids() and r.comment
