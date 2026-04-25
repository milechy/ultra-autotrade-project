-- =============================================================================
-- 046_fee_v10_check_constraint_alignment.sql
-- fee_transactions.risk_mode CHECK 制約を F-3 RiskMode 内部値に揃える
-- 関連: docs/45 §1.3, docs/47, Asana F-4 (1214120401381545)
-- 作成日: 2026-04-25
--
-- 背景:
--   - F-1 (045) 時点では risk_mode CHECK = ('LOW','MIDDLE','HIGH')
--   - F-3 で RiskMode enum を導入: ('conservative','balanced','aggressive')
--   - Aave MDD / Optimizer / Risk Profile が小文字内部値を直参照
--   - F-5 fee_calculator が CHECK 違反を起こさないよう、本マイグレーションで揃える
--
-- なお tier CHECK = ('LOWER','MIDDLE','UPPER') は F-2 InvestmentTier と既に整合済み
-- (大文字、3 値)。fee_transactions は新規テーブル = GENERAL レコード混入の心配なし。
--
-- 適用先:
--   - staging-new: F-4 で実行 (試験)
--   - production:  F-16 で実行 (本番リリース時、045 適用後)
--
-- 等価な Alembic migration: backend/alembic/versions/e5f6a7b8c9d0_check_constraint_alignment.py
-- どちらか一方のみ適用すること。
-- =============================================================================

BEGIN;

-- 旧 CHECK ('LOW','MIDDLE','HIGH') を削除
ALTER TABLE fee_transactions
  DROP CONSTRAINT IF EXISTS chk_fee_tx_risk_mode;

-- 新 CHECK: F-3 RiskMode 内部値に揃える
ALTER TABLE fee_transactions
  ADD CONSTRAINT chk_fee_tx_risk_mode
  CHECK (risk_mode IN ('conservative', 'balanced', 'aggressive'));

COMMENT ON COLUMN fee_transactions.risk_mode IS
  'v10 リスクモード (conservative / balanced / aggressive) — F-3 RiskMode enum 内部値';

COMMIT;

-- =============================================================================
-- 検証クエリ (適用後の確認用)
-- =============================================================================
-- \d fee_transactions
-- 期待: chk_fee_tx_risk_mode CHECK (risk_mode::text = ANY (ARRAY['conservative'::char...
--
-- 動作確認 (rollback で残さない):
-- BEGIN;
--   INSERT INTO fee_transactions (
--     user_id, calculation_month, tier, risk_mode, deposit_amount_jpy
--   ) VALUES (1, '2026-05-01', 'LOWER', 'conservative', 0);
--   -- 成功すること
-- ROLLBACK;
-- BEGIN;
--   INSERT INTO fee_transactions (
--     user_id, calculation_month, tier, risk_mode, deposit_amount_jpy
--   ) VALUES (1, '2026-05-01', 'LOWER', 'LOW', 0);
--   -- chk_fee_tx_risk_mode 違反で失敗すること
-- ROLLBACK;
--
-- =============================================================================
-- ロールバック手順 (緊急時のみ)
-- =============================================================================
-- BEGIN;
-- ALTER TABLE fee_transactions DROP CONSTRAINT IF EXISTS chk_fee_tx_risk_mode;
-- ALTER TABLE fee_transactions
--   ADD CONSTRAINT chk_fee_tx_risk_mode
--   CHECK (risk_mode IN ('LOW', 'MIDDLE', 'HIGH'));
-- COMMIT;
