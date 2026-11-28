# 判定エンジン（AI 担当）

ひらがなの「と」を評価し、60種類の靴下から1足を選んで、AI のコメントを添えて返す。

1. **筆跡解析エンジン**: 誤タップ除去 → 「と」判定（形の近い字 ト・こ・し・て と比較） → 幾何評価（KanjiVG のお手本と照合） → 特徴量20個 → 印象の5軸と候補3つ → レア判定
2. **AI① 判定（Claude）**: 画像＋定量データから、候補3つのうち印象を1つ決め、美しさを採点
3. **靴下ID**: 品質点（幾何評価 0.5 ＋ AI美しさ 0.5）→ 5ランク。`Q{品質}-{印象}` またはレア `R-{名前}`
4. **AI② コメント（Claude）**: 「と」の画像＋選ばれた靴下の画像＋靴下の見た目の説明から、なぜこの靴下になったのかを書く

品質と印象はユーザーに見せない（靴下の選定にだけ使う）。

## API

| メソッド | パス | 内容 |
|---|---|---|
| POST | `/api/judge/full` | 解析エンジン＋AI①②。`{sock_id, comment, degraded}` |
| POST | `/api/judge/geometry` | AI なし（解析エンジン＋テンプレートのコメント）。同じ形 |
| GET | `/api/socks` | 靴下60種の ID 一覧 |
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
{ "sock_id": "Q4-atatakai", "comment": "…", "degraded": false }
```

`DEV=1` のときだけ `debug`（品質・印象・軸スコア・特徴量など）が付く。

## 靴下ID

- 通常 50 種: `Q{1〜5}-{印象}`。印象は `koseiteki` `zatsu` `kawaii` `teinei` `kakkoii` `sensai` `tappitsu` `bukiyou` `atatakai` `tsumetai`
- レア 10 種: `R-katahou` `R-ippon` `R-uragaeshi` `R-kedama` `R-kinshi` `R-idaten` `R-amikake` `R-baby` `R-loose` `R-niji`

## 靴下画像とコメント

1. 靴下画像を `catalog/images/<ID>.png` に置く（SVG は Claude が読めないので PNG に書き出す）
2. `python -m src.judge.tools.describe_socks` で見た目の説明 `catalog/sock_descriptions.json` を作る
3. 説明に読み違いがあれば手で直す

画像が無い間は、AI② は説明なし・画像なしでコメントを書く。

## 調整

- サンプルを確認ページで保存したら `python -m src.judge.tools.build_population` で特徴量の平均・標準偏差を更新する
- 軸の重み: `analysis/axes.py`、レアのしきい値: `analysis/rare.py`、品質ランクの境界: `engine.py`

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
