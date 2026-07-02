# FeeConfig v10_default 本番投入 Runbook (F-4)

> 最終更新: 2026-06-01
> 関連: `docs/45_fee_model_v10_migration_plan.md` §3 / §4 F-4 行
> Asana: F-4 (1214120401381545)
> 実行タイミング: staging dry-run は随時可 / **F-16 本番リリース時**に本番実行
> セット: F-1 (045 DDL) → F-4 (046 CHECK + seed) → F-16 (本番適用)
> PR #483: `045_fee_v10_tables.sql` の CHECK 制約を `conservative/balanced/aggressive` に修正済み

---

## 0. 前提

### 本番 (F-16 実行時)

- F-1 マイグレーション (`045_fee_v10_tables.sql`) **本番適用済み**
- F-4 マイグレーション (`046_fee_v10_check_constraint_alignment.sql`) **本番適用済み**
- F-15 山本さんレビュー完了
- 山本さんへの事前周知完了 (24h 前 DM)

### staging-new 状態 (2026-04-25 確認済み)

| 項目 | 結果 |
|------|------|
| 046 SQL 適用 | ✅ `chk_fee_tx_risk_mode` を ('conservative','balanced','aggressive') に更新 |
| seed 相当 INSERT 投入 | ✅ `fee_configs` に v10_default レコード 1 行 |
| CHECK 動作確認 (positive) | ✅ `risk_mode='conservative'` で INSERT 成功 |
| CHECK 動作確認 (negative) | ✅ `risk_mode='LOW'` で chk_fee_tx_risk_mode 違反 |

### PR #483 と seed 値の整合

| 確認箇所 | 期待値 | 整合 |
|----------|--------|------|
| `045_fee_v10_tables.sql` CHECK (PR #483 修正後) | `('conservative','balanced','aggressive')` | ✅ |
| `046_fee_v10_check_constraint_alignment.sql` CHECK | `('conservative','balanced','aggressive')` | ✅ |
| `fees/models.py` `chk_fee_tx_risk_mode` CHECK | `('conservative','balanced','aggressive')` | ✅ |
| `seed_fee_config_v10.py` `subscription_rates` キー | `conservative / balanced / aggressive` | ✅ |
| `auth/models.py` `RiskMode` 内部値 | `conservative / balanced / aggressive` | ✅ |

> **注**: staging-new は 045 (旧 CHECK = `LOW/MIDDLE/HIGH`) 適用済みのため、046 を先に適用してから seed を実行する。
> 本番は PR #483 merge 後の 045 を初回適用するため、046 不要。

---

## S. Staging dry-run 手順 (本番 F-16 前の事前確認)

> **実行場所**: 本番 VPS (5.223.88.14) — dev VPS から SSH 不可。人間が実行してください。
> **コンテナ名**: `ultra-autotrade-backend-blue-staging-new` / `ultra-autotrade-postgres-staging-new`
> **目的**: seed 値の整合を人間の目で確認してから本番投入の go/no-go を判断する。

### S-1. 現状確認 (read-only, 5 分)

```bash
# S1-A. fee_configs の現状 (既に seed 済みの場合は v10_default が 1 行あるはず)
docker exec ultra-autotrade-postgres-staging-new psql -U ultra -d ultra_autotrade -c "
SELECT id, config_name, is_active, subscription_rates, effective_from
FROM fee_configs;
"

# S1-B. CHECK 制約が 046 適用済みであることを確認
docker exec ultra-autotrade-postgres-staging-new psql -U ultra -d ultra_autotrade -c "
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conname = 'chk_fee_tx_risk_mode';
"
# 期待: CHECK (risk_mode = ANY (ARRAY['conservative'::text, 'balanced'::text, 'aggressive'::text]))

# S1-C. backend health check
curl -sf http://127.0.0.1:8082/health | python3 -m json.tool
# 期待: status=ok
```

### S-2. 046 migration 適用 (staging-new で 045 旧 CHECK を上書き)

> staging-new は 045 (旧 CHECK = `LOW/MIDDLE/HIGH`) 適用済みのため 046 が必要。
> S1-B で CHECK が既に `conservative/balanced/aggressive` なら **この手順はスキップ**。

```bash
# 046 SQL を直接適用
docker exec -i ultra-autotrade-postgres-staging-new psql -U ultra -d ultra_autotrade \
  < /opt/ultra-autotrade/backend/alembic/sql/046_fee_v10_check_constraint_alignment.sql
# 期待: "ALTER TABLE" が出力される

# 適用後確認
docker exec ultra-autotrade-postgres-staging-new psql -U ultra -d ultra_autotrade -c "
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conname = 'chk_fee_tx_risk_mode';
"
# 期待: CHECK (...'conservative'...'balanced'...'aggressive'...)
```

### S-3. Dry-run 実行 (DB 書き込みなし)

```bash
# 投入予定データを確認する (実 INSERT なし)
docker exec -w /app/backend ultra-autotrade-backend-blue-staging-new \
  python scripts/seed_fee_config_v10.py --dry-run
```

**dry-run 出力期待値** (全フィールドを目視確認):

```
[DRY-RUN] Would insert: {
  'config_name': 'v10_default',
  'tier_thresholds_jpy': [1000000, 10000000],
  'tier_fee_rates': [0.3, 0.25, 0.2],
  'tier_monthly_yield_caps': [0.018, 0.023, 0.03],
  'subscription_rates': {'conservative': 0.0, 'balanced': 0.003, 'aggressive': 0.01},
  'expense_markup_enabled': False,
  'expense_markup_rate': Decimal('0'),
  'affiliate_rate': Decimal('0.10'),
  'is_active': True,
  'effective_from': datetime(2026, 5, 1, 0, 0, tzinfo=...)
}
```

**チェックポイント**:
- [ ] `subscription_rates` のキーが `conservative / balanced / aggressive` (大文字 `LOW/MIDDLE/HIGH` でないこと)
- [ ] `subscription_rates` の値が `0.0 / 0.003 / 0.01`
- [ ] `tier_fee_rates` が `[0.3, 0.25, 0.2]`
- [ ] `effective_from` が過去日時 (投入直後から有効)
- [ ] `is_active` が `True`

### S-4. Staging 実投入 (dry-run 確認後)

> **実行判断**: S-3 dry-run の全チェックポイント ✅ を確認してから実行する。
> staging に既に `v10_default` が存在する場合は `[SKIP]` が出力される (冪等)。

```bash
# 実投入
docker exec -w /app/backend ultra-autotrade-backend-blue-staging-new \
  python scripts/seed_fee_config_v10.py
# 期待: [OK] Inserted v10_default (id=N) または [SKIP] v10_default (...) already exists

# 冪等性確認 (再実行 → skip)
docker exec -w /app/backend ultra-autotrade-backend-blue-staging-new \
  python scripts/seed_fee_config_v10.py
# 期待: [SKIP] v10_default (id=N, active) already exists
```

### S-5. Staging 検証

```bash
# DB レコード確認
docker exec ultra-autotrade-postgres-staging-new psql -U ultra -d ultra_autotrade -c "
SELECT id, config_name, is_active, subscription_rates,
       tier_thresholds_jpy, tier_fee_rates, tier_monthly_yield_caps,
       affiliate_rate, effective_from
FROM fee_configs
WHERE config_name = 'v10_default';
"
```

**期待値**:
| カラム | 期待値 |
|--------|--------|
| config_name | `v10_default` |
| is_active | `t` |
| subscription_rates | `{"conservative": 0, "balanced": 0.003, "aggressive": 0.01}` |
| tier_thresholds_jpy | `[1000000, 10000000]` |
| tier_fee_rates | `[0.30, 0.25, 0.20]` |
| tier_monthly_yield_caps | `[0.018, 0.023, 0.030]` |
| affiliate_rate | `0.1000` |
| effective_from | `2026-04-30 15:00:00+00` |

```bash
# CHECK 制約動作確認 — conservative (positive)
docker exec ultra-autotrade-postgres-staging-new psql -U ultra -d ultra_autotrade -c "
BEGIN;
INSERT INTO fee_transactions (user_id, calculation_month, tier, risk_mode, deposit_amount_jpy)
VALUES (1, '2026-05-01', 'LOWER', 'conservative', 0);
ROLLBACK;
"
# 期待: INSERT 0 1 → ROLLBACK (成功)

# CHECK 制約動作確認 — LOW (negative, 旧値が拒否されること)
docker exec ultra-autotrade-postgres-staging-new psql -U ultra -d ultra_autotrade -c "
BEGIN;
INSERT INTO fee_transactions (user_id, calculation_month, tier, risk_mode, deposit_amount_jpy)
VALUES (1, '2026-05-01', 'LOWER', 'LOW', 0);
ROLLBACK;
"
# 期待: ERROR chk_fee_tx_risk_mode → ROLLBACK (正常拒否)
```

### S-6. Staging ロールバック (問題発覚時)

```bash
docker exec ultra-autotrade-postgres-staging-new psql -U ultra -d ultra_autotrade -c "
BEGIN;
DELETE FROM fee_configs WHERE config_name = 'v10_default';
COMMIT;
"
```

---

## 1. 事前バックアップ

```bash
# fee_configs / fee_transactions の現状を保存
docker exec ultra-autotrade-postgres-production pg_dump \
  -U ultra -d ultra_autotrade \
  -t fee_configs -t fee_transactions \
  > /tmp/fee_v10_backup_$(date +%Y%m%d).sql
```

---

## 2. 投入実行 (3 段プロンプト方式、claude.ai 事前承認必須)

### Phase A: 事前確認 (read-only, 5 分)

```bash
# A1. fee_configs の現状 (空であること)
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c "
SELECT COUNT(*) FROM fee_configs;
SELECT COUNT(*) FROM fee_configs WHERE config_name='v10_default';
"
# 期待: count=0 / 0 (F-16 でも未投入)

# A2. CHECK 制約が 046 適用済みであることを確認
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c "
\d fee_transactions
" | grep chk_fee_tx_risk_mode
# 期待: CHECK (risk_mode IN ('conservative','balanced','aggressive'))

# A3. backend health check
curl -sf https://api.ultra-auto-trade.com/health | python3 -m json.tool
# 期待: status=ok, scheduler=true

# A4. F-3 の RISK_MODE_SUBSCRIPTION_RATES が本番コードに反映済みか
docker exec ultra-autotrade-backend-production grep -A3 "RISK_MODE_SUBSCRIPTION_RATES" \
  /app/backend/app/auth/models.py
# 期待: CONSERVATIVE: Decimal("0"), BALANCED: Decimal("0.003"), AGGRESSIVE: Decimal("0.010")
```

### Phase B: プラン提示 → claude.ai 承認

| 項目 | 値 |
|------|-----|
| 実行コマンド | `python /app/backend/scripts/seed_fee_config_v10.py` |
| 期待される変更 | `fee_configs` に 1 行 INSERT (`config_name=v10_default`, `is_active=true`) |
| 想定実行時間 | < 5 秒 |
| ロールバック条件 | INSERT 後の検証クエリで subscription_rates が想定値と異なる場合 |
| 想定停止時間 | ゼロ (バックエンドは無停止) |

### Phase C: 実行 (5 分)

```bash
# C1. dry-run でデータ確認
docker exec -w /app/backend ultra-autotrade-backend-production \
  python scripts/seed_fee_config_v10.py --dry-run
# 期待: [DRY-RUN] Would insert: {...} (実 INSERT なし)

# C2. 実投入
docker exec -w /app/backend ultra-autotrade-backend-production \
  python scripts/seed_fee_config_v10.py
# 期待: [OK] Inserted v10_default (id=1)

# C3. 冪等性確認 (もう一度実行 → skip)
docker exec -w /app/backend ultra-autotrade-backend-production \
  python scripts/seed_fee_config_v10.py
# 期待: [SKIP] v10_default (id=1, active) already exists
```

---

## 3. 検証

```sql
-- レコード確認
SELECT
  id,
  config_name,
  is_active,
  subscription_rates,
  tier_thresholds_jpy,
  tier_fee_rates,
  tier_monthly_yield_caps,
  affiliate_rate,
  effective_from
FROM fee_configs;
```

**期待値**:
| カラム | 期待値 |
|--------|--------|
| id | 1 |
| config_name | `v10_default` |
| is_active | `t` (true) |
| subscription_rates | `{"conservative": 0.0, "balanced": 0.003, "aggressive": 0.01}` |
| tier_thresholds_jpy | `[1000000, 10000000]` |
| tier_fee_rates | `[0.30, 0.25, 0.20]` |
| tier_monthly_yield_caps | `[0.018, 0.023, 0.030]` |
| affiliate_rate | `0.10` |
| effective_from | `2026-04-30 15:00:00+00` (= 2026-05-01 00:00 JST) |

```bash
# CHECK 制約動作確認 (positive)
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c "
BEGIN;
INSERT INTO fee_transactions (user_id, calculation_month, tier, risk_mode, deposit_amount_jpy)
VALUES (1, '2026-05-01', 'LOWER', 'conservative', 0);
ROLLBACK;
"
# 期待: INSERT 0 1 → ROLLBACK (成功)
```

---

## 4. 値変更時の更新手順 (将来運用)

`subscription_rates` 等の値を変更する場合:

1. `backend/app/auth/models.py` の `RISK_MODE_SUBSCRIPTION_RATES` 等を更新 (PR レビュー必須)
2. `backend/scripts/seed_fee_config_v10.py` の `V10_DEFAULT_CONFIG_NAME` を新名 (`v10_default_v2` 等) に変更 (PR レビュー必須)
3. デプロイ後、新 seed 実行で新 config を INSERT
4. 動作確認
5. 旧 config を `is_active=false` に手動 UPDATE
6. 新 config を `is_active=true` に手動 UPDATE
7. `idx_fee_configs_active_effective` index により AI スケジューラーは即座に新 config を参照する

```sql
-- 切替例
UPDATE fee_configs SET is_active = false WHERE config_name = 'v10_default';
UPDATE fee_configs SET is_active = true WHERE config_name = 'v10_default_v2';
```

---

## 5. ロールバック手順

### Phase C 直後に問題発覚した場合

```sql
BEGIN;
DELETE FROM fee_configs WHERE config_name = 'v10_default';
COMMIT;
```

### バックアップから完全復元 (24h 以内)

```bash
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade <<EOF
TRUNCATE fee_configs CASCADE;
\i /tmp/fee_v10_backup_YYYYMMDD.sql
EOF
```

---

## 6. ロールアウト後監視

| チェック項目 | 方法 | 頻度 |
|--------------|------|------|
| `fee_configs` レコード数 | `SELECT COUNT(*) FROM fee_configs;` | 直後 |
| AI スケジューラーが v10_default を参照 | `docker logs --tail=100 ultra-autotrade-backend-production \| grep -i 'fee_config\|v10_default'` | 1h 後 |
| CHECK 違反エラー | `docker logs ... \| grep 'chk_fee_tx_'` | 24h 監視 |
| 山本さん配下異常報告 | Slack `#ultra-auto-project` | 24h 監視 |

---

## 7. 設計判断 (F-4 で確定したこと)

| 項目 | 採用案 | 理由 |
|------|--------|------|
| risk_mode CHECK 制約 | F-3 内部値に揃える (`'conservative','balanced','aggressive'`) | Aave MDD / Optimizer / Risk Profile が小文字内部値を直参照中。fee_calculator (F-5) で大文字変換層を入れずに済む |
| tier CHECK 制約 | F-2 値のまま (`'LOWER','MIDDLE','UPPER'`) | F-2 InvestmentTier と既に整合済み (大文字 3 値)。fee_transactions は新規テーブルのため GENERAL 混入リスクなし |
| seed の冪等性 | `config_name` 一致なら **状態問わず skip** | UNIQUE 制約により重複作成不可。値変更は §4 の新名スイッチ手順で対応 |
| `subscription_rates` JSON キー | F-3 内部値 (lowercase) で固定 | F-5/F-6/F-7 で同じキーを参照する前提 |
| seed script の値ソース | F-3 `RISK_MODE_SUBSCRIPTION_RATES` を **直参照** | spec 値変更時に auth/models.py 1 箇所修正で seed 出力も自動追従 |
| v10_models.py の SQLite 互換 | `JSONB().with_variant(JSON(), "sqlite")` + `BigInteger().with_variant(Integer(), "sqlite")` | 本番は PG (JSONB/BIGINT 維持)、テストは SQLite で動作 |

---

## 8. 引き継ぎ

| タスク | 引き継ぎ事項 |
|--------|--------------|
| F-5 (fee_calculator) | `subscription_rates` JSONB を読むときは F-3 内部値キー (`conservative` 等) を使う |
| F-13 (v9 物理削除) | `seed_fee_config_v10.py` はそのまま残置 (fee_configs 自体は v10 で生き続ける) |
| F-16 (本番リリース) | 本ドキュメント §S で dry-run 確認 → §1〜3 の手順で本番実行 |
| PR #483 | 045 の CHECK を `conservative/balanced/aggressive` に修正。staging-new は 046 で上書き済み。本番は 045 初回適用時から正しい CHECK が入る |
