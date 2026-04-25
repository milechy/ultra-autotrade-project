# FeeConfig v10_default 本番投入 Runbook (F-4)

> 最終更新: 2026-04-25
> 関連: `docs/45_fee_model_v10_migration_plan.md` §3 / §4 F-4 行
> Asana: F-4 (1214120401381545)
> 実行タイミング: **F-16 本番リリース時** (本ドキュメントは設計のみ。F-4 では実行しない)
> セット: F-1 (045 DDL) → F-4 (046 CHECK + seed) → F-16 (本番適用)

---

## 0. 前提

- F-1 マイグレーション (`045_fee_v10_tables.sql`) **本番適用済み**
- F-4 マイグレーション (`046_fee_v10_check_constraint_alignment.sql`) **本番適用済み**
- F-15 山本さんレビュー完了
- 山本さんへの事前周知完了 (24h 前 DM)

### staging-new 試験結果 (2026-04-25)

| 項目 | 結果 |
|------|------|
| 046 SQL 適用 | ✅ `chk_fee_tx_risk_mode` を ('conservative','balanced','aggressive') に更新 |
| seed 相当 INSERT 投入 | ✅ `fee_configs` に v10_default レコード 1 行 |
| CHECK 動作確認 (positive) | ✅ `risk_mode='conservative'` で INSERT 成功 |
| CHECK 動作確認 (negative) | ✅ `risk_mode='LOW'` で chk_fee_tx_risk_mode 違反 |

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
| affiliate_rate | `0.30` |
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
| F-16 (本番リリース) | 本ドキュメント §1〜3 の手順を実行 |
