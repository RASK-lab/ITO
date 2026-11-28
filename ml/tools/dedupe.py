"""同じ画像を調べ直し、ml/data/duplicates.json に書く（くわしくは ml/ito_ml/dedupe.py）。

使い方（リポジトリの直下で。取り込み（fetch_*.py、import_*.py）のあとに）:
  python ml/tools/dedupe.py
build_label_site.py も、はじめにこれと同じことをする。
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ito_ml.dedupe import update_duplicates  # noqa: E402
from ito_ml.manifest import DUPLICATES_PATH, load_items  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    found = update_duplicates()
    by_kept = Counter(found.values())
    print(f"同じ画像 {len(found)} 枚を除く（残る画像 {len(load_items())} 枚）→ {DUPLICATES_PATH}")
    for kept, n in sorted(by_kept.items()):
        print(f"  {kept} を残し、{n} 枚を除く: {', '.join(k for k, v in found.items() if v == kept)}")


if __name__ == "__main__":
    main()
