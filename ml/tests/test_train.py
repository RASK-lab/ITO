"""学習まわりのテスト。リポジトリの直下で: python -m pytest ml/tests

torch・timm・onnxruntime が無ければ、その部分は飛ばす（ml/requirements-train.txt）。
本物のラベル・データベースは使わない（その場で作った画像と、でたらめのラベルで動かす）。
"""

import csv
import json
import random
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

ML = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ML))

from ito_ml import balance, metrics  # noqa: E402
from ito_ml.augment import Augment  # noqa: E402
from ito_ml.preprocess import IMAGE_SIZE, normalize  # noqa: E402


def _glyph(seed: int) -> Image.Image:
    r = random.Random(seed)
    image = Image.new("L", (300, 300), 255)
    draw = ImageDraw.Draw(image)
    for _ in range(3):
        draw.line([(r.randint(40, 260), r.randint(40, 260)) for _ in range(3)], fill=0, width=r.randint(6, 30))
    return normalize(image)


def test_augment_keeps_the_form():
    image = _glyph(0)
    aug = Augment()
    rng = random.Random(1)
    for strength in (0.5, 1.0, 2.0):
        for source in ("google_fonts", "kuzushiji49"):
            out = np.asarray(aug(image, source, strength, rng))
            assert out.shape == (IMAGE_SIZE, IMAGE_SIZE)
            assert out[0, 0] > 200 and out.min() < 80  # 白地に黒のまま、字が残る
    assert aug(image, "x", 0.0, rng) is image  # 強さ 0 なら何もしない


def test_augment_never_flips():
    # 左右で形の違う画像は、水増ししても左右が入れ替わらない（左側が重いまま）
    image = Image.new("L", (300, 300), 255)
    ImageDraw.Draw(image).rectangle((20, 20, 120, 280), fill=0)
    ImageDraw.Draw(image).line((120, 150, 280, 150), fill=0, width=6)
    image = normalize(image)
    rng = random.Random(0)
    for _ in range(20):
        ink = 255 - np.asarray(Augment()(image, "google_fonts", 2.0, rng), dtype=np.float32)
        half = IMAGE_SIZE // 2
        assert ink[:, :half].sum() > ink[:, half:].sum()


def test_balance():
    labels = [0] * 90 + [1] * 9 + [2] * 1
    sources = ["a"] * 100
    w = balance.sample_weights(labels, sources, class_power=1.0, source_power=0.0)
    per_class = [w[np.array(labels) == c].sum() for c in range(3)]
    assert np.allclose(per_class, 1 / 3)  # 各クラスが同じ割合で選ばれる
    s = balance.augment_strength(labels)
    assert s[0] == 1.0 and s[-1] > s[90] > s[0]  # 少ないクラスほど水増しが強い
    cw = balance.class_weights(labels, 4)
    assert cw[3] == 0 and cw[2] > cw[1] > cw[0]


def test_metrics_ignore_accuracy_trap():
    # 多いクラスだけ答えるモデルは、正解率は高いが macro-F1 は低い
    y = [0] * 90 + [1] * 10
    r = metrics.scores(y, [0] * 100, 2)
    assert r["accuracy"] == 0.9 and r["balanced_accuracy"] == 0.5 and r["macro_f1"] < 0.5


def _fake_export(root: Path) -> Path:
    """その場で作った画像と、でたらめで偏ったラベルの書き出し（export_dataset.py と同じ形）"""
    images = root / "images"
    images.mkdir(parents=True)
    classes = [{"key": k, "label": k} for k in ("kawaii", "kakkoii", "teinei", "koseiteki")]
    rng = random.Random(0)
    weights = [0.6, 0.25, 0.1, 0.05]
    with (root / "dataset.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "image", "source", "group", "split", "n_ratings", "label", "n_invalid"])
        for i in range(60):
            _glyph(i).save(images / f"{i}.png")
            label = rng.choices([c["key"] for c in classes], weights)[0]
            source = "google_fonts" if i % 3 else "kuzushiji49"
            split = ["train"] * 6 + ["val", "val", "test", "test"]
            w.writerow([str(i), f"images/{i}.png", source, f"g{i}", split[i % 10], 1, label, 0])
    (root / "meta.json").write_text(json.dumps({"classes": classes, "label_set": "test", "images_copied": True}),
                                    encoding="utf-8")
    return root


def test_fit_exports_onnx_and_predicts(tmp_path, monkeypatch):
    pytest.importorskip("torch")
    pytest.importorskip("timm")
    pytest.importorskip("onnxruntime")
    import train  # ml/tools/train.py

    export = _fake_export(tmp_path / "export")
    monkeypatch.setattr(train, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(sys, "argv", ["train.py", "fit", "--export", str(export), "--backbone", "resnet18",
                                      "--no-pretrained", "--epochs", "1", "--unfreeze", "1", "--batch", "8",
                                      "--workers", "0", "--views", "1", "--head-epochs", "2", "--device", "cpu"])
    train.main()
    run = next((tmp_path / "runs").glob("*-fit-resnet18"))
    meta = json.loads((run / "model.json").read_text(encoding="utf-8"))
    assert meta["check"]["same_argmax"] == 1.0  # ONNX と PyTorch で答えが同じ
    from ito_ml.infer import ImpressionModel

    result = ImpressionModel(run / "model.onnx").predict(Image.new("RGB", (400, 300), "white"))
    assert result["label"] in meta["classes"] and abs(sum(result["probs"].values()) - 1) < 1e-3


sys.path.insert(0, str(ML / "tools"))
