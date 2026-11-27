"""環境変数による設定。ローカルは back/.env（gitignore 済み）、本番は Container の envVars。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    """依存を増やさないための簡易 .env 読み込み（既に設定済みの環境変数は上書きしない）。"""
    for path in (Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env"):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str | None = os.environ.get("ANTHROPIC_API_KEY") or None
    # AI Gateway を使う場合: https://gateway.ai.cloudflare.com/v1/<ACCOUNT_ID>/<GATEWAY_ID>/anthropic
    anthropic_base_url: str | None = os.environ.get("ANTHROPIC_BASE_URL") or None
    llm_model: str = os.environ.get("LLM_MODEL", "claude-haiku-5-5")
    llm_timeout_s: float = float(os.environ.get("LLM_TIMEOUT_S", "15"))
    dev: bool = os.environ.get("DEV", "0") == "1"

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


settings = Settings()
