#!/usr/bin/env bash
# run_proposal_lifecycle_e2e.sh
# Proposal lifecycle E2E (staging / Base Sepolia testnet 専用):
#   新規 test wallet 生成 → server から fund → test partner user + proposal 作成
#   → build-tx API → 署名 → broadcast → submit-tx API → executed 遷移 → on-chain 検証。
#
# 既存の run_non_custodial_e2e.sh は approve/supply をローカル構築するだけで
# build-tx/submit-tx API も proposal lifecycle も通さない。本スクリプトは API 経由で完走する。
#
# 【重要】API/on-chain lifecycle の実証であり、実 partner の Privy 署名経路の実証ではない
# (実 partner は鍵がサーバーに無く CLI 署名不可 = non-custodial 設計の正)。実 partner 経路は
# LINE LIFF + Privy セットアップ後に別途検証する。
#
# 使い方 (staging VPS 上で。実 testnet tx を送信する):
#   bash scripts/run_proposal_lifecycle_e2e.sh [--amount 1.0]
#
# 必要: backend/.venv (web3 / eth-account / sqlalchemy)、.env.staging-new、稼働中 staging backend。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
AMOUNT="${1:-1.0}"
KEY_FILE="/tmp/.lifecycle_partner_key_$(date +%s)"

# .env.staging-new ロード (本番 VPS パス優先、dev VPS フォールバック)
ENV_STAGING_NEW="/opt/ultra-autotrade/.env.staging-new"
ENV_STAGING_DEV="$REPO_ROOT/.env.staging-new"
if [[ -f "$ENV_STAGING_NEW" ]]; then
    echo "[INFO] Loading $ENV_STAGING_NEW"
    set -a && source "$ENV_STAGING_NEW" && set +a
elif [[ -f "$ENV_STAGING_DEV" ]]; then
    echo "[INFO] Loading $ENV_STAGING_DEV"
    set -a && source "$ENV_STAGING_DEV" && set +a
else
    echo "[WARN] .env.staging-new が見つかりません。環境変数を使用"
fi

# 本番ガード: APP_ENV が staging でなければ拒否
if [[ "${APP_ENV:-}" != "staging" ]]; then
    echo "ERROR: APP_ENV=${APP_ENV:-未設定} — 本スクリプトは staging 専用です (本番禁止)"
    exit 1
fi

if [[ -f "$REPO_ROOT/backend/.venv/bin/python3" ]]; then
    PYTHON="$REPO_ROOT/backend/.venv/bin/python3"
else
    PYTHON="python3"
fi

cleanup() { rm -f "$KEY_FILE" 2>/dev/null && echo "[cleanup] removed $KEY_FILE" || true; }
trap cleanup EXIT

echo "=== Step 1: 新規 test wallet 生成 ==="
WALLET_JSON=$("$PYTHON" - <<'EOF'
import json, secrets
from eth_account import Account
pk = "0x" + secrets.token_hex(32)
print(json.dumps({"address": Account.from_key(pk).address, "private_key": pk}))
EOF
)
PARTNER_ADDR=$(echo "$WALLET_JSON" | "$PYTHON" -c "import sys,json;print(json.load(sys.stdin)['address'])")
PARTNER_KEY=$(echo "$WALLET_JSON" | "$PYTHON" -c "import sys,json;print(json.load(sys.stdin)['private_key'])")
printf '%s' "$PARTNER_KEY" > "$KEY_FILE"
chmod 600 "$KEY_FILE"
unset PARTNER_KEY WALLET_JSON  # 鍵をシェル環境に残さない
echo "  Partner address: $PARTNER_ADDR (鍵は $KEY_FILE, mode 600)"

echo ""
echo "=== Step 2: server から fund (ETH gas + USDC) ==="
"$PYTHON" "$SCRIPT_DIR/fund_partner_test_wallet.py" --partner "$PARTNER_ADDR"

echo ""
echo "=== Step 3: proposal lifecycle 検証 (build-tx → sign → submit-tx → executed) ==="
PYTHONPATH="$REPO_ROOT/backend" \
PARTNER_KEY_FILE="$KEY_FILE" \
PARTNER_ADDRESS="$PARTNER_ADDR" \
"$PYTHON" "$SCRIPT_DIR/verify_proposal_lifecycle_staging.py" --amount "$AMOUNT"
