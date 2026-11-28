"""ラベル付けの決まり（次に出す画像の選び方と、集計）。

本番の API（back/src/labeling.py）と、手元で動かすサーバー（ml/labeling/server.py）の
両方がこれを使う。保存のしかたには関わらない（データを受け取って計算するだけ）。

用語:
- item: ラベルを付ける画像 1 枚。{"id", "source", "image", "group"}
- labels: {item_id: {rater: label}}（同じ人が同じ画像に付け直したら上書き）
- config: ラベルの種類や、1 枚に何人で付けるか（ml/labeling/config.json と同じ形）
"""

from __future__ import annotations

import hashlib
from itertools import combinations


def target_of(config: dict, source: str) -> int:
    targets = config["target_ratings"]
    return targets.get(source, targets["default"])


def _order_key(rater: str, item_id: str) -> str:
    # 人ごとに違う、毎回同じ並び（同じフォントの太さ違いなどが続かないように混ぜる）
    return hashlib.sha1(f"{rater}\0{item_id}".encode()).hexdigest()


def choose_next(items: list[dict], labels: dict[str, dict[str, str]], config: dict, rater: str,
                skip: set[str] = frozenset(), reserved: dict[str, int] | None = None) -> tuple[dict | None, int]:
    """その人に次に出す画像と、その人の残りの数。

    - その人がまだ付けていない画像のうち、付けた人数が目標（target_ratings）に届いていないもの。
    - 優先度（source_priority）の高いデータから。
    - 同じ優先度なら、ほかの人が付け始めた画像を先に（全員分がそろった画像から増やし、
      人どうしの一致を測れるようにするため）。
    reserved: いまほかの人の画面に出ている画像の人数（同じ画像を出しすぎないため）
    """
    priority = config["source_priority"]
    reserved = reserved or {}
    best, best_key, remaining = None, None, 0
    for item in items:
        item_id = item["id"]
        done = labels.get(item_id, {})
        if rater in done:
            continue
        target = target_of(config, item["source"])
        if len(done) >= target:
            continue
        remaining += 1
        # 画面に出ているだけの分も数えて、目標を超えて出さないようにする
        if item_id in skip or len(done) + reserved.get(item_id, 0) >= target:
            continue
        # 並べるときは、実際に付いたラベルの数で比べる
        key = (priority.get(item["source"], 9), -len(done), _order_key(rater, item_id))
        if best_key is None or key < best_key:
            best, best_key = item, key
    return best, remaining


def fleiss_kappa(table: list[dict[str, int]], categories: list[str]) -> float | None:
    """1 枚ごとの {ラベル: 人数} から Fleiss の κ（人数が画像ごとに違ってもよい形）。"""
    rows = [r for r in table if sum(r.values()) >= 2]
    if not rows:
        return None
    total = sum(sum(r.values()) for r in rows)
    p_e = sum((sum(r.get(c, 0) for r in rows) / total) ** 2 for c in categories)
    p_bar = sum((sum(v * v for v in r.values()) - sum(r.values())) /
                (sum(r.values()) * (sum(r.values()) - 1)) for r in rows) / len(rows)
    return None if p_e >= 1 else round((p_bar - p_e) / (1 - p_e), 3)


def summarize(items: list[dict], labels: dict[str, dict[str, str]], config: dict) -> dict:
    """進み具合と、人どうしの一致の度合い。"""
    raters = sorted({r for v in labels.values() for r in v})
    per_rater = {r: sum(1 for v in labels.values() if r in v) for r in raters}
    per_label: dict[str, int] = {}
    for v in labels.values():
        for label in v.values():
            per_label[label] = per_label.get(label, 0) + 1
    per_source: dict[str, dict] = {}
    for item in items:
        s = per_source.setdefault(item["source"], {"items": 0, "labeled": 0, "complete": 0})
        n = len(labels.get(item["id"], {}))
        s["items"] += 1
        s["labeled"] += n > 0
        s["complete"] += n >= target_of(config, item["source"])
    # 一致の度合い（「「と」に見えない」は除く。「どれとも言えない」は 1 つの選択肢として数える）
    categories = [c["key"] for c in config["classes"]] + ["unsure"]
    pairs = {}
    for a, b in combinations(raters, 2):
        both = [(v[a], v[b]) for v in labels.values()
                if a in v and b in v and v[a] in categories and v[b] in categories]
        if both:
            pairs[f"{a} × {b}"] = {"n": len(both), "agree": round(sum(x == y for x, y in both) / len(both), 3)}
    table = []
    for v in labels.values():
        counts: dict[str, int] = {}
        for label in v.values():
            if label in categories:
                counts[label] = counts.get(label, 0) + 1
        table.append(counts)
    return {"label_set": config["label_set"], "ratings": sum(per_rater.values()), "per_rater": per_rater,
            "per_label": per_label, "per_source": per_source, "pairwise_agreement": pairs,
            "fleiss_kappa": fleiss_kappa(table, categories)}
