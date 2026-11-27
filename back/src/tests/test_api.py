from fastapi.testclient import TestClient

from src.judge import combine
from src.judge.llm import client as llm_client
from src.judge.llm.schemas import BlindRead, Correction, Critique, ImpressionAxes
from src.main import app

from .helpers import from_reference

api = TestClient(app)


def _payload(char="十", **kw):
    strokes = from_reference(char, **kw)
    return {
        "target": char,
        "intent": "chikarazuyosa",
        "canvas": {"width": 512, "height": 512},
        "strokes": [{"pointerType": "pen", "points": s.tolist()} for s in strokes],
    }


def test_health_still_works():
    assert api.get("/api/health").json()["status"] == "ok"


def test_geometry_endpoint():
    r = api.post("/api/judge/geometry", json=_payload("都"))
    assert r.status_code == 200
    body = r.json()
    assert body["ref_stroke_count"] == 11
    assert body["total"] >= 90


def test_points_with_and_without_pressure():
    p = _payload("十")
    p["strokes"][0]["points"] = [q[:3] for q in p["strokes"][0]["points"]]
    assert api.post("/api/judge/geometry", json=p).status_code == 200


def test_invalid_point_is_rejected():
    p = _payload("十")
    p["strokes"][0]["points"][0] = [1.0]
    assert api.post("/api/judge/geometry", json=p).status_code == 422


def test_unknown_target_is_rejected():
    p = _payload("十")
    p["target"] = "あ"
    assert api.post("/api/judge/geometry", json=p).status_code == 422


def test_refs_endpoint():
    body = api.get("/api/refs/と").json()
    assert body["char"] == "と"
    assert len(body["variants"][0]["strokes"]) == 2


def test_full_without_llm_is_degraded(monkeypatch):
    async def none(*a, **k):
        return None
    monkeypatch.setattr(llm_client, "blind_read", none)
    monkeypatch.setattr(llm_client, "critique", none)
    body = api.post("/api/judge/full", json=_payload("戸")).json()
    assert body["degraded"] is True
    assert body["final"] == body["geometry"]["total"]


def _fake_llm(read_as):
    async def blind(*a, **k):
        return BlindRead(read_as=read_as, confidence=90, impressions=["堂々", "力強い", "素直"],
                         axes=ImpressionAxes(chikarazuyosa=8, yasashisa=3, teinei=6, genki=7, yuuga=4))

    async def crit(*a, **k):
        return Critique(balance=8, line_quality=7, endings=9, overall=8, good_point="縦画がまっすぐ",
                        comment="よく書けています", corrections=[Correction(stroke=2, kind="ending", issue="しっかり止めましょう"),
                                                          Correction(stroke=99, kind="shape", issue="範囲外")])
    return blind, crit


def test_full_with_llm(monkeypatch):
    blind, crit = _fake_llm("十")
    monkeypatch.setattr(llm_client, "blind_read", blind)
    monkeypatch.setattr(llm_client, "critique", crit)
    body = api.post("/api/judge/full", json=_payload("十")).json()
    assert body["degraded"] is False and body["capped"] is False
    assert body["llm"]["intent_score"] == 80
    assert [c["stroke"] for c in body["llm"]["corrections"]] == [2]  # 範囲外の画番号は捨てる
    geo = body["geometry"]["total"]
    expected = round(0.45 * geo + 0.35 * 80 + 0.20 * 80)
    assert body["final"] == expected


def test_misread_caps_score(monkeypatch):
    blind, crit = _fake_llm("土")
    monkeypatch.setattr(llm_client, "blind_read", blind)
    monkeypatch.setattr(llm_client, "critique", crit)
    body = api.post("/api/judge/full", json=_payload("十")).json()
    assert body["capped"] is True
    assert body["final"] == combine.CAP_WHEN_MISREAD


def test_dev_samples_disabled_by_default():
    assert api.post("/api/dev/samples", json=_payload("十")).status_code == 404
