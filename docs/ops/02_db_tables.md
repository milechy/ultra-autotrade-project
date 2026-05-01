# Ultra AutoTrade — DB テーブル一覧

> 生成: 2026-04-24 / ソース: `backend/app/*/models.py`
> DB: PostgreSQL 16 + pgvector (pg16)
> 接続: `postgresql://ultra:<PW>@postgres:5432/ultra_autotrade`

---

## 確認コマンド

```bash
# コンテナ名取得
docker ps | grep postgres

# テーブル一覧確認
docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d ultra_autotrade \
  -c "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;"

# カラム確認（例: proposals）
docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d ultra_autotrade \
  -c "SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name='proposals' ORDER BY ordinal_position;"
```

---

## テーブル一覧

### `users` (auth/models.py)

| カラム | 型 | NULL | 説明 |
|--------|-----|------|------|
| id | Integer PK | NO | 自動採番 |
| email | String(255) UNIQUE | NO | メールアドレス |
| username | String(100) UNIQUE | NO | ユーザー名 |
| hashed_password | String(255) | NO | bcrypt ハッシュ |
| role | String(20) | NO | `admin` / `partner` / `viewer` (default: `viewer`) |
| is_active | Boolean | NO | アクティブフラグ (default: true) |
| created_at | DateTime(tz) | NO | 作成日時 |
| updated_at | DateTime(tz) | NO | 更新日時 |
| terms_accepted_at | DateTime(tz) | YES | 利用規約承諾日時 |
| terms_version | String(20) | YES | 承諾バージョン |
| risk_mode | String(20) | YES | `conservative` / `balanced` / `aggressive` |
| notification_email | String(255) | YES | 通知先メール |
| notification_frequency | String(20) | NO | 通知頻度 |
| max_single_trade_usd | Numeric(20,2) | YES | 1取引上限USD |
| max_daily_trade_usd | Numeric(20,2) | YES | 日次取引上限USD |
| user_mode | String(20) | NO | `managed` / `self` (default: `managed`) |
| execution_policy | String(20) | NO | `auto` / `manual` |
| wallet_address | String(100) | YES | ウォレットアドレス |
| invited_by | Integer FK(users.id) | YES | 招待者ID |
| tier | String(20) | NO | 投資ティア |
| last_judgment_at | DateTime(tz) | YES | 最後のAI判定日時 |

**INDEX**: `email`, `username`

---

### `user_settings` (users/models.py)

| カラム | 型 | NULL | 説明 |
|--------|-----|------|------|
| id | Integer PK | NO | 自動採番 |
| user_id | Integer FK(users.id) UNIQUE | NO | ユーザーID |
| notification_email | String(255) | YES | 通知先メール |
| notification_frequency | String(20) | NO | 通知頻度 |
| max_single_trade_usd | Numeric(20,2) | YES | 1取引上限USD |
| max_daily_trade_usd | Numeric(20,2) | YES | 日次取引上限USD |
| risk_mode | String(20) | NO | リスクモード (default: `conservative`) |
| dark_mode | Boolean | NO | ダークモード (default: true) |
| language | String(10) | NO | 言語 (default: `ja`) |
| two_factor_enabled | Boolean | NO | 2FA有効 (default: false) |
| created_at | DateTime(tz) | NO | 作成日時 |
| updated_at | DateTime(tz) | NO | 更新日時 |

---

### `invitations` (invitations/models.py)

| カラム | 型 | NULL | 説明 |
|--------|-----|------|------|
| id | Integer PK | NO | 自動採番 |
| code | String(16) UNIQUE | NO | 招待コード |
| partner_id | Integer FK(users.id) | NO | 招待者（partner） |
| expires_at | DateTime(tz) | NO | 有効期限 |
| max_uses | Integer | NO | 最大使用回数 (default: 1) |
| used_count | Integer | NO | 使用済み回数 (default: 0) |
| created_at | DateTime(tz) | NO | 作成日時 |
| invited_user_id | Integer FK(users.id) | YES | 使用したユーザーID |

**INDEX**: `code`

---

### `ai_decisions` (ai/models.py)

| カラム | 型 | NULL | 説明 |
|--------|-----|------|------|
| id | Integer PK | NO | 自動採番 |
| user_id | Integer | YES | 対象ユーザーID |
| query | Text | NO | 判定クエリ |
| action | String(10) | NO | `BUY` / `SELL` / `HOLD` |
| confidence | Integer | NO | 信頼度 (0-100) |
| reason | Text | YES | 理由 |
| primary_provider | String(50) | NO | 一次プロバイダ名 |
| primary_action | String(10) | NO | 一次判定 |
| primary_confidence | Integer | NO | 一次信頼度 |
| secondary_provider | String(50) | YES | 二次プロバイダ名 |
| secondary_action | String(10) | YES | 二次判定 |
| secondary_confidence | Integer | YES | 二次信頼度 |
| agreed | Boolean | NO | 一致フラグ (default: false) |
| rag_context_json | JSON | YES | RAGコンテキスト |
| created_at | DateTime(tz) | NO | 作成日時 |

**INDEX**: `user_id`, `action`

---

### `proposals` (proposals/models.py)

| カラム | 型 | NULL | 説明 |
|--------|-----|------|------|
| id | Integer PK | NO | 自動採番 |
| user_id | Integer | NO | 対象ユーザーID |
| ai_decision_id | Integer | YES | AI判定ID |
| operation | String(20) | NO | `deposit` / `withdraw` |
| asset | String(20) | NO | アセット名 (例: `USDC`) |
| amount | Numeric(36,18) | NO | 数量 |
| amount_usd | Numeric(20,2) | NO | USD換算額 |
| reason | Text | NO | 提案理由 |
| expected_hf_after | Numeric | YES | 実行後の予想HF |
| estimated_gas_usd | Numeric | YES | 推定ガス代USD |
| fee_rate | Numeric | YES | 手数料率 |
| fee_amount | Numeric | YES | 手数料額 |
| status | String(20) | NO | `pending` / `approved` / `rejected` / `executed` / `expired` (default: `pending`) |
| approved_at | DateTime(tz) | YES | 承認日時 |
| rejected_at | DateTime(tz) | YES | 拒否日時 |
| executed_at | DateTime(tz) | YES | 実行日時 |
| tx_hash | String(100) | YES | トランザクションハッシュ |
| error_message | Text | YES | エラーメッセージ |
| expires_at | DateTime(tz) | NO | 有効期限 |
| created_at | DateTime(tz) | NO | 作成日時 |
| updated_at | DateTime(tz) | NO | 更新日時 |

**INDEX**: `user_id`, `status`

---

### `transactions` (transactions/models.py)

| カラム | 型 | NULL | 説明 |
|--------|-----|------|------|
| id | Integer PK | NO | 自動採番 |
| user_id | Integer | NO | ユーザーID |
| wallet_address | String(100) | YES | ウォレットアドレス |
| operation | String(20) | NO | `deposit` / `withdraw` |
| asset | String(20) | NO | アセット名 |
| amount | Numeric(36,18) | NO | 数量 |
| amount_usd | Numeric(20,2) | NO | USD換算額 |
| tx_hash | String(100) | YES | txハッシュ |
| chain | String(50) | NO | チェーン名 |
| status | String(20) | NO | `pending` / `confirmed` / `failed` (default: `pending`) |
| ai_decision_id | Integer | YES | AI判定ID |
| gas_used | Numeric | YES | 使用ガス |
| gas_price_gwei | Numeric | YES | ガスプライス |
| is_dry_run | Boolean | NO | ドライラン (default: false) |
| error_message | Text | YES | エラーメッセージ |
| created_at | DateTime(tz) | NO | 作成日時 |
| updated_at | DateTime(tz) | NO | 更新日時 |

**INDEX**: `user_id`, `operation`, `asset`, `status`

---

### `portfolio_snapshots` (portfolio/models.py)

| カラム | 型 | NULL | 説明 |
|--------|-----|------|------|
| id | Integer PK | NO | 自動採番 |
| user_id | Integer | NO | ユーザーID |
| total_value_usd | Numeric(20,2) | NO | 総資産USD |
| total_supply_usd | Numeric(20,2) | NO | 預入USD |
| total_borrow_usd | Numeric(20,2) | NO | 借入USD |
| health_factor | Numeric | YES | Health Factor |
| positions_json | JSON | YES | ポジション詳細 |
| recorded_at | DateTime(tz) | NO | 記録日時 |

**INDEX**: `user_id`

---

### `portfolio_history` (portfolio/models.py)

| カラム | 型 | NULL | 説明 |
|--------|-----|------|------|
| id | Integer PK | NO | 自動採番 |
| user_id | Integer | NO | ユーザーID |
| period_type | String(10) | NO | `daily` / `weekly` / `monthly` |
| period_start | DateTime(tz) | NO | 期間開始 |
| period_end | DateTime(tz) | NO | 期間終了 |
| open_value_usd | Numeric(20,2) | NO | 期初資産USD |
| close_value_usd | Numeric(20,2) | NO | 期末資産USD |
| high_value_usd | Numeric(20,2) | NO | 高値USD |
| low_value_usd | Numeric(20,2) | NO | 安値USD |
| pnl_usd | Numeric(20,2) | NO | 損益USD |
| pnl_pct | Numeric(10,4) | NO | 損益率 |
| avg_health_factor | Numeric | YES | 平均HF |
| snapshot_count | Integer | NO | スナップショット数 (default: 0) |
| created_at | DateTime(tz) | NO | 作成日時 |

**INDEX**: `user_id`, `period_type`

---

### `knowledge_sources` (knowledge/models.py)

| カラム | 型 | NULL | 説明 |
|--------|-----|------|------|
| id | Integer PK | NO | 自動採番 |
| source_url | String(2048) | YES | ソースURL |
| title | String(500) | YES | タイトル |
| item_type | String(20) | NO | `text` / `url` / 他 (default: `text`) |
| status | String(20) | NO | `pending` / `processed` / `failed` (default: `pending`) |
| quality_score | Float | YES | 品質スコア |
| created_at | DateTime(tz) | NO | 作成日時 |
| updated_at | DateTime(tz) | NO | 更新日時 |

**INDEX**: `status`

---

### `knowledge_documents` (knowledge/models.py)

| カラム | 型 | NULL | 説明 |
|--------|-----|------|------|
| id | Integer PK | NO | 自動採番 |
| source_id | Integer FK(knowledge_sources.id) | NO | ソースID |
| raw_text | Text | NO | 生テキスト |
| created_at | DateTime(tz) | NO | 作成日時 |

---

### `knowledge_chunks` (knowledge/models.py)

| カラム | 型 | NULL | 説明 |
|--------|-----|------|------|
| id | Integer PK | NO | 自動採番 |
| document_id | Integer FK(knowledge_documents.id) | NO | ドキュメントID |
| content | Text | NO | チャンクテキスト |
| chunk_index | Integer | NO | チャンクインデックス |
| token_count | Integer | NO | トークン数 |
| created_at | DateTime(tz) | NO | 作成日時 |
| embedding | Vector(1536) | YES | pgvector埋め込み (PostgreSQL) |

---

### `notification_logs` (notifications/models.py)

| カラム | 型 | NULL | 説明 |
|--------|-----|------|------|
| id | Integer PK | NO | 自動採番 |
| channel | String(50) | NO | `slack` / `line` / `push` |
| severity | String(20) | NO | `info` / `warning` / `critical` |
| title | String(255) | NO | タイトル |
| body | Text | NO | 本文 |
| partner_id | Integer | YES | パートナーID |
| user_id | Integer | YES | ユーザーID |
| created_at | DateTime(tz) | NO | 作成日時 |

---

### `fee_configs` (billing/models.py)

| カラム | 型 | NULL | 説明 |
|--------|-----|------|------|
| id | Integer PK | NO | 自動採番 |
| management_fee_rate | Numeric | NO | 管理手数料率 |
| performance_fee_rate | Numeric | NO | 成功報酬率 |
| high_water_mark_enabled | Boolean | NO | HWM有効 |
| minimum_aum | Numeric | NO | 最低運用額 |
| created_at | DateTime(tz) | NO | 作成日時 |
| updated_at | DateTime(tz) | NO | 更新日時 |

---

### `fee_calculations` (billing/models.py)

| カラム | 型 | NULL | 説明 |
|--------|-----|------|------|
| id | Integer PK | NO | 自動採番 |
| user_id | Integer FK(users.id) | NO | ユーザーID |
| calculation_date | Date | NO | 計算日 |
| period_type | String(10) | NO | `daily` / `monthly` |
| aum_snapshot | Numeric | NO | AUMスナップショット |
| management_fee | Numeric | NO | 管理手数料 |
| performance_fee | Numeric | NO | 成功報酬 |
| total_fee | Numeric | NO | 合計手数料 |
| profit_since_hwm | Numeric | NO | HWM以降の利益 |
| high_water_mark | Numeric | NO | ハイウォーターマーク |
| created_at | DateTime(tz) | NO | 作成日時 |

---

### `high_water_marks` (billing/models.py)

| カラム | 型 | NULL | 説明 |
|--------|-----|------|------|
| id | Integer PK | NO | 自動採番 |
| user_id | Integer FK(users.id) UNIQUE | NO | ユーザーID |
| hwm_value | Numeric | NO | HWM値 |
| updated_at | DateTime(tz) | NO | 更新日時 |

---

## マイグレーション方針

このプロジェクトでは **Alembic による自動マイグレーションは使用しない**。
新規カラム追加時は Hetzner 本番サーバーで直接 `ALTER TABLE` を実行すること。

```bash
# 例: proposals テーブルに error_message カラムを追加
docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d ultra_autotrade \
  -c "ALTER TABLE proposals ADD COLUMN IF NOT EXISTS error_message TEXT;"

# 例: transactions テーブルに error_message カラムを追加
docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d ultra_autotrade \
  -c "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS error_message TEXT;"
```

> **注意**: コンテナ名を必ず `docker ps | grep postgres` で確認してから実行すること。
> 推測による本番SQL実行は CLAUDE.md で禁止されている。

---

## 本番テストデータ作成禁止ルール

> **制定**: 2026-04-28 / 背景: `fund_allocations` 本番DBクリーンアップインシデント（282 行削除）

### 絶対禁止事項

| 禁止 | 理由 |
|------|------|
| 本番DB (`ultra_autotrade`) へのテストデータ INSERT | 実ユーザーデータと混在し、手数料計算・AI判定・レポートが汚染される |
| 本番DB へのダミーデータ INSERT | 同上。「仮データ」「動作確認用」も含む |
| 本番コンテナ (`*-production`) での seed スクリプト実行 | production guard なしのスクリプトは即時停止し、実行を取り消す |
| 動作確認のための本番 `INSERT` / `UPDATE` の直打ち | staging で代替できない理由がない限り禁止 |

### テストデータ作成の正しい手順

**1. staging DB のみで作成する**

```bash
# staging コンテナに接続（本番コンテナ名と混同しないこと）
docker ps | grep postgres   # コンテナ名を必ず目視確認
docker exec ultra-autotrade-postgres-staging \
  psql -U ultra -d ultra_autotrade_staging \
  -c "INSERT INTO ..."
```

**2. シードスクリプトを使う（production guard 必須）**

テスト用シードスクリプトは `scripts/seed_test_data.sh` を使用すること（別 PR にて起票予定）。
すべてのシードスクリプトには以下の production guard を先頭に記載すること:

```bash
#!/usr/bin/env bash
set -euo pipefail

# production guard — 本番環境では絶対に実行しない
if [[ "${APP_ENV:-}" == "production" ]]; then
  echo "ERROR: seed_test_data.sh は production 環境で実行禁止です。" >&2
  exit 1
fi

if docker ps --format '{{.Names}}' | grep -q '\-production'; then
  echo "ERROR: production コンテナが検出されました。staging コンテナに切り替えてください。" >&2
  exit 1
fi
```

**3. 削除が必要になった場合**

誤って本番に作成してしまった場合は、削除前に必ず claude.ai に報告し承認を得ること。
削除 SQL は以下の形式で実行し、ログを残す:

```bash
# 削除前に件数確認
docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d ultra_autotrade \
  -c "SELECT COUNT(*) FROM <table> WHERE <condition>;"

# 確認後に削除（transaction で囲む）
docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d ultra_autotrade \
  -c "BEGIN; DELETE FROM <table> WHERE <condition>; -- 件数確認後 COMMIT または ROLLBACK"
```

### 過去インシデント記録

#### 2026-04-28: `fund_allocations` 本番DBクリーンアップ

- **概要**: 本番DB `ultra_autotrade` の `fund_allocations` テーブルにダミーデータが混入していた
- **削除件数**: 282 行
- **影響**: 手数料計算・ポートフォリオ集計に誤ったデータが反映されていた可能性
- **根本原因**: staging/production の区別なくシードスクリプトが実行された
- **対応**: 手動 DELETE で全ダミーデータを削除、本ルールを制定

### チェックリスト（データ投入前に必ず確認）

- [ ] 接続先 DB 名が `ultra_autotrade_staging` であることを確認（`ultra_autotrade` は本番）
- [ ] `docker ps` でコンテナ名に `-production` が含まれていないことを確認
- [ ] スクリプトに production guard が記載されていることを確認
- [ ] データ投入後、staging で正常動作を確認してから本番デプロイを検討
