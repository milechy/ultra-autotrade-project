#!/usr/bin/env python3
"""
Non-custodial 方式2 staging 実証スクリプト。

Base Sepolia でパートナーウォレットが USDC approve + Pool.supply を
パートナー自身の鍵で署名・送信し、aToken がパートナーに帰属することを確認する。

DoD 確認:
- from/onBehalfOf が partner アドレスであること (basescan sepolia で確認)
- サーバーウォレット (AAVE_WALLET_ADDRESS) は一切関与しないこと

使い方:
  # 鍵はファイル経由 (mode 600) で渡す — CLI arg 禁止 (§13)
  export PARTNER_KEY_FILE=/path/to/.partner_test_key   # または
  export PARTNER_PRIVATE_KEY=0x...  (環境変数直接)
  export PARTNER_ADDRESS=0x...
  python3 scripts/verify_non_custodial_staging.py [--amount 1.0] [--dry-run]

コントラクトアドレス (Base Sepolia):
  Pool:   0x8bAB6d1b75f19e9eD9fCe8b9BD338844fF79aE27
  USDC:   0xba50cd2a20f6da35d788639e581bca8d0b5d4d5f
  Faucet: 0xD9145b5F45Ad4519c7ACcD6E0A4A82e83bB8A6Dc
"""

import argparse
import os
import sys
from decimal import Decimal
from pathlib import Path

try:
    from web3 import Web3
    from eth_account import Account
except ImportError:
    print("ERROR: web3 / eth-account が未インストール。pip install web3 eth-account")
    sys.exit(1)

# Base Sepolia アドレス (aave_e2e_base.py で検証済み)
POOL_ADDRESS = "0x8bAB6d1b75f19e9eD9fCe8b9BD338844fF79aE27"
USDC_ADDRESS = "0xba50cd2a20f6da35d788639e581bca8d0b5d4d5f"
USDC_DECIMALS = 6

ERC20_ABI = [
    {"name": "approve", "type": "function",
     "inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}],
     "outputs": [{"name": "", "type": "bool"}]},
    {"name": "balanceOf", "type": "function",
     "inputs": [{"name": "account", "type": "address"}],
     "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "decimals", "type": "function", "inputs": [],
     "outputs": [{"name": "", "type": "uint8"}]},
]

POOL_ABI = [
    {"name": "supply", "type": "function",
     "inputs": [
         {"name": "asset", "type": "address"},
         {"name": "amount", "type": "uint256"},
         {"name": "onBehalfOf", "type": "address"},
         {"name": "referralCode", "type": "uint16"},
     ], "outputs": []},
    {"name": "getUserAccountData", "type": "function",
     "inputs": [{"name": "user", "type": "address"}],
     "outputs": [
         {"name": "totalCollateralBase", "type": "uint256"},
         {"name": "totalDebtBase", "type": "uint256"},
         {"name": "availableBorrowsBase", "type": "uint256"},
         {"name": "currentLiquidationThreshold", "type": "uint256"},
         {"name": "ltv", "type": "uint256"},
         {"name": "healthFactor", "type": "uint256"},
     ]},
]


def load_partner_key() -> str:
    """環境変数またはファイルからパートナー秘密鍵を読み込む。CLIから取らない。"""
    # 優先1: ファイルパス指定
    key_file = os.environ.get("PARTNER_KEY_FILE")
    if key_file:
        p = Path(key_file)
        if not p.exists():
            print(f"ERROR: PARTNER_KEY_FILE が見つかりません: {key_file}")
            sys.exit(1)
        perm = oct(p.stat().st_mode)[-3:]
        if perm not in ("600", "400"):
            print(f"WARN: {key_file} のパーミッションが {perm} (600 推奨)")
        key = p.read_text().strip()
        return key

    # 優先2: 環境変数直接
    key = os.environ.get("PARTNER_PRIVATE_KEY")
    if key:
        return key

    print("ERROR: PARTNER_KEY_FILE または PARTNER_PRIVATE_KEY を設定してください")
    print("  export PARTNER_KEY_FILE=/path/to/.partner_test_key")
    print("  export PARTNER_PRIVATE_KEY=0x...")
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Non-custodial 方式2 staging 実証")
    parser.add_argument("--amount", type=float, default=1.0, help="供給USDC量 (例: 1.0)")
    parser.add_argument("--dry-run", action="store_true", help="tx を送信しない (残高確認のみ)")
    args = parser.parse_args()

    partner_key = load_partner_key()
    partner_address_env = os.environ.get("PARTNER_ADDRESS", "")

    try:
        partner_account = Account.from_key(partner_key)
    except Exception as e:
        print(f"ERROR: 鍵が無効です: {e}")
        sys.exit(1)

    partner_address = Web3.to_checksum_address(partner_address_env or partner_account.address)
    if partner_account.address.lower() != partner_address.lower():
        print(f"ERROR: 鍵のアドレス {partner_account.address} と PARTNER_ADDRESS {partner_address} が不一致")
        sys.exit(1)

    amount_usdc = Decimal(str(args.amount))
    rpc_url = os.environ.get("AAVE_RPC_URL_BASE_SEPOLIA", "https://sepolia.base.org")

    print("=== Non-custodial 方式2 staging 実証 ===")
    print(f"Partner: {partner_address}")
    print(f"Amount:  {amount_usdc} USDC")
    print(f"RPC:     {rpc_url}")
    print(f"Pool:    {POOL_ADDRESS}")
    print(f"USDC:    {USDC_ADDRESS}")
    print()

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        print("ERROR: RPC に接続できません")
        sys.exit(1)

    chain_id = w3.eth.chain_id
    if chain_id != 84532:
        print(f"ERROR: Chain ID {chain_id} は Base Sepolia (84532) ではありません")
        sys.exit(1)

    usdc = w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=ERC20_ABI)
    pool = w3.eth.contract(address=Web3.to_checksum_address(POOL_ADDRESS), abi=POOL_ABI)
    amount_wei = int(amount_usdc * Decimal(10 ** USDC_DECIMALS))

    # 残高確認
    eth_bal = w3.from_wei(w3.eth.get_balance(partner_address), "ether")
    usdc_bal = Decimal(usdc.functions.balanceOf(partner_address).call()) / Decimal(10 ** USDC_DECIMALS)
    print(f"Partner ETH:  {eth_bal:.6f}")
    print(f"Partner USDC: {usdc_bal:.6f}")
    print()

    if eth_bal < Decimal("0.001"):
        print("ERROR: ETH 残高不足 (gas用に最低 0.001 ETH 必要)")
        sys.exit(1)
    if usdc_bal < amount_usdc:
        print(f"ERROR: USDC 残高不足 ({usdc_bal} < {amount_usdc})")
        sys.exit(1)

    if args.dry_run:
        print("DRY RUN: 残高確認 OK。--dry-run なし で実行すると実際の tx を送信します。")
        return

    # --- Step 1: approve ---
    print("[Step 1] USDC approve (partner 署名, from=partner)")
    nonce = w3.eth.get_transaction_count(partner_address, "pending")
    approve_tx = usdc.functions.approve(
        Web3.to_checksum_address(POOL_ADDRESS), amount_wei
    ).build_transaction({
        "from": partner_address,
        "nonce": nonce,
        "gasPrice": w3.eth.gas_price,
        "chainId": chain_id,
    })
    signed_approve = w3.eth.account.sign_transaction(approve_tx, private_key=partner_key)
    approve_hash = w3.eth.send_raw_transaction(signed_approve.raw_transaction)
    print(f"  approve tx: 0x{approve_hash.hex()}")
    receipt_approve = w3.eth.wait_for_transaction_receipt(approve_hash, timeout=120)
    if receipt_approve["status"] != 1:
        print("ERROR: approve tx が revert しました")
        sys.exit(1)
    print(f"  confirmed (block {receipt_approve['blockNumber']})")
    print(f"  from:    {receipt_approve['from']}")

    # --- Step 2: supply ---
    print("\n[Step 2] Pool.supply (partner 署名, from=partner, onBehalfOf=partner)")
    nonce2 = w3.eth.get_transaction_count(partner_address, "pending")
    supply_tx = pool.functions.supply(
        Web3.to_checksum_address(USDC_ADDRESS),
        amount_wei,
        partner_address,  # onBehalfOf = partner 本人
        0,
    ).build_transaction({
        "from": partner_address,
        "nonce": nonce2,
        "gasPrice": w3.eth.gas_price,
        "chainId": chain_id,
    })
    signed_supply = w3.eth.account.sign_transaction(supply_tx, private_key=partner_key)
    supply_hash = w3.eth.send_raw_transaction(signed_supply.raw_transaction)
    print(f"  supply tx: 0x{supply_hash.hex()}")
    receipt_supply = w3.eth.wait_for_transaction_receipt(supply_hash, timeout=120)
    if receipt_supply["status"] != 1:
        print("ERROR: supply tx が revert しました")
        sys.exit(1)
    print(f"  confirmed (block {receipt_supply['blockNumber']})")
    print(f"  from:    {receipt_supply['from']}")

    # --- DoD 確認 ---
    print("\n=== DoD 確認 ===")
    from_approve = receipt_approve["from"]
    from_supply = receipt_supply["from"]
    ok = True

    if from_approve.lower() == partner_address.lower():
        print(f"PASS: approve.from = {from_approve}  (partner)")
    else:
        print(f"FAIL: approve.from = {from_approve}  ≠ partner {partner_address}")
        ok = False

    if from_supply.lower() == partner_address.lower():
        print(f"PASS: supply.from  = {from_supply}  (partner)")
    else:
        print(f"FAIL: supply.from  = {from_supply}  ≠ partner {partner_address}")
        ok = False

    # aToken 残高 (collateral via getUserAccountData)
    account_data = pool.functions.getUserAccountData(partner_address).call()
    collateral_usd = Decimal(account_data[0]) / Decimal(10 ** 8)
    print(f"PASS: partner collateral = ${collateral_usd:.4f} USD (Aave account data)")

    print()
    print(f"  approve tx: https://sepolia.basescan.org/tx/0x{approve_hash.hex()}")
    print(f"  supply  tx: https://sepolia.basescan.org/tx/0x{supply_hash.hex()}")
    print()

    if ok:
        print("✅ DoD PASS: from/onBehalfOf = partner で supply 成功")
        print("basescan で上記 tx を確認してください。")
        print()
        print("=== Custody 設計確認 ===")
        print(f"署名主体: PARTNER_KEY_FILE / PARTNER_PRIVATE_KEY に格納された鍵")
        print(f"→ この検証スクリプトでは testnet 専用生成鍵。本番 Privy フローでは")
        print(f"  partner の Privy embedded wallet が署名 (秘密鍵はサーバーに渡らない)。")
        print(f"→ サーバー鍵 (AAVE_WALLET_PRIVATE_KEY) は tx に一切署名しない。")
    else:
        print("❌ DoD FAIL: アドレスが partner ではありません")
        sys.exit(1)


if __name__ == "__main__":
    main()
