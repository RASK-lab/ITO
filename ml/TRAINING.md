# 学習用の PC（GPU）で、一から学習するまで

ラベル付けの途中でも、その時点のラベルで最後まで通して動かせる（あとで同じ手順をやり直せば、増えたラベルで学習し直せる）。
くわしい決まりは [README.md](README.md) の「モデル」。

## 全体の流れ

```
[R2 のラベル] ──fetch_labels_r2.py──▶ labels/r2-latest.json ─┐
[Google Fonts・くずし字] ──fetch_*.py, dedupe.py──▶ 画像 ──────┴─ export_dataset.py ─▶ 学習用のデータ
                                                                         │
                                         train.py compare / fit ◀────────┘
                                                   │
                                            model.onnx（本番の CPU で使う）
```

画像は公開データなので、学習用の PC でダウンロードし直す（この PC から写さなくてよい）。

## 0. 学習用の PC に入る

研究室のサーバーなら、たいてい SSH で入る（アドレスとユーザー名は研究室の管理者に聞く）。

```bash
ssh ユーザー名@サーバーのアドレス
nvidia-smi              # GPU が見えるか（RTX 5090 などと出れば OK）
tmux new -s ito         # 接続が切れても動き続けるようにする（戻るときは tmux attach -t ito）
```

Windows の PC を直接使うときは、PowerShell で同じことをする（`tmux` は要らない。下の `source .venv/bin/activate` は `.venv\Scripts\activate`）。

## 1. コードを持ってくる（初回だけ）

```bash
git clone https://github.com/<組織>/<リポジトリ>.git ito
cd ito
git checkout 012-f_develop-Sokinandana-feat_dataset
```

2 回目からは `cd ito && git pull`。

## 2. Python の環境を作る（初回だけ）

Python 3.11〜3.12 を使う（`python3 --version`）。

```bash
python3 -m venv ml/.venv
source ml/.venv/bin/activate          # 以後、このターミナルではこの環境を使う（行の頭に (.venv) と出る）
# GPU 用の PyTorch を先に入れる。RTX 5090・Blackwell は CUDA 12.8 以上の版（cu128）が要る
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
pip install -r ml/requirements-train.txt
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"   # True と GPU の名前が出れば OK
```

## 3. 画像をそろえる（初回だけ。数分）

```bash
python ml/tools/fetch_google_fonts.py
python ml/tools/fetch_kuzushiji.py
python ml/tools/dedupe.py              # 同じ画像を除く（28 枚）
```

## 4. R2 の鍵を置く（初回だけ）

もらった鍵を、`ml/r2.env` というファイルに書く（`nano ml/r2.env` などで作る）。

```
R2_ACCOUNT_ID=<Cloudflare のアカウント ID>
R2_ACCESS_KEY_ID=<アクセスキー ID>
R2_SECRET_ACCESS_KEY=<シークレットアクセスキー>
R2_BUCKET=ito-drawing
```

- もらった情報に「S3 API のエンドポイント」（`https://〜.r2.cloudflarestorage.com`）があれば、
  `R2_ACCOUNT_ID` の代わりに `R2_ENDPOINT=<そのアドレス>` と書いてもよい。
- **鍵はパスワードと同じ**。チャット・Git・画面の共有に出さない。`ml/r2.env` は Git に入らない設定にしてある。
- 他人も使うサーバーなら `chmod 600 ml/r2.env`（自分だけ読めるようにする）。

## 5. 毎回: ラベルを取ってきて、学習用のデータにする

```bash
python ml/tools/fetch_labels_r2.py                              # → ml/data/labels/r2-latest.json
python ml/tools/export_dataset.py --labels ml/data/labels/r2-latest.json
```

最後に、クラスごと・データごとの枚数が出る。

## 6. 学習する

```bash
python ml/tools/train.py bench --int8          # 候補ごとの大きさと CPU の時間（初回だけでよい）
python ml/tools/train.py compare --workers 8   # 4 候補の比較。ml/runs/<日時>-compare/report.md を見る
python ml/tools/train.py fit --backbone <compare でよかったもの> --unfreeze 1 --int8 --workers 8
```

- 初回は、学習済みの重み（数十〜数百 MB）を自動でダウンロードする。
- compare の結果の見方: `macro-F1` が高いほどよい。4 クラスならでたらめで約 0.25。
  `google_fonts` の列（本番の入力に近い）を重く見る。差が小さければ、軽いモデル（resnet18）を選ぶ。
- fit の結果: `ml/runs/<日時>-fit-<モデル>/` に `report.md`（成績）、`model.onnx`・`model.int8.onnx`（本番用）。
- ラベルが少ないうちは成績がぶれる（特に、数の少ないクラス）。通して動くことの確認と思って見る。

## 7. 結果を手元に持ってくる

手元の PC（Windows の PowerShell など）で:

```bash
scp -r ユーザー名@サーバーのアドレス:ito/ml/runs/<日時>-fit-<モデル> .
```

推論を試す:

```bash
python ml/tools/train.py predict ml/runs/<日時>-fit-<モデル>/model.onnx 画像.png
```

## うまくいかないとき

| 出たもの | 直し方 |
|---|---|
| `torch.cuda.is_available()` が False | GPU 用でない PyTorch が入っている。2 の `--index-url ...cu128` の行をやり直す |
| `no kernel image is available` | PyTorch が古い（5090 に未対応）。cu128 以上の版を入れ直す |
| `CUDA out of memory` | `--batch 32` などに減らす |
| `R2 の設定が足りません` | `ml/r2.env` の名前・場所を確かめる（`ml/` の中） |
| `AccessDenied`・`SignatureDoesNotMatch` | 鍵の写し間違い（前後の空白など）か、鍵に `ito-drawing` を読む権限がない |
| `書き出したデータがありません` | 5 をやる |
| `学習に使える行がありません` | ラベルがまだ無い（または全部「どれとも言えない」など） |
