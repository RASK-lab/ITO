"""判定 API。パスは本番（Worker → Container）とローカル（Vite proxy → back）で共通。"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from . import combine, render
from .geometry.score import evaluate
from .llm.client import judge_llm
from .refs import raw_reference
from .schemas import GeometryResult, JudgeFullResponse, JudgeRequest, Target
from .settings import settings

router = APIRouter(prefix="/api", tags=["judge"])

EVAL_DIR = Path(__file__).resolve().parents[1] / "eval_data"


def _arrays(req: JudgeRequest) -> list[np.ndarray]:
    return [np.asarray([p[:3] for p in s.points], dtype=float) for s in req.strokes]


def _geometry(req: JudgeRequest) -> GeometryResult:
    return evaluate(req.target, _arrays(req), [s.pointerType for s in req.strokes])


@router.post("/judge/geometry", response_model=GeometryResult, summary="幾何スコアのみ（即時）")
def judge_geometry(req: JudgeRequest) -> GeometryResult:
    return _geometry(req)


@router.post("/judge/full", response_model=JudgeFullResponse, summary="幾何 + 伊藤先生（LLM）+ 統合スコア")
async def judge_full(req: JudgeRequest) -> JudgeFullResponse:
    t0 = time.perf_counter()
    geo = _geometry(req)
    t1 = time.perf_counter()

    strokes = _arrays(req)
    geo_json = json.dumps(
        {"items": geo.items.model_dump(), "per_stroke": [p.model_dump() for p in geo.per_stroke]},
        ensure_ascii=False,
    )
    blind, crit = await judge_llm(render.render_plain(strokes), render.render_numbered(strokes), req.target, req.intent, geo_json)
    t2 = time.perf_counter()

    llm = combine.build_llm_result(blind, crit, req.intent, len(req.strokes))
    final, capped, degraded = combine.final_score(req.target, geo, llm)
    return JudgeFullResponse(
        final=final,
        capped=capped,
        degraded=degraded,
        geometry=geo,
        llm=llm,
        timings_ms={"geometry": int((t1 - t0) * 1000), "llm": int((t2 - t1) * 1000)},
    )


@router.get("/refs/{char}", summary="お手本の点列（0〜1 座標、書き順どおり）")
def get_reference(char: Target) -> dict:
    try:
        return raw_reference(char)
    except KeyError:
        raise HTTPException(status_code=404, detail="お手本がありません")


@router.get("/dev/playground", response_class=HTMLResponse, include_in_schema=False)
def playground() -> str:
    """手書きで判定を試す確認ページ（DEV=1 のときだけ有効）。"""
    if not settings.dev:
        raise HTTPException(status_code=404, detail="Not Found")
    return (Path(__file__).resolve().parent / "playground.html").read_text(encoding="utf-8")


@router.post("/dev/samples", summary="検証用サンプルの保存（DEV=1 のときだけ有効）")
def save_sample(req: JudgeRequest, label: str = "", writer: str = "") -> dict:
    if not settings.dev:
        raise HTTPException(status_code=404, detail="Not Found")
    EVAL_DIR.mkdir(exist_ok=True)
    geo = _geometry(req)
    name = f"{datetime.now():%Y%m%d-%H%M%S-%f}.json"
    (EVAL_DIR / name).write_text(
        json.dumps(
            {"label": label, "writer": writer, "request": req.model_dump(), "geometry": geo.model_dump()},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return {"saved": name, "geometry_total": geo.total}
