# Ultra AutoTrade — デプロイ手順 & 運用チェックリスト

> 生成: 2026-04-24 / 実態から抽出（推測なし）
> 本番: Hetzner VPS (`/opt/ultra-autotrade`) / Staging: 同サーバーの別ポート

---

## 環境一覧

| 環境 | URL | compose file | env file | ポート |
|------|-----|-------------|----------|--------|
| **production** | app/api.ultra-auto-trade.com | `docker-compose.production.yml` | `.env.production` | frontend:3000 / backend:8000 / postgres:5432 |
| **staging** | staging/api-staging.ultra-auto-trade.com | `docker-compose.staging.yml` | `.env.staging-new` | frontend:3001 / backend:8001 / postgres:5433 |

---

## コンテナ名一覧（2026-04-24 container_name 衝突修正後）

| サービス | production | staging |
|---------|-----------|---------|
| backend | `ultra-autotrade-backend-production` | `ultra-autotrade-backend-staging-new` |
| frontend | `ultra-autotrade-frontend-production` | `ultra-autotrade-frontend-staging-new` |
| postgres | `ultra-autotrade-postgres-production` | `ultra-autotrade-postgres-staging-new` |
| cloudflared | `ultra-autotrade-cloudflared-production` | (なし) |
| loki | `ultra-autotrade-loki-production` | `ultra-autotrade-loki-staging-new` |
| promtail | `ultra-autotrade-promtail-production` | `ultra-autotrade-promtail-staging-new` |

---

## ボリューム一覧（name: 明示済み）

| 論理名 | 実体名 (docker volume ls) |
|--------|--------------------------|
| postgres-data | `ultra-autotrade-project_postgres-data` |
| ultra-state | `ultra-autotrade-project_ultra-state` |
| loki-data | `ultra-autotrade-project_loki-data` |
| ultra-log-staging | `ultra-autotrade-project_ultra-log-staging` |

> **重要**: `docker compose down -v` は絶対に禁止。DBボリュームが削除されテスターデータが全滅する。
> `deploy_production.sh` は起動時に `-v` / `--volumes` フラグを検出して即座に exit 1 する。

---

## 本番デプロイ手順（通常）

### 前提

- Hetzner VPS で実行（ローカル Mac からは直接デプロイ不可）
- 実行パス: `/opt/ultra-autotrade`
- `.env.production` に `DATABASE_URL` が直接定義されていること（compose の `${}` 展開に依存しない）

### 手順

```bash
# 1. Hetzner VPS にSSH
ssh hetzner

# 2. プロジェクトディレクトリに移動
cd /opt/ultra-autotrade

# 3. 最新コードを取得（main ブランチ）
git pull origin main

# 4. デプロイ実行（フルビルド）
./scripts/deploy_production.sh

# 完了時の自動実行内容:
# - production guardrail チェック (APP_ENV, BYBIT_SANDBOX, AAVE_NETWORK)
# - check_env_separation.sh 実行
# - DB バックアップ (scripts/backup_db.sh)
# - docker compose down --remove-orphans
# - 旧コンテナ強制削除 (*-production と移行前 *-staging のみ、*-staging-new は保護)
# - docker volume prune
# - frontend --no-cache ビルド + backend ビルド
# - docker compose up -d
# - backend:8000/health ヘルスチェック待機 (60s)
# - frontend:3000 ヘルスチェック待機 (60s)
# - デプロイ後検証: Mixed Content / Tunnel / DB drift / 401 errors / CORS
# - Slack 通知
```

### 部分デプロイ（CSSや文言変更のみ）

```bash
# フロントエンドのみ（バックエンドAPIに変更ない場合のみ使用）
./scripts/deploy_production.sh --frontend-only

# バックエンドのみ
./scripts/deploy_production.sh --backend-only

# ビルドなし（環境変数の再読み込みのみ）
./scripts/deploy_production.sh --no-build
```

> ⚠️ `--frontend-only` は「新しいAPIエンドポイントを呼ぶフロント変更」には使えない。
> バックエンド変更がある場合は必ずフルデプロイ。判断基準:
> ```bash
> git diff main --name-only | grep "^backend/"          # ありならフルデプロイ
> git diff main --name-only | grep "^frontend/lib/api/" # ありならフルデプロイ
> ```

> **`--frontend-only` のイメージ管理 (2026-05-13 RCA)**
> ビルド先行方式（ビルド成功後にコンテナ入れ替え）を採用。
> 旧順序（stop → rmi → build）だとビルド失敗時にイメージもコンテナも消えて起動不可になる。
> ビルドが失敗した場合は ERR トラップが発火し、旧コンテナを維持したまま終了する。

---

## .env.production の必須チェック項目

```bash
# .env.production に DATABASE_URL が直接定義されているか
grep '^DATABASE_URL=' .env.production
# → postgresql://ultra:<実パスワード>@postgres:5432/ultra_autotrade

# APP_ENV が production になっているか
grep '^APP_ENV=' .env.production
# → APP_ENV=production

# BYBIT_SANDBOX が false か
grep '^BYBIT_SANDBOX=' .env.production
# → BYBIT_SANDBOX=false

# AAVE_NETWORK が mainnet か（sepolia が含まれないか）
grep '^AAVE_NETWORK=' .env.production
# → AAVE_NETWORK=base_mainnet

# INTERNAL_API_TOKEN が設定されているか
grep '^INTERNAL_API_TOKEN=' .env.production
# → INTERNAL_API_TOKEN=<token>（空でないこと）

# CORS_ORIGINS に本番フロントエンドが含まれているか
grep '^CORS_ORIGINS=' .env.production
# → CORS_ORIGINS=https://app.ultra-auto-trade.com
```

---

## コンテナ操作コマンド集

```bash
BASE_COMPOSE="docker compose -f docker-compose.production.yml --env-file .env.production"

# コンテナ状態確認
$BASE_COMPOSE ps

# バックエンドログ（直近 100 行）
docker logs --tail=100 ultra-autotrade-backend-production

# フロントエンドログ
docker logs --tail=50 ultra-autotrade-frontend-production

# バックエンドシェル
docker exec -it ultra-autotrade-backend-production /bin/bash

# 本番DBへの接続（postgres コンテナ経由）
docker exec -it ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade

# スケジューラー確認
curl -sf http://localhost:8000/health | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('status:', d.get('status'))
print('scheduler_healthy:', d.get('scheduler_healthy'))
print('warnings:', d.get('warnings'))
"

# INTERNAL_API_TOKEN 確認
docker exec ultra-autotrade-backend-production env | grep INTERNAL_API_TOKEN | cut -c1-30

# DATABASE_URL 確認（接続確認）
docker exec ultra-autotrade-backend-production env | grep DATABASE_URL | sed 's/:.*@/:***@/'

# フロントエンドの埋め込み URL 確認（Mixed Content 検出）
docker exec ultra-autotrade-frontend-production \
  grep -r "http://" /app/.next/static/chunks/ 2>/dev/null | head -5
```

---

## DB マイグレーション手順

> このプロジェクトは Alembic 自動マイグレーションを使用しない。
> 新規カラムは Hetzner 上で手動 `ALTER TABLE` を実行する。

```bash
# Step 1: コンテナ名とDB情報を確認してから実行
docker ps | grep postgres
docker exec ultra-autotrade-postgres-production env | grep POSTGRES

# Step 2: 現在のカラム確認
docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d ultra_autotrade \
  -c "SELECT column_name, data_type FROM information_schema.columns WHERE table_name='<テーブル名>' ORDER BY ordinal_position;"

# Step 3: カラム追加
docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d ultra_autotrade \
  -c "ALTER TABLE <テーブル名> ADD COLUMN IF NOT EXISTS <カラム名> <型>;"

# 例: proposals に error_message カラム追加
docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d ultra_autotrade \
  -c "ALTER TABLE proposals ADD COLUMN IF NOT EXISTS error_message TEXT;"
```

---

## DB バックアップ

```bash
# 手動バックアップ（deploy_production.sh フルデプロイ時は自動実行される）
./scripts/backup_db.sh

# または手動 pg_dump
docker exec ultra-autotrade-postgres-production \
  pg_dump -U ultra ultra_autotrade \
  > /tmp/backup_$(date +%Y%m%d_%H%M%S).sql
```

---

## Staging デプロイ手順

```bash
# staging は Shadow Mode 専用（AI_SHADOW_MODE=true が必須）
cd /opt/ultra-autotrade

./scripts/deploy_staging.sh                   # フルデプロイ
./scripts/deploy_staging.sh --frontend-only   # フロントのみ
./scripts/deploy_staging.sh --backend-only    # バックエンドのみ

# ヘルスチェック（staging ポート: 8001/3001）
curl http://localhost:8001/health
curl http://localhost:3001
```

---

## Docker Compose 設計（2026-04-24 container_name 衝突修正後）

### production.yml の重要設計原則

1. **container_name**: 全サービスに `*-production` suffix（旧 `*-staging` から変更済み）
2. **volumes**: 全4ボリュームに `name:` を明示 → `COMPOSE_PROJECT_NAME` 変更時もデータ保護
3. **networks**: `production-net` を独自定義 → staging.yml との合成を物理的に分離
4. **DATABASE_URL**: compose 内の `${}` 展開を使わない → `.env.production` に直接フルURL記述

```yaml
# production.yml volumes（実際の定義）
volumes:
  postgres-data:
    name: ultra-autotrade-project_postgres-data    # 既存データボリュームを維持
  ultra-state:
    name: ultra-autotrade-project_ultra-state
  loki-data:
    name: ultra-autotrade-project_loki-data
  ultra-log-staging:
    name: ultra-autotrade-project_ultra-log-staging

networks:
  production-net:
    name: ultra-autotrade-project_default
```

### DATABASE_URL の扱い

**NG（廃止済み）**:
```yaml
# compose の ${POSTGRES_PASSWORD} は手動 up 時に空文字になる
environment:
  DATABASE_URL: postgresql://ultra:${POSTGRES_PASSWORD}@postgres:5432/ultra_autotrade
```

**OK（現在の正しい方法）**:
```bash
# .env.production に直接フルURLを記述
DATABASE_URL=postgresql://ultra:<実パスワード>@postgres:5432/ultra_autotrade
```
```yaml
# production.yml は env_file: のみ
env_file:
  - .env.production
environment:
  REBALANCE_SHADOW_MODE: "false"   # これだけ compose 側で上書き
```

---

## Cloudflare Tunnel 運用

- cloudflared は `network_mode: "host"` で稼働（コンテナ名依存なし）
- Ingress ルールは Cloudflare ダッシュボードで管理（config.yml は無視）
  - `https://api.ultra-auto-trade.com` → `http://localhost:8000`
  - `https://app.ultra-auto-trade.com` → `http://localhost:3000`
- Tunnel が落ちた場合: `docker restart ultra-autotrade-cloudflared-production`
- ログ確認: `docker logs ultra-autotrade-cloudflared-production --tail=50`

---

## デプロイ後の検証（手動確認）

```bash
# 1. コンテナ全稼働確認
docker ps --format 'table {{.Names}}\t{{.Status}}' | grep ultra-autotrade

# 2. backend ヘルス（scheduler_healthy = true を確認）
curl -sf http://localhost:8000/health | python3 -m json.tool

# 3. Named Tunnel 経由での疎通
curl -sf https://api.ultra-auto-trade.com/health | python3 -m json.tool
curl -sf https://app.ultra-auto-trade.com | head -5

# 4. DB drift チェック（users テーブル）
docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d ultra_autotrade -t \
  -c "SELECT column_name FROM information_schema.columns WHERE table_name='users' ORDER BY ordinal_position;" \
  | tr '\n' ','

# 5. 401 エラー確認（INTERNAL_API_TOKEN 問題）
docker logs --tail=200 ultra-autotrade-backend-production 2>&1 | grep "401 Unauthorized" | wc -l
# → 5 件超なら INTERNAL_API_TOKEN 未設定の可能性

# 6. CORS 確認
curl -s -I \
  -H "Origin: https://app.ultra-auto-trade.com" \
  -H "Access-Control-Request-Method: GET" \
  http://localhost:8000/health \
  | grep -i "access-control-allow-origin"
```

---

## ロールバック手順

```bash
cd /opt/ultra-autotrade

# 1. 前コミットに戻す（compose ファイルのみ）
git log --oneline -5
git checkout <前コミットハッシュ> -- docker-compose.production.yml scripts/deploy_production.sh

# 2. 再デプロイ
./scripts/deploy_production.sh

# 3. volumes は name: 明示済みのため、プロジェクト名が変わってもデータ保護される
```

---

## 週次メンテナンス

```bash
# Docker クリーンアップ（毎週日曜 03:00 JST に cron 自動実行）
./scripts/docker_cleanup.sh

# 禁止: docker system prune -af（稼働中イメージ削除リスク）
```

---

## よくあるインシデント対応

### backend コンテナが消える（2026-04-24 インシデント）

**原因**: compose の `${POSTGRES_PASSWORD}` が手動 `up` 時に空文字化 → DB接続失敗 → コンテナ終了

**確認**:
```bash
docker logs ultra-autotrade-backend-production 2>&1 | grep "could not connect\|password"
```

**修正**:
```bash
# .env.production に DATABASE_URL が直接定義されているか確認
grep '^DATABASE_URL=' .env.production
# なければ追加
POSTGRES_PW=$(grep '^POSTGRES_PASSWORD=' .env.production | cut -d= -f2-)
printf '\nDATABASE_URL=postgresql://ultra:%s@postgres:5432/ultra_autotrade\n' "$POSTGRES_PW" >> .env.production
# 再起動
./scripts/deploy_production.sh --backend-only
```

### staging-new コンテナが停止した

**確認**:
```bash
docker ps | grep staging-new
```

**再起動**:
```bash
docker compose -f docker-compose.staging.yml --env-file .env.staging-new up -d
```

### DB に接続できない（名前解決失敗）

```bash
# ネットワーク確認
docker inspect ultra-autotrade-backend-production \
  --format "{{json .NetworkSettings.Networks}}" | python3 -m json.tool

# postgres コンテナのネットワーク
docker inspect ultra-autotrade-postgres-production \
  --format "{{json .NetworkSettings.Networks}}" | python3 -m json.tool
# → 同じネットワーク名になっているか確認
```

### 502 Bad Gateway

1. `docker ps` でコンテナが起動しているか確認
2. `docker logs ultra-autotrade-frontend-production` で Next.js Ready ログ確認
3. `curl http://127.0.0.1:3000` でホスト→フロントエンドの疎通確認
4. `docker logs ultra-autotrade-cloudflared-production` で `connection refused` 確認
5. 多くは起動中の一時的状態（30秒待機で自然解消）
