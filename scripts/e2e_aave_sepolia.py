# scripts/e2e_aave_sepolia.py
"""
Sepolia テストネット E2E 検証スクリプト。

WARNING: 実際にトランザクションを送信します（テストネット）
WARNING: 少額（1 USDC）で実施すること
WARNING: 本番ウォレットの秘密鍵は絶対に使わないこと

Usage:
    cd /path/to/ultra-autotrade
    python scripts/e2e_aave_sepolia.py
"""

import os
import sys
import time
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(".env.staging")

sys.path.insert(0, str(Path(__file__).parent / ".." / "backend"))

from app.aave.client import AaveClientError, Web3AaveClient  # noqa: E402

rpc_url = os.environ.get("AAVE_RPC_URL", "")
wallet = os.environ.get("AAVE_WALLET_ADDRESS", "")
private_key = os.environ.get("AAVE_WALLET_PRIVATE_KEY", "")
usdc = "0x94a9D9AC8a22534E3FaCa9F4e7F2E2cf85d5E4C8"  # Sepolia USDC

for var_name, var_val in [
    ("AAVE_RPC_URL", rpc_url),
    ("AAVE_WALLET_ADDRESS", wallet),
    ("AAVE_WALLET_PRIVATE_KEY", private_key),
]:
    if not var_val:
        print(f"ERROR: {var_name} is not set in .env.staging")
        sys.exit(1)

print("=" * 50)
print("Aave V3 Sepolia E2E Test")
print("=" * 50)
print(f"RPC: {rpc_url[:30]}...")
print(f"Wallet: {wallet[:6]}...{wallet[-4:]}")
print(f"USDC: {usdc}")
print()

try:
    client = Web3AaveClient(rpc_url=rpc_url)
    print("RPC 接続: OK")
    print()

    # 1. 事前HF確認
    hf_before = client.get_health_factor(wallet)
    print(f"[1] HF before: {hf_before}")

    if hf_before != Decimal("inf") and hf_before < Decimal("1.6"):
        print("  WARNING: HF < 1.6 — withdraw は HF チェックでブロックされます")
        print("  -> 担保を追加してから再実行してください")
        sys.exit(1)

    # 2. deposit 1 USDC
    print()
    print("[2] Depositing 1 USDC...")
    dep = client.deposit(
        asset_address=usdc,
        amount=Decimal("1.0"),
        wallet_address=wallet,
        private_key=private_key,
        dry_run=False,
    )
    print(f"  deposit tx: {dep['tx_hash']}")
    print(f"  https://sepolia.etherscan.io/tx/{dep['tx_hash']}")

    # 3. 確認待ち
    print()
    print("[3] Waiting 15s for confirmation...")
    time.sleep(15)

    hf_after_deposit = client.get_health_factor(wallet)
    print(f"  HF after deposit: {hf_after_deposit}")

    # 4. withdraw 1 USDC
    print()
    print("[4] Withdrawing 1 USDC...")
    wd = client.withdraw(
        asset_address=usdc,
        amount=Decimal("1.0"),
        wallet_address=wallet,
        private_key=private_key,
        dry_run=False,
    )
    print(f"  withdraw tx: {wd['tx_hash']}")
    print(f"  https://sepolia.etherscan.io/tx/{wd['tx_hash']}")

    # 5. 最終HF確認
    print()
    print("[5] Waiting 15s for confirmation...")
    time.sleep(15)

    hf_final = client.get_health_factor(wallet)
    print(f"  HF final: {hf_final}")

    # Summary
    print()
    print("=" * 50)
    print("Results Summary")
    print("=" * 50)
    print("  RPC接続:           OK")
    print(f"  HF before:         {hf_before}")
    print(f"  deposit tx:        {dep['tx_hash']}")
    print(f"  HF after deposit:  {hf_after_deposit}")
    print(f"  withdraw tx:       {wd['tx_hash']}")
    print(f"  HF final:          {hf_final}")
    print()
    print("E2E 完了")

except AaveClientError as e:
    print(f"AaveClientError: {e}")
    sys.exit(1)
except Exception as e:
    print(f"Unexpected error: {type(e).__name__}: {e}")
    sys.exit(1)
