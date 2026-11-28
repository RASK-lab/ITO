"""学習データ集め（/api/collect/*）。

アプリ本体（/api/drawings）とは別に、学習用の「と」を集める。くわしくは docs/collect.md。

集め方の考え方:
- 学習するのは、印象 10 種への分類だけ。
- 「可愛い」などを、あとから人が見てラベルを付けるのではない。書く人に
  「◯◯に書いてください」と頼み、その頼み（指示。condition）をそのままラベルにする。
  主観のぶれが入らない。
- 1 回（セッション）で 5 回書いてもらう。印象 10 種の指示から、集まった件数の
  少ないものを 5 つ配る（種類ごとの数をそろえる）。
- 書いた人のことは聞かない（v1 では利き手と習字の経験を聞いていた。いまの画面は
  どちらも unknown で送る）。名前、性別、年齢も聞かない。
- 書いた人は、ブラウザに覚えさせた匿名の ID（writer_id）で区別する。同じ人の字が
  学習と評価の両方に入らないように分けるため（書いた人で分けた検証）。

| メソッド | パス | 内容 |
|---|---|---|
| GET | /api/collect/plan | 1 回分の、書いてもらう順番と指示を返す |
| POST | /api/collect/samples | 書いた「と」を 1 つ記録する |

置き場所: 画像は R2（storage.py。キー collect/<id>_1024.png など）、それ以外は
D1 の表 collect_samples（db.py）。線のデータも表に入れる（書き出しを表だけで済ませるため）。
"""

import base64
import binascii
import logging
import random
import re
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src import db, storage
from src.drawings import (
    CANVAS_SIZE,
    LARGE_SIZE,
    MAX_IMAGE_CHARS,
    MAX_IMAGE_SIZE,
    MIN_IMAGE_SIZE,
    PNG_DATA_URL_PREFIX,
    SMALL_SIZE,
    TARGETS,
    StrokeData,
    png_size,
    to_gray,
    to_png,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/collect", tags=["collect（学習データ集め）"])

# 集め方の版。指示の文や、1 回に書いてもらう数を変えたら上げる（混ぜて学習しないため）。
PROTOCOL = "v2"

# 指示（condition）と、画面に出す文。キーは分析の印象のキー（back/src/judge の
# analysis/axes.py と同じ）。ラベルは、このキーそのもの。
# 文は「印象の言葉（そのものずばり）＋ 書き方の手がかり」にしている。言葉だけだと
# 人によって受け取り方がばらつき、手がかりだけだと印象の言葉とずれるため。
# 「繊細」に「小さく」を入れないのは、大きさだけで当てられるラベルにしないため。
INSTRUCTIONS: dict[str, str] = {
    "teinei": "丁寧に（ゆっくり、ていねいに）",
    "zatsu": "雑に（急いで、なぐり書きで）",
    "tappitsu": "達筆に（習字の先生のつもりで、流れるように）",
    "bukiyou": "利き手と反対の手で",
    "kawaii": "可愛く",
    "kakkoii": "かっこよく",
    "atatakai": "暖かい感じに（やさしく、ふんわりと）",
    "tsumetai": "冷たい感じに（きっちり、そっけなく）",
    "koseiteki": "個性的に（自由に、崩して）",
    "sensai": "繊細に（細やかに、そっと）",
}
IMPRESSIONS = tuple(INSTRUCTIONS)

# 1 回で書いてもらう数（10 種のうち 5 種。2 回で 10 種がひととおりそろう）
IMPRESSION_TRIALS = 5

# 利き手と反対の手は、手を持ちかえるので最後にする
LAST_CONDITIONS = ("bukiyou",)

# 集めるときの点の上限。表の 1 行に線のデータを入れるので、アプリ本体（20 万）より
# 小さくする。2 万点の JSON は最大でも約 0.8MB で、D1 の 1 行の上限（2MB）に収まる。
# ふつうの「と」は 100 点前後。
MAX_COLLECT_POINTS = 20_000
MAX_BODY_BYTES = MAX_IMAGE_CHARS + MAX_COLLECT_POINTS * 80 + 4096

# 1 回の中の番号の上限（同じ回で何度も送られるのを防ぐ）
MAX_TRIAL = 30

# ブラウザが作る ID（crypto.randomUUID の形。英小文字・数字・ハイフン）
_ID_PATTERN = re.compile(r"[0-9a-f-]{8,64}")


class CollectTrial(BaseModel):
    """書いてもらう 1 回分"""

    trial: int
    condition: str
    instruction: str


class CollectPlan(BaseModel):
    protocol: str
    trials: list[CollectTrial]


class CollectSampleIn(StrokeData):
    """書いた「と」1 つ。線のデータ（target、canvas、strokes）は /api/drawings と同じ形。"""

    model_config = ConfigDict(allow_inf_nan=False)

    protocol: str
    # 書いた人（ブラウザに覚えさせた匿名の ID）と、1 回（6 個）ごとの ID
    writer_id: str = Field(max_length=64)
    session_id: str = Field(max_length=64)
    # 1 回の中の番号（0 から）
    trial: int = Field(ge=0, le=MAX_TRIAL)
    # 指示（INSTRUCTIONS のキー）。画面に出した文は送らせず、サーバーが持つ文を記録する。
    condition: str
    # 書いた人の申告。答えなかったら unknown。
    dominant_hand: Literal["right", "left", "both", "unknown"]
    # school: 学校の授業だけ、lessons: 習字・書道を習っていた、
    # advanced: 段・師範など、unknown: 答えない
    calligraphy: Literal["school", "lessons", "advanced", "unknown"]
    # 学習に使うことへの同意。true でなければ記録しない。
    consent_train: bool
    # 書く枠の、画面での一辺（CSS ピクセル）と画素密度。端末の大きさで書き方が変わるため。
    display_px: int = Field(ge=50, le=10_000)
    device_pixel_ratio: float = Field(ge=0.1, le=20)
    # 「消去」と「1つ戻る」を押した回数（書き直しの多さ）
    redo_count: int = Field(ge=0, le=100_000)

    image: str = Field(max_length=MAX_IMAGE_CHARS)
    width: int = Field(ge=MIN_IMAGE_SIZE, le=MAX_IMAGE_SIZE)
    height: int = Field(ge=MIN_IMAGE_SIZE, le=MAX_IMAGE_SIZE)


class CollectSampleOut(BaseModel):
    id: str


def make_plan(pointer_type: str) -> list[str]:
    """1 回分の指示の並びを決める。

    印象の指示は、同じ入力の種類（マウス・指・ペン）で集まった件数の少ないものから選ぶ。
    件数が同じなら無作為。入力の種類ごとにそろえるのは、「急いで書いた字はスマホに多い」の
    ような偏りがあると、モデルが入力の種類で当ててしまうため。
    """
    try:
        counts = db.count_collect_conditions(PROTOCOL, pointer_type)
    except Exception:
        # 数えられなくても集めるのは止めない（無作為に選ぶ）
        logger.exception("指示ごとの件数を数えられませんでした")
        counts = {}
    order = sorted(IMPRESSIONS, key=lambda c: (counts.get(c, 0), random.random()))
    chosen = order[:IMPRESSION_TRIALS]
    random.shuffle(chosen)  # 指示の順番による影響を減らす
    chosen.sort(key=lambda c: c in LAST_CONDITIONS)  # 手を持ちかえるものは最後
    return chosen


@router.get("/plan", summary="1 回分の、書いてもらう順番と指示")
def get_plan(pointer: Literal["mouse", "touch", "pen"] = "mouse") -> CollectPlan:
    """pointer: 書くのに使いそうな入力の種類（フロントが画面の種類から推測して送る）。"""
    return CollectPlan(
        protocol=PROTOCOL,
        trials=[
            CollectTrial(trial=i, condition=c, instruction=INSTRUCTIONS[c])
            for i, c in enumerate(make_plan(pointer))
        ],
    )


def _decode_image(sample: CollectSampleIn):
    """data URL の PNG を確かめて、白黒 1 チャネルの画像にする（/api/drawings と同じ決まり）。"""
    if sample.width != sample.height:
        raise HTTPException(422, "画像は正方形（width と height が同じ）で送ってください")
    if not sample.image.startswith(PNG_DATA_URL_PREFIX):
        raise HTTPException(422, "image は PNG の data URL で送ってください")
    try:
        png = base64.b64decode(sample.image[len(PNG_DATA_URL_PREFIX) :], validate=True)
    except binascii.Error:
        raise HTTPException(422, "image の base64 を読めませんでした") from None
    if png_size(png) != (sample.width, sample.height):
        raise HTTPException(422, "image が PNG でないか、width と height が合っていません")
    try:
        return to_gray(png)
    except Exception:
        raise HTTPException(422, "image を PNG として読めませんでした") from None


@router.post("/samples", status_code=201, max_body_size=MAX_BODY_BYTES,
             summary="書いた「と」を 1 つ記録する")
def create_sample(sample: CollectSampleIn) -> CollectSampleOut:
    if sample.protocol != PROTOCOL:
        # 古い画面を開いたままの人など。指示の文が違うかもしれないので記録しない。
        raise HTTPException(409, "集め方が更新されました。ページを読み込み直してください")
    if not sample.consent_train:
        raise HTTPException(422, "学習に使うことへの同意がないので、記録しません")
    if sample.condition not in INSTRUCTIONS:
        raise HTTPException(422, "condition が、決まった指示ではありません")
    if not (_ID_PATTERN.fullmatch(sample.writer_id) and _ID_PATTERN.fullmatch(sample.session_id)):
        raise HTTPException(422, "writer_id と session_id の形が違います")
    if sample.target not in TARGETS:
        raise HTTPException(422, "target が、受け取れる字ではありません")
    if (sample.canvas.width, sample.canvas.height) != (CANVAS_SIZE, CANVAS_SIZE):
        raise HTTPException(422, f"canvas は {CANVAS_SIZE} × {CANVAS_SIZE} で送ってください")
    point_count = sum(len(stroke.points) for stroke in sample.strokes)
    if point_count > MAX_COLLECT_POINTS:
        raise HTTPException(422, f"点の合計は {MAX_COLLECT_POINTS} 個までにしてください")
    gray = _decode_image(sample)

    sample_id = uuid.uuid4().hex
    record = {
        "id": sample_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "protocol": PROTOCOL,
        "writer_id": sample.writer_id,
        "session_id": sample.session_id,
        "trial": sample.trial,
        "condition": sample.condition,
        "instruction": INSTRUCTIONS[sample.condition],
        "dominant_hand": sample.dominant_hand,
        "calligraphy": sample.calligraphy,
        # 最初の線の入力の種類（途中で変わることはほとんどない。線ごとの種類は strokes_json にある）
        "pointer_type": sample.strokes[0].pointerType,
        "display_px": sample.display_px,
        "device_pixel_ratio": sample.device_pixel_ratio,
        "redo_count": sample.redo_count,
        "target": sample.target,
        "duration_ms": sample.strokes[-1].points[-1][2],
        "stroke_count": len(sample.strokes),
        "point_count": point_count,
        "image_1024_key": f"collect/{sample_id}_{LARGE_SIZE}.png",
        "image_256_key": f"collect/{sample_id}_{SMALL_SIZE}.png",
        # /api/drawings の線のデータ（drawings/<id>.json.gz の中身）と同じ形
        "strokes_json": sample.model_dump_json(include=set(StrokeData.model_fields)),
    }
    objects = {
        record["image_1024_key"]: to_png(gray, LARGE_SIZE),
        record["image_256_key"]: to_png(gray, SMALL_SIZE),
    }
    # /api/drawings と同じく、画像を置いてから表に書く。失敗したら置いた画像を消す。
    try:
        for key, data in objects.items():
            storage.put_object(key, data)
        db.insert_collect_sample(record)
    except Exception:
        logger.exception("学習データを保存できませんでした（id: %s）", sample_id)
        for key in objects:
            try:
                storage.delete_object(key)
            except Exception:
                logger.exception("書きかけのデータを消せませんでした（キー: %s）", key)
        raise HTTPException(500, "記録を保存できませんでした") from None
    return CollectSampleOut(id=sample_id)
