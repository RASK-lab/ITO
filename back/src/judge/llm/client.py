"""Claude 呼び出し。AI① 判定と AI② コメント。"""

from __future__ import annotations

import base64
import logging
import mimetypes
from pathlib import Path

import anthropic
from anthropic import AsyncAnthropic

from ..settings import settings
from . import usage
from .prompts import COMMENT_SYSTEM, DESCRIBE_SYSTEM, JUDGE_SYSTEM
from .schemas import SockComment, SockDescription, ToJudgement

log = logging.getLogger(__name__)

_client: AsyncAnthropic | None = None


def get_client() -> AsyncAnthropic | None:
    global _client
    if not settings.llm_enabled or not usage.allow():
        return None
    if _client is None:
        _client = AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            base_url=settings.anthropic_base_url,
            timeout=settings.llm_timeout_s,
            max_retries=1,
        )
    return _client


def image_block(data: bytes, media_type: str = "image/png") -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                        "data": base64.standard_b64encode(data).decode()}}


def file_image_block(path: Path) -> dict:
    mt = mimetypes.guess_type(path.name)[0] or "image/png"
    return image_block(path.read_bytes(), mt)


async def _parse(system: str, content: list[dict], output_format, model: str | None = None):
    client = get_client()
    if client is None:
        return None
    try:
        res = await client.messages.parse(
            model=model or settings.llm_model,
            max_tokens=4000,
            output_config={"effort": "low"},
            system=system,
            messages=[{"role": "user", "content": content}],
            output_format=output_format,
        )
    except anthropic.APIError as e:
        log.warning("LLM API error: %s", e)
        return None
    except Exception:  # noqa: BLE001 - デモを止めない
        log.exception("LLM call failed")
        return None
    usage.record()
    if res.stop_reason != "end_turn":
        log.warning("stop_reason=%s", res.stop_reason)
        return None
    return res.parsed_output


async def judge(to_png: bytes, quantitative_json: str) -> ToJudgement | None:
    """AI① 判定。"""
    return await _parse(JUDGE_SYSTEM, [
        image_block(to_png),
        {"type": "text", "text": "筆跡解析エンジンの定量データ:\n" + quantitative_json},
    ], ToJudgement)


async def comment(to_png: bytes, sock_image: Path | None, user_text: str) -> SockComment | None:
    """AI② コメント。靴下の画像があれば一緒に渡す。"""
    content = [image_block(to_png)]
    if sock_image is not None:
        content.append(file_image_block(sock_image))
    content.append({"type": "text", "text": user_text})
    return await _parse(COMMENT_SYSTEM, content, SockComment, model=settings.comment_model)


async def describe_sock(sock_image: Path) -> SockDescription | None:
    """靴下画像の見た目の説明（事前生成用）。"""
    return await _parse(DESCRIBE_SYSTEM, [
        file_image_block(sock_image),
        {"type": "text", "text": "この靴下の見た目を説明してください。"},
    ], SockDescription)
