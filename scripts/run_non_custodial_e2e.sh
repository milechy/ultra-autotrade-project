#!/usr/bin/env bash
# run_non_custodial_e2e.sh
# Non-custodial 方式2 E2E テスト: 新規パートナーウォレット生成 → 資金調達 → verify
#
# 使い方 (staging VPS または dev VPS 上で):
#   export AAVE_WALLET_PRIVATE_KEY=0x...  # サーバー鍵 (.env.staging-new から)
#   export AAVE_WALLET_ADDRESS=0x...      # サーバー鍵のアドレス
#   bash scripts/run_non_custodial_e2e.sh [--amount 1.0]
#
# または .env.staging-new がある環境では自動ロード:
#   bash scripts/run_non_custodial_e2e.sh
#
# 必要: python3, web3, eth-account, python-dotenv (backend/.venv)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
AMOUNT="${1:-1.0}"
KEY_FILE="/tmp/.partner_test_key_$(date +%s)"

# .env.staging-new の自動ロード (prod VPS パスを優先、dev VPS パスをフォールバック)
ENV_STAGING_NEW="/opt/ultra-autotrade/.env.staging-new"
ENV_STAGING_DEV="$REPO_ROOT/.env.staging-new"

if [[ -f "$ENV_STAGING_NEW" ]]; then
    echo "[INFO] Loading $ENV_STAGING_NEW"
    set -a && source "$ENV_STAGING_NEW" && set +a
elif [[ -f "$ENV_STAGING_DEV" ]]; then
    echo "[INFO] Loading $ENV_STAGING_DEV"
    set -a && source "$ENV_STAGING_DEV" && set +a
else
    echo "[WARN] .env.staging-new が見つかりません。AAVE_WALLET_PRIVATE_KEY を環境変数から使用"
fi

# Python venv の選択
if [[ -f "$REPO_ROOT/backend/.venv/bin/python3" ]]; then
    PYTHON="$REPO_ROOT/backend/.venv/bin/python3"
else
    PYTHON="python3"
fi

echo "=== Step 1: 新規パートナーウォレット生成 ==="
WALLET_JSON=$("$PYTHON" - <<'EOF'
import json, secrets
from eth_account import Account
pk = "0x" + secrets.token_hex(32)
acc = Account.from_key(pk)
print(json.dumps({"address": acc.address, "private_key": pk}))
EOF
)

PARTNER_ADDR=$(echo "$WALLET_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['address'])")
PARTNER_KEY=$(echo "$WALLET_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['private_key'])")

echo "  Partner address: $PARTNER_ADDR"

# 鍵をファイルに書き込み (mode 600)
printf '%s' "$PARTNER_KEY" > "$KEY_FILE"
chmod 600 "$KEY_FILE"
echo "  Key saved to: $KEY_FILE"

echo ""
echo "=== Step 2: パートナーウォレットに資金調達 ==="
"$PYTHON" "$SCRIPT_DIR/fund_partner_test_wallet.py" --partner "$PARTNER_ADDR"

echo ""
echo "=== Step 3: Non-custodial verify (approve + supply) ==="
PARTNER_KEY_FILE="$KEY_FILE" \
PARTNER_ADDRESS="$PARTNER_ADDR" \
"$PYTHON" "$SCRIPT_DIR/verify_non_custodial_staging.py" --amount "$AMOUNT"

echo ""
echo "=== Cleanup ==="
rm -f "$KEY_FILE"
echo "  Removed $KEY_FILE"
