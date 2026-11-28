"""分析の入口。ほかのモジュールからは、ここの関数だけを呼べばよい。

    from src.judge.service import judge_sync

    result = judge_sync(strokes=[{"pointerType": "mouse", "points": [[x, y, t, p], ...]}, ...],
                        canvas=(1024, 1024))
    result.sock_id   # くつしたの ID（例: "REGAL-01"）。back/src/resources/socks.json の id
    result.comment   # 利用者に見せるコメント（2〜3 文）
    result.degraded  # AI を使えず、解析エンジンとテンプレートの文で返したとき True

流れ（くわしくは back/src/judge/README.md）:

1. 解析エンジン（AI なし、0.3 秒ほど）: 誤タップの除外、「と」か、お手本との照合、特徴量、印象の候補 3 つ
2. AI① 判定（Claude）: 候補 3 つから印象を 1 つ決め、字の美しさを採点する
3. くつしたを決める: 品質ランク（綺麗さ 1〜5）× 印象 のマスのくつした
4. AI② コメント（Claude）: 書いた「と」とくつしたの画像を見て、利用者に語りかける文を書く

AI はどの段階で失敗しても（キーが無い、通信の失敗、時間切れ、1 日の上限）、例外は出さずに
AI なしの結果に切り替える。AI に使う時間の合計は JUDGE_AI_BUDGET_S 秒まで（settings.py）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import anyio.from_thread

from . import catalog, engine
from .analysis import rare
from .analysis.axes import IMPRESSION_LABELS
from .llm import client as llm
from .llm.prompts import comment_user_text, forbidden_words_in
from .settings import settings

log = logging.getLogger(__name__)

# DEV=1 のとき、判定したデータを置く場所（Git には入らない）
EVAL_DIR = Path(__file__).resolve().parents[1] / "eval_data"


@dataclass
class JudgeResult:
    sock_id: str                 # くつしたの ID（台帳の id）
    comment: str                 # 利用者に見せるコメント
    degraded: bool               # AI を使えなかったとき True
    debug: dict[str, Any] = field(default_factory=dict)  # 内部の評価（品質・印象・特徴量など。利用者には見せない）


def _strokes_args(strokes: Iterable[Any]) -> tuple[list, list[str]]:
    """線のデータを、dict（JSON のまま）でも pydantic のモデルでも受け取れるようにする。"""
    points, types = [], []
    for s in strokes:
        if isinstance(s, dict):
            points.append(s["points"])
            types.append(s.get("pointerType", "mouse"))
        else:
            points.append(s.points)
            types.append(getattr(s, "pointerType", "mouse"))
    return [[list(p) for p in pts] for pts in points], types


def judge_without_ai(strokes: Iterable[Any], canvas: tuple[float, float]) -> JudgeResult:
    """AI を使わずに判定する（解析エンジンとテンプレートの文だけ。速く、無料）。"""
    points, types = _strokes_args(strokes)
    a = engine.analyze(points, types, canvas)
    d = engine.decide(a, impression=None, ai_beauty=None, ai_is_to=None)
    return JudgeResult(
        sock_id=d["sock_id"], comment=engine.template_comment(d), degraded=True,
        debug=engine.debug_info(a, d, {"timings_ms": a.timings}),
    )


async def _ai_part(a: engine.Analysis, png: bytes, timings: dict) -> tuple[dict, str | None, dict]:
    """AI① 判定 → くつしたを決める → AI② コメント。返り値: (くつしたの決定, コメント or None, debug の追加分)"""
    extra: dict[str, Any] = {}

    t = time.perf_counter()
    j = await llm.judge(png, a.quantitative_json())
    timings["ai_judge"] = int((time.perf_counter() - t) * 1000)
    if j is None:
        return engine.decide(a, impression=None, ai_beauty=None, ai_is_to=None), None, extra

    # 美しさ（4 項目、各 1〜10）を 10〜100 にして品質点に使う
    beauty = max(1.0, min(10.0, (j.balance + j.line_quality + j.endings + j.overall) / 4)) * 10
    d = engine.decide(a, impression=j.impression, ai_beauty=beauty, ai_is_to=j.is_to)
    extra["ai_judgement"] = j.model_dump()

    sid = d["sock_id"]
    sock_image = catalog.image_source(sid)
    extra["sock_image_used"] = str(sock_image) if sock_image else None
    user_text = comment_user_text(
        sock_label=catalog.label(sid),
        impression_label=IMPRESSION_LABELS[d["impression"]],
        quality_rank=d["quality_rank"],
        special_note=rare.NOTES.get(d["special"]) if d["special"] else None,
        judge_reason=j.impression_reason,
        feature_text=a.axes.reasons.get(d["impression"], []),
        description=catalog.description(sid),
        has_image=sock_image is not None,
    )
    t = time.perf_counter()
    c = await llm.comment(png, sock_image, user_text)
    # 「選ばれた」「判定」など、利用者から見て不自然な言葉が入っていたら 1 回だけ書き直させる
    if c is not None and (bad := forbidden_words_in(c.comment)):
        extra["comment_retried"] = True
        c = await llm.comment(png, sock_image, user_text + (
            f"\n前回の文章には使わない言葉（{'、'.join(bad)}）が入っていました。"
            "その言葉を使わずに、編み上がった靴下を手渡す言葉として書き直してください。"))
        if c is not None and forbidden_words_in(c.comment):
            c = None
    timings["ai_comment"] = int((time.perf_counter() - t) * 1000)
    comment = c.comment.strip() if c is not None and c.comment.strip() else None
    return d, comment, extra


async def judge(strokes: Iterable[Any], canvas: tuple[float, float]) -> JudgeResult:
    """書いた「と」を判定し、くつしたとコメントを返す（AI を使う。数秒かかる）。

    strokes: 線の配列。各要素は {"pointerType": "mouse"|"touch"|"pen", "points": [[x, y, t, pressure], ...]}
             （dict でも、同じ項目を持つ pydantic のモデルでもよい）
    canvas:  座標の基準にした枠の (幅, 高さ)。例: (1024, 1024)
    """
    points, types = _strokes_args(strokes)
    a = engine.analyze(points, types, canvas)
    timings = dict(a.timings)
    try:
        d, comment, extra = await asyncio.wait_for(
            _ai_part(a, engine.plain_png(a), timings), timeout=settings.judge_ai_budget_s)
    except asyncio.TimeoutError:
        log.warning("AI が %.0f 秒以内に終わらなかったので、AI なしの結果にします", settings.judge_ai_budget_s)
        d, comment, extra = engine.decide(a, impression=None, ai_beauty=None, ai_is_to=None), None, {"ai_timeout": True}
    except Exception:  # noqa: BLE001 - 分析の失敗で確定を止めない
        log.exception("AI の処理で予期しない失敗。AI なしの結果にします")
        d, comment, extra = engine.decide(a, impression=None, ai_beauty=None, ai_is_to=None), None, {"ai_error": True}

    return JudgeResult(
        sock_id=d["sock_id"],
        comment=comment or engine.template_comment(d),
        degraded=comment is None,
        debug=engine.debug_info(a, d, {**extra, "timings_ms": timings}),
    )


def judge_sync(strokes: Iterable[Any], canvas: tuple[float, float]) -> JudgeResult:
    """judge() を、async でない関数から呼ぶための入口。

    FastAPI の `def`（async でない）経路は、AnyIO の作業スレッドで動く。そこからは
    anyio.from_thread.run でサーバーのイベントループに処理を頼む（ループを止めずに済む）。
    それ以外（スクリプトやテストから直接呼んだとき）は、その場でループを作って動かす。
    """
    try:
        return anyio.from_thread.run(judge, strokes, canvas)
    except RuntimeError:
        # 作業スレッドの外から呼ばれた
        return asyncio.run(judge(strokes, canvas))


def save_for_tuning(request: dict, result: JudgeResult, *, source: str) -> None:
    """DEV=1 のとき、判定したデータを back/src/eval_data/requests/ に保存する（調整・不具合調査用）。

    保存したデータは `python -m src.judge.tools.diagnose`（偏りの集計）と
    `python -m src.judge.tools.build_population`（平均の作り直し）が読む。
    """
    if not settings.dev:
        return
    try:
        d = EVAL_DIR / "requests"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{datetime.now():%Y%m%d-%H%M%S-%f}.json").write_text(json.dumps({
            "source": source, "request": request, "sock_id": result.sock_id, "comment": result.comment,
            "degraded": result.degraded, "analysis": result.debug,
        }, ensure_ascii=False, default=str), encoding="utf-8")
    except Exception:  # noqa: BLE001 - 記録の失敗で確定を止めない
        log.exception("判定データを保存できませんでした")
