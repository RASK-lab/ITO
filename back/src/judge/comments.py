"""AI が使えないときのコメント（テンプレート文）。靴下の名前と説明はデザイン担当の socks.json から引く。"""

from __future__ import annotations

from . import catalog

IMPRESSION_PHRASES = {
    "teinei": "ゆっくりと一画ずつ確かめるように書かれた、丁寧な「と」です。",
    "zatsu": "勢いにまかせて一気に書き上げた、潔い「と」です。",
    "tappitsu": "迷いのない筆運びで、流れるように書かれた達筆な「と」です。",
    "bukiyou": "一画一画に試行錯誤のあとが見える、不器用で愛嬌のある「と」です。",
    "kawaii": "折り返しがころんと丸く、やわらかい印象の可愛い「と」です。",
    "kakkoii": "鋭い折り返しと直線的な線が効いた、かっこいい「と」です。",
    "atatakai": "ふところがゆったりと広く、包み込むような暖かい「と」です。",
    "tsumetai": "すらりと縦に引き締まった、クールで冷たい表情の「と」です。",
    "koseiteki": "お手本にとらわれない大胆な形の、個性的な「と」です。",
    "sensai": "小さく控えめに、細やかに書かれた繊細な「と」です。",
}


def template_comment(sock_id: str, impression: str, special: str | None = None) -> str:
    it = catalog.item(sock_id)
    text = IMPRESSION_PHRASES[impression]
    text += f"その書きぶりが「{it['name']}」になりました。{it['comment']}"
    return text
