"""ETL 文字データベース（産総研）の手書きの「と」を学習データにする。

使い方:
  1. https://etlcdb.db.aist.go.jp/ で利用の登録をして、データを受け取る（研究目的。条件は公式サイトで確認）。
  2. 展開したファイルを ml/data/sources/etl/ に置く（フォルダの分け方は自由。ファイル名で種類を判断する）。
       ETL8G_01 … ETL8G_33、ETL9G_01 … ETL9G_50、ETL8B2C1 … 、ETL9B_1 … 、ETL4C、ETL7LC_1 …
  3. python ml/tools/import_etl.py

扱う種類と「と」の見分け方:
| 種類 | 1 件の大きさ | 画像 | 「と」の見分け方 |
|---|---|---|---|
| ETL8G、ETL9G | 8199 バイト | 128 × 127、16 階調 | JIS コード 0x2448 |
| ETL8B2、ETL9B | 512 バイト | 64 × 63、白黒 | JIS コード 0x2448 |
| ETL4、ETL7（M 型） | 2052 バイト | 64 × 63、16 階調 | 読み（ASCII）が "TO" |

【未確認】この PC では ETL を入手できていないので、実物のファイルでは試していない。
形式は公開されている仕様（ETL の各データの説明）と、広く使われている読み込み方に合わせた。
初めて取り込んだら、出力の件数（ETL8G で 160 件前後、ETL9G で 200 件前後など）と、
ml/data/images/etl/ の画像を目で確かめること。

書いた人の区別: 各件の「用紙の番号」（serial sheet number）を書いた人とみなして group にする。
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ito_ml.manifest import SOURCES_DIR, Item, make_id, save_image, write_manifest  # noqa: E402
from ito_ml.preprocess import normalize  # noqa: E402

SOURCE = "etl"
JIS_TO = 0x2448  # JIS X 0208 の「と」
LICENSE = "ETL Character Database（産総研）。利用の登録が必要。公開・再配布の条件は公式サイトで確認"

# (ファイル名の頭, 1 件のバイト数, struct の形, 画像の大きさ, 画像の階調(ビット), JIS の位置, 用紙の位置, 画像の位置)
FORMATS = [
    ("ETL8G", 8199, ">2H8sI4B4H2B30x8128s11x", (128, 127), 4),
    ("ETL9G", 8199, ">2H8sI4B4H2B34x8128s7x", (128, 127), 4),
    ("ETL8B", 512, ">2H4s504s", (64, 63), 1),
    ("ETL9B", 576, ">2H4s504s64x", (64, 63), 1),
    ("ETL4", 2052, ">H2sH6BI4H4B4x2016s4x", (64, 63), 4),
    ("ETL7", 2052, ">H2sH6BI4H4B4x2016s4x", (64, 63), 4),
]


def records(path: Path, size: int, fmt: str):
    data = path.read_bytes()
    for offset in range(0, len(data) - size + 1, size):
        yield struct.unpack(fmt, data[offset: offset + size])


def to_image(raw: bytes, shape: tuple[int, int], bits: int) -> Image.Image:
    if bits == 1:
        return Image.frombytes("1", shape, raw, "raw").convert("L")
    image = Image.frombytes("F", shape, raw, "bit", 4).convert("L")
    # 16 階調（0〜15）を 0〜255 に広げる
    return image.point(lambda v: min(255, v * 17))


def parse(path: Path, prefix: str, size: int, fmt: str, shape, bits) -> list[tuple[str, Image.Image]]:
    """（用紙の番号, 画像）の並び。「と」だけ。"""
    found = []
    for i, r in enumerate(records(path, size, fmt)):
        if prefix in ("ETL8G", "ETL9G"):
            sheet, jis, raw = r[0], r[1], r[14]
            is_to = jis == JIS_TO
        elif prefix in ("ETL8B", "ETL9B"):
            if i == 0:
                continue  # 先頭の 1 件は見出し（ダミー）
            sheet, jis, raw = r[0], r[1], r[3]
            is_to = jis == JIS_TO
        else:  # ETL4、ETL7（ひらがなだけのデータ。読みで見分ける）
            sheet, reading, raw = r[2], r[1], r[18]
            is_to = reading.strip() == b"TO"
        if is_to:
            found.append((str(sheet), to_image(raw, shape, bits)))
    return found


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    folder = SOURCES_DIR / SOURCE
    files = sorted(p for p in folder.rglob("*") if p.is_file()) if folder.exists() else []
    if not files:
        print(f"{folder} にファイルがありません（使い方はこのファイルの先頭）")
        return
    items: list[Item] = []
    for path in files:
        name = path.name.upper()
        spec = next((f for f in FORMATS if name.startswith(f[0])), None)
        if spec is None or name.endswith("INFO") or path.suffix.lower() in (".txt", ".pdf", ".htm", ".html"):
            continue
        prefix, size, fmt, shape, bits = spec
        try:
            found = parse(path, prefix, size, fmt, shape, bits)
        except struct.error as error:
            print(f"  読めなかった: {path.name}（{error}）")
            continue
        for k, (sheet, image) in enumerate(found):
            item_id = make_id("etl", path.name, sheet, k)
            items.append(Item(
                id=item_id, source=SOURCE, image=save_image(SOURCE, item_id, normalize(image)),
                group=f"etl:{prefix}:{sheet}", kind="handwriting", license=LICENSE,
                meta={"etl_file": path.name, "etl_kind": prefix, "sheet": sheet},
            ))
        print(f"{path.name}: 「と」{len(found)} 件")
    out = write_manifest(SOURCE, items)
    print(f"\n合計 {len(items)} 件 → {out}")


if __name__ == "__main__":
    main()
