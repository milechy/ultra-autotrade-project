#!/bin/bash
# scripts/seed_test_data.sh
#
# Staging DB (ultra_autotrade_staging) にテストデータを投入する。
#
# Usage:
#   DATABASE_URL=postgresql://ultra:pass@localhost:5433/ultra_autotrade_staging ./scripts/seed_test_data.sh
#   または
#   ./scripts/seed_test_data.sh postgresql://ultra:pass@localhost:5433/ultra_autotrade_staging
#
# ROLLBACK: 投入したデータを削除する場合
#   psql "$DATABASE_URL" -c "DELETE FROM fund_allocations WHERE notes LIKE '%seed_test_data.sh%';"
#   psql "$DATABASE_URL" -c "DELETE FROM proposals WHERE reason LIKE '%[seed_test_data.sh]%';"
#   psql "$DATABASE_URL" -c "DELETE FROM ai_decisions WHERE query LIKE '%[seed_test_data.sh]%';"

set -euo pipefail

# ────────────────────────────────────────────────
# 1. 接続先 DB の取得
# ────────────────────────────────────────────────
DB_URL="${1:-${DATABASE_URL:-}}"

if [[ -z "$DB_URL" ]]; then
  echo "❌ ERROR: DATABASE_URL が未設定です。"
  echo "Usage: DATABASE_URL=<url> $0  または  $0 <url>"
  exit 1
fi

# URL から DB 名を抽出 (例: .../ultra_autotrade_staging → ultra_autotrade_staging)
DB_NAME="$(echo "$DB_URL" | sed -E 's|.*/([^/?]+)(\?.*)?$|\1|')"

# ────────────────────────────────────────────────
# 2. 本番 DB ガード
# ────────────────────────────────────────────────
if [[ "$DB_NAME" != "ultra_autotrade_staging" ]]; then
  echo "❌ ERROR: This script is for staging only."
  echo "   Expected DB: ultra_autotrade_staging"
  echo "   Got DB:      $DB_NAME"
  exit 1
fi

# ────────────────────────────────────────────────
# 3. Confirmation prompt
# ────────────────────────────────────────────────
echo ""
echo "⚠️  Seed target: $DB_NAME  ($DB_URL)"
echo ""
read -r -p "Proceeding with seed on $DB_NAME. Type 'yes' to continue: " CONFIRM
if [[ "$CONFIRM" != "yes" ]]; then
  echo "Aborted."
  exit 0
fi

# psql ラッパー (BEGIN/COMMIT ブロックを stdin で受け取る)
psql_exec() {
  psql "$DB_URL" -v ON_ERROR_STOP=1 -q
}

# ────────────────────────────────────────────────
# 4. 投入前: 既存データ件数確認
# ────────────────────────────────────────────────
echo ""
echo "📊 既存データ件数:"
psql "$DB_URL" -t -A -c "
SELECT
  'ai_decisions'    AS table_name, COUNT(*) AS rows FROM ai_decisions
UNION ALL
SELECT
  'proposals',                     COUNT(*)          FROM proposals
UNION ALL
SELECT
  'fund_allocations',              COUNT(*)          FROM fund_allocations;
"

# ────────────────────────────────────────────────
# 5. シードデータ投入
# ────────────────────────────────────────────────
echo ""
echo "🌱 テストデータ投入中..."

psql_exec <<'SQL'
BEGIN;

-- ----------------------------------------------------------------
-- ai_decisions: 10 行 (BUY×4, SELL×3, HOLD×3)
-- ----------------------------------------------------------------
INSERT INTO ai_decisions
  (user_id, query, action, confidence, reason,
   primary_provider, primary_action, primary_confidence,
   secondary_provider, secondary_action, secondary_confidence,
   agreed, created_at)
VALUES
  (1, '[seed_test_data.sh] ETH/USD 4h chart analysis #1',  'BUY',  82, 'RSI oversold, volume spike',          'claude',   'BUY',  82, 'gpt-4o', 'BUY',  79, true,  NOW() - INTERVAL '9 hours'),
  (1, '[seed_test_data.sh] BTC/USD daily momentum #2',     'BUY',  75, 'Golden cross confirmed',               'claude',   'BUY',  75, 'gpt-4o', 'HOLD', 55, false, NOW() - INTERVAL '8 hours'),
  (1, '[seed_test_data.sh] ETH/USD 1h scalp signal #3',    'HOLD', 60, 'Mixed signals, await confirmation',   'claude',   'HOLD', 60, 'gpt-4o', 'HOLD', 65, true,  NOW() - INTERVAL '7 hours'),
  (1, '[seed_test_data.sh] BTC/USD 4h resistance test #4', 'SELL', 78, 'Rejected at key resistance',          'claude',   'SELL', 78, 'gpt-4o', 'SELL', 80, true,  NOW() - INTERVAL '6 hours'),
  (1, '[seed_test_data.sh] ETH/USD funding rate check #5', 'SELL', 70, 'Funding rate extremely positive',     'claude',   'SELL', 70, 'gpt-4o', 'HOLD', 50, false, NOW() - INTERVAL '5 hours'),
  (1, '[seed_test_data.sh] BTC/USD on-chain signal #6',    'BUY',  88, 'Large wallet accumulation detected',  'claude',   'BUY',  88, 'gpt-4o', 'BUY',  85, true,  NOW() - INTERVAL '4 hours'),
  (1, '[seed_test_data.sh] ETH/USD macro context #7',      'HOLD', 55, 'High macro uncertainty',              'claude',   'HOLD', 55, 'gpt-4o', 'HOLD', 58, true,  NOW() - INTERVAL '3 hours'),
  (1, '[seed_test_data.sh] BTC/USD liquidity hunt #8',     'SELL', 72, 'Potential stop-hunt below support',   'claude',   'SELL', 72, 'gpt-4o', 'SELL', 68, true,  NOW() - INTERVAL '2 hours'),
  (1, '[seed_test_data.sh] ETH/USD trend continuation #9', 'BUY',  80, 'Higher highs pattern intact',         'claude',   'BUY',  80, 'gpt-4o', 'BUY',  77, true,  NOW() - INTERVAL '1 hour'),
  (1, '[seed_test_data.sh] BTC/USD end-of-day signal #10', 'HOLD', 65, 'Volume declining into close',         'claude',   'HOLD', 65, 'gpt-4o', 'BUY',  60, false, NOW());

-- ----------------------------------------------------------------
-- proposals: 10 行 (ai_decisions FK 参照なし、status 混在)
-- ----------------------------------------------------------------
INSERT INTO proposals
  (user_id, operation, asset, amount, amount_usd, reason,
   expected_hf_after, estimated_gas_usd, fee_rate, fee_amount,
   status, expires_at, created_at, updated_at)
VALUES
  (1, 'deposit',  'USDC', 500.000000000000000000,  500.00, '[seed_test_data.sh] Staged deposit #1',  1.85, 1.20, 0.0050, 2.50,  'pending',  NOW() + INTERVAL '24 hours', NOW() - INTERVAL '9 hours', NOW() - INTERVAL '9 hours'),
  (1, 'deposit',  'USDC', 300.000000000000000000,  300.00, '[seed_test_data.sh] Staged deposit #2',  1.90, 1.10, 0.0050, 1.50,  'approved', NOW() + INTERVAL '23 hours', NOW() - INTERVAL '8 hours', NOW() - INTERVAL '7 hours'),
  (1, 'withdraw', 'USDC', 200.000000000000000000,  200.00, '[seed_test_data.sh] Staged withdraw #3', 1.70, 1.30, 0.0050, 1.00,  'pending',  NOW() + INTERVAL '22 hours', NOW() - INTERVAL '7 hours', NOW() - INTERVAL '7 hours'),
  (1, 'deposit',  'USDT', 1000.000000000000000000,1000.00, '[seed_test_data.sh] Staged deposit #4',  2.00, 1.50, 0.0030, 3.00,  'executed', NOW() + INTERVAL '21 hours', NOW() - INTERVAL '6 hours', NOW() - INTERVAL '5 hours'),
  (1, 'withdraw', 'USDC', 150.000000000000000000,  150.00, '[seed_test_data.sh] Staged withdraw #5', 1.65, 1.20, 0.0050, 0.75,  'rejected', NOW() + INTERVAL '20 hours', NOW() - INTERVAL '5 hours', NOW() - INTERVAL '4 hours'),
  (1, 'deposit',  'USDC', 750.000000000000000000,  750.00, '[seed_test_data.sh] Staged deposit #6',  1.95, 1.40, 0.0050, 3.75,  'pending',  NOW() + INTERVAL '19 hours', NOW() - INTERVAL '4 hours', NOW() - INTERVAL '4 hours'),
  (1, 'deposit',  'USDT', 250.000000000000000000,  250.00, '[seed_test_data.sh] Staged deposit #7',  1.80, 1.00, 0.0030, 0.75,  'expired',  NOW() - INTERVAL '1 hour',  NOW() - INTERVAL '3 hours', NOW() - INTERVAL '1 hour'),
  (1, 'withdraw', 'USDC', 100.000000000000000000,  100.00, '[seed_test_data.sh] Staged withdraw #8', 1.75, 1.15, 0.0050, 0.50,  'pending',  NOW() + INTERVAL '18 hours', NOW() - INTERVAL '2 hours', NOW() - INTERVAL '2 hours'),
  (1, 'deposit',  'USDC', 600.000000000000000000,  600.00, '[seed_test_data.sh] Staged deposit #9',  1.88, 1.25, 0.0050, 3.00,  'approved', NOW() + INTERVAL '17 hours', NOW() - INTERVAL '1 hour',  NOW() - INTERVAL '30 minutes'),
  (1, 'withdraw', 'USDT', 400.000000000000000000,  400.00, '[seed_test_data.sh] Staged withdraw #10',1.72, 1.35, 0.0030, 1.20,  'pending',  NOW() + INTERVAL '16 hours', NOW(),                        NOW());

-- ----------------------------------------------------------------
-- fund_allocations: 10 行
-- ----------------------------------------------------------------
INSERT INTO fund_allocations
  (partner_id, tester_name, allocated_amount_usd, status, allocated_at, notes, created_at, updated_at)
VALUES
  (1, 'tester-yamamoto',  1000.00, 'active',    NOW() - INTERVAL '9 days',  'seed_test_data.sh #1',  NOW() - INTERVAL '9 days',  NOW() - INTERVAL '9 days'),
  (1, 'tester-tanaka',     500.00, 'active',    NOW() - INTERVAL '8 days',  'seed_test_data.sh #2',  NOW() - INTERVAL '8 days',  NOW() - INTERVAL '8 days'),
  (1, 'tester-suzuki',     750.00, 'active',    NOW() - INTERVAL '7 days',  'seed_test_data.sh #3',  NOW() - INTERVAL '7 days',  NOW() - INTERVAL '7 days'),
  (1, 'tester-sato',      2000.00, 'active',    NOW() - INTERVAL '6 days',  'seed_test_data.sh #4',  NOW() - INTERVAL '6 days',  NOW() - INTERVAL '6 days'),
  (1, 'tester-ito',        300.00, 'withdrawn', NOW() - INTERVAL '5 days',  'seed_test_data.sh #5',  NOW() - INTERVAL '5 days',  NOW() - INTERVAL '2 days'),
  (1, 'tester-watanabe',  1500.00, 'active',    NOW() - INTERVAL '4 days',  'seed_test_data.sh #6',  NOW() - INTERVAL '4 days',  NOW() - INTERVAL '4 days'),
  (1, 'tester-kobayashi',  800.00, 'active',    NOW() - INTERVAL '3 days',  'seed_test_data.sh #7',  NOW() - INTERVAL '3 days',  NOW() - INTERVAL '3 days'),
  (1, 'tester-nakamura',   400.00, 'withdrawn', NOW() - INTERVAL '2 days',  'seed_test_data.sh #8',  NOW() - INTERVAL '2 days',  NOW() - INTERVAL '1 day'),
  (1, 'tester-hayashi',   1200.00, 'active',    NOW() - INTERVAL '1 day',   'seed_test_data.sh #9',  NOW() - INTERVAL '1 day',   NOW() - INTERVAL '1 day'),
  (1, 'tester-kato',       600.00, 'active',    NOW(),                       'seed_test_data.sh #10', NOW(),                       NOW());

COMMIT;
SQL

echo "✅ 投入完了"

# ────────────────────────────────────────────────
# 6. 投入後検証
# ────────────────────────────────────────────────
echo ""
echo "🔍 投入後検証:"
psql "$DB_URL" -t -A -c "
SELECT
  'ai_decisions (seed)'    AS label,
  COUNT(*) AS inserted
FROM ai_decisions
WHERE query LIKE '%[seed_test_data.sh]%'
UNION ALL
SELECT
  'proposals (seed)',
  COUNT(*)
FROM proposals
WHERE reason LIKE '%[seed_test_data.sh]%'
UNION ALL
SELECT
  'fund_allocations (seed)',
  COUNT(*)
FROM fund_allocations
WHERE notes LIKE '%seed_test_data.sh%';
"

echo ""
echo "📊 各テーブル合計件数 (after seed):"
psql "$DB_URL" -t -A -c "
SELECT 'ai_decisions',    COUNT(*) FROM ai_decisions
UNION ALL
SELECT 'proposals',       COUNT(*) FROM proposals
UNION ALL
SELECT 'fund_allocations',COUNT(*) FROM fund_allocations;
"

echo ""
echo "✅ seed_test_data.sh 完了 — DB: $DB_NAME"
echo ""
echo "ROLLBACK する場合:"
echo "  psql \"\$DATABASE_URL\" -c \"DELETE FROM fund_allocations WHERE notes LIKE '%seed_test_data.sh%';\""
echo "  psql \"\$DATABASE_URL\" -c \"DELETE FROM proposals WHERE reason LIKE '%[seed_test_data.sh]%';\""
echo "  psql \"\$DATABASE_URL\" -c \"DELETE FROM ai_decisions WHERE query LIKE '%[seed_test_data.sh]%';\""
