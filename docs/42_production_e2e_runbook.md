# 本番 E2E テストランブック (Production E2E Runbook)

> 最終更新: 2026-05-01 (本日 production deploy + Phase 3 Blue/Green 移行完了直後)
> 対象: production / staging-new
> 関連: docs/22_production_release_checklist.md, docs/14_test_strategy.md, CLAUDE.md

## 0. このドキュメントの目的

本番デプロイ前後の E2E 検証を「**推測ゼロ**」で実行できる手順書。
過去のインシデント(2026-04-18 .env汚染, 2026-04-24 API推測 + container衝突, 2026-04-26 F-6 deploy, 2026-05-01 Blue/Green初期化遅延)から抽出した落とし穴と回避策を集約する。

**読者**: deploy 担当者(小林)、運用エンジニア、CLI(Claude Code)
**前提知識**: Docker Compose, PostgreSQL, FastAPI, Hetzner SSH 接続

---

## 1. 事前知識(必読)

### 1.1 環境一覧

| 環境 | compose ファイル | env ファイル | DB 名 | nginx active |
|---|---|---|---|---|
| production | `docker-compose.production.yml` | `.env.production` | `ultra_autotrade` | blue (port 8010) |
| staging | `docker-compose.staging.yml` | `.env.staging-new` | `ultra_autotrade_staging` | green (port 8021) |
| local | `docker-compose.local.yml` | `.env.local` | (任意) | - |

**注意**:
- `docker-compose.staging-new.yml` という名前のファイルは**存在しない**(命名揺れ historical)
- `.env.staging-new` ← env ファイル名にだけ `-new` suffix が残っている
- `redis` コンテナは production / staging とも**不在**(2026-05-01 確認)

### 1.2 Blue/Green コンテナ名規則

| サービス | production | staging |
|---|---|---|
| backend (active) | `ultra-autotrade-backend-blue-production` | `ultra-autotrade-backend-green-staging-new` |
| frontend | `ultra-autotrade-frontend-production` | `ultra-autotrade-frontend-staging-new` |
| postgres | `ultra-autotrade-postgres-production` | `ultra-autotrade-postgres-staging-new` |
| nginx | `ultra-autotrade-nginx-production` | `ultra-autotrade-nginx-staging-new` |
| cloudflared | `ultra-autotrade-cloudflared-production` | (不在) |
| promtail | `ultra-autotrade-promtail-production` | `ultra-autotrade-promtail-staging-new` |
| loki | `ultra-autotrade-loki-production` | (不在) |

**重要**: 無印の `ultra-autotrade-backend-production` コンテナは**存在しない**。Blue/Green 移行後は **active 側コンテナ名** で操作する。

切替方法: `nginx.conf` の upstream を blue⇔green で書き換えて nginx reload。詳細は §5.

### 1.3 scheduler は backend 内蔵

`ultra-autotrade-scheduler-production` というコンテナは**存在しない**。AI 判定スケジューラーは `ultra-autotrade-backend-blue-production` (active 側) のプロセス内で動作する。

`force-recreate` 対象は基本 backend (active 側) のみ。staging も同様。

### 1.4 COMPOSE_PROJECT_NAME

| 環境 | 値 |
|---|---|
| production | `ultra-autotrade-project` |
| staging | `ultra-autotrade-staging` |

deploy 時の `docker compose up` には `-p <COMPOSE_PROJECT_NAME>` を明示するのが安全(container_name 衝突回避)。

---

## 2. deploy 前 4 点チェック (2026-04-19 メモリ #29 確立、2026-05-01 拡張)

deploy を始める前に**必ず**以下 4 点を確認する。1 点でも漏れるとインシデント再発のリスク高。

### 2.1 docker compose ls + ネットワーク確認

```bash
ssh -i ~/.ssh/hetzner_staging ultra@77.42.46.155
cd /opt/ultra-autotrade

# 起動中の compose project 一覧
docker compose ls

# ネットワーク所属確認(production と staging が混線していないか)
docker network ls | grep ultra-autotrade
docker network inspect ultra-autotrade-project_default | grep -E '(Name|Containers)'
```

**期待**: production と staging が別ネットワーク。コンテナがそれぞれ自環境のネットワークに属する。

### 2.2 DB スキーマ差分検出 (alembic ↔ 本番DB)

```bash
# alembic migration ファイル一覧
ls backend/migrations/versions/ | sort

# 本番DBに適用済み migration 一覧
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade \
  -c "SELECT version_num FROM alembic_version;"

# 期待カラム vs 実テーブル \d 差分(例: users)
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade \
  -c "\d users" | grep -E '(privy_did|wallet_address|execution_policy|terms_accepted_at)'
```

**手動 ALTER TABLE が必要な migration**(2026-05-01 時点判明済み):
- `f6a7b8c9d0e1_add_privy_did_to_users` (privy_did カラム + UNIQUE INDEX)
- `users_execution_policy_check` CHECK 制約

→ deploy 中に手動 SQL 適用が必要。詳細は §3.2。

### 2.3 .env 展開検証

```bash
# 現在 active な backend コンテナで実際の値を確認
docker exec ultra-autotrade-backend-blue-production env | grep -E \
  '(AAVE_NETWORK|AAVE_RPC_URL|REBALANCE_SHADOW_MODE|AI_CROSS_VALIDATION_ENABLED|OPENAI_API_KEY|PRIVY_APP_ID|DATABASE_URL)' \
  | sed 's/=.*/=***/'  # 値はマスクしてログに残す

# .env バックアップ + md5 記録
cp .env.production .env.production.backup-$(date +%Y%m%d_%H%M%S)
md5sum .env.production
```

**注意**:
- `.env (env_file)` と `compose environment: ${VAR}` の展開差異に注意。`${VAR}` は **deploy 元のシェル環境**から展開され、`.env` から読まれない。
- `OPENAI_API_KEY` 等のシークレットは production / staging で**異なる値**(2026-04-26 セキュリティルール)。md5sum で分離確認。

### 2.4 container_name 衝突確認

```bash
# 停止中の同名コンテナがないか
docker ps -a --format 'table {{.Names}}\t{{.Status}}' | grep ultra-autotrade

# 衝突時の対処
docker stop <container_name>
docker rm <container_name>
docker compose -p ultra-autotrade-project -f docker-compose.production.yml up -d
```

---

## 3. deploy 実行手順

### 3.1 通常 deploy (Blue/Green active 切替なし)

```bash
ssh -i ~/.ssh/hetzner_staging ultra@77.42.46.155
cd /opt/ultra-autotrade

# (1) git pull (ローカル push 禁止、Hetzner pull only — CLAUDE.md ABSOLUTE)
git fetch origin
git log --oneline origin/main -5
git checkout main && git pull origin main

# (2) §2 の 4 点チェック実行
# (詳細は §2)

# (3) 必要な手動 ALTER TABLE / migration 適用
# (詳細は §3.2)

# (4) deploy 実行
bash scripts/deploy_production.sh

# (5) §4 の API 検証(/health, /health/aave, etc.)
```

### 3.2 ALLOW_TESTNET=1 bypass (partner 検証フェーズ用)

`deploy_production.sh` の Guard 1 (AAVE_NETWORK testnet 検出 → reject) を一時バイパスする手順。
**用途**: 山本さんが Base Sepolia testnet で先行検証している期間限定。
**期限**: メインネット切替完了後は廃止 (関連: GID 1214443169903298)

```bash
ALLOW_TESTNET=1 bash scripts/deploy_production.sh
```

### 3.3 手動 ALTER TABLE 適用(現時点の必須項目)

```bash
# バックアップ取得(必須)
docker exec ultra-autotrade-postgres-production pg_dump -U ultra ultra_autotrade \
  > /tmp/backup_$(date +%Y%m%d_%H%M%S).sql

# 適用
docker exec -i ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade <<'SQL'
ALTER TABLE users ADD COLUMN IF NOT EXISTS privy_did VARCHAR(255);
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_privy_did ON users(privy_did) WHERE privy_did IS NOT NULL;

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_execution_policy_check;
ALTER TABLE users ADD CONSTRAINT users_execution_policy_check
  CHECK (execution_policy IN ('auto_execute', 'require_approval', 'proposal_only'));
SQL

# 検証
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade \
  -c "\d users" | grep -E '(privy_did|execution_policy)'
```

### 3.4 ロールバック手順

```bash
# Blue/Green 切替で即時ロールバック(active 側を旧コードのまま戻す)
# 詳細手順は §6.1 参照

# git revert での旧コード復元
git checkout main
git log --oneline -3
git revert <merge-commit>
git push origin main
ssh ultra@... "cd /opt/ultra-autotrade && git pull origin main && bash scripts/deploy_production.sh"

# 手動 ALTER TABLE のロールバック(慎重に)
ALTER TABLE users DROP COLUMN privy_did;
ALTER TABLE users DROP CONSTRAINT users_execution_policy_check;
```

---

## 4. deploy 後 API 検証

各 endpoint は backend コードから直接抽出 (2026-05-01 確認、Explore agent 調査結果)。**推測禁止**(2026-04-24 教訓: `/api/auth/login` vs `/auth/login` 混在で 404 連発)。

### 4.1 ヘルスチェック

実装ファイル: `backend/app/main.py:251` (`/health` のみ)、Aave 系は `backend/app/aave/router.py`

| Endpoint | Method | 認証 | 実装 |
|----------|--------|------|------|
| `/health` | GET | 不要 | `backend/app/main.py:251` |
| `/health/db` | — | — | **存在しない** (実装なし) |
| `/health/llm` | — | — | **存在しない** (実装なし) |
| `/aave/health` | — | — | **存在しない** (代わりに `/api/aave/status`, `/api/aave/health-factor`, `/api/aave/chains/health`) |

**curl 例 (`/health`)**:
```bash
curl -fsS https://api.ultra-auto-trade.com/health | python3 -m json.tool
```

期待レスポンス (`backend/app/main.py:251-277` 直読):
```json
{
  "status": "ok",                                  // "ok" or "degraded"
  "env": "production",                             // APP_ENV value
  "scheduler": true,                               // running status
  "scheduler_healthy": true,                       // health check result
  "last_judgment": "2026-05-01T...",               // Optional[datetime]
  "next_judgment": "2026-05-01T...",               // Optional[datetime]
  "scheduler_last_error": null,                    // Optional[str]
  "warnings": [],                                  // List[str], 例: ["scheduler_overdue"]
  "claude_model": "claude-sonnet-4-6",
  "claude_fallback_model": "claude-haiku-4-5-20251001"
}
```

**Aave 系ヘルスチェック (3 endpoint 別建て)**:
```bash
# 1. Aave 全体ステータス
curl -fsS https://api.ultra-auto-trade.com/api/aave/status \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# 2. Health Factor
curl -fsS https://api.ultra-auto-trade.com/api/aave/health-factor \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# 3. マルチチェーン RPC ヘルス
curl -fsS https://api.ultra-auto-trade.com/api/aave/chains/health \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

**不合格時の調査**:
```bash
# scheduler_healthy=false / warnings に値あり
docker logs --tail=100 ultra-autotrade-backend-blue-production 2>&1 | grep -E "ERROR|scheduler"

# Aave RPC 接続 / contract address 確認
docker exec ultra-autotrade-backend-blue-production env | grep -E "AAVE_NETWORK|AAVE_RPC_URL"

# 内部 API 401 (INTERNAL_API_TOKEN 未設定インシデント、2026-04-03)
docker logs --tail=200 ultra-autotrade-backend-blue-production 2>&1 | grep "401"
```

### 4.2 認証フロー

実装: `backend/app/auth/router.py:62` (`prefix="/auth"`)、main.py:205 で `include_router(auth_router)` (prefix 追加なし)。

**重要 (2026-04-24 教訓)**: 全 auth endpoint は `/auth/*`。`/api/auth/*` は**存在しない**。

| Endpoint | Method | 認証 | 行 | 備考 |
|----------|--------|------|---|------|
| `/auth/register` | POST | 不要 | 65 | 新規登録 (INITIAL_ADMIN_EMAIL の場合のみ admin) |
| `/auth/login` | POST | 不要 | 148 | email/password ログイン → JWT 発行 |
| `/auth/logout` | POST | Bearer | 185 | |
| `/auth/me` | GET | Bearer | 203 | 自ユーザー情報取得 |
| `/auth/change-password` | POST | Bearer | 217 | |
| `/auth/terms/status` | GET | Bearer | 243 | 利用規約承諾状況 |
| `/auth/terms/accept` | POST | Bearer | 261 | 利用規約承諾 |
| `/auth/risk-mode` | GET | Bearer | 317 | 自分の RiskMode |
| `/auth/risk-mode` | PUT | Bearer | 338 | RiskMode 変更 (Phase 1 制限あり) |
| `/auth/risk-modes` | GET | 不要 | 380 | 全 RiskMode 一覧 + 許可状態 |
| `/auth/wallet/connect` | POST | Bearer | 407 | **Privy ID Token 検証もここで実施** |
| `/auth/line` | POST | 不要 | 553 | LINE 連携 |

**注意**: `/auth/privy-login` という endpoint は**存在しない**。Privy ID Token は `/auth/wallet/connect` で検証する。

**curl 例 (email/password)**:
```bash
# 1. ログイン → JWT 取得
TOKEN=$(curl -fsS -X POST https://api.ultra-auto-trade.com/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "tester@example.com", "password": "..."}' \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

# 2. /auth/me で自分情報を取得
curl -fsS https://api.ultra-auto-trade.com/auth/me \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# 期待 (UserResponse schema、backend/app/auth/schemas.py):
# {
#   "id": 11, "email": "...", "username": "...",
#   "role": "partner", "execution_policy": "require_approval",
#   "wallet_address": "0x...", "privy_did": "did:privy:...",
#   "risk_mode": "conservative", "risk_mode_label": "ローリスク",
#   "tier": "MIDDLE", ...
# }
```

**curl 例 (Privy ID Token + ウォレット接続、line 407)**:
```bash
# Privy SDK で取得した ID Token を渡す。同時に wallet_address も登録される。
curl -fsS -X POST https://api.ultra-auto-trade.com/auth/wallet/connect \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"privy_token": "<Privy ID Token>", "wallet_address": "0x1234...abcd"}' | python3 -m json.tool
```

**不合格時の調査**:
```bash
# 401 連発 → JWT 検証エラー
docker logs ultra-autotrade-backend-blue-production 2>&1 | grep -E "(jwt|InvalidToken|expired)"

# Privy 検証失敗
docker exec ultra-autotrade-backend-blue-production env | grep PRIVY_APP_ID
# .env と比較。PRIVY_APP_ID は production/staging で同値、PRIVY_APP_SECRET は別値の想定
```

### 4.3 ユーザー登録 + ウォレット接続

実装は **2 ファイルに分散**:
- `backend/app/users/router.py:35` — `prefix="/users"` (**複数形**)
- `backend/app/users/settings_router.py:19` — `prefix="/api/user"` (**単数形**)

**重要**: `/user/connect` / `/user/profile` / `/user/strategies` 等は**存在しない**(タスク仕様の推測)。実態は以下:

| Endpoint | Method | 行 | 用途 |
|----------|--------|---|------|
| `/users` | GET | 38 | 全ユーザー一覧 (admin) |
| `/users` | POST | 60 | ユーザー作成 (admin) |
| `/users/fee-schedule` | GET | 109 | Fee 体系一覧 |
| `/users/{user_id}` | GET | 129 | 単体取得 |
| `/users/{user_id}` | PUT | 160 | 更新 |
| `/users/{user_id}` | DELETE | 251 | 削除 (admin) |
| `/users/{user_id}/tier` | GET | 301 | tier 取得 |
| `/users/{user_id}/fee-info` | GET | 336 | fee 情報 |
| `/api/user/settings` | GET | 22 | 自分の設定 |
| `/api/user/settings` | PUT | 30 | 設定更新 |
| `/api/user/my-allocation` | GET | 93 | 自分のアロケーション |
| `/api/user/pause` | POST | 106 | 自動運用一時停止 |
| `/api/user/resume` | POST | 118 | 再開 |

**ウォレット接続は `/auth/wallet/connect` (§4.2 参照)**。

**curl 例 (自設定取得)**:
```bash
curl -fsS https://api.ultra-auto-trade.com/api/user/settings \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

**DB 確認 SQL**:
```bash
# 山本さん (id=11) の wallet 接続状況
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade \
  -c "SELECT id, username, role, wallet_address, privy_did, execution_policy, risk_mode FROM users WHERE id = 11;"

# 期待 (接続後):
#  id |  username  |  role   |     wallet_address      |   privy_did    | execution_policy  | risk_mode
# ----+------------+---------+-------------------------+----------------+-------------------+--------------
#  11 | yamamoto   | partner | 0x1234...abcd           | did:privy:...  | require_approval  | conservative
```

**不合格時の調査**:
```bash
# wallet_address 未保存 → API エラー or DB 制約違反
docker logs ultra-autotrade-backend-blue-production 2>&1 | grep -E "(wallet|connect)" | tail -20

# 既に他ユーザーで使われている (UNIQUE 制約)
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade \
  -c "SELECT id, username FROM users WHERE wallet_address = '0x1234...abcd';"
```

### 4.4 AI 判定トリガー

実装は **3 ファイルに分散**:
- `backend/app/automation/automation_router.py:135` — `POST /api/ai/trigger` (judgment トリガー)
- `backend/app/ai/decisions_router.py:19` — `prefix="/api/ai/decisions"`
- `backend/app/ai/router.py:55` — `prefix="/ai"`、main.py:212 で `include_router(ai_router, prefix="/api")` → 最終 `/api/ai/*`

| Endpoint | Method | 行 | 認証 |
|----------|--------|---|------|
| `/api/ai/trigger` | POST | automation_router.py:135 | Bearer (admin) |
| `/api/ai/decisions/latest` | GET | decisions_router.py:22 | Bearer |
| `/api/ai/decisions` | GET | decisions_router.py:35 | Bearer |
| `/api/ai/decisions/{decision_id}` | GET | decisions_router.py:75 | Bearer |
| `/api/ai/decisions` | POST | decisions_router.py:89 | Bearer |
| `/api/ai/analyze` | POST | router.py:61 | Bearer |
| `/api/ai/trend/confidence` | GET | router.py:92 | Bearer |
| `/api/ai/sentiment/history` | GET | router.py:154 | Bearer |
| `/api/ai/accuracy` | GET | router.py:279 | Bearer |

**注意**: `/automation/trigger-judgment` は**存在しない**(タスク仕様の推測)。実際は `/api/ai/trigger`。

**リクエストボディ**: `/api/ai/trigger` は **専用 schema なし** (Query parameter のみ)。レスポンスは `AIJudgmentTriggerResponse`。

**curl 例**:
```bash
# admin 権限で AI 判定トリガー (リクエストボディなし)
curl -fsS -X POST https://api.ultra-auto-trade.com/api/ai/trigger \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# 最新判定結果
curl -fsS https://api.ultra-auto-trade.com/api/ai/decisions/latest \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# 期待 (DecisionResponse schema):
# {
#   "id": 123,
#   "created_at": "2026-05-01T...",
#   "final_action": "HOLD",  // BUY / SELL / HOLD
#   "final_confidence": 52,
#   "key_data": {...},  // agents, market data
#   "rationale": "..."
# }
```

**DB 確認 SQL**:
```bash
# 直近 1 時間の判定一覧
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c "
SELECT created_at, final_action, final_confidence,
       key_data->'agents'->'indicator'->>'confidence' AS ind_conf,
       key_data->'agents'->'macro'->>'confidence' AS macro_conf
FROM ai_decisions
WHERE created_at > NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC LIMIT 10;"
```

**不合格時の調査**:
```bash
# scheduler が判定を出していない (HOLD のみ + 低信頼)
docker logs ultra-autotrade-backend-blue-production 2>&1 | grep -E "ai_judgment|aave_utilization_fetch_failed|301 Moved"

# Aave データ無し → indicator confidence < 30 になる
docker exec ultra-autotrade-backend-blue-production python -c "
from app.automation.aave_data_fetcher import fetch_aave_market_data_safe
import json
print(json.dumps({k: str(v) for k,v in fetch_aave_market_data_safe().items()}, indent=2))
"
# 期待: utilization_rate / supply_apy / borrow_apy が None でない値
```

### 4.5 Aave deposit/withdraw 提案

実装: `backend/app/proposals/router.py:37` — `prefix="/api/proposals"`(`/proposals/*` ではなく**`/api/proposals/*`**)

| Endpoint | Method | 行 | 認証 |
|----------|--------|---|------|
| `/api/proposals` | POST | 391 | Bearer | 提案作成 (内部 API)|
| `/api/proposals/pending` | GET | 278 | Bearer | 自分の pending 提案 |
| `/api/proposals/history` | GET | 300 | Bearer | 自分の履歴 |
| `/api/proposals/{proposal_id}` | GET | 377 | Bearer | 単体取得 |
| `/api/proposals/{proposal_id}/approve` | POST | 321 | Bearer | 承認 → 実 deposit/withdraw 実行 |
| `/api/proposals/{proposal_id}/reject` | POST | 353 | Bearer | 却下 |
| `/api/proposals/admin/all` | GET | 188 | Bearer (admin) | 全提案一覧 |
| `/api/proposals/admin/stats` | GET | 241 | Bearer (admin) | 統計 |

**注意**: `/api/proposals` (GET list) は**存在しない** — 一覧取得は `/api/proposals/pending` か `/api/proposals/history` を使う。

**curl 例 (一覧 → 承認)**:
```bash
# 1. 自分の pending 提案一覧
curl -fsS "https://api.ultra-auto-trade.com/api/proposals/pending" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# 2. 承認 → 実 deposit 実行 (CooldownError / HFGuard チェック後)
# ⚠️ ProposalApprove / ProposalReject は専用 schema なし、リクエストボディも基本不要
curl -fsS -X POST https://api.ultra-auto-trade.com/api/proposals/45/approve \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# 期待: status="approved" → 内部実行 → "executed" に遷移、tx_hash がセット
```

**DB 確認 SQL**:
```bash
# 直近 1 時間の山本さん向け提案
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c "
SELECT p.id, p.created_at, p.operation, p.amount_usd, p.status, p.tx_hash, u.username, u.execution_policy
FROM proposals p
JOIN users u ON u.id = p.user_id
WHERE p.created_at > NOW() - INTERVAL '1 hour'
ORDER BY p.created_at DESC LIMIT 20;"

# 提案が出ない場合の確認:
# - execution_policy='require_approval' のユーザーのみ提案対象
# - AI 判定が BUY/SELL を出していること (HOLD なら提案なし)
```

**不合格時の調査**:
```bash
# 承認失敗 → cooldown / HF / amount limit のいずれか
docker logs ultra-autotrade-backend-blue-production 2>&1 | grep -E "(CooldownError|HFGuard|MaxTradeError)"

# tx 失敗 → web3 RPC エラー / nonce 競合
docker logs ultra-autotrade-backend-blue-production 2>&1 | grep -E "(web3|nonce|revert)"
```

### 4.6 ProposalCreate スキーマ (推測絶対禁止領域)

`backend/app/proposals/schemas.py:12-50` から直接抽出 (2026-04-24 教訓: 推測禁止、field 名違いインシデント再発防止)。

#### ProposalCreate (line 12-24)

**全 12 フィールドを完全列挙** (1 文字違いでも 422 Validation Error):

| Field | Type | 必須 | デフォルト | 備考 |
|-------|------|------|-----------|------|
| `user_id` | `int` | ✅ | — | 提案宛先ユーザー ID |
| `ai_decision_id` | `Optional[int]` | ❌ | None | 判定根拠の ai_decisions.id |
| `operation` | `str` | ✅ | — | 操作種別 (deposit/withdraw/rebalance) |
| `asset` | `str` | ✅ | — | 資産シンボル (USDC 等) |
| `amount` | `Decimal` | ✅ | — | 資産量 (asset の単位) |
| `amount_usd` | `Decimal` | ✅ | — | USD 換算金額 |
| `reason` | `str` | ✅ | — | AI 判定理由テキスト (※`rationale` ではない) |
| `expected_hf_after` | `Optional[Decimal]` | ❌ | None | 実行後の予測 HF |
| `estimated_gas_usd` | `Optional[Decimal]` | ❌ | None | 推定ガス代 USD |
| `fee_rate` | `Optional[Decimal]` | ❌ | None | Fee Model 適用レート |
| `fee_amount` | `Optional[Decimal]` | ❌ | None | Fee 適用金額 |
| `expires_at` | `Optional[datetime]` | ❌ | None | 提案有効期限 |

**よくある誤り (2026-04-24 インシデント由来)**:
- ❌ `rationale` → ✅ `reason`
- ❌ `chain_id` / `protocol` / `metadata` フィールドは**存在しない**
- ❌ `amount_usd` のみ送って `asset` / `amount` を省略 → 422

#### ProposalApprove / ProposalReject (line ?)

**専用スキーマは存在しない**。`/api/proposals/{id}/approve` および `/reject` は **リクエストボディを受け付けない**(`backend/app/proposals/router.py:321/353`)。承認/却下時のコメント用 field を将来追加する場合は schemas.py を新設する必要あり。

#### ProposalResponse (line 27-50)

**全 21 フィールド**:

| Field | Type | 備考 |
|-------|------|------|
| `id` | `int` | |
| `user_id` | `int` | |
| `ai_decision_id` | `Optional[int]` | |
| `operation` | `str` | "deposit" / "withdraw" / "rebalance" |
| `asset` | `str` | |
| `amount` | `Decimal` (str で返却) | |
| `amount_usd` | `Decimal` (str で返却) | |
| `reason` | `str` | |
| `expected_hf_after` | `Optional[Decimal]` | |
| `estimated_gas_usd` | `Optional[Decimal]` | |
| `fee_rate` | `Optional[Decimal]` | |
| `fee_amount` | `Optional[Decimal]` | |
| `status` | `str` | `pending` / `approved` / `executed` / `failed` / `rejected` / `expired` |
| `approved_at` | `Optional[datetime]` | |
| `rejected_at` | `Optional[datetime]` | |
| `executed_at` | `Optional[datetime]` | |
| `tx_hash` | `Optional[str]` | 実行後の TX hash |
| `error_message` | `Optional[str]` | 失敗時のエラー (c3d4e5f6a7b8 で追加) |
| `expires_at` | `Optional[datetime]` | |
| `created_at` | `datetime` | |
| `updated_at` | `datetime` | |

**curl で field 名を絶対に推測しない**: backend/app/proposals/schemas.py を必ず直読すること。pydantic 経由なので **field 名一文字違い → 422 Validation Error** で即失敗する (2026-04-24 ProposalCreate スキーマ違反インシデントの根本原因)。

---

## 5. Gate 4 Playwright E2E 実行

### 5.1 deploy 直後の不安定性に注意 (2026-05-01 教訓)

**現象**: 2026-05-01 Phase 3 staging Blue/Green deploy 直後、Gate 4 で **1 failed + 4 flaky** が発生。同じテストを deploy 完了後 ~30 分待機して再実行 → **40/40 全 pass**。

**原因仮説**:
- backend container 起動完了 ≠ アプリ初期化完了
- scheduler 初期化、Aave RPC 接続、LLM API ウォームアップに時間がかかる
- nginx upstream 切替直後の TCP 残接続が混在する可能性

**運用ルール**:
1. deploy 完了後は **30 分待機** してから Gate 4 実行
2. flaky 検出時は `--repeat-each=5` で再現性確認
3. 30 分待っても fail が再現するなら**真のリグレッション**として扱う

**実行コマンド**:
```bash
# Hetzner 内部から実行 (staging URL は Cloudflare Access ブロック中 → §5.2 参照)
ssh -i ~/.ssh/hetzner_staging ultra@77.42.46.155

# nginx 経由 (active slot 自動追跡、IPv4 強制)
docker run --rm --network host \
  -v /opt/ultra-autotrade/frontend:/app -w /app \
  -e STAGING_URL=http://127.0.0.1:3001 \
  -e NEXT_PUBLIC_BACKEND_BASE_URL=http://127.0.0.1:8082 \
  -e BACKEND_URL=http://127.0.0.1:8082 \
  mcr.microsoft.com/playwright:v1.58.2-noble \
  npx playwright test --reporter=list --project='Desktop Chrome' 2>&1 | tail -10

# repeat-each=5 で flaky 確認
docker run --rm --network host \
  -v /opt/ultra-autotrade/frontend:/app -w /app \
  -e STAGING_URL=http://127.0.0.1:3001 \
  -e BACKEND_URL=http://127.0.0.1:8082 \
  mcr.microsoft.com/playwright:v1.58.2-noble \
  npx playwright test --reporter=list --repeat-each=5 e2e/tester-yamamoto-flow.spec.ts
```

**期待**: 113 passed / 0 failed / 47 skipped (2026-05-01 staging で確認済の baseline)

### 5.2 staging URL アクセス制限の対処

**現状** (GID 1214280530443990): staging URL `https://staging.ultra-auto-trade.com` は Cloudflare Access 認証ブロックで外部到達不可。

**代替手段**:

| 手段 | 用途 | コマンド |
|------|------|---------|
| Hetzner 内部から ssh | 推奨 | `ssh ultra@77.42.46.155` → 上記 docker run |
| production URL 直打ち | 本番のみ | `STAGING_URL=https://app.ultra-auto-trade.com BACKEND_URL=https://api.ultra-auto-trade.com` |
| ローカル `npm run dev` | フロント単体 | `STAGING_URL=http://localhost:3000` + `cd frontend && npm run dev` |

**禁止**: 直 IP `77.42.46.155` 接続 (127.0.0.1 バインドにより接続拒否される、これは正常動作)

---

## 6. 障害復旧手順

### 6.1 Blue/Green での即時ロールバック

`scripts/deploy_production.sh` での deploy は blue → green (or 逆) 切替で進む。**旧 active container は stopped 状態で残置** されるので、即時ロールバックが可能。

**手順**:
```bash
ssh -i ~/.ssh/hetzner_staging ultra@77.42.46.155
cd /opt/ultra-autotrade

# 1. 現在 active な slot を確認
grep -E "server backend-(blue|green)" docker/nginx/upstream.production.conf

# 2. 旧 slot を再起動 (stopped 状態だった container を up)
docker start ultra-autotrade-backend-blue-production  # green→blue 戻しの場合

# 3. /health で旧 container が応答するのを待つ
for i in {1..30}; do
  curl -fsS http://127.0.0.1:8010/health > /dev/null 2>&1 && echo "blue OK" && break
  sleep 2
done

# 4. nginx upstream を旧 slot に書き換え
sudo sed -i 's/server backend-green-production:8000/server backend-blue-production:8000/' \
  docker/nginx/upstream.production.conf
docker exec ultra-autotrade-nginx-production nginx -s reload

# 5. 動作確認
curl -fsS https://api.ultra-auto-trade.com/health | python3 -m json.tool
```

**`scripts/rollback_production.sh` がある場合はそちらを優先**(ない場合は上記手動手順):
```bash
ls -la scripts/rollback_*.sh
```

### 6.2 backend コンテナ消失時 (2026-04-24 反面教師)

2026-04-24 に backend container を 3 回連続で消失させたインシデント。原因: container_name 衝突 + `docker compose up` の force-recreate 挙動誤認。

**復旧手順**:
```bash
# 1. 現状確認 (停止コンテナも含めて)
docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' | grep ultra-autotrade

# 2. 衝突している container を停止 + 削除
docker stop ultra-autotrade-backend-blue-production 2>/dev/null
docker rm ultra-autotrade-backend-blue-production 2>/dev/null

# 3. compose project 名を明示して up (CLAUDE.md 教訓)
docker compose -p ultra-autotrade-project \
  -f docker-compose.production.yml \
  --env-file .env.production \
  up -d --no-deps backend-blue

# 4. 起動確認
docker ps --filter "name=ultra-autotrade-backend-blue-production"
docker logs --tail=50 ultra-autotrade-backend-blue-production
```

**注意点**:
- `docker compose down --remove-orphans` で消えない場合は `docker rm -f <container>` で強制削除
- `docker system prune -af` は**禁止** (使用中イメージ削除リスク、CLAUDE.md 明記)
- 復旧後は §4.1 のヘルスチェック実行

### 6.3 .env 汚染復元 (2026-04-18 staging 汚染インシデント)

**原因**: `sed -i 's/X/Y/' .env.staging .env.production` のような一斉置換で、別環境の env まで書き換わる。CLAUDE.md は `sed -i` を**禁止**。

**バックアップ場所**:
```bash
# Hetzner /opt/ultra-autotrade/ 直下に *.backup-YYYYMMDD_HHMMSS で残す
ls -la /opt/ultra-autotrade/.env.production.backup-* 2>/dev/null
ls -la /opt/ultra-autotrade/.env.staging-new.backup-* 2>/dev/null

# git 管理の .example も比較対象に
diff <(grep -v '^#' /opt/ultra-autotrade/.env.production | grep '=' | cut -d= -f1 | sort) \
     <(grep -v '^#' /opt/ultra-autotrade/backend/.env.staging.example | grep '=' | cut -d= -f1 | sort)
```

**復元コマンド**:
```bash
# 1. 現状の汚染 .env をバックアップ (上書きされる前に)
cp .env.production .env.production.before-restore-$(date +%Y%m%d_%H%M%S)

# 2. 直近の正常バックアップから復元
cp .env.production.backup-20260417_103000 .env.production  # 例: 2026-04-17 のもの

# 3. md5 で同一性確認
md5sum .env.production .env.production.before-restore-*

# 4. backend/frontend 再起動
docker compose -p ultra-autotrade-project \
  -f docker-compose.production.yml \
  --env-file .env.production \
  up -d --no-deps --force-recreate backend-blue

# 5. .env が反映されているか確認
docker exec ultra-autotrade-backend-blue-production env | grep -E "AAVE_NETWORK|DATABASE_URL" | sed 's/=.*/=***/'
```

**禁止事項**:
- `sed -i` で複数 .env を同時更新 (一斉汚染リスク)
- `bash scripts/check_env_separation.sh` を skip して deploy

### 6.4 DB migration 失敗時のロールバック

**alembic 未インストール環境** (CLAUDE.md 教訓): production / staging は alembic コマンドが container 内に存在しない。migration は **手動 SQL 適用方式**。

**バックアップから復元 (full restore)**:
```bash
# 1. 現状 DB のスナップショット (失敗 migration 後の状態を保存)
docker exec ultra-autotrade-postgres-production pg_dump -U ultra ultra_autotrade \
  > /tmp/post_failed_migration_$(date +%Y%m%d_%H%M%S).sql

# 2. backend を停止 (DB 接続を切る)
docker stop ultra-autotrade-backend-blue-production

# 3. DB restore (deploy 前に取った backup を使用)
gunzip -c /opt/ultra-autotrade/backups/backup_production_20260501_111758.sql.gz \
  | docker exec -i ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade

# (圧縮していなければ)
docker exec -i ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade \
  < /opt/ultra-autotrade/backups/backup_production_20260501_111758.sql

# 4. backend を再起動
docker start ultra-autotrade-backend-blue-production

# 5. /health 確認
curl -fsS https://api.ultra-auto-trade.com/health | python3 -m json.tool
```

**migration 単独 revert (手動 DROP)**:
```bash
# 例: privy_did 追加を revert
docker exec -i ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade <<'SQL'
DROP INDEX IF EXISTS ix_users_privy_did;
ALTER TABLE users DROP COLUMN IF EXISTS privy_did;
SQL

# 例: CHECK 制約を revert
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade \
  -c "ALTER TABLE users DROP CONSTRAINT IF EXISTS users_execution_policy_check;"
```

**注意**:
- `DROP COLUMN` は不可逆。データ消失するので **full restore** を優先
- backend コードが新カラムを参照している間に DROP すると即時 500 エラー → 必ず backend 停止後に実行

---

## 7. 山本さん運用フロー検証 (docs/22 §12 連携)

partner 先行検証フェーズ専用フロー。docs/22 §12 と重複しない検証手順を集約。

### 7.1 MetaMask 接続確認

**前提**: 山本さん (id=11, role=partner, execution_policy=require_approval) が MetaMask に Base Sepolia testnet USDC を入金済み。

**確認 SQL**:
```bash
# 1. 山本さんの DB 状態
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c "
SELECT id, username, role, wallet_address, privy_did,
       execution_policy, risk_mode, tier, terms_accepted_at, last_judgment_at
FROM users WHERE id = 11;"

# 期待 (フル接続後):
#  id | username | role    | wallet_address  | privy_did      | execution_policy | risk_mode    | tier   | terms_accepted_at | last_judgment_at
#  11 | yamamoto | partner | 0x1234...abcd   | did:privy:...  | require_approval | conservative | MIDDLE | 2026-04-...       | 2026-05-...

# 2. 接続前に確認すべき不在項目
# - wallet_address IS NULL → /user/connect 未実行
# - privy_did IS NULL → Privy ログイン未完了
# - terms_accepted_at IS NULL → 利用規約未承諾
```

**MetaMask + Aave 残高確認 (web3)**:
```bash
docker exec ultra-autotrade-backend-blue-production python -c "
from app.aave.client import get_default_aave_client
from web3 import Web3
c = get_default_aave_client()
addr = '0x1234...abcd'  # 山本さん wallet
checksum = Web3.to_checksum_address(addr)
print('chain_id:', c.w3.eth.chain_id)
print('ETH balance:', c.w3.eth.get_balance(checksum))
# USDC 残高は ERC20 contract.balanceOf(addr) で確認
"
```

### 7.2 /user/approve 承認フロー

**前提条件**:
1. AI 判定が BUY/SELL を出すこと (HOLD なら提案なし)
2. 山本さんの execution_policy = `require_approval`
3. amount_usd が max_single_trade_usd 以下
4. 直近 10 分以内に同チェーンで Aave 操作なし (cooldown)

**確認手順**:

```bash
# 1. 山本さん向け pending 提案を確認
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c "
SELECT p.id, p.created_at, p.operation, p.amount_usd, p.status,
       p.ai_decision_id, p.rationale
FROM proposals p
WHERE p.user_id = 11 AND p.status = 'pending'
ORDER BY p.created_at DESC LIMIT 5;"

# 提案がない場合の原因分布:
# - AI が HOLD のみ → §4.4 の指標 confidence を確認
# - cooldown 中 → 直近の executed/failed を確認
# - max_single_trade_usd 超過 → users.max_single_trade_usd を確認

# 2. ユーザー側で /proposals/{id}/approve を呼ぶ (frontend UI 経由が通常)
TOKEN=<山本さんの JWT>
curl -fsS -X POST https://api.ultra-auto-trade.com/proposals/45/approve \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' | python3 -m json.tool

# 期待: {"status": "approved" → "executed", "tx_hash": "0x...", "executed_at": "..."}

# 3. 承認後 30 秒以内に DB 反映確認
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c "
SELECT id, status, tx_hash, error_message, executed_at
FROM proposals WHERE id = 45;"

# 4. 失敗時の原因分布
# - status=failed + error_message → web3 RPC エラー / nonce / revert
# - status=approved のまま (executed にならない) → scheduler 未稼働
docker logs --tail=200 ultra-autotrade-backend-blue-production 2>&1 \
  | grep -E "proposal_45|tx_hash|CooldownError|HFGuard"
```

### 7.3 24h 観察項目

GID 1214444133815913 の notes より、24h 観察期間で確認すべき 4 項目 (A-D):

**A. AI 判定の動作確認** (BUY/SELL が 1 件以上出ること):
```bash
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c "
SELECT date_trunc('hour', created_at) AS hour,
       final_action, COUNT(*) AS n, AVG(final_confidence)::int AS avg_conf
FROM ai_decisions
WHERE created_at >= '<deploy 時刻>'
GROUP BY 1, 2
ORDER BY 1 DESC, 2;"

# Gate 4 合格条件: BUY または SELL が ≥1 件
```

**B. proposals 作成確認** (require_approval ユーザーに提案が出ること):
```bash
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c "
SELECT p.created_at, p.operation, p.amount_usd, u.username, u.execution_policy
FROM proposals p
JOIN users u ON u.id = p.user_id
WHERE p.created_at >= '<deploy 時刻>'
ORDER BY p.created_at DESC LIMIT 20;"
```

**C. 旧 V2 REST エラーが 0 件**:
```bash
docker logs ultra-autotrade-backend-blue-production --since=24h 2>&1 \
  | grep -E "(aave_utilization_fetch_failed|301 Moved Permanently|aave-api-v2.aave.com)" | wc -l
# 期待: 0
```

**D. scheduler 健全性 + warning なし**:
```bash
# 24h 中の WARN/ERROR 件数
docker logs ultra-autotrade-backend-blue-production --since=24h 2>&1 \
  | grep -cE "(ERROR|WARN|aave_chain_registry_miss|scheduler_last_error)"

# /health の継続観察 (warnings 配列)
curl -fsS https://api.ultra-auto-trade.com/health | python3 -m json.tool | grep -A 2 warnings
```

**24h 観察 NG 時のアクション**:
- A の BUY/SELL 0 件 → Lane D 再オープン (AI 判定ロジック調査)
- B で require_approval ユーザーに提案 0 件 → Lane D Phase 5 修正の verification
- C の旧 V2 エラー >0 → 即時 backend ログ調査、PR #159 の挙動確認
- D の scheduler_last_error / warnings に値あり → INTERNAL_API_TOKEN 等の env 設定確認

---

## 8. 再発防止策(根本解決、メモリ #29 原則)

| インシデント | 症状 | 原因 | 予防策 |
|---|---|---|---|
| 2026-04-18 .env staging 汚染 | staging で production の値が混入 | sed -i 一斉更新で別環境 .env まで書換 | sed -i 禁止、awk 明示行のみ |
| 2026-04-24 API パス推測 | curl で 404 連発 | /api/auth/login vs /auth/login 混在 | プロジェクトナレッジから schema 必読、§4 curl テンプレ整備 |
| 2026-04-24 ProposalCreate スキーマ違反 | INSERT で field 名不一致 | 推測でリクエストボディ生成 | pydantic モデル直読、§4.6 で field 一覧 |
| 2026-04-24 container_name 衝突 | up で backend 消失 | 別 project 名で同 container_name | §2.4 事前チェック必須 |
| 2026-04-26 .env PASSWORD 未展開 | DB 接続不能 | compose `${PW}` がシェル環境から展開されず | docker exec env で実値検証 |
| 2026-05-01 Blue/Green 初期化遅延 | Gate 4 で 1 failed + 4 flaky | deploy 完了 ≠ アプリ初期化完了 | Gate 4 を deploy 後 30分以降に走らせる運用ルール |

### 8.1 deploy_production.sh への組み込み (TODO)
- [ ] §2 の 4 点チェックを sanity check として組み込み
- [ ] 手動 ALTER TABLE 必要 migration の自動検出 (alembic vs 実DB)
- [ ] deploy 完了後 30 分自動待機 → Gate 4 自動実行 (carry over: GID 未起票)

### 8.2 CI 改善 (TODO)
- [ ] CI .env 分離必須化(production / staging / test)
- [ ] compose file 統一 (staging-new.yml の historical 名残整理)
- [ ] PR diff に手動 ALTER TABLE が含まれる場合の警告 lint
