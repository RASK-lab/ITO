"""アプリで集めた手書きの「と」（#collect、表 collect_samples）を学習データにする。

使い方:
  1. 本番の D1 から書き出す（Cloudflare にログインできる人。ブランチ 010 の docs/collect.md）
       cd infra/cloudflare
       npx wrangler d1 execute ito-db --remote --json --command "SELECT * FROM collect_samples" > collect.json
       python scripts/export-collect.py infra/cloudflare/collect.json out/collect
  2. python ml/tools/import_collect.py out/collect/samples.jsonl

- 書いた人は全員、学習に使うことに同意している（同意がないと記録されない）。
- 画像は、線のデータから一定の太さで描き直す（preprocess.render_strokes）。
  アプリの線（筆圧で太さが変わる）とは少し違う。
- 集めたときの指示（「可愛く」など）は meta.instructed に入れる。ラベル付けの画面には出さない
  （見た人が感じた印象でラベルを付けるため）。指示とラベルの一致を、あとで比べられる。
- まとまり（group）は書いた人（writer_id）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ito_ml.manifest import Item, make_id, save_image, write_manifest  # noqa: E402
from ito_ml.preprocess import normalize, render_strokes  # noqa: E402

SOURCE = "collect"
LICENSE = "アプリの学習データ集め（#collect）。書いた人が学習への利用に同意。チームの外に配らない"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 2:
        print("使い方: python ml/tools/import_collect.py <samples.jsonl>")
        return
    items: list[Item] = []
    with open(sys.argv[1], encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            s = json.loads(line)
            drawing = s["drawing"]
            image = render_strokes(drawing["strokes"], drawing["canvas"]["width"])
            item_id = make_id("col", s["id"])
            items.append(Item(
                id=item_id, source=SOURCE, image=save_image(SOURCE, item_id, normalize(image)),
                group=f"col:{s['writer_id']}", kind="handwriting", license=LICENSE,
                meta={"collect_id": s["id"], "writer_id": s["writer_id"], "instructed": s["condition"],
                      "pointer_type": s["pointer_type"], "dominant_hand": s.get("dominant_hand"),
                      "calligraphy": s.get("calligraphy"), "protocol": s.get("protocol")},
            ))
    out = write_manifest(SOURCE, items)
    print(f"{len(items)} 件 → {out}")


if __name__ == "__main__":
    main()
