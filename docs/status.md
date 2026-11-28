# いまの実装の状況（引き継ぎ用）

フロントとバックエンドの基本機能（ブランチ `004-f_develop-otoham-feat_base`）で、何ができていて、どこに何があり、何が仮で、何が残っているかをまとめた文書です。別の担当や、その担当が使う AI エージェントが、最初に読むことを想定しています。

最終更新: 2026-11-28

## 30 秒でつかむ

- ITO は、利用者がひらがなの「と」を書くと、その字に合った「くつした」とメッセージを返すアプリ。
- 画面は 4 つ動く: 最初の画面 → 書く画面 → 待機中 → 結果（くつしたとメッセージ）。
- 「確定」を押すと、線のデータと画像がバックエンドに送られ、保存される。
- **くつしたとメッセージは分析（`back/src/judge`）が作る**。書かれた「と」の綺麗さ（5 段階）と印象（10 種）でくつしたを選び、AI（Claude）がメッセージを書く。AI ありで 3〜11 秒。API キーが無いときは AI なしで動く。
- **保存先は手元の代わり**（フォルダと SQLite）。本番では Worker 経由で R2 と D1 に切り替える。切り替えの口はバックエンド側だけ用意済みで、Worker 側はまだない。
- 動作のテストは、途中から意図的に省いている（速度優先）。確かめていない点は末尾にまとめた。

## 動かし方

```bash
docker compose up --build -d
# 画面: http://localhost:5173   API: http://localhost:8000   API の一覧: http://localhost:8000/docs
```

## 画面の流れ

| 画面 | アドレス | ファイル | 内容 |
|---|---|---|---|
| 最初の画面 | `/` | `front/src/pages/StartPage.tsx` | ユーザーネームを入れて「手紙を書く」。空でも進める（空なら `User`）。15 文字まで |
| 書く画面 | `/#write` | `front/src/pages/WritePage.tsx`、`front/src/components/WritingCanvas.tsx` | 枠に「と」を書く。「消去」「1つ戻る」「確定」。左上に、最初の画面へ戻るボタン（開発中の近道） |
| 待機中 | `/#write` のまま | `front/src/pages/WaitingPage.tsx` | 文を 1 行出すだけ。最低 1.5 秒 |
| 結果 | `/#write` のまま | `front/src/pages/ResultPage.tsx` | くつしたの画像、メッセージ 1 行、「もう一度」 |

- 画面の切り替えは `front/src/App.tsx`（ライブラリなし。アドレスの `#` で切り替え）。
- ユーザーネームは、ブラウザに覚える（`front/src/userName.ts`。`localStorage`）。
- 再読み込みで残るのは、ユーザーネームと「書く画面にいたこと」だけ。書きかけの線と結果は残らない。
- 見た目は最小限（`front/src/index.css`）。デザインはこれから入れる。対象は PC のブラウザ。

## 確定で送る内容と返る内容

`POST /api/drawings`（フロントからは相対パス。`front/src/api/drawings.ts`）。くわしくは [api.md](api.md)。

送る内容:

```json
{
  "user_name": "トークン永田",
  "target": "と",
  "canvas": { "width": 1024, "height": 1024 },
  "strokes": [
    { "pointerType": "mouse", "points": [[231.3, 319.2, 0, 0.5], [232.1, 320.3, 3, 0.5]] }
  ],
  "image": "data:image/png;base64,…",
  "width": 1112,
  "height": 1112
}
```

- `points` の 1 点は `[x, y, t, 筆圧]`。x, y は枠を 1024 × 1024 とみなした座標（小数 1 桁）。t は最初の線を書きはじめた瞬間を 0 とした経過ミリ秒（整数）。筆圧は 0〜1（マウスは 0.5）。
- `pointerType` は、線ごとに `mouse` / `touch` / `pen`。
- 線は、押してから離すまでが 1 本。消した線は送らない。点の合計は 20 万個まで。
- `image` は、フロントが線から描いた白地に黒の PNG。一辺は 1024 以上 4096 以下の正方形。
- 分析側の資料の形（`{target, intent, canvas, strokes}`）に合わせてある。`intent` は送っていない（ITO に入れるか未定）。

返る内容（201）:

```json
{
  "id": "b9d693587968457e8264707d0a59e2f2",
  "created_at": "2026-11-28T05:41:36+00:00",
  "sock": { "id": "WORN-09", "name": "子うさぎの靴下", "image": "/socks/worn-09.webp" },
  "message": "あなたの「と」に、くつした「子うさぎの靴下」が届きました。"
}
```

## 確定のときにバックエンドがすること

`back/src/drawings.py` の `create_drawing`。

1. 中身を確かめる（形、範囲、画像が PNG か、申告した大きさと合うか）。
2. 結果を作る（`make_result()`。分析 `src.judge.service.judge_sync` を呼んで、くつしたとメッセージを決める）。
3. 画像を白黒 1 チャネルにして、1024 × 1024 と 256 × 256 を作る（Pillow）。
4. 置き場に 3 つ置く（`back/src/storage.py`）。
5. 台帳に 1 行書く（`back/src/db.py`）。
6. 途中で失敗したら、置いたものを消して 500 を返す。

保存されるもの（くわしくは [data.md](data.md)）:

| キー | 中身 |
|---|---|
| `drawings/<id>_1024.png` | 白黒 1 チャネル、1024 × 1024 |
| `drawings/<id>_256.png` | 白黒 1 チャネル、256 × 256（枠全体をそのまま縮小） |
| `drawings/<id>.json.gz` | `{target, canvas, strokes}` を gzip で圧縮したもの |
| 台帳 `drawings` の 1 行 | id、created_at、上の 3 つのキー、target、duration_ms、stroke_count、point_count、sock_id、message、user_name |

## くつした

50 種の静的データ。くわしくは [socks.md](socks.md)。

| 場所 | 中身 |
|---|---|
| `data/socks/socks.json` | 台帳（正。人が編集するのはここだけ） |
| `data/socks/original/` | 元の PNG 50 枚（学習用。加工しない） |
| `front/public/socks/` | 表示用の WebP 50 枚（写し。`/socks/worn-01.webp` で配られる） |
| `back/src/resources/socks.json` | バックエンド用の写し |
| `scripts/build-socks.sh` | `data/socks/` から写しを作り直す |

- ID は `WORN-01` の形。系統 6 つ（WORN、DAILY、CRAFT、REGAL、HEIR、APEX）が、段階 1〜6 とレア度に対応する。
- 字の印象 10 種 × 綺麗さ 5 段階の 50 通りに、くつしたが 1 つずつ割り当ててある。

## 担当ごとの「つなぐ場所」

### 分析（つないだ。くわしくは `back/src/judge/README.md`）

- `back/src/drawings.py` の `make_result(drawing)` が、分析の入口 `src.judge.service.judge_sync` を呼んでいる。
- フロントは、これまでどおり `POST /api/drawings` だけを呼ぶ。応答の `sock` と `message` をそのまま表示する。
- 点の上限は `/api/drawings` と同じ（点の合計 20 万個）。上限いっぱいでも、AI を除く分析は 1.5 秒ほど。
- AI に使う時間は合計 11 秒まで（`JUDGE_AI_BUDGET_S`）。フロントの打ち切り（15 秒）より短い。
- くつしたの台帳は、分析も `back/src/resources/socks.json` を使う（分析側の写しは消した）。
- `message` は AI が書く 2〜3 文（100〜150 字ほど）。結果の画面は一行を想定しているので、見せ方を合わせたい（フロント）。
- AI の API キー（`ANTHROPIC_API_KEY`）がないと AI なしで動く。Docker のコンテナと本番に渡す方法は、下のインフラの担当へ。

### インフラの担当へ

- **保存先の切り替えは、環境変数 `ITO_STORE_URL` 1 つ**。なければ手元のフォルダと SQLite、あれば Worker に HTTP で頼む。
- バックエンドが Worker に頼む口（仮。合わせて決めたい）。どれも成功なら 2xx:

| メソッドとパス | 本文 | Worker がすること |
|---|---|---|
| `PUT <ITO_STORE_URL>/objects/<キー>` | ファイルの中身 | R2 に置く |
| `DELETE <ITO_STORE_URL>/objects/<キー>` | なし | R2 から消す（無くても成功） |
| `POST <ITO_STORE_URL>/db/query` | `{"sql": "INSERT … VALUES (?, …)", "params": […]}` | D1 で実行する |

- D1 の表は `back/src/db.py` の `SCHEMA` で作る。
- 伝えておきたい点:
  - コンテナのファイルは眠ると消えるので、R2 と D1 につなぐまで、本番では記録が残らない。
  - 1 回の送信は、ふつうの「と」で約 55KB、上限いっぱいで最大約 32MB。上限いっぱいのとき、バックエンドは 1 件で 200MB 前後のメモリを一時的に使う。
  - 依存に `pillow` が増えた。`back/requirements.txt` は版を固定していない。バックエンドは新しめの FastAPI の機能（経路ごとの本文の上限）を使う。
  - 本番でも、`/api/` をバックエンドに届ける必要がある（手元では Vite が中継している）。
  - くつしたの画像は `front/public/socks/` にあり、フロントのビルドに一緒に入る。
- 分析（AI）のための設定（くわしくは `back/src/judge/settings.py` の先頭と `.env.example`）:
  - `ANTHROPIC_API_KEY`（秘密の値）: コンテナに渡す。無いと AI なしで動く。手元の Docker では、`compose.yaml` の backend に `env_file: .env` を足せば渡る（相談したい）。本番は Worker の secret からコンテナの環境変数に渡す。
  - `SOCK_IMAGE_BASE_URL`: 本番で公開しているサイトの URL（例: `https://hackathon-ito-app.<アカウント>.workers.dev`）。AI がくつしたの画像（`/socks/*.webp`）を読みに行くのに使う。無くても動く（くつしたの説明文だけで書く）。
  - コンテナから `api.anthropic.com`（または AI Gateway）へ外に出られる必要がある。
  - 依存に numpy・scipy・anthropic などが増えた（`back/requirements.txt`、版は固定）。イメージが少し大きくなる。

### フロントとデザインの担当（このブランチの続き）

- デザインは未着手。世界観の調査とカラーパレットの候補は、ブランチ `003-f_feature01-otoham-docs_worldview` にある。
- 残っている画面と機能は、[spec/index.html](spec/index.html) の「機能の一覧」を参照。

## 仮のもの・決まっていないこと

| 項目 | いま | 決めること |
|---|---|---|
| メッセージの見せ方 | AI が書く 2〜3 文を、結果の画面に一行として出している | 複数の文の見せ方（フロント） |
| 分析の調整 | 「平均的な書き方」は分析の担当がマウスで書いた 12 件から作った仮のもの | チーム全員の字（できればデモで使う機器）で作り直す（`back/src/judge/README.md` の「調整」） |
| 保存先 | 手元のフォルダと SQLite | Worker の口の形、R2 と D1 の用意 |
| 画像を誰が描くか | フロントが描いて送る | サーバーが線から描く形にするか |
| お題の字と意図 | 字は「と」固定、意図は送らない | ITO に入れるか |
| 結果の再読み込み | 書く画面に戻る | 結果を残すか（ID をアドレスに入れて取り直すなど） |
| 書いた「と」の公開 | していない（`is_public` は 0 のまま） | 「いろんな『と』を見る」の作り方、画像を配る URL |
| ユーザーネームの変更 | 最初の画面に戻って直す | 書く画面の右上から変えられるようにする（あとで実装） |
| 送信の回数の制限、認証 | なし | 本番に出す前に決める |

## 確かめていないこと

速度を優先して、途中から動作のテストを省いています。次は、コードを読んだだけ、または lint・型チェック・読み込みの確認だけです。

- 待機中の画面と結果の画面の一連の流れ（確定 → 待機中 → 結果 → もう一度）。
- 失敗したときに、線を残したまま書く画面に戻ること。
- 書く画面の左上の「戻る」ボタン。
- 最初の画面で、名前を空のまま進む流れと、Enter キーで進む流れ。
- `ITO_STORE_URL` を設定したときの保存（Worker 側の口がまだないため）。
- 実際のデプロイ。
- 送る形を切り替えたあとの回帰の一部（右クリック、送信中は書けない、15 秒の打ち切り、上限 20 万点での画面の動き、保存の途中の失敗、同時の確定）。切り替える前には、どれも確認済み。
- Chrome 以外のブラウザ、実機のペンと指。

## 文書の一覧

| 文書 | 内容 |
|---|---|
| [development.md](development.md) | 開発の前提と決まりごと |
| [api-list.md](api-list.md) | API の一覧 |
| [api.md](api.md) | API のくわしい形 |
| [data.md](data.md) | データの形と置き場所、本番での切り替え |
| [socks.md](socks.md) | くつしたのデータ |
| [spec/index.html](spec/index.html) | 仕様書（機能ごと。ブラウザで開く） |
| [git-conventions.md](git-conventions.md) | ブランチ名とコミットメッセージ |
