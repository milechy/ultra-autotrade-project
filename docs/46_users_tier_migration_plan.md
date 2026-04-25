# users.tier マイグレーションプラン (F-2)

> 最終更新: 2026-04-25
> 関連: `docs/45_fee_model_v10_migration_plan.md` §2.2 / §4 F-2 行
> Asana: F-2 (1214120248237710)
> 実行タイミング: **F-16 本番リリース時** (本ドキュメントは設計のみ。F-2 では実行しない)

---

## 0. 前提

### 本番 DB 現状 (2026-04-25 read-only 調査)

| 項目 | 値 |
|------|-----|
| `users.tier` 値分布 | GENERAL × 6 (UPPER 0) |
| `users.tier` 列型 | `VARCHAR(20)`, `NOT NULL`, `DEFAULT 'GENERAL'` |
| 関連テーブル | `fund_allocations` (partner_id / tester_user_id / allocated_amount_usd / status) |

### 既存 6 ユーザー snapshot

| id | username | role | tier (現状) | active 割り振り USD |
|----|----------|------|-------------|---------------------|
| 1  | hkobayashi   | admin   | GENERAL | 0 |
| 7  | admin-hk     | admin   | GENERAL | 0 |
| 8  | partner-test | editor  | GENERAL | 0 |
| 11 | yamamoto     | partner | GENERAL | 0 |
| 13 | 小林テスト   | viewer  | GENERAL | 1100.00 |
| 14 | 小林テステス | viewer  | GENERAL | 0 |

### v10 要件 (F-2 enum)

| tier | 境界 (JPY) | 用途 |
|------|------------|------|
| LOWER  | 〜 1,000,000 | デフォルト (デポジット 100 万円以下) |
| MIDDLE | 1,000,001 〜 10,000,000 | デポジット 100 万 〜 1000 万円 |
| UPPER  | 10,000,001 〜 | デポジット 1000 万円〜 |

マイグレーション方針: 手動 `ALTER` + `UPDATE` (Alembic 自動マイグレーションは未使用。`docs/ops/02_db_tables.md` 準拠)。

---

## 1. 既存 6 ユーザーの再判定方針

### 1.1 デポジット額算出

ユーザーごとの算出ソース:
- `viewer` (テスター): `fund_allocations.allocated_amount_usd × USDJPY` の合計 (status='active')
- `admin` / `partner` / `editor`: 個人デポジット情報を v10 で別途設計 (現状 0 として扱う)

### 1.2 判定アルゴリズム

```python
deposit_jpy = sum(allocated_amount_usd for fa in active_allocations if fa.tester_user_id = u.id) * USDJPY

if deposit_jpy <= 1_000_000:
    tier = "LOWER"
elif deposit_jpy <= 10_000_000:
    tier = "MIDDLE"
else:
    tier = "UPPER"
```

### 1.3 USDJPY レート

- 切替時点 (F-16 実行直前) の Bybit ティッカー or 中央値レートをスナップショットして固定
- 本ドキュメント上の試算は **USDJPY=150** を仮置き (F-16 実行時に最新値で再計算する)
- F-16 実行後の `fee_transactions` 計算では同じレートを参照する設計 (F-5 で詳細実装)

### 1.4 試算結果 (USDJPY=150 固定、2026-04-25 snapshot)

| id | username | alloc USD | deposit JPY | 判定 tier |
|----|----------|-----------|-------------|-----------|
| 1  | hkobayashi   | 0       | 0       | LOWER |
| 7  | admin-hk     | 0       | 0       | LOWER |
| 8  | partner-test | 0       | 0       | LOWER |
| 11 | yamamoto     | 0       | 0       | LOWER |
| 13 | 小林テスト   | 1100.00 | 165,000 | LOWER |
| 14 | 小林テステス | 0       | 0       | LOWER |

**結論**: 6 ユーザー全員 LOWER に収束。MIDDLE/UPPER 該当者はゼロ。

---

## 2. マイグレーション SQL (F-16 本番適用予定、本タスクでは実行しない)

### 2.1 事前チェック

```bash
# tier 値分布の最終確認
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c "
SELECT tier, COUNT(*) FROM users GROUP BY tier ORDER BY tier;
"

# fund_allocations の active 件数確認
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c "
SELECT tester_user_id, SUM(allocated_amount_usd) AS usd
FROM fund_allocations
WHERE status='active'
GROUP BY tester_user_id;
"
```

### 2.2 バックアップ

```bash
docker exec ultra-autotrade-postgres-production pg_dump -U ultra -d ultra_autotrade \
  -t users -t fund_allocations \
  > /tmp/users_fund_alloc_backup_$(date +%Y%m%d).sql
```

### 2.3 マイグレーション本体

```sql
BEGIN;

-- 1. column DEFAULT 切替 (新規ユーザー作成時の初期値)
ALTER TABLE users ALTER COLUMN tier SET DEFAULT 'LOWER';

-- 2. 既存値変換 (デポジット額ベース、USDJPY は実行時に決定)
--    下記の :usdjpy パラメータは実行時に SET で渡す
\set usdjpy 150

WITH user_deposits AS (
  SELECT u.id,
         COALESCE(SUM(fa.allocated_amount_usd) * :usdjpy, 0) AS deposit_jpy
  FROM users u
  LEFT JOIN fund_allocations fa
    ON fa.tester_user_id = u.id AND fa.status = 'active'
  GROUP BY u.id
)
UPDATE users u
SET tier = CASE
  WHEN ud.deposit_jpy <= 1000000  THEN 'LOWER'
  WHEN ud.deposit_jpy <= 10000000 THEN 'MIDDLE'
  ELSE 'UPPER'
END
FROM user_deposits ud
WHERE u.id = ud.id
  AND u.tier = 'GENERAL';  -- v10 値 (LOWER/MIDDLE/UPPER) は再判定対象外

-- 3. 検証
SELECT tier, COUNT(*) FROM users GROUP BY tier ORDER BY tier;
-- 期待: LOWER:6 (現状 snapshot 通り)

COMMIT;
```

### 2.4 適用後の追加検証

```bash
# Pydantic で読めることを確認 (バックエンド再起動後)
curl -sf https://api.ultra-auto-trade.com/health | python3 -m json.tool

# 各ユーザーの tier 表示
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c "
SELECT id, username, role, tier FROM users ORDER BY id;
"
```

---

## 3. ロールバック手順

### 3.1 SQL レベル (F-16 当日のみ実行可)

```sql
BEGIN;

-- バックアップ復元 (\copy or pg_restore)
TRUNCATE users CASCADE;
\copy users FROM '/tmp/users_backup_<date>.csv' CSV HEADER

-- column DEFAULT を v9 値に戻す
ALTER TABLE users ALTER COLUMN tier SET DEFAULT 'GENERAL';

COMMIT;
```

### 3.2 アプリケーションレベル

- F-2 PR を revert (gh pr revert) → main 再デプロイ
- enum に GENERAL がそのまま残っているため、過渡期互換は維持

---

## 4. 実行タイミング (F-16)

1. F-15 山本さんレビュー完了
2. **山本さんへの事前周知 (24h 前 DM)**:
    - 「次回バックエンド更新時に手数料モデルが v10 に切り替わり、ティアが LOWER (一般) として表示されます」
    - 「金額・操作には影響なし」
3. F-16 本番リリース時に本 SQL 実行
4. backend 再起動
5. 各ユーザーのダッシュボードで tier 表示が「一般」(LOWER) になっていることを確認

---

## 5. ロールアウト後監視

| チェック項目 | 方法 | 頻度 |
|--------------|------|------|
| tier 値分布 | `SELECT tier, COUNT(*) FROM users GROUP BY tier;` | 直後 + 24h 後 |
| API `/users/{id}/tier` | curl 6 回 (全ユーザー) | 直後 |
| 山本さん配下異常報告 | Slack `#ultra-auto-project` | 24h 監視 |
| Pydantic バリデーションエラー | `docker logs ... \| grep -i 'validationerror\|invalidvalue'` | 直後 + 6h |

---

## 6. 設計判断 (F-2 で確定したこと)

| 項目 | 採用案 | 理由 |
|------|--------|------|
| enum 拡張方針 | **Option A**: GENERAL を deprecated として残し、LOWER/MIDDLE/UPPER 追加 | 本番 6 ユーザーが現在 GENERAL を保持しており、Pydantic バリデーション失敗を防ぐため |
| tier 単位 | JPY (`determine_tier_jpy`) | v10 spec が JPY 境界を採用 |
| 旧 USD パス (`determine_tier`) | 戻り値を GENERAL → LOWER に変更 | v10 vocabulary 統一 |
| 日本語ラベル | `TIER_JP_LABELS` 辞書を auth/models.py に集約 | 単一情報源、フロントは API 経由で取得 |
| `users.tier` DEFAULT | F-2 でコード側 `'LOWER'`、DB 側は F-16 で `ALTER DEFAULT` | コード側は単独デプロイで OK、DB DEFAULT 切替は本番 SQL 必須 |

---

## 7. F-3 / F-13 / F-16 への引き継ぎ

| タスク | 引き継ぎ事項 |
|--------|--------------|
| F-3 (RiskMode enum) | 本ドキュメントの設計を踏襲 (deprecated 残置 → F-13 削除) |
| F-13 (v9 物理削除) | `InvestmentTier.GENERAL` 削除 + `TIER_JP_LABELS` から GENERAL エントリ削除 + `dynamic_fee.py` / `fee_service.py` の GENERAL 互換マップ削除 |
| F-16 (本番リリース) | 本ドキュメント §2 SQL を実行 |
