#!/usr/bin/env python3
"""
Partner test wallet 資金調達スクリプト (Base Sepolia testnet のみ)。

staging サーバーウォレットから partner test wallet に:
  1. ETH 転送 (gas 用、0.02 ETH)
  2. Aave testnet faucet から USDC mint (partner に直接)

使い方:
  python3 scripts/fund_partner_test_wallet.py --partner 0xD3b437...

/opt/ultra-autotrade/.env.staging-new を自動 load (AAVE_WALLET_PRIVATE_KEY / AAVE_WALLET_ADDRESS / ALCHEMY_RPC_URL_BASE_SEPOLIA or AAVE_RPC_URL)

WARNING: staging / testnet 専用。本番環境で絶対に使わない。
"""

import argparse
import os
import sys
from decimal import Decimal
from pathlib import Path

try:
    from web3 import Web3
    from eth_account import Account
    from dotenv import load_dotenv
except ImportError as e:
    print(f"Missing dependency: {e}. pip install web3 eth-account python-dotenv")
    sys.exit(1)

# /opt/ultra-autotrade/.env.staging-new から読み込む (本番VPS絶対パス)
_env_path = Path("/opt/ultra-autotrade/.env.staging-new")
if _env_path.exists():
    load_dotenv(_env_path)
    print(f"[INFO] Loaded {_env_path}")
else:
    print(f"[WARN] {_env_path} not found, using environment variables")

POOL_ADDRESS = "0x8bAB6d1b75f19e9eD9fCe8b9BD338844fF79aE27"
FAUCET_ADDRESS = "0xD9145b5F45Ad4519c7ACcD6E0A4A82e83bB8A6Dc"
USDC_ADDRESS = "0xba50cd2a20f6da35d788639e581bca8d0b5d4d5f"
USDC_DECIMALS = 6
ETH_TO_SEND = Decimal("0.02")
USDC_TO_MINT = Decimal("5")

FAUCET_ABI = [
    {
        "name": "mint", "type": "function",
        "inputs": [
            {"name": "token", "type": "address"},
            {"name": "to", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    }
]

ERC20_ABI = [
    {"name": "balanceOf", "type": "function",
     "inputs": [{"name": "account", "type": "address"}],
     "outputs": [{"name": "", "type": "uint256"}]},
]


def mask(addr: str) -> str:
    return f"{addr[:6]}...{addr[-4:]}" if len(addr) > 10 else addr


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--partner", required=True, help="Partner test wallet address")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    rpc_url = os.environ.get("ALCHEMY_RPC_URL_BASE_SEPOLIA") or os.environ.get("AAVE_RPC_URL", "https://sepolia.base.org")
    server_key = os.environ.get("AAVE_WALLET_PRIVATE_KEY", "")
    server_addr = os.environ.get("AAVE_WALLET_ADDRESS", "")

    if not server_key or not server_addr:
        print("ERROR: AAVE_WALLET_PRIVATE_KEY / AAVE_WALLET_ADDRESS が設定されていません (.env.staging-new 要確認)")
        sys.exit(1)

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        print(f"ERROR: RPC に接続できません ({rpc_url})")
        sys.exit(1)

    chain_id = w3.eth.chain_id
    if chain_id != 84532:
        print(f"ERROR: Chain ID {chain_id} は Base Sepolia (84532) ではありません")
        sys.exit(1)

    server_account = Account.from_key(server_key)
    partner = Web3.to_checksum_address(args.partner)
    server = Web3.to_checksum_address(server_addr)

    if server_account.address.lower() != server.lower():
        print(f"ERROR: AAVE_WALLET_PRIVATE_KEY のアドレス {server_account.address} と AAVE_WALLET_ADDRESS {server} が不一致")
        sys.exit(1)

    # 残高確認
    server_eth = w3.from_wei(w3.eth.get_balance(server), "ether")
    faucet = w3.eth.contract(address=Web3.to_checksum_address(FAUCET_ADDRESS), abi=FAUCET_ABI)
    usdc = w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=ERC20_ABI)
    partner_eth = w3.from_wei(w3.eth.get_balance(partner), "ether")
    partner_usdc = Decimal(usdc.functions.balanceOf(partner).call()) / Decimal(10 ** USDC_DECIMALS)

    print(f"[Server]  {mask(server)}: {server_eth:.4f} ETH")
    print(f"[Partner] {mask(partner)}: {partner_eth:.6f} ETH / {partner_usdc:.2f} USDC")
    print()

    if server_eth < ETH_TO_SEND + Decimal("0.01"):
        print(f"ERROR: サーバーウォレットの ETH が不足 ({server_eth} < {ETH_TO_SEND + Decimal('0.01')})")
        sys.exit(1)

    if args.dry_run:
        print(f"DRY RUN: {ETH_TO_SEND} ETH → {mask(partner)}")
        print(f"DRY RUN: {USDC_TO_MINT} USDC (faucet mint) → {mask(partner)}")
        return

    # Step 1: ETH 転送
    print(f"[Step 1] {ETH_TO_SEND} ETH 転送: {mask(server)} → {mask(partner)}")
    nonce = w3.eth.get_transaction_count(server, "pending")
    eth_tx = {
        "from": server,
        "to": partner,
        "value": w3.to_wei(ETH_TO_SEND, "ether"),
        "gas": 21000,
        "gasPrice": w3.eth.gas_price,
        "nonce": nonce,
        "chainId": chain_id,
    }
    signed = w3.eth.account.sign_transaction(eth_tx, private_key=server_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"  eth_transfer tx: 0x{tx_hash.hex()}")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    print(f"  confirmed (status={receipt['status']}, block={receipt['blockNumber']})")

    # Step 2: Aave faucet から USDC mint → partner
    print(f"\n[Step 2] {USDC_TO_MINT} USDC faucet mint → {mask(partner)}")
    amount_raw = int(USDC_TO_MINT * Decimal(10 ** USDC_DECIMALS))
    nonce2 = w3.eth.get_transaction_count(server, "pending")
    mint_tx = faucet.functions.mint(
        Web3.to_checksum_address(USDC_ADDRESS),
        partner,
        amount_raw,
    ).build_transaction({
        "from": server,
        "nonce": nonce2,
        "gasPrice": w3.eth.gas_price,
        "chainId": chain_id,
    })
    signed_mint = w3.eth.account.sign_transaction(mint_tx, private_key=server_key)
    mint_hash = w3.eth.send_raw_transaction(signed_mint.raw_transaction)
    print(f"  faucet_mint tx: 0x{mint_hash.hex()}")
    receipt_mint = w3.eth.wait_for_transaction_receipt(mint_hash, timeout=120)
    print(f"  confirmed (status={receipt_mint['status']}, block={receipt_mint['blockNumber']})")

    # 結果確認
    partner_eth_after = w3.from_wei(w3.eth.get_balance(partner), "ether")
    partner_usdc_after = Decimal(usdc.functions.balanceOf(partner).call()) / Decimal(10 ** USDC_DECIMALS)
    print()
    print(f"[Partner] after: {partner_eth_after:.6f} ETH / {partner_usdc_after:.2f} USDC")
    print("✅ 資金調達完了")
    print()
    print("次のステップ:")
    print(f"  export PARTNER_KEY_FILE=.partner_test_key")
    print(f"  export PARTNER_ADDRESS={partner}")
    print(f"  python3 scripts/verify_non_custodial_staging.py --amount 1.0")


if __name__ == "__main__":
    main()
