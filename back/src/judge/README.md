# 判定エンジン（AI 担当）

ひらがなの「と」を評価し、50種類の靴下から1足を選んで、AI のコメントを添えて返す。

1. **筆跡解析エンジン**: 誤タップ除去 → 「と」判定（形の近い字 ト・こ・し・て と比較） → 幾何評価（KanjiVG のお手本と照合） → 特徴量20個 → 印象の5軸と候補3つ → 特別な書き方の検出
2. **AI① 判定（Claude）**: 画像＋定量データから、候補3つのうち印象を1つ決め、美しさを採点
3. **靴下ID**: 品質点（幾何評価 0.5 ＋ AI美しさ 0.5）→ 5ランク（＝綺麗さ）。印象×綺麗さのマスにある靴下の ID（例: `REGAL-01`）
4. **AI② コメント（Claude）**: 「と」の画像＋選ばれた靴下の画像＋靴下の見た目の説明から、なぜこの靴下になったのかを書く

品質と印象はユーザーに見せない（靴下の選定にだけ使う）。

## API

| メソッド | パス | 内容 |
|---|---|---|
| POST | `/api/judge/full` | 解析エンジン＋AI①②。`{sock_id, comment, degraded}` |
| POST | `/api/judge/geometry` | AI なし（解析エンジン＋テンプレートのコメント）。同じ形 |
| GET | `/api/socks` | 靴下50種の一覧（socks.json の items） |
| GET | `/api/refs/to` | 「と」のお手本の点列 |
| GET | `/api/dev/playground` | 確認ページ（`DEV=1` のときだけ） |
| POST | `/api/dev/samples` | 検証サンプルを `back/src/eval_data/` に保存（`DEV=1` のときだけ） |

リクエスト:

```json
{
  "canvas": { "width": 512, "height": 512 },
  "strokes": [ { "pointerType": "pen", "points": [[x, y, t_ms, pressure], ...] } ]
}
```

- キャンバスは正方形・固定サイズにする（字の大きさをキャンバスに対する比で測るため）
- 1 画 = `pointerdown` から `pointerup` まで。`getCoalescedEvents()` で点を取る
- `t` は書き始めからの経過ミリ秒（画ごとにリセットしない）。`pressure` は省略可

レスポンス:

```json
{ "sock_id": "REGAL-08", "comment": "…", "degraded": false }
```

`DEV=1` のときだけ `debug`（品質・印象・軸スコア・特徴量など）が付く。

## 靴下（デザイン担当のデータ）

- `catalog/socks.json` と `catalog/images/*.png` はデザイン担当のデータをそのまま置いている（50種）
- 各靴下は「印象（feature）10種 × 綺麗さ（beauty）1〜5」の50マスに1足ずつ対応。判定エンジンは印象と品質ランク（＝綺麗さ）を決めて、そのマスの靴下の `id`（例: `REGAL-01`）を返す
- AI② コメントには、靴下の画像と socks.json の `name` `rarity` `comment` `review.reason` を渡す
- データを差し替えたら `python -c "from src.judge import catalog; print(catalog.check())"` で欠けがないか確認できる（空リストなら OK）
- 特別な書き方（一筆書き、書き順が逆、極端に速い など）は靴下の選定には使わず、コメントで触れる

## 調整

- サンプルを確認ページで保存したら `python -m src.judge.tools.build_population` で特徴量の平均・標準偏差を更新する
- 軸の重み: `analysis/axes.py`、特別な書き方のしきい値: `analysis/rare.py`、品質ランクの境界: `engine.py`

## 環境変数

`.env.example` を参照。`ANTHROPIC_API_KEY` が無いと AI を呼ばず、`degraded: true` で返す。

## 開発（`back/` で）

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt   # macOS/Linux は .venv/bin/python
.venv/Scripts/python -m pytest src/tests
DEV=1 .venv/Scripts/python -m uvicorn src.main:app --reload --port 8000   # http://localhost:8000/api/dev/playground
```

Docker の場合: `docker compose exec backend pip install pytest httpx` のあと `docker compose exec backend python -m pytest src/tests`。
