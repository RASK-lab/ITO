"""KanjiVG の SVG からお手本の点列 JSON を生成する。

実行（back/ で）:
    python -m src.judge.tools.build_refs

出力: src/judge/refs/<文字>.json
KanjiVG (https://kanjivg.tagaini.net/) は CC BY-SA 3.0。
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from svgpathtools import parse_path

KANJIVG_RAW = "https://raw.githubusercontent.com/KanjiVG/kanjivg/master/kanji/{code}.svg"
REFS_DIR = Path(__file__).resolve().parent.parent / "refs"
VIEWBOX = 109.0
SAMPLES = 64

# お題の「と」6字
TARGETS = ["十", "都", "戸", "徒", "ト", "と"]

SVG_NS = "{http://www.w3.org/2000/svg}"
KVG_TYPE = "{http://kanjivg.tagaini.net}type"


def code_of(ch: str) -> str:
    return f"{ord(ch):05x}"


def fetch_svg(code: str) -> str:
    with urllib.request.urlopen(KANJIVG_RAW.format(code=code), timeout=30) as res:
        return res.read().decode("utf-8")


def sample_path(d: str, n: int = SAMPLES) -> list[list[float]]:
    """SVG パスを弧長で等間隔に n 点サンプリングし、0〜1 に正規化する。"""
    path = parse_path(d)
    ts = np.linspace(0.0, 1.0, 400)
    dense = np.array([[path.point(t).real, path.point(t).imag] for t in ts])
    seg = np.linalg.norm(np.diff(dense, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    targets = np.linspace(0.0, cum[-1], n)
    xs = np.interp(targets, cum, dense[:, 0])
    ys = np.interp(targets, cum, dense[:, 1])
    pts = np.stack([xs, ys], axis=1) / VIEWBOX
    return [[round(float(x), 5), round(float(y), 5)] for x, y in pts]


def parse_strokes(svg_text: str, code: str) -> list[dict]:
    root = ET.fromstring(svg_text)
    pattern = re.compile(rf"kvg:{code}-s(\d+)$")
    strokes = []
    for el in root.iter(f"{SVG_NS}path"):
        m = pattern.match(el.get("id", ""))
        if not m:
            continue
        strokes.append({
            "index": int(m.group(1)),
            "kvg_type": el.get(KVG_TYPE, ""),
            "points": sample_path(el.get("d", "")),
        })
    strokes.sort(key=lambda s: s["index"])
    return strokes


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    REFS_DIR.mkdir(parents=True, exist_ok=True)
    for ch in TARGETS:
        code = code_of(ch)
        strokes = parse_strokes(fetch_svg(code), code)
        out = {
            "char": ch,
            "code": code,
            "source": "KanjiVG (CC BY-SA 3.0)",
            "variants": [{"name": "kanjivg", "strokes": strokes}],
        }
        path = REFS_DIR / f"{code}.json"
        path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        types = " ".join(s["kvg_type"] or "?" for s in strokes)
        print(f"{ch} ({code}): {len(strokes)} strokes  types: {types}")


if __name__ == "__main__":
    main()
