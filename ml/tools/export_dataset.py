"""ラベルを付けた画像を、学習に使う形に書き出す。

使い方（リポジトリの直下で）:
  python ml/tools/export_dataset.py                 # ml/data/export/<日時>/ に書き出す
  python ml/tools/export_dataset.py --copy-images   # 画像も写す（研究室の GPU などへ持っていくとき）

出力（ml/data/export/<日時>/）:
  dataset.csv     1 行に画像 1 枚（ラベルが 1 つ以上ある画像だけ）。列は下の COLUMNS
  labels_raw.csv  1 行にラベル 1 つ（画像、付けた人、ラベル、かかったミリ秒、日時）
  meta.json       ラベルの種類、前処理の版、件数、一致の度合い、データごとのライセンス
  images/         --copy-images のとき。dataset.csv の image はこのフォルダからの相対パス

dataset.csv の主な列:
- image: 画像のパス（--copy-images なしなら ml/data からの相対パス）
- split: train / val / test（group ごとに分ける。同じフォント・同じ人の字は同じ側。毎回同じ結果）
- votes_<ラベル>: そのラベルを選んだ人数。人数の割合を、そのまま「やわらかいラベル」として使える
- label: 多数決のラベル。同数のとき・「どれとも言えない」が最多のときは空
- agreement: 最多のラベルの人数 ÷ 付けた人数
- n_invalid: 「「と」に見えない」の人数。学習では、これが過半数の画像を除くとよい
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ito_ml.manifest import DATA_DIR, ML_DIR, load_items  # noqa: E402
from ito_ml.preprocess import IMAGE_SIZE, PREPROCESS_VERSION  # noqa: E402

CONFIG_PATH = ML_DIR / "labeling" / "config.json"
DB_PATH = DATA_DIR / "labels.sqlite3"
# 学習・検証・テストの割合
SPLITS = (("train", 0.8), ("val", 0.1), ("test", 0.1))


def split_of(group: str) -> str:
    """group から決まる分け方（ハッシュで決めるので、データが増えても既存の画像の側は変わらない）"""
    x = int(hashlib.sha1(group.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
    acc = 0.0
    for name, ratio in SPLITS:
        acc += ratio
        if x < acc:
            return name
    return SPLITS[-1][0]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--copy-images", action="store_true")
    args = parser.parse_args()

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    classes = [c["key"] for c in config["classes"]]
    keys = classes + [c["key"] for c in config["special"]]
    items = {i["id"]: i for i in load_items()}
    with sqlite3.connect(DB_PATH) as connection:
        rows = connection.execute(
            "SELECT item_id, rater, label, ms, created_at FROM labels WHERE label_set = ? ORDER BY created_at",
            (config["label_set"],)).fetchall()
    votes: dict[str, Counter] = {}
    for item_id, _, label, _, _ in rows:
        votes.setdefault(item_id, Counter())[label] += 1

    out = DATA_DIR / "export" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True)
    with (out / "labels_raw.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["item_id", "rater", "label", "ms", "created_at"])
        w.writerows(rows)

    columns = (["id", "image", "source", "kind", "group", "split", "n_ratings"]
               + [f"votes_{k}" for k in keys] + ["label", "agreement", "n_invalid", "license", "meta"])
    counts = Counter()
    with (out / "dataset.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(columns)
        for item_id, v in votes.items():
            item = items.get(item_id)
            if item is None:
                continue  # 台帳から消えた画像
            n = sum(v.values())
            top = v.most_common()
            best, best_n = top[0]
            tie = len(top) > 1 and top[1][1] == best_n
            label = best if best in classes and not tie else ""
            image = item["image"]
            if args.copy_images:
                dest = out / "images" / Path(image).relative_to("images")
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(DATA_DIR / image, dest)
                image = dest.relative_to(out).as_posix()
            split = split_of(item["group"])
            w.writerow([item_id, image, item["source"], item["kind"], item["group"], split, n]
                       + [v.get(k, 0) for k in keys]
                       + [label, round(best_n / n, 3), v.get("invalid", 0), item["license"],
                          json.dumps(item["meta"], ensure_ascii=False)])
            counts[(item["source"], split, label or "（未定）")] += 1

    meta = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "label_set": config["label_set"], "question": config["question"],
        "classes": config["classes"], "special": config["special"],
        "preprocess": {"version": PREPROCESS_VERSION, "image_size": IMAGE_SIZE,
                       "note": "ml/ito_ml/preprocess.py の normalize。本番の推論でも同じものを使う"},
        "n_items": len(votes), "n_ratings": len(rows),
        "counts": [{"source": s, "split": sp, "label": lb, "n": n} for (s, sp, lb), n in sorted(counts.items())],
        "licenses": sorted({items[i]["license"] for i in votes if i in items}),
        "images_copied": args.copy_images,
    }
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"画像 {len(votes)} 枚、ラベル {len(rows)} 個 → {out}")
    for (s, sp, lb), n in sorted(counts.items()):
        print(f"  {s}\t{sp}\t{lb}\t{n}")


if __name__ == "__main__":
    main()
