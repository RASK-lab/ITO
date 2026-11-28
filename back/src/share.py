"""結果ごとのシェア。カードの画像を預かり、シェア用のページを返す。

X などは、投稿されたアドレスのページを読みに来て、そこに書いてある画像をカードとして
出す。結果 1 件ごとにアドレス（/api/share/<記録の ID>）を作り、その結果の画像
（くつしたと、書いた「と」が入ったもの）をカードに指定する。

カードの画像は、フロントが作って送る（front/src/shareCard.ts の makeXCard）。
置き場のキーは cards/<記録の ID>.jpg。題と説明に使うくつしたは、送らせずに、
台帳（db.py）の記録から引く。

パスがどれも /api/ で始まるのは、本番で Worker がバックエンドに渡すのが /api/ だけのため。
"""

import html
import io
import logging
import re
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from PIL import Image

from src import db, socks, storage
from src.settings import SITE_URL

logger = logging.getLogger(__name__)

router = APIRouter(tags=["share"])

# カードの大きさ。X の大きなカード（summary_large_image）に合う横長。
# フロント（front/src/shareCard.ts の X_CARD_WIDTH と X_CARD_HEIGHT）と同じ値にする。
CARD_WIDTH, CARD_HEIGHT = 1200, 630
# 受け取るカードの画像の上限（バイト）。フロントが送るのは 100〜200KB ほど。
MAX_CARD_BYTES = 1_000_000
JPEG_SIGNATURE = b"\xff\xd8\xff"
# カードの画像を、ブラウザや X に覚えさせる秒数（1 週間）。一度置いた画像は変えない。
CARD_MAX_AGE_SECONDS = 7 * 24 * 60 * 60

# 記録の ID の形（drawings.py が uuid4().hex で作る、32 桁の 16 進）
_ID_PATTERN = re.compile(r"[0-9a-f]{32}")

# 手元で動かしているときの、画面のアドレス（compose.yaml の frontend）
LOCAL_SITE_URL = "http://localhost:5173"
_HOST_PATTERN = re.compile(r"[a-z0-9.-]+(:[0-9]+)?")
_IP_ADDRESS_PATTERN = re.compile(r"[0-9.]+")


def site_url(request: Request) -> str:
    """サイトのアドレス（最後の / なし）。カードの画像などを、絶対 URL で書くのに使う。

    環境変数 ITO_SITE_URL があれば、それを使う。なければ、リクエストの Host から決める。
    本番では、Worker がリクエストをそのままコンテナに渡すので、Host は公開している
    ドメインになる（ただしコンテナには http で届くので、https に決め打ちする）。
    手元では、Host が localhost や backend（Vite の中継ごし）になるので、
    画面のアドレス（LOCAL_SITE_URL）にする。
    """
    if SITE_URL:
        return SITE_URL
    host = request.headers.get("host", "").lower()
    name = host.split(":")[0]
    if (
        not _HOST_PATTERN.fullmatch(host)
        or "." not in name
        or _IP_ADDRESS_PATTERN.fullmatch(name)
    ):
        return LOCAL_SITE_URL
    return f"https://{host}"


def card_key(drawing_id: str) -> str:
    return f"cards/{drawing_id}.jpg"


def find_sock(drawing_id: str) -> dict | None:
    """記録の ID から、結果のくつしたを引く。記録やくつしたが無ければ None。"""
    sock_id = db.get_sock_id(drawing_id)
    return socks.get_sock(sock_id) if sock_id else None


def check_card(data: bytes) -> None:
    """カードの画像として受け取れるか（JPEG で、決まった大きさか）を確かめる。"""
    if not data.startswith(JPEG_SIGNATURE):
        raise HTTPException(422, "カードの画像は JPEG で送ってください")
    try:
        with Image.open(io.BytesIO(data), formats=["JPEG"]) as image:
            # 展開する前に、先頭に書かれた大きさを確かめる
            if image.size != (CARD_WIDTH, CARD_HEIGHT):
                raise HTTPException(
                    422, f"カードの画像は {CARD_WIDTH} × {CARD_HEIGHT} で送ってください"
                )
            # 最後まで展開できるかを確かめる（途中で切れた画像を置かない）
            image.load()
    except HTTPException:
        raise
    except Exception:
        # 壊れた画像では、Pillow が OSError や SyntaxError など、いろいろな例外を出す
        raise HTTPException(422, "カードの画像を JPEG として読めませんでした") from None


# 本文は、読み込みながら大きさを数え、上限を超えたところで 413 にして打ち切る
@router.put("/api/drawings/{drawing_id}/card", max_body_size=MAX_CARD_BYTES)
def put_card(
    drawing_id: str, card: Annotated[bytes, Body(media_type="image/jpeg")]
) -> dict:
    """カードの画像を預かり、シェア用のページのパスを返す。"""
    if not _ID_PATTERN.fullmatch(drawing_id):
        raise HTTPException(422, "id の形が違います")
    check_card(card)
    key = card_key(drawing_id)
    try:
        if find_sock(drawing_id) is None:
            raise HTTPException(404, "記録がありません")
        # すでにあれば、置き換えない。記録の ID はシェア用のアドレスに入っていて、
        # 投稿を見た人なら誰でも知っている。あとから別の画像に差し替えられないようにする。
        if storage.get_object(key) is None:
            storage.put_object(key, card)
    except HTTPException:
        raise
    except Exception:
        logger.exception("カードの画像を保存できませんでした（id: %s）", drawing_id)
        raise HTTPException(500, "カードの画像を保存できませんでした") from None
    return {"share_path": f"/api/share/{drawing_id}"}


@router.get("/api/cards/{drawing_id}.jpg")
def get_card(drawing_id: str) -> Response:
    """カードの画像を返す。X などが、シェア用のページを読んだあとに取りに来る。"""
    card = None
    if _ID_PATTERN.fullmatch(drawing_id):
        try:
            card = storage.get_object(card_key(drawing_id))
        except Exception:
            logger.exception("カードの画像を読めませんでした（id: %s）", drawing_id)
            raise HTTPException(500, "カードの画像を読めませんでした") from None
    if card is None:
        raise HTTPException(404, "カードの画像がありません")
    return Response(
        card,
        media_type="image/jpeg",
        headers={
            "Cache-Control": f"public, max-age={CARD_MAX_AGE_SECONDS}",
            "X-Content-Type-Options": "nosniff",
        },
    )


# シェア用のページ。形は、くつしたごとの固定のページ（scripts/build-share.py の PAGE）と同じ。
# {meta} のほかに、値は入らない。
PAGE = """<!doctype html>
<html lang="ja">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{title}</title>
{meta}    <!-- 人が開いたら、最初の画面に移す。カードを作るロボットはスクリプトを動かさないので、ここに残る。 -->
    <script>
      location.replace("/");
    </script>
  </head>
  <body>
    <p><a href="/">ITO を開く</a></p>
  </body>
</html>
"""


def make_page(title: str, properties: dict[str, str]) -> str:
    """ページの HTML を作る。入れる値は、ここですべてエスケープする。"""
    meta = "".join(
        # og: で始まるものは property、twitter: で始まるものは name に書く決まり
        f'    <meta {"property" if key.startswith("og:") else "name"}='
        f'"{html.escape(key)}" content="{html.escape(value)}" />\n'
        for key, value in properties.items()
    )
    return PAGE.format(title=html.escape(title), meta=meta)


def to_top_page(status_code: int) -> HTMLResponse:
    """カードの指定がなく、最初の画面へ移すだけのページ。"""
    return HTMLResponse(make_page("ITO", {}), status_code=status_code)


@router.get("/api/share/{drawing_id}", response_class=HTMLResponse)
def share_page(drawing_id: str, request: Request) -> HTMLResponse:
    """結果 1 件ぶんの、シェア用のページ。カードの指定（OGP）が書いてある。

    記録やカードの画像が無い ID では、最初の画面へ移すだけのページを 404 で返す
    （人が開いたら最初の画面に移り、ロボットにはカードを出させない）。
    """
    if not _ID_PATTERN.fullmatch(drawing_id):
        return to_top_page(404)
    try:
        sock = find_sock(drawing_id)
        if sock is None or storage.get_object(card_key(drawing_id)) is None:
            return to_top_page(404)
    except Exception:
        logger.exception("シェア用のページを作れませんでした（id: %s）", drawing_id)
        return to_top_page(500)

    site = site_url(request)
    title = f"くつした「{sock['name']}」"
    page = make_page(
        f"{title} | ITO",
        {
            "og:type": "website",
            "og:site_name": "ITO",
            "og:title": title,
            "og:description": sock.get("comment", ""),
            "og:url": f"{site}/api/share/{drawing_id}",
            "og:image": f"{site}/api/cards/{drawing_id}.jpg",
            "og:image:width": str(CARD_WIDTH),
            "og:image:height": str(CARD_HEIGHT),
            "twitter:card": "summary_large_image",
        },
    )
    return HTMLResponse(page)
