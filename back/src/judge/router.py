"""判定 API。パスは本番（Worker → Container）とローカル（Vite proxy → back）で共通。"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from . import catalog, engine
from .analysis import rare
from .analysis.axes import IMPRESSION_LABELS
from .llm import client as llm
from .llm.prompts import comment_user_text
from .refs import TARGET, raw_reference
from .schemas import JudgeRequest, JudgeResponse
from .settings import settings

router = APIRouter(prefix="/api", tags=["judge"])

EVAL_DIR = Path(__file__).resolve().parents[1] / "eval_data"


def _analyze(req: JudgeRequest) -> engine.Analysis:
    return engine.analyze(
        [s.points for s in req.strokes],
        [s.pointerType for s in req.strokes],
        (req.canvas.width, req.canvas.height),
    )


@router.post("/judge/geometry", response_model=JudgeResponse, response_model_exclude_none=True,
             summary="AI を使わずに判定（解析エンジン＋テンプレートのコメント）")
def judge_geometry(req: JudgeRequest) -> JudgeResponse:
    a = _analyze(req)
    d = engine.decide(a, impression=None, ai_beauty=None, ai_is_to=None)
    return JudgeResponse(
        sock_id=d["sock_id"], comment=engine.template_comment(d), degraded=True,
        debug=engine.debug_info(a, d, {"timings_ms": a.timings}) if settings.dev else None,
    )


@router.post("/judge/full", response_model=JudgeResponse, response_model_exclude_none=True,
             summary="解析エンジン → AI①判定 → 靴下ID → AI②コメント")
async def judge_full(req: JudgeRequest) -> JudgeResponse:
    a = _analyze(req)
    png = engine.plain_png(a)

    t1 = time.perf_counter()
    j = await llm.judge(png, a.quantitative_json())
    t2 = time.perf_counter()
    if j is not None:
        beauty = (j.balance + j.line_quality + j.endings + j.overall) / 4
        beauty = max(1.0, min(10.0, beauty)) * 10
        d = engine.decide(a, impression=j.impression, ai_beauty=beauty, ai_is_to=j.is_to)
    else:
        d = engine.decide(a, impression=None, ai_beauty=None, ai_is_to=None)

    c = None
    if j is not None:
        sid = d["sock_id"]
        sock_image = catalog.image_source(sid)
        c = await llm.comment(png, sock_image, comment_user_text(
            sock_label=catalog.label(sid),
            impression_label=IMPRESSION_LABELS[d["impression"]],
            quality_rank=d["quality_rank"],
            special_note=rare.NOTES.get(d["special"]) if d["special"] else None,
            judge_reason=j.impression_reason,
            feature_text=a.axes.reasons.get(d["impression"], []),
            description=catalog.description(sid),
            has_image=sock_image is not None,
        ))
    t3 = time.perf_counter()

    comment = c.comment.strip() if c is not None and c.comment.strip() else engine.template_comment(d)
    degraded = j is None or c is None
    extra = {
        "ai_judgement": j.model_dump() if j is not None else None,
        "sock_image_used": str(catalog.image_source(d["sock_id"])) if catalog.image_source(d["sock_id"]) else None,
        "timings_ms": {**a.timings, "ai_judge": int((t2 - t1) * 1000), "ai_comment": int((t3 - t2) * 1000)},
    }
    return JudgeResponse(
        sock_id=d["sock_id"], comment=comment, degraded=degraded,
        debug=engine.debug_info(a, d, extra) if settings.dev else None,
    )


@router.get("/socks", summary="靴下50種の一覧（socks.json の内容）")
def list_socks() -> list[dict]:
    return [catalog.item(sid) for sid in catalog.all_ids()]


@router.get("/refs/to", summary="「と」のお手本の点列（0〜1 座標、書き順どおり）")
def get_reference() -> dict:
    return raw_reference(TARGET)


@router.get("/dev/playground", response_class=HTMLResponse, include_in_schema=False)
def playground() -> str:
    """手書きで判定を試す確認ページ（DEV=1 のときだけ有効）。"""
    if not settings.dev:
        raise HTTPException(status_code=404, detail="Not Found")
    return (Path(__file__).resolve().parent / "playground.html").read_text(encoding="utf-8")


@router.get("/dev/sock-image/{sock_id}", include_in_schema=False)
def dev_sock_image(sock_id: str) -> FileResponse:
    """確認ページ用に靴下画像を返す（DEV=1 のときだけ。本番の画像配信はフロント側）。"""
    path = catalog.image_path(sock_id) if settings.dev and sock_id in catalog.all_ids() else None
    if path is None:
        raise HTTPException(status_code=404, detail="Not Found")
    return FileResponse(path)


@router.post("/dev/samples", summary="検証用サンプルの保存（DEV=1 のときだけ有効）")
def save_sample(req: JudgeRequest, intended: str = "", quality: int | None = None, writer: str = "") -> dict:
    """intended: 書いたつもりの印象（koseiteki など）、quality: 人が付けた品質 1-5。"""
    if not settings.dev:
        raise HTTPException(status_code=404, detail="Not Found")
    EVAL_DIR.mkdir(exist_ok=True)
    a = _analyze(req)
    d = engine.decide(a, impression=None, ai_beauty=None, ai_is_to=None)
    name = f"{datetime.now():%Y%m%d-%H%M%S-%f}.json"
    (EVAL_DIR / name).write_text(json.dumps({
        "intended": intended, "quality": quality, "writer": writer,
        "request": req.model_dump(), "analysis": engine.debug_info(a, d),
    }, ensure_ascii=False), encoding="utf-8")
    return {"saved": name, "sock_id_without_ai": d["sock_id"]}
