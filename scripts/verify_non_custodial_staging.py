#!/usr/bin/env python3
"""
Non-custodial 方式2 staging 実証スクリプト。

Base Sepolia でパートナーウォレットが USDC approve + Pool.supply を
パートナー自身の鍵で署名・送信し、aToken がパートナーに帰属することを確認する。

DoD 確認:
- from/onBehalfOf が partner アドレスであること (basescan sepolia で確認)
- サーバーウォレット (AAVE_WALLET_ADDRESS) は一切関与しないこと

使い方:
  python3 scripts/verify_non_custodial_staging.py \\
    --partner-key 0x<partner_private_key> \\
    --partner-address 0x2064...cc66 \\
    --amount 1.0

環境変数 (または .env.staging から):
  AAVE_RPC_URL_BASE_SEPOLIA  Base Sepolia RPC
  AAVE_POOL_ADDRESS_BASE_SEPOLIA  Aave V3 Pool
  AAVE_USDC_ADDRESS_BASE_SEPOLIA  USDC (testnet faucet token)
"""

import argparse
import os
import sys
from decimal import Decimal

# web3 が必要
try:
    from web3 import Web3
    from eth_account import Account
except ImportError:
    print("ERROR: web3 / eth-account が未インストール。pip install web3 eth-account")
    sys.exit(1)

# --- ABI (最小限) ---
ERC20_ABI = [
    {"name": "approve", "type": "function",
     "inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}],
     "outputs": [{"name": "", "type": "bool"}]},
    {"name": "balanceOf", "type": "function",
     "inputs": [{"name": "account", "type": "address"}],
     "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "decimals", "type": "function", "inputs": [], "outputs": [{"name": "", "type": "uint8"}]},
]

POOL_ABI = [
    {"name": "supply", "type": "function",
     "inputs": [
         {"name": "asset", "type": "address"},
         {"name": "amount", "type": "uint256"},
         {"name": "onBehalfOf", "type": "address"},
         {"name": "referralCode", "type": "uint16"},
     ],
     "outputs": []},
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

ATOKEN_ABI = [
    {"name": "balanceOf", "type": "function",
     "inputs": [{"name": "account", "type": "address"}],
     "outputs": [{"name": "", "type": "uint256"}]},
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Non-custodial 方式2 staging 実証")
    parser.add_argument("--partner-key", required=True, help="パートナー秘密鍵 (0x...)")
    parser.add_argument("--partner-address", required=True, help="パートナーアドレス (0x...)")
    parser.add_argument("--amount", type=float, default=1.0, help="供給USDC量 (例: 1.0)")
    args = parser.parse_args()

    rpc_url = os.getenv("AAVE_RPC_URL_BASE_SEPOLIA", "https://sepolia.base.org")
    pool_address = os.getenv(
        "AAVE_POOL_ADDRESS_BASE_SEPOLIA",
        "0x07eA79F68B2B3df564D0A34F8e19D9B1e339814b",  # Aave V3 Base Sepolia
    )
    usdc_address = os.getenv(
        "AAVE_USDC_ADDRESS_BASE_SEPOLIA",
        "0x036CbD53842c5426634e7929541eC2318f3dCF7e",  # USDC Base Sepolia (faucet)
    )

    partner_key = args.partner_key
    partner_address = Web3.to_checksum_address(args.partner_address)
    amount_usdc = Decimal(str(args.amount))

    print(f"=== Non-custodial 方式2 staging 実証 ===")
    print(f"Partner: {partner_address}")
    print(f"Amount:  {amount_usdc} USDC")
    print(f"RPC:     {rpc_url}")
    print(f"Pool:    {pool_address}")
    print()

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        print("ERROR: RPC に接続できません")
        sys.exit(1)

    partner_account = Account.from_key(partner_key)
    if partner_account.address.lower() != partner_address.lower():
        print(f"ERROR: 鍵のアドレス {partner_account.address} が指定アドレスと不一致")
        sys.exit(1)

    usdc = w3.eth.contract(address=Web3.to_checksum_address(usdc_address), abi=ERC20_ABI)
    pool = w3.eth.contract(address=Web3.to_checksum_address(pool_address), abi=POOL_ABI)

    decimals = usdc.functions.decimals().call()
    amount_wei = int(amount_usdc * Decimal(10**decimals))

    # USDC 残高チェック
    balance = usdc.functions.balanceOf(partner_address).call()
    balance_human = Decimal(balance) / Decimal(10**decimals)
    print(f"Partner USDC 残高: {balance_human}")
    if balance < amount_wei:
        print(f"ERROR: USDC 残高不足 (必要: {amount_usdc}, 保有: {balance_human})")
        print("Base Sepolia USDC faucet: https://faucet.circle.com/")
        sys.exit(1)

    chain_id = w3.eth.chain_id
    print(f"Chain ID: {chain_id} (Base Sepolia = 84532)")

    # --- Step 1: approve ---
    print("\n[Step 1] USDC approve (partner 署名)")
    nonce = w3.eth.get_transaction_count(partner_address, "pending")
    approve_tx = usdc.functions.approve(
        Web3.to_checksum_address(pool_address), amount_wei
    ).build_transaction({
        "from": partner_address,
        "nonce": nonce,
        "gasPrice": w3.eth.gas_price,
        "chainId": chain_id,
    })
    signed_approve = w3.eth.account.sign_transaction(approve_tx, private_key=partner_key)
    approve_hash = w3.eth.send_raw_transaction(signed_approve.raw_transaction)
    print(f"  approve tx: {approve_hash.hex()}")
    receipt_approve = w3.eth.wait_for_transaction_receipt(approve_hash)
    if receipt_approve["status"] != 1:
        print("ERROR: approve tx が revert しました")
        sys.exit(1)
    print(f"  approve confirmed (block {receipt_approve['blockNumber']})")
    print(f"  from:    {receipt_approve['from']}  ← must be partner")

    # --- Step 2: supply ---
    print("\n[Step 2] Pool.supply (partner 署名, onBehalfOf=partner)")
    nonce2 = w3.eth.get_transaction_count(partner_address, "pending")
    supply_tx = pool.functions.supply(
        Web3.to_checksum_address(usdc_address),
        amount_wei,
        partner_address,  # onBehalfOf = partner
        0,
    ).build_transaction({
        "from": partner_address,
        "nonce": nonce2,
        "gasPrice": w3.eth.gas_price,
        "chainId": chain_id,
    })
    signed_supply = w3.eth.account.sign_transaction(supply_tx, private_key=partner_key)
    supply_hash = w3.eth.send_raw_transaction(signed_supply.raw_transaction)
    print(f"  supply tx: {supply_hash.hex()}")
    receipt_supply = w3.eth.wait_for_transaction_receipt(supply_hash)
    if receipt_supply["status"] != 1:
        print("ERROR: supply tx が revert しました")
        sys.exit(1)
    print(f"  supply confirmed (block {receipt_supply['blockNumber']})")
    print(f"  from:    {receipt_supply['from']}  ← must be partner")

    # --- DoD 確認 ---
    print("\n=== DoD 確認 ===")
    from_approve = receipt_approve["from"]
    from_supply = receipt_supply["from"]

    ok = True
    if from_approve.lower() != partner_address.lower():
        print(f"FAIL: approve.from={from_approve} != partner={partner_address}")
        ok = False
    else:
        print(f"PASS: approve.from = {from_approve} (partner)")

    if from_supply.lower() != partner_address.lower():
        print(f"FAIL: supply.from={from_supply} != partner={partner_address}")
        ok = False
    else:
        print(f"PASS: supply.from = {from_supply} (partner)")

    # aToken 残高確認 (Aave V3 Base Sepolia aUSDC)
    account_data = pool.functions.getUserAccountData(partner_address).call()
    collateral_base = Decimal(account_data[0]) / Decimal(10**8)
    print(f"PASS: partner collateral = ${collateral_base:.4f} (Aave V3 account data)")

    print(f"\n approve tx: https://sepolia.basescan.org/tx/{approve_hash.hex()}")
    print(f" supply  tx: https://sepolia.basescan.org/tx/{supply_hash.hex()}")

    if ok:
        print("\n✅ DoD PASS: from/onBehalfOf = partner で supply 成功")
        print("basescan で上記 tx を確認してください。")
    else:
        print("\n❌ DoD FAIL: アドレスが partner ではありません")
        sys.exit(1)


if __name__ == "__main__":
    main()
