"""保存した検証サンプル（eval_data/*.json）から特徴量の平均・標準偏差を計算し、
analysis/population.json に書き出す。速さ系の特徴量は入力機器ごとにも計算する。

実行（back/ で）:
    python -m src.judge.tools.build_population
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from ..analysis import population
from ..analysis.axes import DEVICE_DEPENDENT

EVAL_DIR = Path(__file__).resolve().parents[2] / "eval_data"
MIN_SAMPLES = 8


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    # 確認ページで保存したサンプル（eval_data/*.json）と、DEV=1 で自動記録した判定（eval_data/requests/*.json）
    files = sorted(EVAL_DIR.glob("*.json")) + sorted((EVAL_DIR / "requests").glob("*.json"))
    values: dict[str, list[float]] = defaultdict(list)
    for f in files:
        s = json.loads(f.read_text(encoding="utf-8"))
        feats = s["analysis"]["features"]
        types = [st["pointerType"] for st in s["request"]["strokes"]]
        device = max(set(types), key=types.count)
        for k, v in feats.items():
            if v is None or k not in population.DEFAULTS:
                continue
            values[k].append(v)
            if k in DEVICE_DEPENDENT:
                values[f"{k}@{device}"].append(v)
    out = {}
    for k, vs in values.items():
        if len(vs) >= MIN_SAMPLES:
            base = k.split("@")[0]
            floor = population.DEFAULTS[base][1] * 0.25  # 標準偏差が小さすぎると z 値が暴れるので下限を置く
            out[k] = [float(np.mean(vs)), float(max(np.std(vs), floor))]
    population.POPULATION_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"サンプル {len(files)} 件から {len(out)} 項目を書き出しました: {population.POPULATION_FILE}")
    for k, (m, s) in sorted(out.items()):
        print(f"  {k:22s} 平均 {m:8.3f}  標準偏差 {s:7.3f}")


if __name__ == "__main__":
    main()
