"""学習のときだけ使う、画像の水増し（データ拡張）。

入力も出力も preprocess.normalize で整えた画像（IMAGE_SIZE の正方形、白地に黒、モード L）。
最後にもう一度 normalize を通すので、本番の入力と同じ形のまま変化だけを足せる。

方針（印象の手がかりを壊さない）:
- 左右・上下の反転はしない（「と」は左右対称でなく、反転すると別の字になる）。
- 回転・傾き・縦横比は少しだけ（大きく傾けると「勢い」などの印象が変わる）。
- 線の太さは 1 ピクセル（256 の画像で）だけ太く・細くする（太さも印象の手がかりなので小さく）。
- 一部を消す（切り抜き）加工はしない（字の形が変わり、印象が変わる）。
- 「ぼかし・粗くする」加工を、くっきりした画像（フォント、アプリで書いた字）に多めにかける。
  くずし字は 28 × 28 を拡大したぼやけた画像なので、モデルが「ぼやけている＝くずし字」で
  見分けてしまうのを防ぐ（印象ではなく、データの出どころを覚えてしまうため）。

strength（0 で何もしない、1 がふつう、2 まで）: 数の少ないクラスの画像は何度も選ばれる
（balance.py）ので、同じ画像がそのまま繰り返されないよう、強めにかける。
"""

from __future__ import annotations

import math
import random

import numpy as np
from PIL import Image, ImageFilter

from .preprocess import IMAGE_SIZE, normalize

# くっきりした画像のデータ（ぼかし・粗くする加工を多めにかける）
SHARP_SOURCES = frozenset({"google_fonts", "local_fonts", "collect", "etl"})


class Augment:
    def __init__(self, rotate_deg: float = 5.0, shear: float = 0.08, aspect: float = 0.08,
                 stroke_p: float = 0.3, degrade_p_sharp: float = 0.5, degrade_p_other: float = 0.1,
                 blur_p: float = 0.2, ink_p: float = 0.5, noise_p: float = 0.2) -> None:
        self.rotate_deg, self.shear, self.aspect = rotate_deg, shear, aspect
        self.stroke_p, self.blur_p, self.ink_p, self.noise_p = stroke_p, blur_p, ink_p, noise_p
        self.degrade_p_sharp, self.degrade_p_other = degrade_p_sharp, degrade_p_other

    def __call__(self, image: Image.Image, source: str = "", strength: float = 1.0,
                 rng: random.Random | None = None) -> Image.Image:
        rng = rng or random
        s = max(0.0, min(strength, 2.0))
        if s == 0:
            return image
        image = self._geometry(image, s, rng)
        if rng.random() < self.stroke_p * min(s, 1.0):
            # 白地に黒なので、MinFilter で黒（線）が太り、MaxFilter で細る
            image = image.filter(ImageFilter.MinFilter(3) if rng.random() < 0.5 else ImageFilter.MaxFilter(3))
        degrade_p = self.degrade_p_sharp if source in SHARP_SOURCES else self.degrade_p_other
        if rng.random() < degrade_p * min(s, 1.0):
            image = self._degrade(image, rng)
        elif rng.random() < self.blur_p * min(s, 1.0):
            image = image.filter(ImageFilter.GaussianBlur(rng.uniform(0.5, 1.5)))
        image = self._ink(image, s, rng)
        # 本番と同じ形に整え直す（回転などで字の範囲が変わるため）
        return normalize(image)

    def _geometry(self, image: Image.Image, s: float, rng) -> Image.Image:
        angle = math.radians(rng.uniform(-1, 1) * self.rotate_deg * s)
        shear = rng.uniform(-1, 1) * self.shear * s
        sx = 1 + rng.uniform(-1, 1) * self.aspect * s
        sy = 1 / sx
        # 出力の座標 → 入力の座標 の変換（中心を軸に、回転・横方向の傾き・縦横比）
        cos, sin = math.cos(angle), math.sin(angle)
        a, b = cos / sx, (sin + shear * cos) / sx
        d, e = -sin / sy, (cos - shear * sin) / sy
        # 余白を広げてから回すと、字のはしが切れない（広げた画像の中心は IMAGE_SIZE）
        big = Image.new("L", (IMAGE_SIZE * 2, IMAGE_SIZE * 2), 255)
        big.paste(image, (IMAGE_SIZE // 2, IMAGE_SIZE // 2))
        center = IMAGE_SIZE
        c = center - a * center - b * center
        f = center - d * center - e * center
        return big.transform(big.size, Image.Transform.AFFINE, (a, b, c, d, e, f),
                             resample=Image.Resampling.BICUBIC, fillcolor=255)

    def _degrade(self, image: Image.Image, rng) -> Image.Image:
        # 小さくしてから戻す（くずし字の 28 × 28 に近い粗さまで）
        size = rng.randint(28, 96)
        small = image.resize((size, size), Image.Resampling.BOX)
        return small.resize(image.size, Image.Resampling.BICUBIC)

    def _ink(self, image: Image.Image, s: float, rng) -> Image.Image:
        """インクの濃さのむらと、紙のざらつき"""
        do_ink = rng.random() < self.ink_p
        do_noise = rng.random() < self.noise_p * min(s, 1.0)
        if not (do_ink or do_noise):
            return image
        ink = 1.0 - np.asarray(image, dtype=np.float32) / 255.0
        if do_ink:
            ink = np.clip(ink * rng.uniform(0.8, 1.0), 0, 1) ** rng.uniform(0.7, 1.4)
        if do_noise:
            np_rng = np.random.default_rng(rng.randrange(2**32))
            ink = np.clip(ink + np_rng.normal(0, 0.03, ink.shape).astype(np.float32), 0, 1)
        return Image.fromarray(np.uint8(np.round((1.0 - ink) * 255)), mode="L")
