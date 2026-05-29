#!/usr/bin/env bash
# verify_rebalance_shadow_source.sh
# REBALANCE_SHADOW_MODE が compose environment: ではなく .env 単一ソースで管理されているか検証する
# DoD: PR #457 (chore/rebalance-shadow-mode-env-ref-20260529)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PASS=0
FAIL=0

ok()   { echo "✅ $1"; PASS=$((PASS+1)); }
fail() { echo "❌ $1"; FAIL=$((FAIL+1)); }
warn() { echo "⚠️  $1"; }

echo "=== verify_rebalance_shadow_source ==="

# ── [1] compose の environment: に REBALANCE_SHADOW_MODE が残っていないこと ──

PROD_HIT=$(awk '
  /^  [a-z]/ { in_env=0 }
  /^    environment:/ { in_env=1 }
  in_env && /REBALANCE_SHADOW_MODE/ && !/^[[:space:]]*#/ { print NR": "$0 }
' "$PROJECT_ROOT/docker-compose.production.yml")

if [ -z "$PROD_HIT" ]; then
  ok "docker-compose.production.yml: REBALANCE_SHADOW_MODE は environment: に存在しない"
else
  fail "docker-compose.production.yml: REBALANCE_SHADOW_MODE が environment: に残存"
  echo "  $PROD_HIT"
fi

STAGING_HIT=$(awk '
  /^  [a-z]/ { in_env=0 }
  /^    environment:/ { in_env=1 }
  in_env && /REBALANCE_SHADOW_MODE/ && !/^[[:space:]]*#/ { print NR": "$0 }
' "$PROJECT_ROOT/docker-compose.staging.yml")

if [ -z "$STAGING_HIT" ]; then
  ok "docker-compose.staging.yml: REBALANCE_SHADOW_MODE は environment: に存在しない"
else
  fail "docker-compose.staging.yml: REBALANCE_SHADOW_MODE が environment: に残存"
  echo "  $STAGING_HIT"
fi

# ── [2] .env 側に REBALANCE_SHADOW_MODE が明示されているか ──

if [ -f "$PROJECT_ROOT/.env.production" ]; then
  if grep -q "^REBALANCE_SHADOW_MODE=" "$PROJECT_ROOT/.env.production"; then
    VAL=$(grep "^REBALANCE_SHADOW_MODE=" "$PROJECT_ROOT/.env.production" | cut -d= -f2)
    ok ".env.production: REBALANCE_SHADOW_MODE=$VAL"
  else
    fail ".env.production: REBALANCE_SHADOW_MODE が未設定"
  fi
else
  warn ".env.production が存在しない (本番 VPS 上での確認が必要)"
fi

if [ -f "$PROJECT_ROOT/.env.staging-new" ]; then
  if grep -q "^REBALANCE_SHADOW_MODE=" "$PROJECT_ROOT/.env.staging-new"; then
    VAL=$(grep "^REBALANCE_SHADOW_MODE=" "$PROJECT_ROOT/.env.staging-new" | cut -d= -f2)
    ok ".env.staging-new: REBALANCE_SHADOW_MODE=$VAL"
  else
    fail ".env.staging-new: REBALANCE_SHADOW_MODE が未設定"
  fi
else
  warn ".env.staging-new が存在しない (本番 VPS 上での確認が必要)"
fi

# ── [3] .env.production.example に REBALANCE_SHADOW_MODE=true が記載されているか ──

if grep -q "^REBALANCE_SHADOW_MODE=true" "$PROJECT_ROOT/.env.production.example"; then
  ok ".env.production.example: REBALANCE_SHADOW_MODE=true"
else
  fail ".env.production.example: REBALANCE_SHADOW_MODE=true が未設定"
fi

# ── Summary ──

echo ""
echo "PASS=$PASS FAIL=$FAIL"
if [ "$FAIL" -eq 0 ]; then
  echo "✅ All checks passed"
  exit 0
else
  echo "❌ $FAIL check(s) failed"
  exit 1
fi
