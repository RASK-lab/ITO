"""置き場所などの設定。環境変数で差し替えられる。"""

import os
from pathlib import Path

# データの置き場。既定は back/data（コンテナ内では /app/data）。
DATA_DIR = Path(
    os.environ.get("ITO_DATA_DIR", Path(__file__).resolve().parent.parent / "data")
)
