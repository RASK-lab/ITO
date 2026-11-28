# ITO ドキュメント

チームで共有する文書の置き場です。GitHub 上でそのまま読めます。

| 文書 | 内容 |
|---|---|
| [status.md](status.md) | いまの実装の状況（引き継ぎ用）。何ができていて、何が仮で、どこにつなぐか。最初に読む |
| [development.md](development.md) | 開発の前提と決まりごと（構成、言語、起動方法、進め方） |
| [api-list.md](api-list.md) | API の一覧（1 枚で見渡す。実装済み、ほかのブランチ、Worker に頼む口、まだないもの） |
| [api.md](api.md) | 実装済みの API の、送る内容・返る内容のくわしい形 |
| [data.md](data.md) | データの形と置き場所（くつした、書かれた「と」、データベースの表） |
| [../ml/README.md](../ml/README.md) | 印象分類の学習データ（入手したデータ、4 人でのラベル付け、書き出しの形、前処理） |
| [socks.md](socks.md) | くつした 50 種のデータ（置き場所、名前の決まり、項目の意味、直し方） |
| [git-conventions.md](git-conventions.md) | ブランチ名とコミットメッセージの決まり |
| [spec/index.html](spec/index.html) | 仕様書（機能ごとに追記していく）。ブラウザで開いて読む |

`docs/local/` は各自の手元だけに置く作業用フォルダで、Git には入りません。

## 文書を足すとき

- 決まりごとが増えたら `development.md` に書く。
- API を足したり変えたりしたら、同じコミットで `api.md` も直す。
- 機能を実装したら `spec/index.html` に節を足し、末尾の変更履歴に 1 行書く。
