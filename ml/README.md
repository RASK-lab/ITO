# 「と」の印象分類の学習データ

書かれた「と」の**画像だけ**から印象を分類するモデルを学習するための、データ集め・ラベル付け・書き出しの仕組みです。

- 正解は「見た人がどう感じたか」。チーム 4 人で、同じ画像にそれぞれラベルを付ける。
- 入力は画像だけ。書く速さ・書き順・解析エンジンの特徴（`back/src/judge`）は使わない（凍結）。
- 学習データと本番の入力の見た目をそろえるため、画像はすべて同じ前処理（`ito_ml/preprocess.py`）を通す。本番でも、利用者の画像を同じ関数に通してからモデルに渡す。

## 入手できたデータ（2026-11-28）

| データ名 | 中身 | 枚数 | 入手 | ライセンス・注意 |
|---|---|---|---|---|
| `google_fonts` | Google Fonts の日本語フォント（68 ファミリーの全部の太さ） | **187** | `tools/fetch_google_fonts.py`（自動） | OFL など。Google の雰囲気のタグ（Cute など 20 種）も `meta.tags` に入れてある。変体仮名のフォント 2 つ（Yuji Hentaigana）は「と」の位置に別の字形が入っている（`meta.variant_glyph`） |
| `kuzushiji49` | 古典籍のくずし字（Kuzushiji-49）の「と」 | **7,000** | `tools/fetch_kuzushiji.py`（自動） | CC BY-SA 4.0（出典の表示が必要）。28 × 28 を拡大したのでぼやける。筆の字で、形の違う変体仮名も混ざる。ラベル付けは後回しの設定 |
| `etl` | ETL 文字データベース（産総研）の手書き | 約 830 の見込み（ETL4: 120、ETL7: 350、ETL8: 160、ETL9: 200） | 利用の登録が必要 → `tools/import_etl.py` | まだ入手していない。読み込みは仕様に合わせて作ったが、実物では未確認 |
| `collect` | アプリで集めた手書き（`#collect`） | 集まった分 | 本番の D1 から書き出す → `tools/import_collect.py` | 書いた人が学習への利用に同意済み。チームの外に配らない |
| `local_fonts` | 手元のフォントファイル | — | `ml/data/sources/local_fonts/` に置く → `tools/import_local_fonts.py` | ライセンスを確かめてから置く。Windows・Office のフォントは条件が個別に違うので、チームで判断 |

調べたが使っていないもの: 東京農工大の手書きデータ（HANDS。メールで購入の申し込みが必要）、古典籍くずし字の元の解像度のデータ（容量が大きい）。

## 準備（リポジトリの直下で）

```bash
python -m pip install -r ml/requirements.txt     # numpy、pillow（バックエンドの .venv にも入っている）
python ml/tools/fetch_google_fonts.py             # 約 2 分
python ml/tools/fetch_kuzushiji.py                # 約 75MB をダウンロード
# ETL や集めた手書きが手に入ったら
python ml/tools/import_etl.py
python ml/tools/import_collect.py out/collect/samples.jsonl
```

できるもの（`ml/data/`。Git には入れない）:

```
ml/data/
  sources/<データ名>/          ダウンロードした元のデータ
  images/<データ名>/<id>.png   前処理した画像（256 × 256、白地に黒）
  manifests/<データ名>.jsonl   1 行に 1 枚（id、画像、データ名、まとまり、種類、ライセンス、meta）
  labels.sqlite3               ラベルの記録
  export/<日時>/               学習に使う形に書き出したもの
```

取り込みのスクリプトは、何度実行しても同じ結果になります（データ名ごとに台帳を作り直す。画像の id は変わらないので、付けたラベルは残る）。

## ラベル付け

ふだんは**本番のアプリの `/label/`**（例: `https://<公開しているサイト>/label/`）で付ける。どこからでも、スマホからでも付けられる。

| | 本番の `/label/` | 手元のサーバー |
|---|---|---|
| 使う場面 | ふだん。外から、人を集めて | 公開できない画像（ETL、アプリで集めた手書き）に付けるとき、ネットがないとき |
| 画像 | Google Fonts、くずし字（公開してよいものだけ） | `ml/data/manifests` のすべて |
| 入り方 | 名前（自由に入れる）と合言葉 | 名前だけ（同じネットワークの中だけで使う） |
| ラベルの置き場 | R2 の `labels/<label_set>/`（`back/src/labeling.py`） | `ml/data/labels.sqlite3` |

画面（`front/public/label/index.html`）と、次の画像の選び方・集計（`back/src/labeling_core.py`）は共通。

### 始める前に決めること

`labeling/config.json` の `classes`（印象の種類）。いまは仮に **可愛い／かっこいい／丁寧／個性的** の 4 種と、「どれとも言えない」「「と」に見えない」にしてある。

付け始めてから種類を変えるときは、`label_set` を `v2` などに上げる（前の種類で付けたラベルと混ざらない）。

### 本番に出す・変える

`config.json` を直したとき、画像を足したとき、合言葉を変えるときは、次を実行してコミットし、デプロイする。

```bash
python ml/tools/build_label_site.py --passcode <合言葉>   # 合言葉を変えないなら --passcode は付けない
```

- `front/public/label/img/`（表示用の画像。公開してよいデータだけ）、`back/src/resources/label_items.json`（画像の一覧）、`back/src/resources/label_config.json`（設定と合言葉の SHA-256）ができる。
- 合言葉そのものは保存しない。ラベルを付ける人に口頭などで伝える。
- 環境変数 `LABEL_PASSCODE` をコンテナに渡すと、そちらが優先される（インフラの設定が要る。いまは使っていない）。
- Worker・D1 の設定は変えずに動く（ラベルは R2 に置く）。

### 手元のサーバーで動かす

```bash
python ml/labeling/server.py
```

表示された `http://<IP>:8765` を、同じ Wi-Fi の PC・スマホで開く。

- 画像を見て、印象にいちばん近いものを**直感で 2〜3 秒で**選ぶ。数字キーでも選べる。`Backspace` で 1 つ戻って付け直せる。
- どのデータ（フォントか手書きか）かは表示しない（先入観を避けるため）。
- 1 枚に 4 人ずつ付ける（`target_ratings`。くずし字だけは 2 人）。付ける人が増えたら、数を増やしてもよい。ほかの人が付け始めた画像が先に出るので、全員の分がそろった画像から増えていく。
- 「集計」で、人ごとの数、データごとの進み具合、2 人ずつの一致率、Fleiss の κ を見られる。一致の度合いが低いラベルは、意味をすり合わせてから続ける。
- 目安: 1 枚 2〜3 秒なら、フォント 187 枚で 1 人 10 分、ETL 約 830 枚で 1 人 40 分。

### 注意

- 手元のサーバーには合言葉がない。会場・研究室のネットワークの中だけで使う。
- `ml/data/labels.sqlite3` はこの PC にしか無い。ときどき写しをとる（書き出しでもよい）。
- 本番のラベルは R2 にある。`label_set` を変えると、別の置き場（`labels/v2/`）になる（前のラベルは消えない）。

## 書き出す

```bash
# 本番で付けたラベルを取り出す（合言葉が要る）
curl -H "X-Label-Passcode: <合言葉>" https://<公開しているサイト>/api/label/export > labels.json
# 手元のラベル（ml/data/labels.sqlite3）と合わせて書き出す
python ml/tools/export_dataset.py --labels labels.json --copy-images   # ml/data/export/<日時>/
```

| ファイル | 中身 |
|---|---|
| `dataset.csv` | 1 行に画像 1 枚。`image`、`source`、`group`、`split`（train/val/test）、`votes_<ラベル>`（選んだ人数）、`label`（多数決。決まらなければ空）、`agreement`、`n_invalid`、`meta` |
| `labels_raw.csv` | 1 行にラベル 1 つ（画像、付けた人、ラベル、かかったミリ秒、日時） |
| `meta.json` | ラベルの種類、前処理の版、件数、ライセンスの一覧 |
| `images/` | 画像（`--copy-images` のとき） |

- `split` は `group`（同じフォントの太さ違い、同じ人の字）ごとに決まる。同じフォント・同じ人の字が、学習と評価の両方に入らない。データを足しても、すでにある画像の側は変わらない。
- 書き出したフォルダは、まるごと研究室の GPU のマシンに写せば使える。ETL・集めた手書きを含むので、チームの外には配らない。

PyTorch で読む例（`ito_ml/dataset.py`）:

```python
import sys; sys.path.insert(0, "ml")
from ito_ml.dataset import ToDataset
train = ToDataset("ml/data/export/20261128-200000", split="train", soft=True)
x, y = train[0]   # x: 1×256×256（0〜1）、y: 人数の割合（soft=True）かクラスの番号
```

## 前処理（学習と本番で同じにする）

`ito_ml/preprocess.py` の `normalize`:

1. 白黒にし、背景が暗い画像（ETL、くずし字）は反転して白地に黒にそろえる。
2. 字の部分だけを切り出し、縦横の比を保って余白 12% の正方形に置く。
3. 256 × 256 にする。

位置と大きさの違いは消す。線の太さ・かすれ・筆の形は残す（印象の手がかりなので）。

- フォントは 512 ピクセルの大きさで描いてから整える。
- 集めた手書きは、線のデータから一定の太さ（枠の 2%）で描き直す（`render_strokes`）。アプリでブラシの種類と太さを選べるようにしたら、**アプリと同じ描き方をここにも入れ**、学習データ・本番の両方で同じブラシの画像にする。
- 前処理を変えたら `PREPROCESS_VERSION` を上げ、取り込みをやり直して学習し直す。

## テスト

```bash
python -m pytest ml/tests
```
