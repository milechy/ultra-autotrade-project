# テスター環境デプロイチェックリスト

**対象:** 開発者 / デプロイ担当者
**環境:** Staging (Hetzner VPS)
**最終更新:** 2026-03-24

---

## デプロイ前チェック

### コード品質

```bash
# バックエンド: lint
cd backend
ruff check .

# バックエンド: フォーマット確認
ruff format --check .

# バックエンド: 型チェック
mypy app/ --config-file ../pyproject.toml

# バックエンド: テスト (coverage 80%+)
pytest tests/ --cov=app --cov-fail-under=80 -q

# フロントエンド: lint
cd frontend
npm run lint
```

すべてエラー 0 であることを確認してから次のステップへ進む。

### Git 状態確認

```bash
# 未コミットの変更がないことを確認
git status

# dev ブランチが最新であることを確認
git fetch origin
git log origin/dev..dev --oneline

# リモートに push
git push origin dev
```

---

## デプロイ手順

### 1. Hetzner VPS に SSH 接続

```bash
ssh hetzner
# または
ssh user@<hetzner-ip>
```

### 2. リポジトリを最新化

```bash
cd /opt/ultra-autotrade
git fetch origin
git pull origin dev
```

### 3. Docker イメージをビルド

```bash
# キャッシュなしでフルビルド
docker compose -f docker-compose.staging.yml build --no-cache
```

> ビルドには 5〜10 分かかる場合があります。

### 4. コンテナを再起動

```bash
# 既存コンテナを停止・削除
docker compose -f docker-compose.staging.yml down

# コンテナをバックグラウンドで起動
docker compose -f docker-compose.staging.yml up -d
```

### 5. 起動確認

```bash
# コンテナの状態を確認 (全サービスが Up であること)
docker compose -f docker-compose.staging.yml ps
```

期待する出力:
```
NAME                                    STATUS
ultra-autotrade-backend-staging         Up
ultra-autotrade-frontend-staging        Up
ultra-autotrade-postgres-staging        Up (healthy)
ultra-autotrade-loki-staging            Up
ultra-autotrade-promtail-staging        Up
```

---

## デプロイ後の動作検証

### ヘルスチェック

```bash
# バックエンド: ヘルスエンドポイント
curl -s http://localhost:8000/health
# 期待値: {"status":"ok","env":"staging"}

# フロントエンド: HTTP ステータスコード
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
# 期待値: 200
```

### API エンドポイント確認

```bash
# セーフティスコア取得
curl -s http://localhost:8000/api/transparency/safety-score
# 期待値: {"score": <数値>, ...} が返ること

# オートメーションステータス確認
curl -s http://localhost:8000/api/automation/status
# 期待値: {"running": true, ...} が返ること
```

### ログ確認

```bash
# バックエンドログ (エラーがないことを確認)
docker logs ultra-autotrade-backend-staging --tail 50

# フロントエンドログ
docker logs ultra-autotrade-frontend-staging --tail 50
```

---

## テストユーザーアカウント

### ロール定義

| ロール | 権限 | 用途 |
|--------|------|------|
| admin | 全機能 + 管理画面 | 管理者テスト |
| editor | 設定変更 + 取引操作 | 一般ユーザーテスト |
| viewer | 閲覧のみ | 読み取り権限テスト |

### テストユーザーのシード

```bash
# Hetzner VPS 上で実行
docker exec -it ultra-autotrade-backend-staging bash

# シードスクリプトを実行
python -m app.scripts.seed_test_users
```

シードスクリプトが存在しない場合は、API を使って手動作成する:

```bash
# admin ユーザー作成
curl -s -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin-tester@ultra-auto-trade.com",
    "password": "TestAdmin2026!",
    "display_name": "Admin Tester",
    "role": "admin"
  }'

# editor ユーザー作成
curl -s -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "editor-tester@ultra-auto-trade.com",
    "password": "TestEditor2026!",
    "display_name": "Editor Tester",
    "role": "editor"
  }'

# viewer ユーザー作成
curl -s -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "viewer-tester@ultra-auto-trade.com",
    "password": "TestViewer2026!",
    "display_name": "Viewer Tester",
    "role": "viewer"
  }'
```

> テストアカウントの認証情報はテスターに安全な方法 (Slack DM 等) で共有すること。

---

## ロールバック手順

デプロイ後に重大な問題が発生した場合は以下の手順でロールバックする。

### 1. 直前のコミットを特定

```bash
# デプロイ履歴を確認
git log --oneline -10
```

### 2. 直前のバージョンに戻す

```bash
# 対象のコミットハッシュを指定してチェックアウト
git checkout <previous-commit-hash>
```

### 3. イメージを再ビルドして再起動

```bash
docker compose -f docker-compose.staging.yml build --no-cache
docker compose -f docker-compose.staging.yml down
docker compose -f docker-compose.staging.yml up -d
```

### 4. 動作確認

ヘルスチェックセクションの手順を再度実施して復旧を確認する。

### 5. Slack に通知

```bash
WEBHOOK=$(grep SLACK_WEBHOOK_URL .env.staging | cut -d= -f2-)
curl -s -X POST "$WEBHOOK" \
  -H "Content-Type: application/json" \
  -d '{"text": "⚠️ [Deploy] ロールバック実施\n理由: <理由を記載>\nロールバック先: <コミットハッシュ>"}'
```

---

## デプロイ完了通知

デプロイが正常に完了したら Slack に通知する:

```bash
WEBHOOK=$(grep SLACK_WEBHOOK_URL .env.staging | cut -d= -f2-)
curl -s -X POST "$WEBHOOK" \
  -H "Content-Type: application/json" \
  -d '{"text": "✅ [Deploy] Staging デプロイ完了\nブランチ: dev\nコミット: <hash>\n検証: ヘルスチェック OK / API OK"}'
```
