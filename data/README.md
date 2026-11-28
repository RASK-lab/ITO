# data — 元データの置き場

アプリが使う、あらかじめ用意したデータの「正」を置く場所です。Git で管理します。

| 場所 | 中身 |
|---|---|
| `socks/socks.json` | くつした 50 種の台帳（名前、説明、分類）。人が編集するのはここだけ |
| `socks/original/` | くつしたの元の画像（PNG、512 × 512、背景は透明）。学習にも使うので加工しない |

## 写し

フロントとバックエンドのコンテナからは、この `data/` を直接読めません。そのため、ここから作った「写し」をそれぞれの中に置いています。

| 写し | 元 | 使うところ |
|---|---|---|
| `front/public/socks/*.webp` | `socks/original/*.png` を軽い WebP に変換したもの | 画面（`/socks/worn-01.webp` で見える） |
| `back/src/resources/socks.json` | `socks/socks.json` をそのままコピーしたもの | バックエンド |
| `front/public/share/*.jpg`、`front/public/s/*/index.html` | 台帳と元の画像から作った、シェア用のカード画像とページ | X などに投稿されたアドレスのカード |

写しは手で編集しません。`data/socks/` を直したら、次のコマンドで作り直し、元データと写しを同じコミットに入れます。

```bash
scripts/build-socks.sh   # cwebp（brew install webp）と Pillow（pip install pillow）が必要
```

項目の意味や、くつしたを足す・差し替える手順は [docs/socks.md](../docs/socks.md) にあります。

なお、`back/data/` は別のものです（バックエンドが動いている間に書き込む場所で、Git には入りません）。
