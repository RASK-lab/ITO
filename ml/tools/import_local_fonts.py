"""手元にあるフォントファイル（.ttf、.otf、.ttc）で「と」を描き、学習データにする。

使い方:
  1. フォントを ml/data/sources/local_fonts/ に置く（下のフォルダに分けてもよい）。
     ライセンスを確かめ、同じフォルダに LICENSE などのファイルも置いておく。
  2. python ml/tools/import_local_fonts.py

- Google Fonts 以外の無料フォント（配布サイトのものなど）を足すためのもの。
  フォントごとに、学習に使ってよいかをライセンスで確かめてから置くこと。
- Windows や Office に入っているフォント（メイリオ、HG 系など）は、ライセンスの条件が
  個別に違う。使うかどうかはチームで判断する（このスクリプトは自動では読みに行かない）。
- .ttc（複数の書体が入ったファイル）は、入っている書体をすべて使う。
- まとまり（group）はファイル名ごと（同じファイルの書体違いは同じ側に入れる）。
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ito_ml.manifest import SOURCES_DIR, Item, make_id, save_image, write_manifest  # noqa: E402
from ito_ml.preprocess import normalize, render_font  # noqa: E402

SOURCE = "local_fonts"
CHAR = "と"


def faces(path: Path):
    """（書体の番号, 書体の名前）の並び"""
    index = 0
    while True:
        try:
            font = ImageFont.truetype(str(path), 32, index=index)
        except OSError:
            return
        yield index, " ".join(font.getname())
        if path.suffix.lower() != ".ttc":
            return
        index += 1


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    folder = SOURCES_DIR / SOURCE
    paths = sorted(p for p in folder.rglob("*") if p.suffix.lower() in (".ttf", ".otf", ".ttc")) \
        if folder.exists() else []
    if not paths:
        print(f"{folder} にフォントがありません（使い方はこのファイルの先頭）")
        return
    items: list[Item] = []
    for path in paths:
        for index, name in faces(path):
            try:
                image = render_font(path, CHAR, index=index)
            except Exception as error:
                print(f"  とばした: {path.name} {name}（{error}）")
                continue
            if image is None:
                print(f"  とばした: {path.name} {name}（「{CHAR}」が無い）")
                continue
            item_id = make_id("lf", path.stem, index)
            items.append(Item(
                id=item_id, source=SOURCE, image=save_image(SOURCE, item_id, normalize(image)),
                group=f"lf:{path.name}", kind="font",
                license=f"{path.parent.relative_to(folder).as_posix() or '.'} のライセンスのファイルを参照",
                meta={"file": path.relative_to(folder).as_posix(), "face_index": index, "name": name},
            ))
            print(f"{path.name} [{index}] {name}")
    out = write_manifest(SOURCE, items)
    print(f"\n{len(items)} 書体 → {out}")


if __name__ == "__main__":
    main()
