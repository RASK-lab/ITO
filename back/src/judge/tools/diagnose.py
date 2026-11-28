"""記録した判定（eval_data/requests/）を集計し、印象・品質の偏りの原因を調べる。

実行（back/ で）:
    python -m src.judge.tools.diagnose
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

from ..analysis import axes, population

EVAL_DIR = Path(__file__).resolve().parents[2] / "eval_data"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    files = sorted((EVAL_DIR / "requests").glob("*.json")) + sorted(EVAL_DIR.glob("*.json"))
    rows = [json.loads(f.read_text(encoding="utf-8")) for f in files]
    rows = [r for r in rows if r.get("analysis")]
    print(f"判定 {len(rows)} 件\n")
    if not rows:
        return
    print("靴下:", Counter(r.get("sock_id") or r["analysis"].get("sock", {}).get("name") for r in rows).most_common())
    print("品質ランク:", Counter(r["analysis"]["quality"]["rank"] for r in rows).most_common())
    print("印象（最終）:", Counter(r["analysis"]["impression"]["id"] for r in rows).most_common())
    print("候補1位:", Counter(r["analysis"]["impression"]["candidates"][0] for r in rows).most_common())
    print("入力機器:", Counter(s["pointerType"] for r in rows for s in r["request"]["strokes"]).most_common())

    q = [(r["analysis"]["quality"]["geometry"], (r["analysis"].get("ai_judgement") or {})) for r in rows]
    print("\n幾何評価: 平均 %.1f" % np.mean([g for g, _ in q]))
    ai = [j for _, j in q if j]
    if ai:
        print("AI美しさ: 平均 %.1f（balance %.1f / line %.1f / endings %.1f / overall %.1f）" % (
            np.mean([(j["balance"] + j["line_quality"] + j["endings"] + j["overall"]) / 4 * 10 for j in ai]),
            *[np.mean([j[k] for j in ai]) for k in ("balance", "line_quality", "endings", "overall")]))

    print("\n軸スコア（平均 ± 標準偏差、正: 左の印象 / 負: 右の印象）")
    for name, (pos, neg, _) in axes.AXES.items():
        v = [r["analysis"]["impression"]["axes"][name] for r in rows]
        print(f"  {axes.IMPRESSION_LABELS[pos]:>5}/{axes.IMPRESSION_LABELS[neg]:<5} {np.mean(v):+.2f} ± {np.std(v):.2f}")

    print("\n特徴量（実測の平均 / 仮の母集団の平均 → 平均の z 値）")
    for k in population.DEFAULTS:
        v = [r["analysis"]["features"].get(k) for r in rows]
        v = [x for x in v if x is not None]
        if not v:
            continue
        m, s = population.stats(k)
        print(f"  {population.LABELS[k]:<16} 実測 {np.mean(v):8.3f}  仮 {m:8.3f}  z {(np.mean(v) - m) / s:+.2f}")


if __name__ == "__main__":
    main()
