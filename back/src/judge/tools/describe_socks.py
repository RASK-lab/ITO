"""靴下60種の画像を Claude に読ませ、見た目の説明を catalog/sock_descriptions.json に保存する。

実行（back/ で、ANTHROPIC_API_KEY が必要）:
    python -m src.judge.tools.describe_socks          # まだ説明が無い靴下だけ
    python -m src.judge.tools.describe_socks --all    # すべて作り直す

画像は catalog/images/<ID>.png（または .jpg / .webp）に置く。SVG は読めないので PNG に書き出しておく。
"""

from __future__ import annotations

import asyncio
import json
import sys

from .. import catalog
from ..llm import client


async def main(redo_all: bool) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    out = {} if redo_all or not catalog.DESCRIPTIONS_FILE.is_file() else json.loads(
        catalog.DESCRIPTIONS_FILE.read_text(encoding="utf-8"))
    missing_images = []
    for sid in catalog.all_ids():
        if sid in out:
            continue
        path = catalog.image_path(sid)
        if path is None:
            missing_images.append(sid)
            continue
        d = await client.describe_sock(path)
        if d is None:
            print(f"{sid}: 失敗（APIキーや画像を確認）")
            continue
        out[sid] = d.model_dump()
        print(f"{sid}: {d.overall} / {', '.join(d.colors)} / {d.pattern}")
        catalog.DESCRIPTIONS_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"説明あり: {len(out)} / 60")
    if missing_images:
        print("画像が無い靴下:", " ".join(missing_images))


if __name__ == "__main__":
    asyncio.run(main("--all" in sys.argv))
