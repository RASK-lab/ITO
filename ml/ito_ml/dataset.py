"""書き出した学習データ（tools/export_dataset.py）を読む。

- load_rows と ImageSet: 学習（tools/train.py）で使う。
- ToDataset: 自分で学習を書くときの簡単な例。

    from ito_ml.dataset import ToDataset
    train = ToDataset("ml/data/export/20261128-200000", split="train")
    image, target = train[0]   # image: 1×256×256 の float（0〜1。白地に黒）、target: クラスの番号

- soft=True にすると、target は人数の割合（やわらかいラベル。合計 1）になる。
  4 人の意見が割れた画像の情報も使える。
- 「「と」に見えない」が過半数の画像と、クラスのラベルが 1 つも無い画像は除く。
- 推論のときは、利用者の画像を ito_ml.preprocess.normalize に通してから、同じ形にする。
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from PIL import Image

from .manifest import DATA_DIR


class ToDataset:
    def __init__(self, export_dir: str | Path, split: str | None = None, soft: bool = False,
                 transform=None) -> None:
        export_dir = Path(export_dir)
        meta = json.loads((export_dir / "meta.json").read_text(encoding="utf-8"))
        self.classes = [c["key"] for c in meta["classes"]]
        # 画像を写して書き出したときは書き出したフォルダ、そうでなければ ml/data からの相対パス
        self.root = export_dir if meta.get("images_copied") else DATA_DIR
        self.soft, self.transform = soft, transform
        self.rows = []
        with (export_dir / "dataset.csv").open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if split and row["split"] != split:
                    continue
                votes = np.array([int(row[f"votes_{c}"]) for c in self.classes], dtype=np.float32)
                if int(row["n_invalid"]) * 2 > int(row["n_ratings"]) or votes.sum() == 0:
                    continue
                if not soft and not row["label"]:
                    continue  # 多数決で決まらなかった画像
                self.rows.append((row["image"], votes / votes.sum(), row["label"]))

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int):
        import torch

        path, soft, label = self.rows[index]
        image = np.asarray(Image.open(self.root / path).convert("L"), dtype=np.float32) / 255.0
        x = torch.from_numpy(image)[None]
        if self.transform is not None:
            x = self.transform(x)
        y = torch.from_numpy(soft) if self.soft else self.classes.index(label)
        return x, y


def load_rows(export_dir: str | Path) -> tuple[list[dict], list[str]]:
    """学習に使う行と、クラスの一覧。

    1 行: {"id", "path"（画像の絶対パス）, "source", "group", "split", "y"（クラスの番号）}
    - 多数決のラベル（label）がクラスの画像だけ。「どれとも言えない」「「と」に見えない」と、
      意見が割れて決まらなかった画像は使わない。
    """
    export_dir = Path(export_dir)
    meta = json.loads((export_dir / "meta.json").read_text(encoding="utf-8"))
    classes = [c["key"] for c in meta["classes"]]
    root = export_dir if meta.get("images_copied") else DATA_DIR
    rows = []
    with (export_dir / "dataset.csv").open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["label"] not in classes or int(row["n_invalid"]) * 2 > int(row["n_ratings"]):
                continue
            rows.append({"id": row["id"], "path": str(root / row["image"]), "source": row["source"],
                         "group": row["group"], "split": row["split"], "y": classes.index(row["label"])})
    return rows, classes


class ImageSet:
    """PyTorch の Dataset として使う（torch を import しないので、ここでは継承しない）。

    返すもの: (画像 1×256×256 の float（0〜1、白地に黒）, クラスの番号, 行の番号)
    augment: augment.Augment（学習のときだけ）。strength: 1 枚ごとの水増しの強さ（balance.py）
    """

    def __init__(self, rows: list[dict], augment=None, strength=None) -> None:
        self.rows, self.augment, self.strength = rows, augment, strength

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int):
        import random

        import torch

        row = self.rows[index]
        with Image.open(row["path"]) as image:
            image = image.convert("L")
        if self.augment is not None:
            s = 1.0 if self.strength is None else float(self.strength[index])
            image = self.augment(image, row["source"], s, random)
        x = torch.from_numpy(np.asarray(image, dtype=np.float32) / 255.0)[None]
        return x, row["y"], index
