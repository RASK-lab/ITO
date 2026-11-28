"""くずし字（Kuzushiji-49）の「と」を学習データにする。

使い方（リポジトリの直下で）: python ml/tools/fetch_kuzushiji.py

- データ: Kuzushiji-49（ROIS-DS 人文学オープンデータ共同利用センター）。
  https://github.com/rois-codh/kmnist 。ライセンスは CC BY-SA 4.0（出典の表示が必要。
  作ったデータを配るときは同じライセンスにする）。
  出典: 「KMNISTデータセット」（CODH作成）『日本古典籍くずし字データセット』（国文研ほか所蔵）を翻案、
  doi:10.20676/00000341
- 「と」は 7,000 枚（学習用 6,000、テスト用 1,000）。28 × 28 の灰色の画像で、
  黒地に白い字。ここで 256 に拡大するので、ぼやける。
- 古典籍の筆の字で、元になった漢字が違う、いまの「と」と形の違う字（変体仮名）も
  混ざっている。現代の手書きとは見た目がかなり違うので、ラベル付けは後回しにしてある
  （labeling/config.json の source_priority）。
- 書いた人の情報は無いので、1 枚ごとに別のまとまり（group）にする。
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ito_ml.manifest import SOURCES_DIR, Item, make_id, save_image, write_manifest  # noqa: E402
from ito_ml.preprocess import normalize  # noqa: E402

SOURCE = "kuzushiji49"
BASE_URL = "http://codh.rois.ac.jp/kmnist/dataset/k49/"
FILES = ["k49-train-imgs.npz", "k49-train-labels.npz", "k49-test-imgs.npz", "k49-test-labels.npz",
         "k49_classmap.csv"]
LICENSE = ("CC BY-SA 4.0。「KMNISTデータセット」（CODH作成）『日本古典籍くずし字データセット』"
           "（国文研ほか所蔵）を翻案、doi:10.20676/00000341")


def download() -> Path:
    folder = SOURCES_DIR / SOURCE
    folder.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        path = folder / name
        if not path.exists():
            print(f"ダウンロード: {name}")
            with urllib.request.urlopen(BASE_URL + name, timeout=300) as response:
                path.write_bytes(response.read())
    return folder


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    folder = download()
    classmap = (folder / "k49_classmap.csv").read_text(encoding="utf-8").splitlines()[1:]
    target = next(int(row.split(",")[0]) for row in classmap if row.split(",")[2] == "と")
    items: list[Item] = []
    for split in ("train", "test"):
        images = np.load(folder / f"k49-{split}-imgs.npz")["arr_0"]
        labels = np.load(folder / f"k49-{split}-labels.npz")["arr_0"]
        for index in np.nonzero(labels == target)[0]:
            item_id = make_id("k49", split, int(index))
            image = normalize(Image.fromarray(images[index]))
            items.append(Item(
                id=item_id, source=SOURCE, image=save_image(SOURCE, item_id, image),
                group=f"k49:{split}:{int(index)}", kind="classical", license=LICENSE,
                meta={"k49_split": split, "k49_index": int(index), "original_size": 28},
            ))
    path = write_manifest(SOURCE, items)
    print(f"「と」{len(items)} 枚 → {path}")


if __name__ == "__main__":
    main()
