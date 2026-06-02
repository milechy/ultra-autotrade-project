-- =============================================================================
-- 050_fee_allowances.sql
-- Fee Transfer & Allowance v1 DDL
-- 関連: Asana 1215272587496967 / 1215273755294098
-- 作成日: 2026-06-02
-- =============================================================================

BEGIN;

-- 1. fee_transactions に on-chain tx_hash 列を追加
ALTER TABLE fee_transactions
    ADD COLUMN IF NOT EXISTS on_chain_tx_hash VARCHAR(66) NULL;

COMMENT ON COLUMN fee_transactions.on_chain_tx_hash IS
    'on-chain fee transfer の tx hash (FEE_TRANSFER_ENABLED=true 後に格納)';

-- 2. fee_allowances テーブル (user→operator aToken permit 追跡)
CREATE TABLE IF NOT EXISTS fee_allowances (
    id               BIGSERIAL                    PRIMARY KEY,
    user_id          INTEGER                      NOT NULL
                     REFERENCES users(id) ON DELETE CASCADE,
    user_wallet_addr VARCHAR(42)                  NOT NULL,
    allowance_limit  NUMERIC(18, 6)               NOT NULL,
    permit_deadline  TIMESTAMPTZ                  NOT NULL,
    tx_hash_permit   VARCHAR(66)                  NULL,
    status           VARCHAR(16)                  NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending','submitted','confirmed','expired')),
    created_at       TIMESTAMPTZ                  NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ                  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fee_allowances_user
    ON fee_allowances (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_fee_allowances_status
    ON fee_allowances (status)
    WHERE status IN ('pending', 'submitted');

COMMENT ON TABLE fee_allowances IS
    'user→operator aToken upper-limit permit 追跡 (EIP-2612)';

COMMIT;
