"""環境変数による設定。ローカルは back/.env（gitignore 済み）、本番は Container の envVars。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    """依存を増やさないための簡易 .env 読み込み（既に設定済みの環境変数は上書きしない）。"""
    here = Path(__file__).resolve()
    # back/.env とリポジトリ直下の .env（compose の env_file と同じ場所）を探す
    for path in (Path.cwd() / ".env", here.parents[2] / ".env", here.parents[3] / ".env"):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip('"').strip("'")
            if value:  # 空欄の行は無視する（空文字の ANTHROPIC_BASE_URL を SDK が接続先として使ってしまうため）
                os.environ.setdefault(key.strip(), value)


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str | None = os.environ.get("ANTHROPIC_API_KEY") or None
    # AI Gateway を使う場合: https://gateway.ai.cloudflare.com/v1/<ACCOUNT_ID>/<GATEWAY_ID>/anthropic
    anthropic_base_url: str | None = os.environ.get("ANTHROPIC_BASE_URL") or None
    llm_model: str = os.environ.get("LLM_MODEL", "claude-haiku-5-5")
    # AI② コメントだけ別モデルにする場合（未設定なら llm_model）
    comment_model: str = os.environ.get("COMMENT_MODEL") or os.environ.get("LLM_MODEL", "claude-haiku-5-5")
    # 1日あたりの Claude 呼び出し回数の上限（超えたら AI なしで返す）
    llm_daily_limit: int = int(os.environ.get("LLM_DAILY_LIMIT", "3000"))
    llm_timeout_s: float = float(os.environ.get("LLM_TIMEOUT_S", "15"))
    dev: bool = os.environ.get("DEV", "0") == "1"
    # 本番で靴下画像を置く場所の URL（例: R2 の公開 URL）。設定すると AI② は {URL}/{靴下ID}.png を読む
    sock_image_base_url: str | None = os.environ.get("SOCK_IMAGE_BASE_URL") or None

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


settings = Settings()
