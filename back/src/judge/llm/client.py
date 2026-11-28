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
from .prompts import COMMENT_SYSTEM, JUDGE_SYSTEM
from .schemas import SockComment, ToJudgement

log = logging.getLogger(__name__)

_client: AsyncAnthropic | None = None


def get_client() -> AsyncAnthropic | None:
    global _client
    if not settings.llm_enabled or not usage.allow():
        return None
    if _client is None:
        _client = AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            # 環境変数が空文字でも既定の接続先を使う（compose の env_file に空欄があっても動くように）
            base_url=settings.anthropic_base_url or "https://api.anthropic.com",
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


async def comment(to_png: bytes, sock_image: Path | str | None, user_text: str) -> SockComment | None:
    """AI② コメント。靴下の画像（ローカルファイルまたは URL）があれば一緒に渡す。"""
    content = [image_block(to_png)]
    if isinstance(sock_image, Path):
        content.append(file_image_block(sock_image))
    elif isinstance(sock_image, str):
        content.append({"type": "image", "source": {"type": "url", "url": sock_image}})
    content.append({"type": "text", "text": user_text})
    return await _parse(COMMENT_SYSTEM, content, SockComment, model=settings.comment_model)
