"""同じ画像（見た目で区別できない画像）を見つけて、1 枚だけ残す。

同じ字形が別の名前で入っていることがある（例: M PLUS 1 と M PLUS 2、Shippori Mincho と
Shippori Mincho B1、BIZ UDGothic と BIZ UDPGothic（文字の幅だけが違う））。
残すと、同じ画像に何度もラベルを付けることになり、学習と評価の両方に同じ画像が入ってしまう。

- 前処理した画像（ml/data/images）を 64 × 64 に縮め、画素の差の二乗平均の平方根（0〜1）で比べる。
- THRESHOLD より近い画像を同じとみなす。2026-11-28 のデータでは、同じ字形どうしは 0.010 以下、
  別の字形でいちばん近いもの（M PLUS 1p と M PLUS Rounded 1c の 300）は 0.020 だった。
- 同じものの中では、group の名前が短いもの（元のフォント。"B1"、"P"、"Code" などが付かないほう）を残す。
- 結果は ml/data/duplicates.json（{除いた画像の id: 残した画像の id}）に書き、load_items がそれを見て除く。
"""

from __future__ import annotations

import json

import numpy as np
from PIL import Image

from .manifest import DATA_DIR, DUPLICATES_PATH, load_items

THRESHOLD = 0.015
SIZE = 64
CHUNK = 500


def _vectors(items: list[dict]) -> np.ndarray:
    rows = []
    for item in items:
        with Image.open(DATA_DIR / item["image"]) as image:
            small = image.convert("L").resize((SIZE, SIZE), Image.Resampling.BOX)
        rows.append(np.asarray(small, dtype=np.float32).ravel() / 255)
    return np.stack(rows)


def find_duplicates(items: list[dict], threshold: float = THRESHOLD) -> dict[str, str]:
    """{除く画像の id: 残す画像の id}"""
    if len(items) < 2:
        return {}
    # 残したいものが前に来るように並べる
    items = sorted(items, key=lambda i: (len(i["group"]), i["group"], i["id"]))
    x = _vectors(items)
    sq = (x * x).sum(1)
    parent = list(range(len(items)))

    def root(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for start in range(0, len(items), CHUNK):
        d2 = sq[start:start + CHUNK, None] + sq[None, :] - 2 * x[start:start + CHUNK] @ x.T
        rms = np.sqrt(np.maximum(d2, 0) / x.shape[1])
        for a, b in zip(*np.nonzero(rms < threshold)):
            a += start
            if a < b:
                ra, rb = root(a), root(b)
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)  # 前（残したいほう）を根にする
    return {items[i]["id"]: items[root(i)]["id"] for i in range(len(items)) if root(i) != i}


def update_duplicates() -> dict[str, str]:
    """すべての画像で調べ直し、ml/data/duplicates.json に書く。"""
    found = find_duplicates(load_items(include_duplicates=True))
    DUPLICATES_PATH.write_text(json.dumps(found, ensure_ascii=False, indent=1), encoding="utf-8")
    return found
