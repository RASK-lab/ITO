# 開発の前提と決まりごと

ITO の開発で全員が守る前提をまとめています。変わったらこの文書を直してください。

## 構成

| 場所 | 役割 | 言語 |
|---|---|---|
| `front/` | フロントエンド | TypeScript / React（Vite） |
| `back/` | バックエンド | Python（FastAPI） |
| `infra/` | Docker・Cloudflare・運用の設定 | — |
| `compose.yaml` | ローカル開発環境 | — |
| `data/` | 共有する元データ（くつしたの台帳と元の画像）。くわしくは [socks.md](socks.md) | — |
| `scripts/` | 元データからアプリ用の写しを作り直すコマンド | — |
| `docs/` | 共有する文書 | — |

- 既存のディレクトリ構成をそのまま使う。新しい置き場を作る前に、既存の場所に収まらないかを確かめる。
- `infra/` と `compose.yaml` の変更は、インフラ担当者に相談してから行う。

## 実行環境

- 開発中は、各自の PC の Docker で起動し、`localhost` で確認する。
- 対象は PC のブラウザ（マウス操作）。スマホやタブレットへの対応はあとで考える。
- デプロイ（Cloudflare）はあとで行う。今はローカルで動くことを優先する。

```bash
docker compose up --build -d   # 起動
docker compose ps              # 状態の確認
docker compose logs -f         # ログ
docker compose down            # 停止
```

| 開く場所 | URL |
|---|---|
| 画面 | http://localhost:5173 |
| API | http://localhost:8000 |
| API の一覧（Swagger UI） | http://localhost:8000/docs |

## API

- フロントから API を呼ぶときは、必ず相対パス（`/api/...`）で書く。`http://localhost:8000/...` のような絶対 URL は書かない。デプロイ先でそのまま動かすため。
- 開発中は、Vite が `/api` への通信をバックエンドに中継する（`front/vite.config.ts`）。
- API のパスは `/api/` から始める。
- API の内容は [api.md](api.md) に整理する。足したり変えたりしたら、同じコミットで直す。

## 軽さ

- デザインを入れるまでは、見た目は最小限にする。
- ライブラリは、必要になるまで足さない。足すときは理由を PR に書く。

## 進め方

- 機能は 1 つずつ、部品に分けて実装する。指示された範囲の外は実装しない。
- 実装した機能は [spec/index.html](spec/index.html) に追記する。
- ブランチ名とコミットメッセージは [git-conventions.md](git-conventions.md) に従う。
- API キーなどの秘密の値はコミットしない（`.env` は Git に入らない。ひな形は `.env.example`）。

## 確認コマンド

```bash
docker compose exec frontend npm run lint    # フロントの lint
docker compose exec frontend npx tsc -b      # フロントの型チェック
```

バックエンドのテストと lint はまだ用意していません。
