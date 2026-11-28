"""ラベル付けを本番のアプリ（/label/）で行うためのファイルを作る。

使い方（リポジトリの直下で。取り込み（fetch_*.py、import_*.py）のあとに）:
  python ml/tools/build_label_site.py --passcode <合言葉>   # 合言葉を決める・変えるとき
  python ml/tools/build_label_site.py                       # 画像を足したとき（合言葉はそのまま）

作るもの（どれも Git に入れて、デプロイで配る）:
  front/public/label/img/<データ名>/<id>.png    表示用の画像
  back/src/resources/label_items.json           画像の一覧（id、データ名、画像のパス、group）
  back/src/resources/label_config.json          ml/labeling/config.json の写し ＋ 合言葉の SHA-256

- 公開してよいデータ（PUBLIC_SOURCES）だけを入れる。ETL（再配布の条件がある）と、
  アプリで集めた手書き（チームの外に出さない）は入れない。手元のサーバー
  （ml/labeling/server.py）でラベルを付ける。
- 表示用の画像は、学習用の画像（ml/data/images/）を小さくしたもの。くずし字は元が 28 × 28
  なので 64 × 64 にする（容量を減らすため。画面で拡大して見せる）。
- 合言葉そのものは保存しない（SHA-256 だけ）。合言葉は口頭やチャットでラベルを付ける人に伝える。
- 画像の id はそのまま（ml/data の id と同じ）なので、本番で付けたラベルを書き出しにそのまま使える。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ito_ml.manifest import DATA_DIR, ML_DIR, load_items  # noqa: E402

REPO = ML_DIR.parent
SITE_IMG = REPO / "front" / "public" / "label" / "img"
RESOURCES = REPO / "back" / "src" / "resources"
# 公開してよいデータと、表示用の画像の一辺
PUBLIC_SOURCES = {"google_fonts": 256, "kuzushiji49": 64}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--passcode", help="合言葉（決める・変えるときだけ）")
    args = parser.parse_args()

    config = json.loads((ML_DIR / "labeling" / "config.json").read_text(encoding="utf-8"))
    old = RESOURCES / "label_config.json"
    if args.passcode:
        config["passcode_sha256"] = hashlib.sha256(args.passcode.encode("utf-8")).hexdigest()
    elif old.exists():
        config["passcode_sha256"] = json.loads(old.read_text(encoding="utf-8")).get("passcode_sha256")
    if not config.get("passcode_sha256"):
        print("合言葉がまだありません。--passcode を付けて実行してください")
        return
    config.pop("raters", None)  # 本番では、付ける人が自分の名前を入れる

    if SITE_IMG.exists():
        shutil.rmtree(SITE_IMG)
    items = []
    for item in load_items():
        size = PUBLIC_SOURCES.get(item["source"])
        if size is None:
            continue
        dest = SITE_IMG / item["source"] / f"{item['id']}.png"
        dest.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(DATA_DIR / item["image"]) as image:
            image.convert("L").resize((size, size), Image.Resampling.LANCZOS).save(dest, optimize=True)
        items.append({"id": item["id"], "source": item["source"], "group": item["group"],
                      "image": "/" + dest.relative_to(REPO / "front" / "public").as_posix()})

    (RESOURCES / "label_items.json").write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    old.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    total = sum(p.stat().st_size for p in SITE_IMG.rglob("*.png"))
    print(f"画像 {len(items)} 枚（{total / 1e6:.1f}MB）→ {SITE_IMG}")
    print(f"一覧と設定 → {RESOURCES / 'label_items.json'}、{old}")


if __name__ == "__main__":
    main()
