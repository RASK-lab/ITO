# ITO ドキュメント

チームで共有する文書の置き場です。GitHub 上でそのまま読めます。

| 文書 | 内容 |
|---|---|
| [development.md](development.md) | 開発の前提と決まりごと（構成、言語、起動方法、進め方） |
| [api.md](api.md) | API の一覧と、送る内容・返る内容 |
| [data.md](data.md) | データの形と置き場所（くつした、書かれた「と」、データベースの表） |
| [socks.md](socks.md) | くつした 50 種のデータ（置き場所、名前の決まり、項目の意味、直し方） |
| [git-conventions.md](git-conventions.md) | ブランチ名とコミットメッセージの決まり |
| [spec/index.html](spec/index.html) | 仕様書（機能ごとに追記していく）。ブラウザで開いて読む |

`docs/local/` は各自の手元だけに置く作業用フォルダで、Git には入りません。

## 文書を足すとき

- 決まりごとが増えたら `development.md` に書く。
- API を足したり変えたりしたら、同じコミットで `api.md` も直す。
- 機能を実装したら `spec/index.html` に節を足し、末尾の変更履歴に 1 行書く。
