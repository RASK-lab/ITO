#!/usr/bin/env python3
"""くつしたごとの、シェア用のページとカード画像を作り直す。

X などに投稿されたアドレスの下に、画像つきのカードを出すためのもの。
  data/socks/socks.json + data/socks/original/*.png
    →  front/public/share/worn-01.jpg      （カード画像。1200 × 630）
    →  front/public/s/worn-01/index.html   （カード画像の指定（OGP）を書いたページ）

ページは、人が開くと最初の画面に移る。フロントの「シェア」は、このページのアドレス
（/s/worn-01/）を投稿の文に入れる（front/src/shareCard.ts の sharePageUrl）。

使い方: scripts/build-share.py（ふつうは scripts/build-socks.sh が最後に呼ぶ）
必要なもの: Pillow（pip install pillow）と、日本語のフォント。

カードの画像は、X が外から取りに来る。そのため、アドレスは本番のドメインから書く必要がある。
ドメインが変わったら、下の SITE_URL を直して作り直す（環境変数 ITO_SITE_URL でも渡せる）。
"""

import html
import json
import os
import shutil
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("Pillow が見つかりません。'pip install pillow' で入れてから、もう一度実行してください。")

# 本番のアドレス（最後の / なし）。まだ決まっていないので、仮のものを入れている。
SITE_URL = os.environ.get("ITO_SITE_URL", "https://ito.example").rstrip("/")

ROOT = Path(__file__).resolve().parent.parent
SOCKS_JSON = ROOT / "data" / "socks" / "socks.json"
PNG_DIR = ROOT / "data" / "socks" / "original"
CARD_DIR = ROOT / "front" / "public" / "share"
PAGE_DIR = ROOT / "front" / "public" / "s"

# カードの大きさ。X の大きなカード（summary_large_image）に合う横長。
CARD_WIDTH, CARD_HEIGHT = 1200, 630

# 日本語のフォント（細字、太字）。上から順に探して、最初に見つかったものを使う。
FONT_CANDIDATES = [
    # macOS
    ("/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc", "/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc"),
    # Linux（Noto Sans CJK）
    (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    ),
]


def find_fonts() -> tuple[str, str]:
    for regular, bold in FONT_CANDIDATES:
        if os.path.exists(regular) and os.path.exists(bold):
            return regular, bold
    sys.exit("日本語のフォントが見つかりません。FONT_CANDIDATES にフォントの場所を足してください。")


def wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    """幅に収まるよう、1 文字ずつ見て行を分ける。"""
    lines, line = [], ""
    for ch in text:
        # 句読点や閉じかっこは、行の頭に送らない
        if line and ch not in "。、」" and draw.textlength(line + ch, font=font) > max_width:
            lines.append(line)
            line = ch
        else:
            line += ch
    if line:
        lines.append(line)
    return lines


def make_card(item: dict, regular: str, bold: str) -> Image.Image:
    """カード画像を作る。白地の左にくつした、右にレアリティ・名前・説明。見た目は仮のもの。"""
    card = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), "#fff")
    sock = Image.open(PNG_DIR / f"{item['id'].lower()}.png").convert("RGBA")
    sock = sock.resize((560, 560), Image.LANCZOS)
    card.paste(sock, (40, 35), sock)

    draw = ImageDraw.Draw(card)
    left, width = 640, 510
    small = ImageFont.truetype(regular, 30)
    large = ImageFont.truetype(bold, 60)

    y = 150
    draw.text((left, y), item["rarity"], font=small, fill="#555")
    y += 60
    for line in wrap(draw, item["name"], large, width)[:2]:
        draw.text((left, y), line, font=large, fill="#222")
        y += 80
    y += 20
    for line in wrap(draw, item["comment"], small, width)[:4]:
        draw.text((left, y), line, font=small, fill="#222")
        y += 48
    draw.text((left, CARD_HEIGHT - 90), "ITO", font=small, fill="#555")
    return card


PAGE = """<!doctype html>
<html lang="ja">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{title} | ITO</title>
    <meta property="og:type" content="website" />
    <meta property="og:site_name" content="ITO" />
    <meta property="og:title" content="{title}" />
    <meta property="og:description" content="{description}" />
    <meta property="og:url" content="{url}" />
    <meta property="og:image" content="{image}" />
    <meta property="og:image:width" content="{width}" />
    <meta property="og:image:height" content="{height}" />
    <meta name="twitter:card" content="summary_large_image" />
    <!-- 人が開いたら、最初の画面に移す。カードを作るロボットはスクリプトを動かさないので、ここに残る。 -->
    <script>
      location.replace("/");
    </script>
  </head>
  <body>
    <p><a href="/">ITO を開く</a></p>
  </body>
</html>
"""


def make_page(item: dict) -> str:
    sock_id = item["id"].lower()
    return PAGE.format(
        title=html.escape(f"くつした「{item['name']}」"),
        description=html.escape(item["comment"]),
        url=html.escape(f"{SITE_URL}/s/{sock_id}/"),
        image=html.escape(f"{SITE_URL}/share/{sock_id}.jpg"),
        width=CARD_WIDTH,
        height=CARD_HEIGHT,
    )


def main() -> None:
    items = json.loads(SOCKS_JSON.read_text(encoding="utf-8"))["items"]
    regular, bold = find_fonts()

    # 台帳から消えたくつしたの分が残らないよう、毎回すべて作り直す
    for folder in (CARD_DIR, PAGE_DIR):
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True)

    for item in items:
        sock_id = item["id"].lower()
        make_card(item, regular, bold).save(CARD_DIR / f"{sock_id}.jpg", quality=85)
        page = PAGE_DIR / sock_id / "index.html"
        page.parent.mkdir()
        page.write_text(make_page(item), encoding="utf-8")

    print(f"作り直しました: front/public/share/（カード画像）、front/public/s/（ページ）。{len(items)} 件、アドレスは {SITE_URL}")


if __name__ == "__main__":
    main()
