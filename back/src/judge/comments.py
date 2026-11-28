"""AI が使えないときのコメント（テンプレート文）。"""

from __future__ import annotations

IMPRESSION_PHRASES = {
    "teinei": "ゆっくりと一画ずつ確かめるように書かれた、丁寧な「と」です。",
    "zatsu": "勢いにまかせて一気に書き上げた、潔い「と」です。",
    "tappitsu": "迷いのない筆運びで、流れるように書かれた達筆な「と」です。",
    "bukiyou": "一画一画に試行錯誤のあとが見える、不器用で愛嬌のある「と」です。",
    "kawaii": "折り返しがころんと丸く、やわらかい印象のかわいい「と」です。",
    "kakkoii": "鋭い折り返しと直線的な線が効いた、かっこいい「と」です。",
    "atatakai": "ふところがゆったりと広く、包み込むような温かい「と」です。",
    "tsumetai": "すらりと縦に引き締まった、クールで冷たい表情の「と」です。",
    "koseiteki": "お手本にとらわれない大胆な形の、個性的な「と」です。",
    "sensai": "小さく控えめに、細やかに書かれた繊細な「と」です。",
}

QUALITY_PHRASES = {
    "low": "その書きぶりが、味のあるくたびれた風合いの靴下になりました。",
    "mid": "その書きぶりが、毎日履きたくなる気取らない靴下になりました。",
    "high": "整った線の運びが、目の詰まった上質な靴下になりました。",
}

RARE_PHRASES = {
    "R-katahou": "「と」とは少し違う字に見えたので、相方の見つからない片方だけの靴下になりました。",
    "R-ippon": "一筆で書き上げたので、1本の糸のまま靴下になりました。",
    "R-uragaeshi": "2画目から書き始めたので、裏返しの靴下になりました。",
    "R-kedama": "あちこちに残った小さな点が、毛玉になって靴下についてきました。",
    "R-kinshi": "お手本のような見事な「と」です。金の糸で編んだ特別な靴下になりました。",
    "R-idaten": "目にも止まらぬ速さの一筆が、韋駄天ソックスを呼びました。",
    "R-amikake": "じっくり時間をかけて書いたので、靴下もまだ編みかけのようです。",
    "R-baby": "とても小さく書かれた「と」なので、ベビーサイズの靴下になりました。",
    "R-loose": "キャンバスいっぱいに大きく書いたので、ゆったりしたルーズソックスになりました。",
    "R-niji": "どの印象にも偏らない、ど真ん中の「と」です。すべての色を集めた虹色の靴下になりました。",
}


def quality_band(rank: int) -> str:
    return "low" if rank <= 2 else ("mid" if rank == 3 else "high")


def template_comment(sock_id: str, impression: str, quality_rank: int) -> str:
    if sock_id in RARE_PHRASES:
        return RARE_PHRASES[sock_id]
    return IMPRESSION_PHRASES[impression] + QUALITY_PHRASES[quality_band(quality_rank)]
