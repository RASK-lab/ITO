"""ストロークから PNG を描く（LLM に渡す画像。クライアントからは画像を受け取らない）。"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .geometry.normalize import normalize_xy

SIZE = 512
MARGIN = 0.12
LINE_WIDTH = 14

# 画番号の色（11画まで見分けられるように）
PALETTE = [
    (214, 40, 40), (0, 114, 178), (0, 158, 115), (230, 159, 0), (204, 121, 167),
    (86, 180, 233), (120, 80, 40), (90, 90, 90), (140, 60, 200), (0, 140, 140), (180, 150, 0),
]


def _to_canvas(strokes: list[np.ndarray]) -> list[np.ndarray]:
    norm = normalize_xy([np.asarray(s, dtype=float)[:, :2] for s in strokes])
    inner = SIZE * (1 - 2 * MARGIN)
    return [(p - 0.5) * inner + SIZE / 2 for p in norm]


def _draw_line(d: ImageDraw.ImageDraw, p: np.ndarray, color, width: int) -> None:
    pts = [tuple(map(float, q)) for q in p]
    if len(pts) == 1:
        pts = pts * 2
    d.line(pts, fill=color, width=width, joint="curve")
    r = width / 2
    for x, y in (pts[0], pts[-1]):
        d.ellipse([x - r, y - r, x + r, y + r], fill=color)


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_plain(strokes: list[np.ndarray]) -> bytes:
    """白地に黒の素の画像（ブラインド判読用）。"""
    img = Image.new("RGB", (SIZE, SIZE), "white")
    d = ImageDraw.Draw(img)
    for p in _to_canvas(strokes):
        _draw_line(d, p, (20, 20, 20), LINE_WIDTH)
    return _png(img)


def render_numbered(strokes: list[np.ndarray]) -> bytes:
    """画ごとに色を変え、書き始めの位置に画番号を付けた画像（講評用）。"""
    img = Image.new("RGB", (SIZE, SIZE), "white")
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=26)
    pts = _to_canvas(strokes)
    for k, p in enumerate(pts):
        _draw_line(d, p, PALETTE[k % len(PALETTE)], LINE_WIDTH - 4)
    placed: list[tuple[float, float]] = []
    for k, p in enumerate(pts):
        sx, sy = float(p[0][0]), float(p[0][1])
        # 番号は書き始めの「手前」（進行方向の逆側）に置く。書き始めが近い画（都の 9 と 11 など）でも重なりにくい
        ahead = p[min(6, len(p) - 1)] - p[0]
        norm = float(np.hypot(*ahead))
        back = -ahead / norm if norm > 1e-6 else np.array([-0.7, -0.7])
        dist = 26.0
        for _ in range(6):
            x, y = sx + back[0] * dist, sy + back[1] * dist
            if all((x - a) ** 2 + (y - b) ** 2 >= 34 ** 2 for a, b in placed):
                break
            dist += 16
        x, y = min(max(x, 18), SIZE - 18), min(max(y, 18), SIZE - 18)
        placed.append((x, y))
        d.line([(sx, sy), (x, y)], fill=PALETTE[k % len(PALETTE)], width=2)
        label = str(k + 1)
        d.ellipse([x - 16, y - 16, x + 16, y + 16], fill="white", outline=PALETTE[k % len(PALETTE)], width=3)
        d.text((x, y), label, fill=(0, 0, 0), font=font, anchor="mm")
    return _png(img)
