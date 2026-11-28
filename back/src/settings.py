"""置き場所などの設定。環境変数で差し替えられる。"""

import os
from pathlib import Path

# データの置き場。既定は back/data（コンテナ内では /app/data）。
DATA_DIR = Path(
    os.environ.get("ITO_DATA_DIR", Path(__file__).resolve().parent.parent / "data")
)

# 本番で、画像の置き場（R2）と台帳（D1）への読み書きを頼む先（Cloudflare の Worker）。
# 例: http://ito.store 。設定されていなければ、手元の代わり（DATA_DIR のフォルダと
# SQLite）を使う。頼む口の形は back/src/storage.py と back/src/db.py の先頭を参照。
STORE_URL = os.environ.get("ITO_STORE_URL", "").rstrip("/")
# Worker の返事を待つ秒数
STORE_TIMEOUT_SECONDS = 10

# シェア用のページに書く、サイトのアドレス（例: https://example.com 。最後の / なし）。
# 設定されていなければ、リクエストの Host から決める（back/src/share.py の site_url）。
SITE_URL = os.environ.get("ITO_SITE_URL", "").rstrip("/")
