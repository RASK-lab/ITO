"""Google Fonts の日本語フォントすべてで「と」を描き、学習データにする。

使い方（リポジトリの直下で）: python ml/tools/fetch_google_fonts.py

- 対象: Google Fonts の一覧で、文字の範囲（subsets）に japanese を含むファミリーの、すべての太さ。
  2026-11-28 時点で 68 ファミリー、187 書体。
- フォントは「と」だけを含む小さなファイルを Google Fonts の API から取る（text=と の指定）。
  ml/data/sources/google_fonts/ に置き、2 回目からはダウンロードしない。
- Google が付けている雰囲気のタグ（Expressive。Cute、Calm など 20 種、0〜100）も
  meta.tags に入れる。私たちのラベルと比べる材料（ラベルそのものではない）。
- ライセンス: Google Fonts のフォントは OFL などのオープンなライセンス。ファミリーごとの
  ライセンスは https://github.com/google/fonts の ofl/、apache/、ufl/ を参照。
"""

from __future__ import annotations

import csv
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ito_ml.manifest import SOURCES_DIR, Item, make_id, save_image, write_manifest  # noqa: E402
from ito_ml.preprocess import normalize, render_font  # noqa: E402

SOURCE = "google_fonts"
CHAR = "と"
METADATA_URL = "https://fonts.google.com/metadata/fonts"
TAGS_URL = "https://raw.githubusercontent.com/google/fonts/main/tags/all/families.csv"
CSS_URL = "https://fonts.googleapis.com/css2?family={family}:wght@{weight}&text={text}"
# 古いブラウザのふりをすると、Google Fonts は woff2 ではなく TrueType（Pillow で読める）を返す
OLD_UA = "Mozilla/4.0"
# Google Fonts に続けて頼むときの間隔（秒）
INTERVAL_S = 0.2


def get(url: str, ua: str = "Mozilla/5.0") -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def load_metadata() -> list[dict]:
    text = get(METADATA_URL).decode("utf-8")
    # 先頭に、ほかのサイトから読まれないための ")]}'" が付くことがある
    data = json.loads(text[text.index("{"):])
    return [f for f in data["familyMetadataList"] if "japanese" in (f.get("subsets") or [])]


def load_tags() -> dict[str, dict[str, float]]:
    tags: dict[str, dict[str, float]] = {}
    for row in csv.reader(io.StringIO(get(TAGS_URL).decode("utf-8"))):
        # 形: ファミリー名, (空), /Expressive/Cute, 76
        if len(row) >= 4 and row[2].startswith("/Expressive/"):
            tags.setdefault(row[0], {})[row[2].rsplit("/", 1)[-1]] = float(row[3])
    return tags


def download_font(family: str, weight: str) -> Path:
    path = SOURCES_DIR / SOURCE / make_id(family) / f"{weight}.ttf"
    if path.exists():
        return path
    css = get(CSS_URL.format(family=urllib.parse.quote_plus(family), weight=weight,
                             text=urllib.parse.quote(CHAR)), ua=OLD_UA).decode("utf-8")
    url = re.search(r"url\((https://[^)]+)\)", css).group(1)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(get(url, ua=OLD_UA))
    time.sleep(INTERVAL_S)
    return path


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    families = load_metadata()
    tags = load_tags()
    items: list[Item] = []
    for f in families:
        family = f["family"]
        for weight in sorted(f["fonts"], key=lambda w: int(w.rstrip("i"))):
            if weight.endswith("i"):
                continue  # 斜体（日本語フォントにはふつう無い）
            try:
                image = render_font(download_font(family, weight), CHAR)
            except Exception as error:  # 1 書体の失敗で全体を止めない
                print(f"  とばした: {family} {weight}（{error}）")
                continue
            if image is None:
                print(f"  とばした: {family} {weight}（「{CHAR}」が無い）")
                continue
            item_id = make_id("gf", family, weight)
            items.append(Item(
                id=item_id, source=SOURCE, image=save_image(SOURCE, item_id, normalize(image)),
                group=f"gf:{family}", kind="font",
                license="Google Fonts（OFL など。https://github.com/google/fonts でファミリーごとに確認）",
                meta={"family": family, "weight": int(weight), "category": f.get("category"),
                      "stroke": f.get("stroke"), "designers": f.get("designers"),
                      "tags": tags.get(family, {}),
                      # 変体仮名のフォントは、「と」の位置に別の字形（元の漢字が違う仮名）が入っている
                      "variant_glyph": "Hentaigana" in family},
            ))
        print(f"{family}: {sum(1 for i in items if i.meta['family'] == family)} 書体")
    path = write_manifest(SOURCE, items)
    print(f"\n{len(families)} ファミリー、{len(items)} 書体 → {path}")


if __name__ == "__main__":
    main()
