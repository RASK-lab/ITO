# API の一覧

ITO にある API を、1 枚で見渡すための一覧です。送る内容と返る内容のくわしい形は [api.md](api.md) にあります。

- API を足したり変えたりしたら、同じコミットでこの一覧と `api.md` を直す。
- フロントからは、必ず相対パス（`/api/...`）で呼ぶ。
- 起動中は、実装されている API を http://localhost:8000/docs でも確かめられる（機械が読む形は http://localhost:8000/openapi.json ）。

最終更新: 2026-11-28

## 1. 実装済み（このブランチで動くもの）

| メソッド | パス | 何をするか | 呼ぶ側 | 実装 | 状態 |
|---|---|---|---|---|---|
| GET | `/api/health` | バックエンドが動いているかの確認 | 確認用（画面からは呼ばない） | `back/src/main.py` | 動く |
| POST | `/api/drawings` | 書いた「と」（線のデータ、画像、ユーザーネーム）を受け取って保存し、結果（くつしたとメッセージ）を返す | 書く画面の「確定」（`front/src/api/drawings.ts`） | `back/src/drawings.py` | 動く。結果は仮（無作為のくつした）。保存先は手元の代わり |
| PUT | `/api/drawings/{id}/card` | 結果 1 件ぶんの、X のカード用の画像（1200 × 630 の JPEG）を預かり、シェア用のページのパスを返す | シェアの画面を開いたとき（`front/src/api/share.ts`） | `back/src/share.py` | 動く（手元で確認。本番では未確認） |
| GET | `/api/cards/{id}.jpg` | 預かったカードの画像を返す | X などのロボット（シェア用のページに書いた `og:image`） | `back/src/share.py` | 同上 |
| GET | `/api/share/{id}` | 結果 1 件ぶんの、シェア用のページ（HTML）。カードの指定（OGP）が書いてある。人が開くと最初の画面に移る | X に投稿されたアドレス。X などのロボットと、投稿を見た人 | `back/src/share.py` | 同上 |
| GET | `/api/label/config` | 学習データのラベル付けの設定（印象の種類） | ラベル付けの画面（`front/public/label/index.html`、アドレスは `/label/`） | `back/src/labeling.py` | 動く |
| GET | `/api/label/next` | 次にラベルを付ける画像（合言葉が要る。以下同じ） | 同上 | 同上 | 動く |
| POST | `/api/label/labels` | ラベルを 1 つ記録する（R2 に置く） | 同上 | 同上 | 動く |
| GET | `/api/label/mine`、`/api/label/stats`、`/api/label/export` | 自分が付けたラベル、集計、すべてのラベルの書き出し | 同上、`ml/tools/export_dataset.py` | 同上 | 動く |

くわしい形: ラベル付けは [ml/README.md](../ml/README.md)、[api.md の POST /api/drawings](api.md#post-apidrawings)、[api.md の「シェア」](api.md#シェア結果ごとのカード)

## 2. 分析側のブランチにあるもの（まだ取り込んでいない）

ブランチ `001-f_develop-Sokinandana-feat_judge` で確かめた内容です（2026-11-28 時点）。取り込むまでに変わる可能性があります。フロントからは、いまは呼んでいません。

| メソッド | パス | 何をするか | 送る内容 | 返る内容 |
|---|---|---|---|---|
| POST | `/api/judge/full` | 線の解析と、AI による判定 | `{canvas, strokes}`（線の形は `/api/drawings` と同じ） | `{sock_id, comment, degraded}` |
| POST | `/api/judge/geometry` | AI を使わない判定 | 同上 | 同上 |
| GET | `/api/socks` | くつした 50 種の一覧 | — | くつしたの配列 |
| GET | `/api/refs/to` | 「と」のお手本の点の並び | — | 点の並び |
| — | `/api/dev/*` | 開発用の確認ページなど（`DEV=1` のときだけ） | — | — |

つなぎ方の案: フロントは `/api/drawings` だけを呼び、その中から分析の処理を直接呼ぶ（`back/src/drawings.py` の `make_result()` を差し替える）。`/api/judge/*` をフロントから直接呼ぶかどうかは、分析の担当と決める。

## 3. バックエンドが Worker に頼む口（本番だけ。仮）

ブラウザからは呼びません。バックエンド（コンテナ）が、保存のために Worker へ送る通信です。環境変数 `ITO_STORE_URL` があるときだけ使います。Worker 側はまだ実装されていません。形はインフラの担当と合わせて決めます。

| メソッド | パス | 何をするか | 本文 | 呼ぶ側 |
|---|---|---|---|---|
| PUT | `<ITO_STORE_URL>/objects/<キー>` | R2 にファイルを置く | ファイルの中身 | `back/src/storage.py` |
| DELETE | `<ITO_STORE_URL>/objects/<キー>` | R2 から消す（無くても成功） | なし | `back/src/storage.py` |
| GET | `<ITO_STORE_URL>/objects/<キー>` | R2 から読む（無ければ 404）。カードの画像を返すときと、あるかを確かめるときに使う | なし | `back/src/storage.py` |
| POST | `<ITO_STORE_URL>/db/query` | D1 で SQL を実行する。`INSERT INTO drawings …` と `SELECT …` だけ。返事は `{"results": [行, …]}` | `{"sql": "…", "params": […]}` | `back/src/db.py` |

くわしい説明: [data.md の「本番での保存先の切り替え」](data.md)

## 4. まだないもの（作る予定、または決めること）

| 何のための API か | 使う画面 | 決めること |
|---|---|---|
| 保存した「と」の一覧を返す | いろんな「と」を見る | 公開してよい記録の選び方、画像を配る URL、ページ分け |
| 1 件の結果を取り直す | 結果の画面（再読み込みしても残す場合） | ID をアドレスに入れるか |
| くつしたの一覧を返す | くつした一覧 | 分析側の `GET /api/socks` を使うか、静的なファイルにするか |
| ユーザーネームを変える | 書く画面の右上（あとで実装） | サーバーに持つか、ブラウザだけで持つか（いまはブラウザだけ） |
