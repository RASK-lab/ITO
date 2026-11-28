import json

from fastapi.testclient import TestClient

from src.judge.llm import client as llm_client
from src.judge.llm.schemas import SockComment, ToJudgement
from src.main import app

from .helpers import from_reference

api = TestClient(app)
CANDIDATES_KEY = "印象の候補（この中から1つ選ぶ）"


def _payload(char="と", **kw):
    return {
        "canvas": {"width": 512, "height": 512},
        "strokes": [{"pointerType": "pen", "points": s.tolist()} for s in from_reference(char, **kw)],
    }


def test_health_still_works():
    assert api.get("/api/health").json()["status"] == "ok"


def test_geometry_endpoint_returns_sock_and_comment():
    body = api.post("/api/judge/geometry", json=_payload(noise=0.03, seed=1)).json()
    assert {"sock_id", "comment", "degraded"} <= set(body)
    assert body["degraded"] is True
    assert body["sock_id"] in [s["id"] for s in api.get("/api/socks").json()]
    assert "debug" not in body  # DEV=1 のときだけ


def test_points_with_and_without_pressure():
    p = _payload()
    p["strokes"][0]["points"] = [q[:3] for q in p["strokes"][0]["points"]]
    assert api.post("/api/judge/geometry", json=p).status_code == 200


def test_invalid_point_is_rejected():
    p = _payload()
    p["strokes"][0]["points"][0] = [1.0]
    assert api.post("/api/judge/geometry", json=p).status_code == 422


def test_socks_list():
    socks = api.get("/api/socks").json()
    assert len(socks) == 50
    assert {"id", "name", "image", "classification"} <= set(socks[0])


def test_refs_endpoint():
    assert api.get("/api/refs/to").json()["char"] == "と"


def test_full_without_llm_is_degraded(monkeypatch):
    async def none(*a, **k):
        return None
    monkeypatch.setattr(llm_client, "judge", none)
    body = api.post("/api/judge/full", json=_payload(noise=0.03, seed=1)).json()
    assert body["degraded"] is True
    assert body["comment"]


def test_full_with_llm(monkeypatch):
    seen = {}

    async def judge(png, qjson):
        seen["qjson"] = qjson
        cands = json.loads(qjson)[CANDIDATES_KEY]
        return ToJudgement(is_to=True, is_to_confidence=90, impression=cands[1]["id"], impression_reason="理由",
                           balance=6, line_quality=6, endings=6, overall=6)

    async def comment(png, sock_image, text):
        seen["text"] = text
        seen["image"] = sock_image
        return SockComment(comment="AIのコメントです。")

    monkeypatch.setattr(llm_client, "judge", judge)
    monkeypatch.setattr(llm_client, "comment", comment)
    body = api.post("/api/judge/full", json=_payload(noise=0.03, seed=1)).json()
    assert body["degraded"] is False
    assert body["comment"] == "AIのコメントです。"
    assert "選ばれた靴下" in seen["text"]
    assert seen["image"] is not None  # 靴下画像を AI に渡している
    second = json.loads(seen["qjson"])[CANDIDATES_KEY][1]["id"]
    from src.judge import catalog
    feature = catalog.item(body["sock_id"])["classification"]["feature"]
    assert catalog.FEATURE_TO_IMPRESSION[feature] == second
    assert "靴下の説明" in seen["text"]


def test_dev_endpoints_disabled_by_default():
    assert api.post("/api/dev/samples", json=_payload()).status_code == 404
    assert api.get("/api/dev/playground").status_code == 404
