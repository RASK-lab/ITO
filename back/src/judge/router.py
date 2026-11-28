"""分析を単体で確かめるための API（/api/judge/*、/api/socks、/api/refs/to、/api/dev/*）。

画面（フロント）は、ふだん POST /api/drawings だけを呼ぶ。分析はその中から
service.judge_sync() で呼ばれる（back/src/drawings.py の make_result）。
ここにある API は、分析だけを試したいとき・保存せずに結果だけ欲しいときに使う。

| メソッド | パス | 内容 |
|---|---|---|
| POST | /api/judge/full | 分析（AI あり）。保存はしない |
| POST | /api/judge/geometry | 分析（AI なし。速く無料）。保存はしない |
| GET | /api/socks | くつした 50 種の台帳（back/src/resources/socks.json の items） |
| GET | /api/refs/to | 「と」のお手本の点の並び |
| GET | /api/dev/playground | 手書きで分析を試す確認ページ（DEV=1 のときだけ） |
| POST | /api/dev/samples | 調整用のサンプルを保存（DEV=1 のときだけ） |
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from . import catalog, service
from .refs import TARGET, raw_reference
from .schemas import JudgeRequest, JudgeResponse
from .settings import settings

router = APIRouter(prefix="/api", tags=["judge（分析）"])


def _canvas(req: JudgeRequest) -> tuple[float, float]:
    return (req.canvas.width, req.canvas.height)


def _response(result: service.JudgeResult) -> JudgeResponse:
    # 内部の評価（debug）は DEV=1 のときだけ返す（利用者に品質や印象を見せないため）
    return JudgeResponse(
        sock_id=result.sock_id, comment=result.comment, degraded=result.degraded,
        debug=result.debug if settings.dev else None,
    )


@router.post("/judge/full", response_model=JudgeResponse, response_model_exclude_none=True,
             summary="分析（AI あり）。保存はしない")
async def judge_full(req: JudgeRequest) -> JudgeResponse:
    """線のデータから、くつしたとコメントを返す。2〜7 秒かかる。

    画面からは、保存も一緒に行う POST /api/drawings を使う。
    """
    result = await service.judge(req.strokes, _canvas(req))
    service.save_for_tuning(req.model_dump(), result, source="judge/full")
    return _response(result)


@router.post("/judge/geometry", response_model=JudgeResponse, response_model_exclude_none=True,
             summary="分析（AI なし）。保存はしない")
def judge_geometry(req: JudgeRequest) -> JudgeResponse:
    """AI を使わずに、解析エンジンとテンプレートの文だけで返す（0.3 秒ほど。無料）。"""
    result = service.judge_without_ai(req.strokes, _canvas(req))
    service.save_for_tuning(req.model_dump(), result, source="judge/geometry")
    return _response(result)


@router.get("/socks", summary="くつした 50 種の台帳")
def list_socks() -> list[dict]:
    """back/src/resources/socks.json の items をそのまま返す（id, name, image, classification など）。"""
    return [catalog.item(sid) for sid in catalog.all_ids()]


@router.get("/refs/to", summary="「と」のお手本の点の並び")
def get_reference() -> dict:
    """KanjiVG のお手本。座標は 0〜1、書き順どおり（糸のアニメーションなどで使える）。"""
    return raw_reference(TARGET)


# ---------- 開発用（DEV=1 のときだけ。本番では 404） ----------

def _require_dev() -> None:
    if not settings.dev:
        raise HTTPException(status_code=404, detail="Not Found")


@router.get("/dev/playground", response_class=HTMLResponse, include_in_schema=False)
def playground() -> str:
    """手書きで分析を試す確認ページ。内部の評価（品質・印象・特徴量）も表示する。"""
    _require_dev()
    return (Path(__file__).resolve().parent / "playground.html").read_text(encoding="utf-8")


@router.get("/dev/sock-image/{sock_id}", include_in_schema=False)
def dev_sock_image(sock_id: str) -> FileResponse:
    """確認ページ用のくつしたの画像（本番の画像は、フロントが /socks/*.webp で配る）。"""
    _require_dev()
    path = catalog.image_path(sock_id) if sock_id in catalog.all_ids() else None
    if path is None:
        raise HTTPException(status_code=404, detail="Not Found")
    return FileResponse(path)


@router.post("/dev/samples", summary="調整用のサンプルを保存（DEV=1 のときだけ）")
def save_sample(req: JudgeRequest, intended: str = "", quality: int | None = None, writer: str = "") -> dict:
    """intended: 書いたつもりの印象（koseiteki など）、quality: 人が付けた綺麗さ 1〜5、writer: 書いた人。"""
    _require_dev()
    result = service.judge_without_ai(req.strokes, _canvas(req))
    service.EVAL_DIR.mkdir(exist_ok=True)
    name = f"{datetime.now():%Y%m%d-%H%M%S-%f}.json"
    (service.EVAL_DIR / name).write_text(json.dumps({
        "intended": intended, "quality": quality, "writer": writer,
        "request": req.model_dump(), "analysis": result.debug,
    }, ensure_ascii=False, default=str), encoding="utf-8")
    return {"saved": name, "sock_id_without_ai": result.sock_id}
