#!/usr/bin/env python3
# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# scripts/mint_test_usdc.py
"""
Mint test USDC from Aave testnet faucet.

対応チェーン:
  - arbitrum_sepolia (chain_id=421614)
  - base_sepolia     (chain_id=84532)

環境変数（.env.staging から自動ロード）:
  AAVE_WALLET_PRIVATE_KEY           - 送信元ウォレットの秘密鍵
  AAVE_WALLET_ADDRESS               - ウォレットアドレス（--wallet 省略時）
  ALCHEMY_RPC_URL_ARBITRUM_SEPOLIA  - Arbitrum Sepolia RPC URL
  ALCHEMY_RPC_URL_BASE_SEPOLIA      - Base Sepolia RPC URL（優先）
  AAVE_RPC_URL_BASE_SEPOLIA         - Base Sepolia RPC URL（フォールバック）

使用例:
  python scripts/mint_test_usdc.py --chain arbitrum_sepolia --amount 5000
  python scripts/mint_test_usdc.py --chain base_sepolia --dry-run
  python scripts/mint_test_usdc.py --chain arbitrum_sepolia --wallet 0xABC...
"""

import argparse
import logging
import os
import sys
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env.staging")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Aave V3 Testnet Faucet addresses
FAUCET_ADDRESSES: dict[str, str] = {
    "arbitrum_sepolia": "0x1265305F033156bbF8Ba54fE45DD5685BEc4Cc44",
    "base_sepolia": "0xD9145b5F45Ad4519c7ACcD6E0A4A82e83bB8A6Dc",
}

# USDC contract addresses
USDC_ADDRESSES: dict[str, str] = {
    "arbitrum_sepolia": "0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d",
    "base_sepolia": "0xba50cd2a20f6da35d788639e581bca8d0b5d4d5f",
}

CHAIN_IDS: dict[str, int] = {
    "arbitrum_sepolia": 421614,
    "base_sepolia": 84532,
}

CHAIN_NAMES: dict[str, str] = {
    "arbitrum_sepolia": "Arbitrum Sepolia",
    "base_sepolia": "Base Sepolia",
}

EXPLORER_TX_URLS: dict[str, str] = {
    "arbitrum_sepolia": "https://sepolia.arbiscan.io/tx/",
    "base_sepolia": "https://sepolia.basescan.org/tx/",
}

# USDC has 6 decimals
USDC_DECIMALS = 6

_FAUCET_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "token", "type": "address"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "mint",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

_ERC20_ABI = [
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]


def mask_address(addr: str) -> str:
    """Mask address to first 6 + last 4 chars for safe logging."""
    if len(addr) < 10:
        return addr
    return f"{addr[:6]}...{addr[-4:]}"


def get_rpc_url(chain: str) -> str:
    """Resolve RPC URL from environment variables with fallback."""
    if chain == "arbitrum_sepolia":
        url = os.environ.get("ALCHEMY_RPC_URL_ARBITRUM_SEPOLIA", "")
        if not url:
            logger.error("Missing env var: ALCHEMY_RPC_URL_ARBITRUM_SEPOLIA")
            sys.exit(1)
        return url
    # base_sepolia
    url = os.environ.get("ALCHEMY_RPC_URL_BASE_SEPOLIA") or os.environ.get(
        "AAVE_RPC_URL_BASE_SEPOLIA", ""
    )
    if not url:
        logger.error("Missing env var: ALCHEMY_RPC_URL_BASE_SEPOLIA (or AAVE_RPC_URL_BASE_SEPOLIA)")
        sys.exit(1)
    return url


def get_usdc_balance(w3, usdc_address: str, wallet_address: str) -> Decimal:
    """Get USDC balance for a wallet."""
    from web3 import Web3

    token = w3.eth.contract(address=Web3.to_checksum_address(usdc_address), abi=_ERC20_ABI)
    balance_raw = token.functions.balanceOf(Web3.to_checksum_address(wallet_address)).call()
    return Decimal(balance_raw) / Decimal(10**USDC_DECIMALS)


def mint_usdc(
    chain: str,
    amount: Decimal,
    wallet_override: str | None,
    dry_run: bool,
) -> None:
    """Mint test USDC from Aave faucet on the specified chain."""
    try:
        from web3 import Web3
    except ImportError as exc:
        logger.error("Missing dependency: %s. Install: pip install web3", exc)
        sys.exit(1)

    # Resolve config
    rpc_url = get_rpc_url(chain)
    private_key = os.environ.get("AAVE_WALLET_PRIVATE_KEY", "")
    wallet_address = wallet_override or os.environ.get("AAVE_WALLET_ADDRESS", "")

    if not wallet_address:
        logger.error("Wallet address not set. Use --wallet or set AAVE_WALLET_ADDRESS env var.")
        sys.exit(1)
    if not private_key and not dry_run:
        logger.error("Missing env var: AAVE_WALLET_PRIVATE_KEY")
        sys.exit(1)

    chain_id = CHAIN_IDS[chain]
    chain_name = CHAIN_NAMES[chain]
    faucet_address = FAUCET_ADDRESSES[chain]
    usdc_address = USDC_ADDRESSES[chain]
    amount_raw = int(amount * Decimal(10**USDC_DECIMALS))

    logger.info("Chain    : %s (chain_id=%d)", chain_name, chain_id)
    logger.info("Wallet   : %s", mask_address(wallet_address))
    logger.info("Faucet   : %s", mask_address(faucet_address))
    logger.info("USDC     : %s", mask_address(usdc_address))
    logger.info("Amount   : %s USDC (%d raw units)", amount, amount_raw)
    logger.info("Dry-run  : %s", dry_run)

    # Connect to RPC
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    rpc_ok = w3.is_connected()
    if not rpc_ok:
        if dry_run:
            logger.warning("Cannot connect to %s RPC (dry-run: continuing anyway)", chain_name)
        else:
            logger.error("Cannot connect to %s RPC", chain_name)
            sys.exit(1)
    else:
        logger.info("RPC connected. Block: %d", w3.eth.block_number)

    checksum_wallet = Web3.to_checksum_address(wallet_address)

    # Balance before (skip if RPC unavailable)
    if rpc_ok:
        balance_before = get_usdc_balance(w3, usdc_address, checksum_wallet)
        logger.info("USDC balance before: %s", balance_before)
    else:
        balance_before = None

    if dry_run:
        logger.info(
            "[DRY-RUN] Would call faucet.mint(token=%s, to=%s, amount=%d)",
            mask_address(usdc_address),
            mask_address(checksum_wallet),
            amount_raw,
        )
        logger.info("[DRY-RUN] No transaction sent.")
        return

    # Build and send transaction
    faucet = w3.eth.contract(
        address=Web3.to_checksum_address(faucet_address),
        abi=_FAUCET_ABI,
    )

    nonce = w3.eth.get_transaction_count(checksum_wallet, "pending")
    tx = faucet.functions.mint(
        Web3.to_checksum_address(usdc_address),
        checksum_wallet,
        amount_raw,
    ).build_transaction(
        {
            "chainId": chain_id,
            "from": checksum_wallet,
            "nonce": nonce,
            "gas": 200_000,
            "gasPrice": w3.eth.gas_price,
        }
    )

    # 秘密鍵はログに出力しない
    signed_tx = w3.eth.account.sign_transaction(tx, private_key=private_key)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_hex = tx_hash.hex()
    logger.info("Transaction sent: 0x%s", tx_hex)
    logger.info("Track: %s0x%s", EXPLORER_TX_URLS[chain], tx_hex)

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    status = "SUCCESS" if receipt["status"] == 1 else "FAILED"
    logger.info("Faucet tx status: %s (block=%s)", status, receipt["blockNumber"])

    if receipt["status"] != 1:
        logger.error("Faucet transaction failed")
        sys.exit(1)

    # Balance after
    balance_after = get_usdc_balance(w3, usdc_address, checksum_wallet)
    if balance_before is not None:
        received = balance_after - balance_before
        logger.info("USDC balance after: %s (received: +%s)", balance_after, received)
    else:
        logger.info("USDC balance after: %s", balance_after)


def main() -> None:
    parser = argparse.ArgumentParser(description="Mint test USDC from Aave testnet faucet")
    parser.add_argument(
        "--chain",
        choices=["arbitrum_sepolia", "base_sepolia"],
        required=True,
        help="Target chain: arbitrum_sepolia or base_sepolia",
    )
    parser.add_argument(
        "--amount",
        type=str,
        default="5000",
        help="Amount of USDC to mint in human units (default: 5000)",
    )
    parser.add_argument(
        "--wallet",
        type=str,
        default=None,
        help="Wallet address to mint to (default: AAVE_WALLET_ADDRESS env var)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show params without sending any transaction",
    )
    args = parser.parse_args()

    amount = Decimal(args.amount)
    if amount <= 0:
        logger.error("Amount must be positive, got %s", amount)
        sys.exit(1)

    mint_usdc(
        chain=args.chain,
        amount=amount,
        wallet_override=args.wallet,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
