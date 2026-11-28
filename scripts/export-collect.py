"""集めた学習データ（表 collect_samples）を、学習に使う形に書き出す。

くわしくは docs/collect.md の「書き出す」。Python の標準ライブラリだけで動く。

入力は次のどちらか:
  - 手元の SQLite（back/data/ito.sqlite3）
  - 本番の D1 から wrangler で取り出した JSON
      cd infra/cloudflare
      npx wrangler d1 execute ito-db --remote --json \
        --command "SELECT * FROM collect_samples" > collect.json

使い方（リポジトリの直下で）:
  python scripts/export-collect.py back/data/ito.sqlite3 out/collect
  python scripts/export-collect.py infra/cloudflare/collect.json out/collect

出力（out/collect/）:
  samples.jsonl  1 行に「と」1 つ。表の列に、線のデータ（drawing）を展開したもの
  summary.txt    指示 × 入力の種類ごとの件数、書いた人の数など（集まり具合の確認用）

画像（R2 の collect/<id>_256.png など）は書き出さない。線のデータから描き直せるため
（学習では、線の太さをそろえて描き直す予定。docs/collect.md）。
"""

import argparse
import collections
import json
import sqlite3
import sys
from pathlib import Path


def load_rows(source: Path) -> list[dict]:
    if source.suffix == ".json":
        data = json.loads(source.read_text(encoding="utf-8"))
        # wrangler の --json は [{"results": [...], "success": true, "meta": {...}}]
        if isinstance(data, list) and data and isinstance(data[0], dict) and "results" in data[0]:
            return [row for part in data for row in part["results"]]
        return data
    connection = sqlite3.connect(source)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute("SELECT * FROM collect_samples ORDER BY created_at")]
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path, help="ito.sqlite3 か、wrangler で取り出した JSON")
    parser.add_argument("out", type=Path, help="書き出すフォルダ")
    args = parser.parse_args()

    rows = load_rows(args.source)
    args.out.mkdir(parents=True, exist_ok=True)

    counts: collections.Counter = collections.Counter()
    writers: set[str] = set()
    with (args.out / "samples.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            sample = dict(row)
            # 線のデータは、/api/drawings の線のデータと同じ形（target, canvas, strokes）
            sample["drawing"] = json.loads(sample.pop("strokes_json"))
            sample["consent_show"] = bool(sample["consent_show"])
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
            counts[(sample["protocol"], sample["condition"], sample["pointer_type"])] += 1
            writers.add(sample["writer_id"])

    lines = [f"件数: {len(rows)}", f"書いた人（writer_id）の数: {len(writers)}", "",
             "集め方\t指示\t入力\t件数"]
    lines += [f"{p}\t{c}\t{t}\t{n}" for (p, c, t), n in sorted(counts.items())]
    (args.out / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
