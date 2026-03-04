# scripts/check_deposit_dryrun.py
"""
deposit() dry_run 確認スクリプト。
実際のトランザクションは送信しない。

Usage:
    cd /path/to/ultra-autotrade
    python scripts/check_deposit_dryrun.py
"""

import os
import sys
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(".env.staging")

sys.path.insert(0, str(Path(__file__).parent / ".." / "backend"))

from app.aave.client import AaveClientError, Web3AaveClient  # noqa: E402

rpc_url = os.environ.get("AAVE_RPC_URL", "")
wallet = os.environ.get("AAVE_WALLET_ADDRESS", "")
private_key = os.environ.get("AAVE_WALLET_PRIVATE_KEY", "")
usdc_address = "0x94a9D9AC8a22534E3FaCa9F4e7F2E2cf85d5E4C8"  # Sepolia USDC

for var_name, var_val in [
    ("AAVE_RPC_URL", rpc_url),
    ("AAVE_WALLET_ADDRESS", wallet),
    ("AAVE_WALLET_PRIVATE_KEY", private_key),
]:
    if not var_val:
        print(f"ERROR: {var_name} is not set in .env.staging")
        sys.exit(1)

try:
    client = Web3AaveClient(rpc_url=rpc_url)
    print("RPC 接続: OK")

    # dry_run=True -> tx送信なし
    result = client.deposit(
        asset_address=usdc_address,
        amount=Decimal("1.0"),  # 1 USDC
        wallet_address=wallet,
        private_key=private_key,
        dry_run=True,
    )
    print(f"dry_run result: {result}")

    assert result["dry_run"] is True, "dry_run should be True"
    assert result["tx_hash"] is None, "tx_hash should be None in dry_run"
    assert result["amount"] == "1.0", f"amount should be '1.0', got {result['amount']}"

    print()
    print("deposit dry_run OK — tx未送信を確認")

except AaveClientError as e:
    print(f"AaveClientError: {e}")
    sys.exit(1)
except Exception as e:
    print(f"Unexpected error: {type(e).__name__}: {e}")
    sys.exit(1)
