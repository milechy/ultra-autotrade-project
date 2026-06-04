-- =============================================================================
-- 045_fee_v10_tables.sql
-- Fee Model v10 (Option A: 既存billing完全置換) DDL
-- 関連: docs/45_fee_model_v10_migration_plan.md / Asana F-1 (1214120248239215)
-- 作成日: 2026-04-25
--
-- 適用先:
--   - staging-new: F-1 で実行 (試験)
--   - production:  F-16 で実行 (本番リリース時)
--
-- 前提条件:
--   - fee_configs / fee_calculations / high_water_marks が **0 行** であること
--   - 本番 DB は F-0 (PR #121) で 0 行確認済み (2026-04-25 時点)
--   - staging-new は F-1 着手時に 0 行確認 (このコメント参照タイミングで再確認すること)
--
-- 等価な Alembic migration: backend/alembic/versions/d4e5f6a7b8c9_fee_v10_tables.py
-- どちらか一方のみ適用すること (両方流すと 2 回目で失敗する)
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 1. 既存 v9 billing 3 テーブルの DROP (Option A)
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS fee_calculations CASCADE;
DROP TABLE IF EXISTS high_water_marks CASCADE;
DROP TABLE IF EXISTS fee_configs CASCADE;

-- -----------------------------------------------------------------------------
-- 2. fee_configs (v10) CREATE
-- -----------------------------------------------------------------------------
CREATE TABLE fee_configs (
  id BIGSERIAL PRIMARY KEY,
  config_name VARCHAR(64) NOT NULL UNIQUE,
  tier_thresholds_jpy JSONB NOT NULL,
  tier_fee_rates JSONB NOT NULL,
  tier_monthly_yield_caps JSONB NOT NULL,
  subscription_rates JSONB NOT NULL,
  expense_markup_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  expense_markup_rate NUMERIC(6, 4) NOT NULL DEFAULT 0,
  affiliate_rate NUMERIC(6, 4) NOT NULL DEFAULT 0.30,
  is_active BOOLEAN NOT NULL DEFAULT FALSE,
  effective_from TIMESTAMP WITH TIME ZONE NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_fee_configs_active_effective
  ON fee_configs (is_active, effective_from DESC);

COMMENT ON TABLE fee_configs IS
  'Fee model v10 設定 (リスクモード・tier・サブスク率等)';
COMMENT ON COLUMN fee_configs.tier_thresholds_jpy IS
  '一般/ミドル/アッパー境界 JPY 配列 (例: [1000000, 10000000])';
COMMENT ON COLUMN fee_configs.tier_fee_rates IS
  'tier 別手数料率配列 (例: [0.30, 0.25, 0.20])';
COMMENT ON COLUMN fee_configs.tier_monthly_yield_caps IS
  'tier 別月次利回り上限 (例: [0.018, 0.023, 0.030])';
COMMENT ON COLUMN fee_configs.subscription_rates IS
  'リスクモード別月額サブスク率 (例: {"low":0,"middle":0.003,"high":0.010})';

-- -----------------------------------------------------------------------------
-- 3. fee_transactions (v10) CREATE
--   FK: users.id は INTEGER (auth/models.py:57 確認済み)
-- -----------------------------------------------------------------------------
CREATE TABLE fee_transactions (
  id BIGSERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  calculation_month DATE NOT NULL,
  tier VARCHAR(16) NOT NULL,
  risk_mode VARCHAR(16) NOT NULL,
  deposit_amount_jpy NUMERIC(18, 2) NOT NULL,
  gross_profit_jpy NUMERIC(18, 2) NOT NULL DEFAULT 0,
  expense_jpy NUMERIC(18, 2) NOT NULL DEFAULT 0,
  net_profit_jpy NUMERIC(18, 2) NOT NULL DEFAULT 0,
  fee_rate_applied NUMERIC(6, 4) NOT NULL DEFAULT 0,
  fee_amount_jpy NUMERIC(18, 2) NOT NULL DEFAULT 0,
  subscription_rate_applied NUMERIC(6, 4) NOT NULL DEFAULT 0,
  subscription_amount_jpy NUMERIC(18, 2) NOT NULL DEFAULT 0,
  subscription_protected BOOLEAN NOT NULL DEFAULT FALSE,
  monthly_yield_cap_applied NUMERIC(6, 4) NOT NULL DEFAULT 0,
  yield_excess_to_uata_jpy NUMERIC(18, 2) NOT NULL DEFAULT 0,
  user_takehome_jpy NUMERIC(18, 2) NOT NULL DEFAULT 0,
  affiliate_id INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
  affiliate_amount_jpy NUMERIC(18, 2) NOT NULL DEFAULT 0,
  calculated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  finalized_at TIMESTAMP WITH TIME ZONE NULL,

  CONSTRAINT chk_fee_tx_tier CHECK (tier IN ('LOWER', 'MIDDLE', 'UPPER')),
  CONSTRAINT chk_fee_tx_risk_mode CHECK (risk_mode IN ('conservative', 'balanced', 'aggressive')),
  CONSTRAINT uq_fee_tx_user_month UNIQUE (user_id, calculation_month)
);

CREATE INDEX idx_fee_tx_user_month
  ON fee_transactions (user_id, calculation_month DESC);
CREATE INDEX idx_fee_tx_finalized
  ON fee_transactions (finalized_at)
  WHERE finalized_at IS NULL;
CREATE INDEX idx_fee_tx_affiliate
  ON fee_transactions (affiliate_id)
  WHERE affiliate_id IS NOT NULL;

COMMENT ON TABLE fee_transactions IS
  'Fee model v10 月次手数料計算結果 (1 ユーザー × 1 月で 1 行)';
COMMENT ON COLUMN fee_transactions.tier IS
  'v10 投資ティア (LOWER / MIDDLE / UPPER)';
COMMENT ON COLUMN fee_transactions.risk_mode IS
  'v10 リスクモード (conservative / balanced / aggressive) — F-3 RiskMode enum 内部値';
COMMENT ON COLUMN fee_transactions.subscription_protected IS
  'サブスク控除によりユーザー手取りが負にならないよう保護されたか';

COMMIT;

-- =============================================================================
-- 検証クエリ (適用後の確認用)
-- =============================================================================
-- SELECT table_name FROM information_schema.tables
--   WHERE table_schema='public'
--     AND table_name IN ('fee_configs','fee_transactions','fee_calculations','high_water_marks')
--   ORDER BY table_name;
-- 期待: fee_configs, fee_transactions のみ
--
-- \d fee_configs
-- \d fee_transactions
--
-- =============================================================================
-- ロールバック手順 (緊急時のみ)
-- =============================================================================
-- BEGIN;
-- DROP TABLE IF EXISTS fee_transactions CASCADE;
-- DROP TABLE IF EXISTS fee_configs CASCADE;
-- -- v9 billing テーブルの再構築は backend/app/billing/models.py から
-- -- alembic stamp <prev_revision> + alembic upgrade head で復元可能
-- COMMIT;
