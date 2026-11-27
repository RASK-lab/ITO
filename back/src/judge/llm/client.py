"""Claude 呼び出し。①ブラインド判読と②AI講評（美しさの採点と講評）を並列に実行する。"""

from __future__ import annotations

import asyncio
import base64
import logging

import anthropic
from anthropic import AsyncAnthropic

from ..settings import settings
from .prompts import BLIND_SYSTEM, REVIEW_SYSTEM, review_user_text
from .schemas import BlindRead, Critique

log = logging.getLogger(__name__)

_client: AsyncAnthropic | None = None


def get_client() -> AsyncAnthropic | None:
    global _client
    if not settings.llm_enabled:
        return None
    if _client is None:
        _client = AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            base_url=settings.anthropic_base_url,
            timeout=settings.llm_timeout_s,
            max_retries=1,
        )
    return _client


def image_block(png: bytes) -> dict:
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": base64.standard_b64encode(png).decode()},
    }


async def blind_read(plain_png: bytes) -> BlindRead | None:
    client = get_client()
    if client is None:
        return None
    res = await client.messages.parse(
        model=settings.llm_model,
        max_tokens=4000,
        output_config={"effort": "low"},
        system=BLIND_SYSTEM,
        messages=[{
            "role": "user",
            "content": [image_block(plain_png), {"type": "text", "text": "この手書き文字を判読し、印象を評価してください。"}],
        }],
        output_format=BlindRead,
    )
    if res.stop_reason != "end_turn":
        log.warning("blind_read stop_reason=%s", res.stop_reason)
        return None
    return res.parsed_output


async def critique(numbered_png: bytes, target: str, intent: str, geometry_json: str) -> Critique | None:
    client = get_client()
    if client is None:
        return None
    res = await client.messages.parse(
        model=settings.llm_model,
        max_tokens=4000,
        output_config={"effort": "low"},
        system=REVIEW_SYSTEM,
        messages=[{
            "role": "user",
            "content": [image_block(numbered_png), {"type": "text", "text": review_user_text(target, intent, geometry_json)}],
        }],
        output_format=Critique,
    )
    if res.stop_reason != "end_turn":
        log.warning("critique stop_reason=%s", res.stop_reason)
        return None
    return res.parsed_output


async def judge_llm(
    plain_png: bytes, numbered_png: bytes, target: str, intent: str, geometry_json: str
) -> tuple[BlindRead | None, Critique | None]:
    """両方を並列に呼ぶ。失敗した側は None（幾何スコアだけで続行できるように）。"""
    results = await asyncio.gather(
        blind_read(plain_png),
        critique(numbered_png, target, intent, geometry_json),
        return_exceptions=True,
    )
    out = []
    for r in results:
        if isinstance(r, anthropic.APIError):
            log.warning("LLM API error: %s", r)
            out.append(None)
        elif isinstance(r, BaseException):
            log.exception("LLM call failed", exc_info=r)
            out.append(None)
        else:
            out.append(r)
    return out[0], out[1]
