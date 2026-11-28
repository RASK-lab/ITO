# 学習データ集め

いろいろな人が書いたひらがなの「と」を、学習データとして集める仕組みです。アプリ本体（「と」を書くとくつしたが届く）とは別の画面・別の表に記録します。

- 画面: `https://<公開しているサイト>/#collect`（手元では http://localhost:5173/#collect ）。アプリの最初の画面からはつないでいないので、このアドレスを配る。
- 実装: `front/src/pages/CollectPage.tsx`、`front/src/api/collect.ts`、`back/src/collect.py`、`back/src/db.py`（表 `collect_samples`）、`scripts/export-collect.py`（書き出し）

## 何を学習するためのデータか

どう学習するか（画像だけか、線の特徴も使うか）は、集め終わってから決める。どの方法でも使えるように、線のデータ（位置・時間・筆圧）と画像の両方を残す。

### ラベルの考え方

「良い」「可愛い」を、あとから人が見てラベルにするのではない。**書く人に「◯◯に書いてください」と頼み、その頼み（指示）をそのままラベルにする**。誰かの主観でラベルが揺れない。

| ラベル（`condition`） | 画面に出す指示 | 使いみち |
|---|---|---|
| `natural` | いつもどおりに | 指示なしの、自然な字。「良い」の比べ合い（あとで集める）と、平均的な書き方に使う |
| `teinei` | 丁寧に（ゆっくり、ていねいに） | 印象の分類（10 種） |
| `zatsu` | 雑に（急いで、なぐり書きで） | 〃 |
| `tappitsu` | 達筆に（習字の先生のつもりで、流れるように） | 〃 |
| `bukiyou` | 利き手と反対の手で | 〃（本当に不器用になる） |
| `kawaii` | 可愛く | 〃 |
| `kakkoii` | かっこよく | 〃 |
| `atatakai` | 暖かい感じに（やさしく、ふんわりと） | 〃 |
| `tsumetai` | 冷たい感じに（きっちり、そっけなく） | 〃 |
| `koseiteki` | 個性的に（自由に、崩して） | 〃 |
| `sensai` | 繊細に（細やかに、そっと） | 〃 |

- キーは、分析の印象 10 種のキー（くつしたの決め方）と同じ。学習したモデルを、そのままくつしたの決め方につなげられる。
- 指示の文は「印象の言葉 ＋ 書き方の手がかり」。言葉だけだと受け取り方がばらつき、手がかりだけだと印象の言葉からずれるため。
- 「繊細」に「小さく」を入れていないのは、大きさだけで当てられるラベルにしないため。
- 指示に合わせて演じて書いた字なので、自然に書いた字とは少し違う。

### 「良い」について

「良い」は人によって違うので、ラベルとしては集めない。あとで、`natural` の「と」を 2 つ並べて「どちらが良い『と』か」を大勢に選んでもらい、点数にする（Bradley-Terry）。選ぶ人どうしの一致の度合いも測る。比べ合いの画面はまだない。ほかの人に見せてよいと同意した「と」（`consent_show`）だけを使う。

### 聞かないこと

名前、性別、年齢は聞かない。1 文字から性別や年齢を当てるのは根拠が弱く、当たったように見えても思い込みの再生産になりやすい。個人の情報の扱いも重くなる。

## 1 回の流れ

1. 説明を読み、同意し、2 つの質問に答える（利き手、習字・書道の経験）。答えはブラウザに覚え、次から入った状態で始まる。
2. 「と」を 6 回書く。1 回ごとに「次へ」で送る（途中でやめても、それまでの分は残る）。
   - 最初の 2 回は「いつもどおりに」（指示を見る前の自然な字にするため）。
   - 残りの 4 回は、印象 10 種の指示から、**同じ入力の種類（マウス・指・ペン）で集まった件数の少ないもの**を配る。種類ごとの数がそろう。入力の種類ごとにそろえるのは、たとえば「急いで書いた字はスマホが多い」という偏りがあると、モデルが入力の種類で当ててしまうため。
   - 4 回の順番は無作為。ただし「利き手と反対の手で」は、手を持ちかえるので最後。
   - 書きにくい指示は「飛ばす」で飛ばせる（記録しない）。
3. お礼の画面。「もう 1 回書く」で、別の指示の組み合わせをもう 6 回書ける。

同じブラウザで書いた「と」には、同じ無作為な番号（`writer_id`）が付く。学習で、同じ人の字が学習と評価の両方に入らないように分けるため（書いた人で分けた検証）。

## 記録する内容（表 `collect_samples`）

アプリ本体の表 `drawings` とは分けている。画像は R2（手元ではフォルダ）、それ以外はこの表。

| 列 | 内容 |
|---|---|
| `id` | 記録の ID（英数字 32 文字） |
| `created_at` | 記録した日時（UTC） |
| `protocol` | 集め方の版（いまは `v1`）。指示の文や回数を変えたら上げる。違う版を混ぜて学習しないため |
| `writer_id` | 書いた人の匿名の番号（ブラウザに覚える。名前とは結び付かない） |
| `session_id` | 1 回（6 個）ごとの番号 |
| `trial` | 1 回の中の順番（0〜5） |
| `condition` | 指示（ラベル）。上の表のキー |
| `instruction` | 画面に出した指示の文（サーバーが持つ文を記録する） |
| `dominant_hand` | 利き手（`right`・`left`・`both`・`unknown`） |
| `calligraphy` | 習字・書道の経験（`school` 学校の授業だけ・`lessons` 習っていた・`advanced` 段・師範など・`unknown`） |
| `consent_show` | ほかの人に見せてよいか（1/0）。学習に使うことへの同意がない「と」は、記録しない |
| `pointer_type` | 最初の線の入力の種類（`mouse`・`touch`・`pen`） |
| `display_px` | 書く枠の、画面での一辺（CSS ピクセル）。スマホと PC で書き方が変わるため |
| `device_pixel_ratio` | 画面の画素密度 |
| `redo_count` | 「消去」と「1つ戻る」を押した回数（書き直しの多さ） |
| `target` | 書いた字（`と`） |
| `duration_ms`、`stroke_count`、`point_count` | 書くのにかかった時間、線の本数、点の数（`drawings` と同じ） |
| `image_1024_key`、`image_256_key` | 画像のキー（`collect/<id>_1024.png`、`collect/<id>_256.png`。決まりは `drawings` の画像と同じ） |
| `strokes_json` | 線のデータ（JSON）。`drawings/<id>.json.gz` の中身と同じ形（`target`、`canvas`、`strokes`） |

線のデータを表に直接入れているのは、表だけで書き出せるようにするため。アプリ本体と違い、集めるときは点を 2 万個まで（`MAX_COLLECT_POINTS`）にしているので、1 行が D1 の上限（2MB）を超えない。ふつうの「と」は 100 点前後（約 2KB）。

## 書き出す

```bash
# 手元（リポジトリの直下で）
python scripts/export-collect.py back/data/ito.sqlite3 out/collect

# 本番（D1）。Cloudflare にログインできる人が実行する
cd infra/cloudflare
npx wrangler d1 execute ito-db --remote --json --command "SELECT * FROM collect_samples" > collect.json
cd ../..
python scripts/export-collect.py infra/cloudflare/collect.json out/collect
```

`out/collect/samples.jsonl`（1 行に「と」1 つ。線のデータは `drawing` に展開）と、`summary.txt`（指示 × 入力の種類ごとの件数）ができる。集まり具合は `summary.txt` で確かめる。`collect.json` と `out/` は個人の書いたデータなので、Git に入れない。

## 本番で動かすために（インフラ担当へのお願い）

`infra/` は、インフラ担当と相談してから変える決まりなので、まだ変えていない。本番で集めるには、次の 2 つが必要。どちらも `main` に入れば、`infra/scripts/deploy.sh` がそのまま反映する。

1. D1 に表を作る: `infra/cloudflare/migrations/0002_create_collect_samples.sql` を足す。中身は `back/src/db.py` の `SCHEMA` のうち `collect_samples` の部分（`CREATE TABLE` と `CREATE INDEX`）をそのまま写したもの。
2. Worker がこの表への書き込みを通すようにする: `infra/cloudflare/worker.ts` の `ALLOWED_SQL` に 1 行足す。

```ts
const ALLOWED_SQL = [
  /^\s*INSERT\s+INTO\s+drawings\b/i,
  /^\s*INSERT\s+INTO\s+collect_samples\b/i, // 学習データ集め（back/src/collect.py）
  /^\s*SELECT\b/i,
];
```

R2 の画像（`collect/...`）は、いまの Worker のままで置ける。

## 決まっていないこと

- 「良い」の比べ合いの画面（2 つの `natural` を並べて選ぶ）。
- 送信の回数の制限。いまは誰でも何度でも送れる（同じ回の番号は 30 まで）。いたずらの記録は、書き出したあとに `writer_id` や時間で除く。
- 集めたデータをいつまで残すか。同意の取り消し（いまは `writer_id` を本人が知る方法がない）。
