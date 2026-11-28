"""書いた「と」を受け取り、画像を整えて記録し、結果（くつしたとメッセージ）を返す。

置き場所は storage.py（画像と線のデータ）と db.py（台帳）に任せる。
記録の形は docs/data.md にある。

結果（くつしたとメッセージ）は、分析（back/src/judge）が作る（下の make_result）。
"""

import base64
import binascii
import gzip
import io
import logging
import random
import struct
import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt

from src import db, socks, storage
from src.judge.service import judge_sync, save_for_tuning

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/drawings", tags=["drawings"])

# 点の合計の上限。線の本数には上限を置かない（短い線をたくさん書く使い方があるため）。
# フロント（front/src/components/WritingCanvas.tsx の MAX_POINTS）と同じ値にする。
MAX_POINTS = 200_000
MAX_IMAGE_CHARS = 16_000_000
# 本文全体の上限（バイト）。image の上限に、点 1 個あたり 80 バイトを足した大きさ。
# フロントが送る点は、JSON にすると 1 個あたり 35 バイトまで。線 1 本ごとに、入れ物
# （pointerType と points の名前）の 36 バイトが加わる。点が 1 個だけの線ばかりでも、
# 点 1 個あたり 80 バイトより必ず小さい。
MAX_BODY_BYTES = MAX_IMAGE_CHARS + MAX_POINTS * 80 + 1024

# 受け取る画像の一辺（ピクセル）。画像は正方形で受け取る。
# 下限は、保存する大きいほうの画像と同じ。小さい画像を引き伸ばすとぼやけるので、
# フロントが必ずこれ以上の大きさで描き起こして送る。
# 上限は、画像を展開して加工するときのメモリで決めている（一辺 4096 で、1 回の確定に
# つき約 80MB。倍の 8192 では 4 倍になる）。
# フロント（WritingCanvas.tsx の MIN_IMAGE_SIZE と MAX_IMAGE_SIZE）と同じ値にする。
MIN_IMAGE_SIZE = 1024
MAX_IMAGE_SIZE = 4096

# 保存する画像の一辺（ピクセル）。キーの名前と台帳の列の名前にも、この数が入っている。
LARGE_SIZE = 1024  # 保存用・あとで表示する用
SMALL_SIZE = 256  # 深層学習用・一覧の小さい表示用

# 受け取れる字。いまは「と」だけ。字を増やすときは、ここに足す。
# フロント（front/src/api/drawings.ts の TARGET）が送る字は、ここになければならない。
TARGETS = ("と",)

# ユーザーネームの決まり。フロント（front/src/userName.ts）と同じ値にする。
MAX_USER_NAME_LENGTH = 15
# 名前を入れずに進んだときの名前
DEFAULT_USER_NAME = "User"

# 線の座標の基準にする枠の一辺。端末の画面の大きさに関係なく、枠をこの大きさと
# みなした座標で受け取る（保存する大きいほうの画像と同じ基準）。
# フロント（WritingCanvas.tsx の STROKE_CANVAS_SIZE）と同じ値にする。
CANVAS_SIZE = LARGE_SIZE
# 枠の外へ出た線は、フロントが「枠の一辺ぶん外側まで」で止めて送る
MIN_POSITION = -CANVAS_SIZE
MAX_POSITION = CANVAS_SIZE * 2

# 台帳の整数に入れる値の上限（JavaScript が正確に扱える整数の上限と同じ）
MAX_INTEGER = 2**53 - 1

# 線のデータを gzip にするときの強さ（1〜9）。いちばん強い 9 は、6 と比べて
# ほとんど小さくならず、時間は倍かかるので使わない。
GZIP_LEVEL = 6

PNG_DATA_URL_PREFIX = "data:image/png;base64,"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


# 点は [x, y, t, pressure] の並び。項目の名前と並びは、分析側の資料に合わせている。
# 数だけを受け取る（"1" のような文字や true は受け取らない）。
# x, y: 枠の左上を (0, 0)、一辺を CANVAS_SIZE とした位置
Position = Annotated[StrictFloat, Field(ge=MIN_POSITION, le=MAX_POSITION)]
# t: 最初の線を書きはじめてからの経過ミリ秒（整数）
Elapsed = Annotated[StrictInt, Field(ge=0, le=MAX_INTEGER)]
# pressure: 筆圧
Pressure = Annotated[StrictFloat, Field(ge=0, le=1)]
Point = tuple[Position, Position, Elapsed, Pressure]


class Canvas(BaseModel):
    width: int
    height: int


class Stroke(BaseModel):
    """ポインタを押してから離すまでの 1 本の線"""

    # NaN と無限大は受け取らない（記録した JSON が壊れるため）
    model_config = ConfigDict(allow_inf_nan=False)

    # 書きはじめたときの入力の種類
    pointerType: Literal["mouse", "touch", "pen"]
    points: list[Point] = Field(min_length=1, max_length=MAX_POINTS)


class StrokeData(BaseModel):
    """線のデータ。分析側がそのまま読める形で、この 3 項目をそのまま保存する。"""

    # 書いた字。TARGETS にあるかは、下で確かめる。
    target: str
    # 線の座標の基準にした枠の大きさ。CANVAS_SIZE の正方形かは、下で確かめる。
    canvas: Canvas
    strokes: list[Stroke] = Field(min_length=1, max_length=MAX_POINTS)


class DrawingIn(StrokeData):
    model_config = ConfigDict(allow_inf_nan=False)

    # 書いた人のユーザーネーム。送られなかったり空だったりしたら DEFAULT_USER_NAME にする。
    # 長さは、前後の空白を取ってから下で確かめる。
    user_name: str = Field(default="", max_length=200)

    image: str = Field(max_length=MAX_IMAGE_CHARS)
    # 送った画像の大きさの申告。実物と合っているかは、下で確かめる。
    width: int = Field(ge=MIN_IMAGE_SIZE, le=MAX_IMAGE_SIZE)
    height: int = Field(ge=MIN_IMAGE_SIZE, le=MAX_IMAGE_SIZE)


class SockOut(BaseModel):
    """結果として返すくつした。image は、フロントがそのまま <img src> に使えるパス。"""

    id: str
    name: str
    image: str


class DrawingOut(BaseModel):
    id: str
    created_at: str
    # ここから下は結果。分析（make_result）が作る。
    sock: SockOut
    # 利用者へのメッセージ。AI が書いた 2〜3 文（100〜150 字ほど）。改行は含まない。
    message: str


def make_result(drawing: StrokeData) -> tuple[SockOut, str]:
    """結果（くつしたと、利用者へのメッセージ）を、分析（back/src/judge）で作る。

    分析は、書かれた「と」の線から、字の綺麗さ（5 段階）と印象（10 種）を決めて、
    台帳のそのマスのくつしたを選び、AI（Claude）がくつしたの画像を見ながら
    メッセージ（2〜3 文）を書く。AI が使えないとき（キーが無い、時間切れなど）は、
    分析が自動で AI なしの結果（テンプレートの文）に切り替えるので、ここでは気にしなくてよい。
    かかる時間は、AI ありで 3〜11 秒、AI なしで 0.3 秒ほど（上限は JUDGE_AI_BUDGET_S）。

    分析そのものが予期せず失敗したときだけ、確定を止めないように、無作為のくつしたを返す。
    """
    try:
        result = judge_sync(drawing.strokes, (drawing.canvas.width, drawing.canvas.height))
        # DEV=1 のときだけ、調整用に判定データを残す（back/src/eval_data/。Git には入らない）
        save_for_tuning(drawing.model_dump(include=set(StrokeData.model_fields)), result, source="drawings")
        sock = next(s for s in socks.all_socks() if s["id"] == result.sock_id)
        message = result.comment
    except Exception:
        logger.exception("分析に失敗したので、くつしたを無作為に選びます")
        sock = random.choice(socks.all_socks())
        message = f"あなたの「と」から、くつした「{sock['name']}」が編み上がりました。"
    return SockOut(id=sock["id"], name=sock["name"], image=sock["image"]), message


def to_stroke_data(drawing: DrawingIn) -> bytes:
    """線のデータを、保存する形（JSON を gzip で圧縮したもの）にする。"""
    data = drawing.model_dump_json(include=set(StrokeData.model_fields))
    # mtime=0: 圧縮した時刻を入れない（同じ中身なら、いつ圧縮しても同じバイト列になる）
    return gzip.compress(data.encode(), compresslevel=GZIP_LEVEL, mtime=0)


def png_size(png: bytes) -> tuple[int, int] | None:
    """PNG の先頭（IHDR）から幅と高さを読む。PNG でなければ None。"""
    if len(png) < 24 or not png.startswith(PNG_SIGNATURE) or png[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", png[16:24])


def to_gray(png: bytes) -> Image.Image:
    """PNG を、白黒 1 チャネル（8 ビットのグレースケール）の画像にする。

    2 値化はしない（線の縁の中間の濃さは残す）。透明な部分は白地に重ねる。
    """
    with Image.open(io.BytesIO(png), formats=["PNG"]) as image:
        if image.mode.startswith("I"):
            # Pillow は 16 ビットの濃さを 255 で頭打ちにしてしまい、正しく変換できない
            raise ValueError("16 ビットのグレースケールの PNG は扱えません")
        if image.has_transparency_data:
            # ブラウザが作る PNG は RGBA。そのときは写しを作らない（メモリを使うため）
            rgba = image if image.mode == "RGBA" else image.convert("RGBA")
            white = Image.new("L", rgba.size, 255)
            gray = Image.composite(rgba.convert("L"), white, rgba.getchannel("A"))
        else:
            gray = image.convert("L")
    # 元の PNG に付いていた情報（色の設定など）は、保存する画像に持ち越さない
    gray.info.clear()
    return gray


def to_png(gray: Image.Image, size: int) -> bytes:
    """一辺 size の正方形に縮小して、PNG にする。"""
    if gray.size != (size, size):
        # BICUBIC は、縁がぼやけにくく、白地と線の中に余計な濃淡も出ない
        # （LANCZOS は、線の縁の外側に薄い波が出る）
        gray = gray.resize((size, size), Image.Resampling.BICUBIC)
    out = io.BytesIO()
    # 圧縮は Pillow の既定のまま。いちばん強い圧縮（optimize）は、1 割ほど小さくなる
    # 代わりに 5〜10 倍の時間がかかるので使わない。
    gray.save(out, format="PNG")
    return out.getvalue()


# 本文は、読み込みながら大きさを数え、上限を超えたところで 413 にして打ち切る
@router.post("", status_code=201, max_body_size=MAX_BODY_BYTES)
def create_drawing(drawing: DrawingIn) -> DrawingOut:
    if drawing.target not in TARGETS:
        raise HTTPException(422, "target が、受け取れる字ではありません")
    if (drawing.canvas.width, drawing.canvas.height) != (CANVAS_SIZE, CANVAS_SIZE):
        raise HTTPException(
            422, f"canvas は {CANVAS_SIZE} × {CANVAS_SIZE} で送ってください"
        )
    user_name = drawing.user_name.strip() or DEFAULT_USER_NAME
    if len(user_name) > MAX_USER_NAME_LENGTH:
        raise HTTPException(
            422, f"user_name は {MAX_USER_NAME_LENGTH} 文字までにしてください"
        )
    point_count = sum(len(stroke.points) for stroke in drawing.strokes)
    if point_count > MAX_POINTS:
        raise HTTPException(422, f"点の合計は {MAX_POINTS} 個までにしてください")
    if drawing.width != drawing.height:
        raise HTTPException(422, "画像は正方形（width と height が同じ）で送ってください")
    if not drawing.image.startswith(PNG_DATA_URL_PREFIX):
        raise HTTPException(422, "image は PNG の data URL で送ってください")
    try:
        png = base64.b64decode(drawing.image[len(PNG_DATA_URL_PREFIX) :], validate=True)
    except binascii.Error:
        raise HTTPException(422, "image の base64 を読めませんでした") from None
    # 画像を展開する前に、先頭に書かれた大きさを確かめる（大きすぎる画像を展開しないため）
    size = png_size(png)
    if size is None:
        raise HTTPException(422, "image が PNG ではありません")
    if size != (drawing.width, drawing.height):
        raise HTTPException(422, "width と height が画像の大きさと合っていません")
    try:
        gray = to_gray(png)
    except Exception:
        # 壊れた PNG では、Pillow が OSError や SyntaxError など、いろいろな例外を出す
        raise HTTPException(422, "image を PNG として読めませんでした") from None

    # 結果は、保存する前に作る。くつしたの台帳が読めないときは、何も保存せずに失敗にする
    # （くつしたのない記録を残さない。返す形も、くつしたのない場合を作らずに済む）。
    try:
        sock, message = make_result(drawing)
    except Exception:
        logger.exception("結果を作れませんでした（くつしたの台帳を読めない、など）")
        raise HTTPException(500, "結果を作れませんでした") from None

    drawing_id = uuid.uuid4().hex
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    record = {
        "id": drawing_id,
        "created_at": created_at,
        "image_1024_key": f"drawings/{drawing_id}_{LARGE_SIZE}.png",
        "image_256_key": f"drawings/{drawing_id}_{SMALL_SIZE}.png",
        "strokes_key": f"drawings/{drawing_id}.json.gz",
        "target": drawing.target,
        # 最初の線を書きはじめてから、最後の線を離すまで（最後の線の最後の点の t）
        "duration_ms": drawing.strokes[-1].points[-1][2],
        "stroke_count": len(drawing.strokes),
        "point_count": point_count,
        "sock_id": sock.id,
        "message": message,
        "user_name": user_name,
    }
    objects = {
        record["image_1024_key"]: to_png(gray, LARGE_SIZE),
        record["image_256_key"]: to_png(gray, SMALL_SIZE),
        record["strokes_key"]: to_stroke_data(drawing),
    }

    # 先に画像と線のデータを置き、最後に台帳へ書く（台帳にあるのに中身がない、を作らない）
    try:
        for key, data in objects.items():
            storage.put_object(key, data)
        db.insert_drawing(record)
    except Exception:
        logger.exception("記録を保存できませんでした（id: %s）", drawing_id)
        # 片方だけ残さない
        for key in objects:
            try:
                storage.delete_object(key)
            except Exception:
                logger.exception("書きかけのデータを消せませんでした（キー: %s）", key)
        raise HTTPException(500, "記録を保存できませんでした") from None
    return DrawingOut(
        id=drawing_id, created_at=created_at, sock=sock, message=message
    )
