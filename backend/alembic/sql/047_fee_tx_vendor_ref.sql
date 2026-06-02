-- 047_fee_tx_vendor_ref.sql
-- Add vendor_reference_id and charged_at to fee_transactions (F-7 vendor-agnostic adapter)
-- Corresponds to alembic revision: l2m3n4o5p6q7

ALTER TABLE fee_transactions
    ADD COLUMN IF NOT EXISTS vendor_reference_id VARCHAR(128),
    ADD COLUMN IF NOT EXISTS charged_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_fee_tx_vendor_ref
    ON fee_transactions (vendor_reference_id)
    WHERE vendor_reference_id IS NOT NULL;
