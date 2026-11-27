# ITO

## 開発環境

- Frontend: TypeScript / React / Vite
- Backend: Python / FastAPI
- Environment: Docker Compose
- Version Control: Git / GitHub

## 必要なツール

- Git
- Docker Engine または Docker Desktop
- Docker Compose
- VSCode（推奨）

ホスト環境へのPython・Node.jsのインストールは不要です。

## ディレクトリ構成

- `front/`: フロントエンド
- `back/`: バックエンド
- `infra/`: Docker・Cloudflare・運用設定
- `compose.yaml`: ローカル開発環境

## 開発環境の起動

リポジトリをcloneし、リポジトリ直下で以下を実行してください。

```bash
docker compose up --build -d
```

### アクセス先

- Frontend: http://localhost:5173
- Backend: http://localhost:8000
- Swagger UI: http://localhost:8000/docs

## 基本コマンド

```bash
# 起動
docker compose up -d

# 再ビルド
docker compose up --build -d

# 状態確認
docker compose ps

# ログ確認
docker compose logs -f

# 停止
docker compose down
```

## 開発ルール

- mainブランチから機能ごとのブランチを作成する。
- フロントエンドはfront/で開発する。
- バックエンドはback/で開発する。
- infra/やcompose.yamlの変更はインフラ担当者に相談する。
- APIのパスは原則として/api/から始める。
- APIキーや機密情報をGitにコミットしない。
- 実装完了後はPull Requestを作成する。

## デプロイ

Cloudflareへのデプロイはインフラ担当者が手動で実施する。

通常の機能開発にCloudflareアカウントやWranglerは不要です。
