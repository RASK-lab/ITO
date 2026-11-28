"""画像の前処理（学習データと本番の推論で、必ず同じものを使う）。

印象の分類モデルは、この関数で整えた画像だけを見る。学習データ（フォント・公開データ・
集めた手書き）も、本番で利用者が書いた「と」も、ここを通してから使う。
ここを変えたら PREPROCESS_VERSION を上げ、画像を作り直して学習し直す。

整え方（v1）:
1. 白黒 1 チャネルにする。背景が暗い画像（ETL、くずし字など）は白黒を反転し、
   「白地に黒い字」にそろえる。背景は画像の外周の明るさで判断する。
2. 字の部分（インクのある範囲）だけを切り出す。位置と大きさの違いを消すため。
3. 縦横の比を保ったまま、余白（MARGIN）をつけた正方形に置く。
4. IMAGE_SIZE × IMAGE_SIZE に縮小（拡大）する。

線の太さ・かすれ・筆の形は消さない（印象の手がかりなので）。本番では、利用者が
選ぶブラシと太さで描いた画像を、そのままこの関数に通す。
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont

PREPROCESS_VERSION = "v1"

# 整えたあとの画像の一辺（ピクセル）
IMAGE_SIZE = 256
# 字のまわりの余白（字の長いほうの辺に対する割合。片側）
MARGIN = 0.12
# この濃さ（0〜1。1 が真っ黒）を超える画素を「インク」とみなして、字の範囲を決める
INK_THRESHOLD = 0.25


def ink_array(image: Image.Image) -> np.ndarray:
    """インクの濃さ（0〜1。1 が最も濃い）の 2 次元配列にする。背景の明暗は自動で判断する。"""
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        # 透明な部分は白地にする
        rgba = image.convert("RGBA")
        white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        image = Image.alpha_composite(white, rgba)
    gray = np.asarray(image.convert("L"), dtype=np.float32) / 255.0
    border = np.concatenate([gray[0], gray[-1], gray[:, 0], gray[:, -1]])
    # 外周が暗ければ「暗い地に明るい字」とみなして反転する
    ink = gray if np.median(border) < 0.5 else 1.0 - gray
    # 背景のむら（スキャンの地の色など）を 0 に寄せる
    background = float(np.median(np.concatenate([ink[0], ink[-1], ink[:, 0], ink[:, -1]])))
    if background > 0:
        ink = np.clip((ink - background) / max(1.0 - background, 1e-6), 0.0, 1.0)
    return ink


def normalize(image: Image.Image) -> Image.Image:
    """学習と推論に使う形（IMAGE_SIZE の正方形、白地に黒、モード L）に整える。"""
    ink = ink_array(image)
    ys, xs = np.nonzero(ink > INK_THRESHOLD)
    if len(xs) == 0:
        # 何も書かれていない
        return Image.new("L", (IMAGE_SIZE, IMAGE_SIZE), 255)
    crop = ink[ys.min(): ys.max() + 1, xs.min(): xs.max() + 1]
    h, w = crop.shape
    side = int(round(max(h, w) * (1 + 2 * MARGIN)))
    canvas = np.zeros((side, side), dtype=np.float32)
    top, left = (side - h) // 2, (side - w) // 2
    canvas[top: top + h, left: left + w] = crop
    out = Image.fromarray(np.uint8(np.round((1.0 - canvas) * 255)), mode="L")
    # BICUBIC: 縁がぼやけにくく、白地に余計な波が出にくい（back/src/drawings.py と同じ考え）
    return out.resize((IMAGE_SIZE, IMAGE_SIZE), Image.Resampling.BICUBIC)


def render_font(path: str, char: str = "と", size: int = 512, index: int = 0) -> Image.Image | None:
    """フォントで 1 文字を描く（白地に黒）。その字がフォントに無ければ None。

    index: .ttc（複数の書体が入ったファイル）の書体の番号
    """
    font = ImageFont.truetype(str(path), size, index=index)
    canvas = size * 2
    image = Image.new("L", (canvas, canvas), 255)
    ImageDraw.Draw(image).text((canvas // 2, canvas // 2), char, font=font, fill=0, anchor="mm")
    if np.asarray(image).min() == 255:
        return None
    # 字が無いフォントは、代わりの記号（□ など）を描く。私用領域の字と同じ形なら「無い」とみなす
    missing = Image.new("L", (canvas, canvas), 255)
    ImageDraw.Draw(missing).text((canvas // 2, canvas // 2), "\U000f0000", font=font, fill=0, anchor="mm")
    if np.array_equal(np.asarray(image), np.asarray(missing)):
        return None
    return image


def render_strokes(strokes: list[dict], canvas_size: float, width_ratio: float = 0.02,
                   image_size: int = 1024) -> Image.Image:
    """線のデータ（/api/drawings、/api/collect と同じ形）を、一定の太さで描く。

    いまのアプリの線（筆圧で太さが変わる）とは少し違う。アプリでブラシを選べるように
    なったら、本番と同じ描き方に合わせる。
    """
    scale = image_size / canvas_size
    width = max(1, int(round(image_size * width_ratio)))
    image = Image.new("L", (image_size, image_size), 255)
    draw = ImageDraw.Draw(image)
    for stroke in strokes:
        pts = [(p[0] * scale, p[1] * scale) for p in stroke["points"]]
        if len(pts) > 1:
            draw.line(pts, fill=0, width=width, joint="curve")
        r = width / 2
        for x, y in (pts[0], pts[-1]):
            draw.ellipse((x - r, y - r, x + r, y + r), fill=0)
    return image
