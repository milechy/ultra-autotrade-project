# Ultra AutoTrade — デプロイ手順 & 運用チェックリスト

> 生成: 2026-04-24 / 実態から抽出（推測なし）
> 本番: Hetzner VPS (`/opt/ultra-autotrade`) / Staging: 同サーバーの別ポート

---

## 環境一覧

| 環境 | URL | compose file | env file | ポート |
|------|-----|-------------|----------|--------|
| **production** | app/api.ultra-auto-trade.com | `docker-compose.production.yml` | `.env.production` | frontend:3000 / backend:8000(nginx経由) / postgres:5432 |
| **staging** | staging/api-staging.ultra-auto-trade.com | `docker-compose.staging.yml` | `.env.staging-new` | frontend:3001 / nginx:8082(backend経由) / postgres:5433（旧 backend:8001 は廃止、nginx upstream = backend-blue:8000） |

---

## コンテナ名一覧（2026-04-24 container_name 衝突修正後 / 2026-05-22 Blue/Green 反映）

> **2026-05-22 訂正**: staging compose (`docker-compose.staging.yml`) は `profiles:` 指定なし。
> `up -d` 既定で **7 サービス全て**（postgres / backend-blue / backend-green / nginx / frontend / loki / promtail）が起動する。
> 旧記述「backend 単体（backend-staging-new）/ 5コンテナ構成」は B案リネーム期の名残であり、現 compose と矛盾するため削除。
> nginx upstream は `docker/nginx/upstream.staging.conf` の `set $backend backend-blue:8000;` で blue 固定。

| サービス | production | staging |
|---------|-----------|---------|
| backend-blue | `ultra-autotrade-backend-blue-production` | `ultra-autotrade-backend-blue-staging-new` |
| backend-green | `ultra-autotrade-backend-green-production` | `ultra-autotrade-backend-green-staging-new` |
| frontend | `ultra-autotrade-frontend-production` | `ultra-autotrade-frontend-staging-new` |
| postgres | `ultra-autotrade-postgres-production` | `ultra-autotrade-postgres-staging-new` |
| nginx | `ultra-autotrade-nginx-production` | `ultra-autotrade-nginx-staging-new` |
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
# → AAVE_NETWORK=base

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

# ヘルスチェック（staging ポート: 8082/3001 / 旧8001は廃止）
curl http://127.0.0.1:8082/health
curl http://localhost:3001
```

---

## 緊急停止 e2e 検証（`scripts/e2e_emergency_stop.sh`）

> 2026-07-02 更新: 3-VPS構成移行（production=5.223.88.14 / staging=188.34.167.142 に完全分離）後の
> staging スタックに合わせて更新済み。忘れられがちだが、緊急停止まわりの全経路を通しで確認できる
> 唯一のスクリプトのため、インシデント対応・定期ドリルの両方でここに記載しておく。

### 用途

- **インシデント対応時**: 緊急停止の全経路（API kill switch / スケジューラー無効化 / エラー連続検知 /
  Health Factor 閾値 / resume 復元）が正しく機能するかを、本番障害の前後に確認する。
- **定期ドリル**: production へ影響を与えずに、staging 上で5経路の動作を通しで検証する e2e スモーク
  テストとして、月次などの定期実行に使う。

検証する5経路（TC-1〜TC-5）:

| TC | 経路 | 内容 |
|----|------|------|
| TC-1 | API kill switch | `POST /api/automation/emergency-stop` → `is_trading_paused=true` → `ai_decisions` delta=0 → Slack通知 → resume |
| TC-2 | env var 停止 | `DISABLE_AI_JUDGMENT_SCHEDULER=1` でスケジューラー起動をスキップ（`DO_SCHEDULER_RESTART_TEST=true` 時のみ実際に再起動して検証） |
| TC-3 | エラー連続検知 | emergency_stop 発動中に `/api/ai/trigger` が reject されることを確認（Claude API 連続失敗の代替検証） |
| TC-4 | Health Factor < 1.6 | 閾値ロジックの単体検証 + `LINE_NOTIFY_TOKEN` 設定確認（staging は dummy AAVE のため実HF注入は不可） |
| TC-5 | resume / 復元 | 全TC後の最終復元確認（`is_trading_paused=false` / `emergency_reason` クリア / scheduler 再開） |

### 前提

- **staging VPS (188.34.167.142) 上でのみ実行する**。production (5.223.88.14) では絶対に実行しない
  （2026-07-02 移行後、staging は production と別 VPS に分離済み）。
- `ADMIN_EMAIL` / `ADMIN_PASSWORD`（staging admin ユーザー）が必須。

### 実行方法

```bash
# iMac から staging VPS へSSH
ssh -i ~/.ssh/hetzner_assistone_stagingdev root@188.34.167.142

# staging VPS 上で
export ADMIN_EMAIL='<staging admin email>'
export ADMIN_PASSWORD='<staging admin password>'
cd /opt/ultra-autotrade
bash scripts/e2e_emergency_stop.sh
```

初回や手順確認のみ行いたい場合は、まず `DRY_RUN=true` で実際の API 呼び出しをせず手順のみ出力させる。

```bash
DRY_RUN=true bash scripts/e2e_emergency_stop.sh
```

### 主要 env（オプション、default で概ね動作する）

| env | default | 用途 |
|-----|---------|------|
| `STAGING_BASE_URL` | `http://127.0.0.1:8082` | staging backend への base URL |
| `POSTGRES_CONTAINER` / `BACKEND_CONTAINER` | 自動検出（`*staging*` を含むもの） | 対象コンテナ |
| `DB_USER` / `DB_NAME` | `ultra` / `ultra_autotrade_staging` | `ai_decisions` COUNT確認用 |
| `AI_DELTA_WAIT_SEC` | `5` | `ai_decisions` delta 観測待ち秒数 |
| `LOG_TAIL_LINES` | `300` | backend ログ確認の tail 行数 |
| `DO_SCHEDULER_RESTART_TEST` | `false` | `true` で TC-2 の実再起動検証を実施（staging backend が一時再起動される） |
| `SKIP_TCS` | (なし) | スキップする TC 番号をカンマ区切りで指定（例: `"2,4"`） |
| `ENV_FILE` | `/opt/ultra-autotrade/.env.production` | Slack webhook URL 読込元 |

### 結果の見方

各 TC ごとに `[PASS]` / `[FAIL]` / `[SKIP]` が出力され、最後にサマリが表示される。

```
=== e2e Emergency Stop Summary ===
[PASS] TC-1: API kill switch        paused=true / delta=0 / slack=1hits / resume HTTP=200 / restored
...
PASS=5 FAIL=0 SKIP=0
```

- `FAIL` が1件でもあれば終了コードが非0になる。緊急停止の実装または通知経路に問題がある可能性が
  あるため、該当 TC のログを遡って原因を確認すること。
- `SKIP` は想定内のことがある（`DISABLE_AI_JUDGMENT_SCHEDULER` 未設定 かつ
  `DO_SCHEDULER_RESTART_TEST=false` の場合の TC-2、`SKIP_TCS` 指定時、`DRY_RUN=true` 時の全 TC）。

### 安全装置（production への誤爆防止）

- dev VPS（hostname が `uata-dev*`）では即 EXIT し、実行手順のみ表示する
- `/health` の `env=staging` を確認してから実行（production への誤接続防止）
- 検出したコンテナ名に `staging` が含まれることを確認（含まれなければ `[FATAL]` で終了）
- DB操作は `SELECT` のみ（DB write なし）
- emergency stop の reason に `E2E_TAG`（実行毎のユニークタグ）を含め、実運用ログと区別できるようにする
- 全 TC 完了後、`trap` により終了時に必ず resume を試みる（途中で失敗しても staging が停止したままにならない）

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

## `--frontend-only` デプロイ時の backend drift 注意（2026-07-06 追記）

`--frontend-only` は以下の Guard を **完全にスキップする設計**である:

- **Guard 2**（環境分離チェック: `DATABASE_URL` / `AAVE_NETWORK` 等の staging↔production 混入検知）
- **Guard 4**（DB schema gap チェック: models.py と実 DB スキーマの alembic drift 検知）

これは frontend-only 実行時に backend コンテナを一切 recreate しないため、backend 側の
安全性を再検証する必要がない、という設計判断による（意図的な skip であり不具合ではない）。

### 「working tree は進むが backend コンテナは据え置かれる」二重状態

`--frontend-only` 実行後、production の **git working tree（`git rev-parse HEAD`）は
origin/main の最新コミットまで進む**が、`ultra-autotrade-backend-green-production`
コンテナは **デプロイ前の古いイメージのまま起動し続ける**。

つまり以下の二重状態が生じる:

| 対象 | 状態 |
|---|---|
| production working tree (`git rev-parse HEAD`) | origin/main 最新（backend の未反映コミットも含む） |
| backend-green コンテナの Image ID | デプロイ前と同一（`docker inspect --format='{{.Image}}'` で確認可） |

この状態で `git log <前回反映HEAD>..origin/main -- backend/` を実行すると、
**working tree には取り込まれているが実行中コンテナには反映されていない** backend
コミット一覧が得られる。次回 backend/full デプロイまでの申し送り事項として、
この一覧を都度記録しておくこと。

**実例（2026-07-06、PR #939〜#947 frontend-only デプロイ時点）**:
production は cf8583e4 (#917) → ff366a43 (#947) まで origin/main 追従したが、
backend-green は cf8583e4 時点のイメージ（`sha256:74605864...`）のまま据え置き。
以下 14 コミット分の backend 変更（fee model / PolicyEngine / eMode / GHO シグナル /
`privy_wallet_id` + 新規 alembic migration `pw20260705_add_privy_wallet_id.py` 等）が
working tree には存在するが未デプロイのまま積み上がっている:

```
623ef5ea feat(staging): 新規テスターに自動でデモ資金を割当(Lido/Pendle提案の体験拡張) (#938)
5c1a1845 fix(ai): 価格テクニカルシグナル取得を無認証の公開ccxt.bybit()に変更 (#937)
d6144e52 feat(ai): Indicator Agentに価格モメンタムシグナルを追加(HOLD脱却A) (#936)
1d680dad feat(privy): per-user privy_wallet_id 取得（非カストディアル SCW 執行の前提配線） (#935)
8437ca0d fix(audit): デプロイ前監査で検出した2件の修正 + コメント整合 (#934)
e3090412 feat(legal): 月額料金の実額開示 + 同意ゲート（弁護士レビュー用・徴収はOFF継続） (#932)
86ce0bc6 test(deposit-gate): A-4 実行時ゲート enforcement 統合テスト（承認/モード切替） (#930)
eb7bda2e fix(deposit-gate): A-2/A-3 実行時ゲートを main へ再ランド（孤立PR #899 復旧） (#929)
dd443e14 refactor(fees): 収益受取を設計Aに統一・設計B(Lane R)を解消 (PR-2) (#928)
5e0043d1 feat(fees): 月次バッチのtier判定をdeposit_jpyから都度算出・書き戻し配線 (#927)
95a772af fix(liff-chat): EOA/SmartWallet不一致による資金迷子バグを修正 (#925)
93c6a4b2 feat(ai): GHO借入シグナルをMarketContextへ追加（Phase 1: 観測のみ） (#921)
1ad0aa90 fix(aave): eMode切替をサーバー側で実送信完結させる (#920)
b4d88ca1 fix(policy): build-tx（非カストディアル主経路）にPolicyEngine検査を配線 (#919)
```

### 次回 backend/full デプロイ時の申し送り

上記のように backend 差分が積み上がっている状態で次回 `--backend-only` または
フル `./scripts/deploy_production.sh` を実行する際は、CLAUDE.md の
「Tier S ファイルは 1 日 1 PR まで」原則に照らし、以下を事前に判断すること:

- 新規 alembic migration（`pw20260705_add_privy_wallet_id.py` 等）が含まれる場合、
  デプロイ前に `docs/ops/02_db_tables.md` の CHECK 制約 enum 突き合わせルールに従い
  models.py との整合を確認する
- 積み上がった backend コミット群を 1 回で一括反映するか、機能単位で分割反映するかを
  Phase 2 相当の承認プロセスで判断する（Tier S ファイル `backend/app/main.py` /
  `backend/migrations/versions/*.py` 等が含まれる場合は 1 日 1 PR 原則の対象）

**実例（2026-08-03、PWA アイコン差し替え PR #1009 frontend-only デプロイ時点）**:
production は `c4fa16f1`（#999, 2026-07-21）→ `c9897d8f`（#1009, 2026-08-03）まで
origin/main 追従したが、backend-green は `c4fa16f1` 時点のイメージ
（`sha256:613ab59a8340...`、作成日時 2026-07-21T08:47:09Z）のまま据え置き。
以下 3 コミット分の backend 変更が working tree には存在するが未デプロイのまま
積み上がっている（デプロイ実行時点で `./scripts/deploy_production.sh --frontend-only`
の post-deploy チェックでも `alembic check` WARNING（未適用 migration あり、DB revision:
`x4y5z6a7b8c9`）として検出済み）:

```
661ed110 fix(portfolio): 消費者ユーザーの残高 snapshot を per-user 経路で記録 (#1003)
5cf1039c fix(liff): 安全利回り提案の理由文からプロトコル名(Aave)を除去 (#1004)
004d0f81 feat(staging): テスターのスマートウォレットへBase SepoliaテストネットUSDCを自動補充 (#1007)
```

補足:
- `#1007` は `.env.staging` / `.env.staging-v4` 専用フラグ（`AUTO_FUND_TESTER_ONCHAIN_USDC`）
  を前提とする staging 限定機能であり、production への影響はコード上は無い想定だが、
  backend イメージ未反映のため実挙動は次回 backend デプロイまで未検証。
- `#1003` はポータフォリオ snapshot の per-user 記録経路追加（新規 DB 書き込みパス）。
  次回 backend デプロイ時に本番実データでの記録確認が必要（過去 memory:
  `project_portfolio_snapshot_per_user_gap` 参照）。
- `#1004` は消費者向け理由文からのプロトコル名除去（frontend #1002/#1005/#1006 と対の
  backend 側修正）。frontend 側は既に本デプロイで反映済みのため、backend 側未反映との
  整合状態を次回デプロイまで意識すること。

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

### AI判定スケジューラが inactive color skip し続ける（2026-06-26 インシデント）

**症状**: コンテナは healthy・nginx も疎通200・feeds も毎時更新されているのに、
`ai_decisions` テーブルに新規行が増えず、AI由来 proposal が生成されない（実ユーザーに提案ゼロ）。

**真因**: nginx upstream の実 active（`docker/nginx/upstream.production.conf` の `set $backend backend-XXX`）と
`.env.production` の `ACTIVE_BACKEND_COLOR` が **drift**。`backend/app/main.py` の
`_is_inactive_color_skip()`（BACKEND_COLOR ≠ ACTIVE_BACKEND_COLOR かつ両方set→True）により、
実トラフィックを受けている唯一の生存コンテナが「自分は非アクティブ」と誤判定し、
AI判定スケジューラを丸ごと skip する。feeds/HOWL は color ガード無しなので動き続けるため
気づきにくい。2026-06-26 に本番で 22 日間（6/04〜）この状態が継続していた。

**診断（read-only）**:
```bash
# 起動ログに skip が出ているか
docker logs <active-backend> 2>&1 | grep -E "AI judgment scheduler started|inactive color: scheduler skip"
# nginx 実 active と env の一致確認
grep -E 'set \$backend' docker/nginx/upstream.production.conf      # 例: backend-blue
docker exec <active-backend> printenv | grep -E "BACKEND_COLOR|ACTIVE_BACKEND_COLOR"
# 死活: ai_decisions が最近書かれているか
docker exec <postgres> psql -U ultra -d ultra_autotrade -c "SELECT MAX(created_at) FROM ai_decisions;"
```

**復旧**: `.env.production` の `ACTIVE_BACKEND_COLOR` を nginx 実 active（通常 blue）に揃え、
当該 backend を **force-recreate**（env はコンテナ作成時固定のため `restart` では反映されない）。
```bash
ENV_FILE=.env.production
TMP=$(mktemp "${ENV_FILE}.XXXXXX")
awk '{if($0 ~ /^ACTIVE_BACKEND_COLOR=/){print "ACTIVE_BACKEND_COLOR=blue"}else{print}}' "$ENV_FILE" > "$TMP"
cat "$TMP" > "$ENV_FILE" && rm -f "$TMP"        # inode 保持・sed -i 禁止
docker compose -f docker-compose.production.yml --env-file .env.production \
  up -d --no-deps --force-recreate backend-blue
# 検証: 起動ログに "AI judgment scheduler started" が出ること
```

**再発防止**: deploy 後に nginx 実 active と `.env.production` の `ACTIVE_BACKEND_COLOR` の
整合を `deploy_production.sh` がチェックする（drift で WARN）。また healthcheck L3
（`ai_decisions_24h < 3 → FAIL`）はこの障害を検知できるが、**検知できていても気づけるとは限らない**
（本件は L3 FAIL が 6099 回 Slack 送信されたが連発で埋没した＝アラート疲労）。
FAIL 通知は dedup/throttle 済み（同一FAILは1h毎に再送・状態変化時のみ即送信、
`scripts/healthcheck_l1_l6.sh`）。Twilio 電話エスカレーション（5連続FAIL）の credentials 設定も推奨。
