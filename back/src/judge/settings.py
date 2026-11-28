"""分析（back/src/judge）の設定。すべて環境変数で変えられる。

| 環境変数 | 既定 | 内容 |
|---|---|---|
| ANTHROPIC_API_KEY | なし | Claude の API キー。無ければ AI を使わず、解析エンジンとテンプレートの文だけで返す |
| ANTHROPIC_BASE_URL | なし | Cloudflare AI Gateway を通すときだけ（例: https://gateway.ai.cloudflare.com/v1/<ACCOUNT>/<GATEWAY>/anthropic） |
| LLM_MODEL | claude-haiku-5-5 | 判定とコメントに使うモデル |
| COMMENT_MODEL | LLM_MODEL と同じ | コメントだけ別のモデルにするとき |
| LLM_DAILY_LIMIT | 3000 | 1 日に Claude を呼ぶ回数の上限（1 回の確定で 2〜3 回呼ぶ）。超えたら AI なしで返す |
| LLM_TIMEOUT_S | 15 | Claude 1 回の呼び出しを待つ秒数 |
| JUDGE_AI_BUDGET_S | 11 | 1 回の確定で AI に使ってよい合計の秒数。超えたら AI なしの結果に切り替える（フロントは 15 秒で打ち切るため） |
| SOCK_IMAGE_BASE_URL | なし | 本番で公開しているサイトの URL。AI にくつしたの画像を見せるのに使う（catalog.image_source） |
| SOCK_IMAGE_DIR | なし | くつしたの画像を置いたフォルダ（手元で、リポジトリの外の画像を使うとき） |
| DEV | 0 | 1 にすると、開発用の確認ページ（/api/dev/*）と、判定データの記録（back/src/eval_data/）が有効になる |

手元では、リポジトリ直下または back/ の `.env` も読む（すでに設定されている環境変数は上書きしない）。
本番（Cloudflare Containers）では、Worker からコンテナに渡す環境変数で設定する。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    """依存を増やさないための簡易 .env 読み込み（既に設定済みの環境変数は上書きしない）。"""
    here = Path(__file__).resolve()
    # 今いるフォルダ、back/、リポジトリ直下 の順に .env を探す。コンテナの中には無いので何もしない
    candidates = [Path.cwd() / ".env"] + [p / ".env" for p in here.parents[2:4]]
    for path in candidates:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip('"').strip("'")
            # 空欄の行は無視する（空文字の ANTHROPIC_BASE_URL を SDK が接続先として使ってしまうため）
            if value:
                os.environ.setdefault(key.strip(), value)


_load_dotenv()


def _env(name: str, default: str | None = None) -> str | None:
    """空文字は「設定なし」として扱う（compose の env_file に空欄があっても既定値を使うため）。"""
    v = os.environ.get(name)
    return v if v else default


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str | None = _env("ANTHROPIC_API_KEY")
    anthropic_base_url: str | None = _env("ANTHROPIC_BASE_URL")
    llm_model: str = _env("LLM_MODEL", "claude-haiku-5-5")
    comment_model: str = _env("COMMENT_MODEL") or _env("LLM_MODEL", "claude-haiku-5-5")
    llm_daily_limit: int = int(_env("LLM_DAILY_LIMIT", "3000"))
    llm_timeout_s: float = float(_env("LLM_TIMEOUT_S", "15"))
    judge_ai_budget_s: float = float(_env("JUDGE_AI_BUDGET_S", "11"))
    sock_image_base_url: str | None = _env("SOCK_IMAGE_BASE_URL")
    dev: bool = _env("DEV", "0") == "1"

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


settings = Settings()
