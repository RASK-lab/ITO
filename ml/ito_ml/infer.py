"""学習したモデル（ONNX）で推論する。本番の CPU で動かす形（PyTorch は要らない）。

要るもの: onnxruntime、numpy、pillow（と、この ito_ml/preprocess.py）

    from ito_ml.infer import ImpressionModel
    model = ImpressionModel("ml/runs/<日時>/model.onnx")   # 隣の model.json も読む
    model.predict(Image.open("drawing.png"))
    # → {"label": "kawaii", "probs": {"kawaii": 0.61, ...}, "preprocess": "v1"}

- 入力の画像は何でもよい（色付き・透明・暗い地でも）。preprocess.normalize で学習と同じ形にする。
- 本番のサーバーは vCPU 1/4 なので、計算に使うスレッドは 1 つにしている（threads で変えられる）。
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from .preprocess import PREPROCESS_VERSION, normalize


def softmax(logits: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    z = logits / temperature
    z = z - z.max(-1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(-1, keepdims=True)


class ImpressionModel:
    def __init__(self, onnx_path: str | Path, threads: int = 1) -> None:
        import onnxruntime as ort

        onnx_path = Path(onnx_path)
        self.meta = json.loads(onnx_path.with_suffix(".json").read_text(encoding="utf-8"))
        if self.meta["preprocess"] != PREPROCESS_VERSION:
            raise ValueError(f"前処理の版が違います（モデル {self.meta['preprocess']}、いま {PREPROCESS_VERSION}）")
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(onnx_path), options, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.classes: list[str] = self.meta["classes"]

    @staticmethod
    def to_input(image: Image.Image) -> np.ndarray:
        """どんな画像も、モデルの入力（1×1×256×256、0〜1、白地に黒）にする"""
        x = np.asarray(normalize(image), dtype=np.float32) / 255.0
        return x[None, None]

    def logits(self, x: np.ndarray) -> np.ndarray:
        return self.session.run(None, {self.input_name: x.astype(np.float32)})[0]

    def predict(self, image: Image.Image) -> dict:
        p = softmax(self.logits(self.to_input(image)), self.meta.get("temperature", 1.0))[0]
        return {"label": self.classes[int(p.argmax())],
                "probs": {c: round(float(v), 4) for c, v in zip(self.classes, p)},
                "preprocess": PREPROCESS_VERSION}
