"""学習データまわりのテスト。リポジトリの直下で: python -m pytest ml/tests"""

import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ML = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ML))
sys.path.insert(0, str(ML / "tools"))
sys.path.insert(0, str(ML.parent / "back"))

from ito_ml.preprocess import IMAGE_SIZE, normalize, render_strokes  # noqa: E402


def _drawing(dark_background: bool) -> Image.Image:
    bg, fg = (0, 255) if dark_background else (255, 0)
    image = Image.new("L", (200, 120), bg)
    ImageDraw.Draw(image).rectangle((20, 30, 60, 90), fill=fg)
    return image


def test_normalize_crops_centers_and_fixes_polarity():
    for dark in (False, True):
        out = np.asarray(normalize(_drawing(dark)))
        assert out.shape == (IMAGE_SIZE, IMAGE_SIZE)
        assert out[0, 0] == 255 and out[IMAGE_SIZE // 2, IMAGE_SIZE // 2] == 0  # 白地に黒、字は中央
        ys, xs = np.nonzero(out < 128)
        # 縦長の四角は、縦がほぼ枠いっぱい（余白の分だけ小さい）
        assert 0.7 < (ys.max() - ys.min()) / IMAGE_SIZE < 0.8


def test_blank_image_stays_blank():
    assert np.asarray(normalize(Image.new("L", (50, 50), 255))).min() == 255


def test_render_strokes():
    strokes = [{"pointerType": "mouse", "points": [[100, 100, 0, 0.5], [900, 900, 50, 0.5]]}]
    out = np.asarray(normalize(render_strokes(strokes, 1024)))
    assert out.min() == 0


def test_etl8g_record_is_parsed(tmp_path):
    import import_etl

    fmt = ">2H8sI4B4H2B30x8128s11x"
    # 字の部分だけ明るい（ETL と同じく、暗い地に明るい字）16 階調の画像
    pixels = np.zeros((127, 128), dtype=np.uint8)
    pixels[30:90, 40:80] = 15
    packed = ((pixels.flatten()[0::2] << 4) | pixels.flatten()[1::2]).astype(np.uint8).tobytes()
    to = struct.pack(fmt, 7, 0x2448, b"A.TO    ", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, packed)
    other = struct.pack(fmt, 7, 0x2422, b"A.A     ", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, packed)
    path = tmp_path / "ETL8G_01"
    path.write_bytes(other + to)
    found = import_etl.parse(path, *import_etl.FORMATS[0])
    assert [sheet for sheet, _ in found] == ["7"]
    out = np.asarray(normalize(found[0][1]))
    assert out[0, 0] == 255 and out[IMAGE_SIZE // 2, IMAGE_SIZE // 2] < 50


def test_split_is_stable_and_by_group():
    import export_dataset

    assert export_dataset.split_of("gf:Noto Sans JP") == export_dataset.split_of("gf:Noto Sans JP")
    splits = [export_dataset.split_of(f"g{i}") for i in range(2000)]
    assert 0.75 < splits.count("train") / 2000 < 0.85


def test_fleiss_kappa():
    from src import labeling_core

    cats = ["a", "b"]
    assert labeling_core.fleiss_kappa([{"a": 4}, {"b": 4}, {"a": 4}], cats) == 1.0
    assert labeling_core.fleiss_kappa([{"a": 1}], cats) is None
