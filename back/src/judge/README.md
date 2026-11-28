# 分析（back/src/judge）

書かれたひらがなの「と」から、くつした（50 種のどれか）と、利用者へのメッセージを決める部分です。
画面からは `POST /api/drawings`（確定）の中で呼ばれます。仕様書では「機能 04」です。

## 担当ごとに知っておくこと

### フロントエンド

- **呼ぶ API は変わりません。** `POST /api/drawings` の応答の `sock`（くつした）と `message`（メッセージ）を出すだけです。
- 応答まで **3〜11 秒** かかります（AI を使うため）。AI に使う時間は合計 11 秒までにしてあり、`front/src/api/drawings.ts` の打ち切り（15 秒）より短いです。待機中の画面は、数秒待つ前提で作ってください。
- `message` は **2〜3 文（100〜150 字ほど）**。改行は入りません。結果の画面で折り返して表示してください。
- 綺麗さや印象（分析の途中の値）は返しません。利用者に見せない方針です。
- 使えると便利な API（どれも保存はしない）:
  - `GET /api/socks` … くつした 50 種の台帳（くつした一覧の画面などに）
  - `GET /api/refs/to` … 「と」のお手本の点の並び（座標 0〜1、書き順どおり。演出などに）

### インフラ

コンテナに渡す環境変数です（全体は `settings.py` の先頭）。どれも無くても起動はします。

| 環境変数 | 本番での値 | 無いとき |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude の API キー（**秘密の値**。Worker の secret からコンテナに渡す） | AI なしで動く（くつしたは解析エンジンだけで選び、メッセージはテンプレートの文） |
| `SOCK_IMAGE_BASE_URL` | 公開しているサイトの URL（例: `https://hackathon-ito-app.<アカウント>.workers.dev`） | くつしたの画像を AI に見せず、説明文だけでメッセージを書く |
| `ANTHROPIC_BASE_URL` | Cloudflare AI Gateway を通すときだけ | Claude に直接つなぐ |
| `LLM_DAILY_LIMIT` | 1 日に Claude を呼ぶ回数の上限（既定 3000。1 回の確定で 2〜3 回） | 3000 |
| `DEV` | 本番では設定しない（`0`） | 開発用の API（`/api/dev/*`）は 404 |

- コンテナから `api.anthropic.com`（または AI Gateway）へ外に出られる必要があります。
- `SOCK_IMAGE_BASE_URL` を設定すると、Claude がそのサイトの `/socks/*.webp` を読みに行きます。サイトがインターネットから見える必要があります。
- 手元の Docker で AI を使うには、`compose.yaml` の backend に `env_file: .env` を足す必要があります（相談させてください）。
- 費用の目安: Haiku 5.5 で 1 回の確定あたり約 0.2〜0.3 円。

### 分析の担当（調整する人）

下の「調整」と「開発」を見てください。

## 入口（ほかのコードから呼ぶとき）

```python
from src.judge.service import judge_sync          # async でない関数から（/api/drawings はこれ）
from src.judge.service import judge                # async の関数から（await judge(...)）
from src.judge.service import judge_without_ai     # AI を使わない（速く、無料）

result = judge_sync(strokes, (1024, 1024))
result.sock_id    # "REGAL-07"（back/src/resources/socks.json の id）
result.comment    # 利用者へのメッセージ
result.degraded   # AI を使えなかったとき True
result.debug      # 分析の途中の値（綺麗さ、印象、特徴量など。利用者には見せない）
```

`strokes` は `/api/drawings` の `strokes` と同じ形（`[{"pointerType": "mouse", "points": [[x, y, t, pressure], ...]}, ...]`）。dict でも pydantic のモデルでも受け取ります。AI はどこで失敗しても例外を出さず、AI なしの結果に切り替えます。

## 流れ

```
線のデータ
 → 解析エンジン（AI なし、0.3 秒ほど）                       engine.analyze
     誤タップ（とても短い線）を除く                             analysis/strokes.py
     「と」か（形の近い ト・こ・し・て と比べる）               engine.py、refs/
     お手本（KanjiVG）との照合 7 項目                           geometry/
     特徴 20 個（速さ、折り返しの丸み、縦横比、傾き…）          analysis/features.py
     みんなの平均と比べる（偏差）                               analysis/population.py
     印象の 5 軸と、候補 3 つ                                    analysis/axes.py
     特別な書き方（一筆書き、書き順が逆、極端に速い…）         analysis/rare.py
 → AI① 判定（Claude）: 候補 3 つから印象を 1 つ、美しさを採点   llm/client.py judge
 → くつしたを決める: 綺麗さ 5 段階 × 印象 10 種のマス           engine.decide、catalog.py
 → AI② メッセージ（Claude）: 書かれた「と」とくつしたを見て書く llm/client.py comment、llm/prompts.py
```

- 綺麗さ（品質点）＝ お手本との一致度と AI の美しさを、それぞれ「みんなの平均とばらつき」で揃えてから合わせたもの（平均 50）。境界はおよそ 10% / 20% / 40% / 20% / 10% に分かれる位置（`engine.py` の `QUALITY_BOUNDS`）。
- メッセージに「選ばれた」「判定」などの仕組みの言葉が入ったら、1 回だけ書き直させる。それでも入っていたらテンプレートの文（`comments.py`）。

### 印象 10 種（5 本の軸の両端）

| 軸 | 正の端 | 負の端 | 主に見る特徴 |
|---|---|---|---|
| 慎重さ | 丁寧 `teinei` | 雑 `zatsu` | 速さ、書く時間、止め、継ぎ足し |
| 運筆の流れ | 達筆 `tappitsu` | 不器用 `bukiyou` | 速さのむら、途中で止まる回数、ふるえ、画の間 |
| 形の丸み | 可愛い `kawaii` | かっこいい `kakkoii` | 折り返しの丸み、角、直線の割合 |
| 広がり | 暖かい `atatakai` | 冷たい `tsumetai` | 縦横比、ふところの広さ、2 画の間隔 |
| 大胆さ | 個性的 `koseiteki` | 繊細 `sensai` | 傾き、配置のずれ、大きさ、筆圧 |

台帳の `classification.feature`（日本語）との対応は `catalog.py` の `FEATURE_TO_IMPRESSION`。

### レア（特別な書き方のくつした）

台帳にはまだありません。台帳に次の形の項目を足せば、プログラムを変えずに使われます（`feature`・`beauty` の代わりに `special`）。

```json
{ "id": "RARE-01", "level": 7, "rarity": "幻", "name": "片方だけの靴下", "comment": "…",
  "image": "/socks/rare-01.webp", "classification": { "special": "not_to", "review": { "reason": "…" } } }
```

| `special` | 条件（初期値。`analysis/rare.py`） |
|---|---|
| `not_to` | 「と」と読めない |
| `one_stroke` | 一筆で書いた |
| `reversed_order` | 書き順が逆 |
| `many_taps` | 誤タップ・継ぎ足しが 3 つ以上 |
| `masterpiece` | 品質点 95 以上 |
| `very_fast` | 0.6 秒未満 |
| `very_slow` | 8 秒以上 |
| `very_small` | 字がキャンバスの 8% 未満 |
| `very_large` | 字がキャンバスの 95% 以上 |
| `balanced` | どの印象にも偏らない |

レアが台帳に無いあいだは、通常の 50 種から選び、メッセージでその書き方に一言触れます。

## API（分析だけを試す。保存はしない）

| メソッド | パス | 内容 |
|---|---|---|
| POST | `/api/judge/full` | 分析（AI あり） |
| POST | `/api/judge/geometry` | 分析（AI なし） |
| GET | `/api/socks` | くつした 50 種の台帳 |
| GET | `/api/refs/to` | 「と」のお手本の点の並び |
| GET | `/api/dev/playground` | 手書きで分析を試す確認ページ（`DEV=1` のときだけ） |
| POST | `/api/dev/samples` | 調整用のサンプルを保存（`DEV=1` のときだけ） |

送る内容は `/api/drawings` の `canvas` と `strokes` だけ。返る内容は `{sock_id, comment, degraded}`（`DEV=1` のときは `debug` も）。くわしくは `docs/api.md`。

## 調整

「みんなの平均とばらつき」（`analysis/population.json`）は、いまは分析の担当がマウスで書いた 12 件から作った仮のものです。チーム全員の字（できればデモで使う機器）で作り直してください。

1. `DEV=1` で起動する。確定（`/api/drawings`）や確認ページで書くたびに、`back/src/eval_data/requests/` に判定データが残る（Git には入らない）
2. 偏りを見る: `python -m src.judge.tools.diagnose`
3. 平均を作り直す: `python -m src.judge.tools.build_population`（保存したデータを、いまのプログラムで計算し直して作る）

ほかに変えられるところ: 軸の重み `analysis/axes.py`、特別な書き方のしきい値 `analysis/rare.py`、綺麗さの境界 `engine.py`、AI への指示 `llm/prompts.py`。

## 開発（`back/` で）

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt   # macOS/Linux は .venv/bin/python
.venv/Scripts/python -m pytest src/tests
DEV=1 .venv/Scripts/python -m uvicorn src.main:app --port 8000   # 確認ページ: http://localhost:8000/api/dev/playground
```

- `.env`（リポジトリ直下か `back/`）の `ANTHROPIC_API_KEY` を読む。
- リポジトリから動かすと、くつしたの画像を `data/socks/original/` から読んで AI に見せる。

Docker の場合: `docker compose exec backend pip install pytest httpx` のあと `docker compose exec backend python -m pytest src/tests`。

## お手本データ

`refs/*.json` は KanjiVG（CC BY-SA 3.0）から `python -m src.judge.tools.build_refs` で作ったもの。「と」と、「と」ではない判定に使う形の近い字（ト・こ・し・て）。
