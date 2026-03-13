#!/usr/bin/env python3
"""
Get test tokens from Aave testnet faucet on Base Sepolia.

Requirements: web3>=6.0, python-dotenv, eth-account

Usage:
    python scripts/aave_faucet_base.py [--dry-run] [--asset usdc] [--amount 1000]
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

# Aave V3 Base Sepolia contract addresses
# Verify: https://docs.aave.com/developers/deployed-contracts/v3-testnet-addresses
AAVE_FAUCET_BASE_SEPOLIA = "0xD9145b5F45Ad4519c7ACcD6E0A4A82e83bB8A6Dc"

ASSET_ADDRESSES = {
    "usdc": "0xba50cd2a20f6da35d788639e581bca8d0b5d4d5f",
    "weth": "0x4200000000000000000000000000000000000006",
}

ASSET_DECIMALS = {
    "usdc": 6,
    "weth": 18,
}

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
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
]


def mask_address(addr: str) -> str:
    """Mask address to first 6 + last 4 chars for safe logging."""
    if len(addr) < 10:
        return addr
    return f"{addr[:6]}...{addr[-4:]}"


def get_token_balance(w3, token_address: str, wallet_address: str, decimals: int) -> Decimal:
    """Get ERC-20 token balance."""
    from web3 import Web3
    token = w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=_ERC20_ABI)
    balance_raw = token.functions.balanceOf(Web3.to_checksum_address(wallet_address)).call()
    return Decimal(balance_raw) / Decimal(10 ** decimals)


def faucet_mint(asset: str, amount: Decimal, dry_run: bool) -> None:
    """Mint test tokens from Aave faucet on Base Sepolia."""
    try:
        from web3 import Web3
        from eth_account import Account
    except ImportError as exc:
        logger.error("Missing dependency: %s. Install: pip install web3 eth-account", exc)
        sys.exit(1)

    asset = asset.lower()
    if asset not in ASSET_ADDRESSES:
        logger.error("Unknown asset '%s'. Supported: %s", asset, list(ASSET_ADDRESSES.keys()))
        sys.exit(1)

    rpc_url = os.environ.get("AAVE_RPC_URL_BASE_SEPOLIA", "")
    private_key = os.environ.get("AAVE_PRIVATE_KEY", "")
    wallet_address = os.environ.get("AAVE_WALLET_ADDRESS", "")

    for name, val in [
        ("AAVE_RPC_URL_BASE_SEPOLIA", rpc_url),
        ("AAVE_PRIVATE_KEY", private_key),
        ("AAVE_WALLET_ADDRESS", wallet_address),
    ]:
        if not val:
            logger.error("Missing env var: %s", name)
            sys.exit(1)

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        logger.error("Cannot connect to Base Sepolia RPC")
        sys.exit(1)

    account = Account.from_key(private_key)
    checksum_wallet = Web3.to_checksum_address(wallet_address)
    token_address = ASSET_ADDRESSES[asset]
    decimals = ASSET_DECIMALS[asset]
    amount_raw = int(amount * Decimal(10 ** decimals))

    logger.info("Wallet: %s", mask_address(checksum_wallet))
    logger.info("Asset: %s (%s)", asset.upper(), mask_address(token_address))
    logger.info("Amount: %s %s (%s raw units)", amount, asset.upper(), amount_raw)

    # Balance before
    balance_before = get_token_balance(w3, token_address, checksum_wallet, decimals)
    logger.info("%s balance before: %s", asset.upper(), balance_before)

    if dry_run:
        logger.info("[DRY RUN] Would call faucet.mint(token=%s, to=%s, amount=%s)", mask_address(token_address), mask_address(checksum_wallet), amount_raw)
        logger.info("[DRY RUN] No transaction sent.")
        return

    faucet = w3.eth.contract(
        address=Web3.to_checksum_address(AAVE_FAUCET_BASE_SEPOLIA),
        abi=_FAUCET_ABI,
    )

    tx = faucet.functions.mint(
        Web3.to_checksum_address(token_address),
        checksum_wallet,
        amount_raw,
    ).build_transaction({
        "from": checksum_wallet,
        "nonce": w3.eth.get_transaction_count(checksum_wallet),
        "gas": 200000,
        "gasPrice": w3.eth.gas_price,
    })

    signed_tx = w3.eth.account.sign_transaction(tx, private_key=account.key)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    logger.info("Transaction sent: 0x%s", tx_hash.hex())
    logger.info("Track: https://sepolia.basescan.org/tx/0x%s", tx_hash.hex())

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    status = "SUCCESS" if receipt["status"] == 1 else "FAILED"
    logger.info("Faucet tx status: %s (block=%s)", status, receipt["blockNumber"])

    if receipt["status"] != 1:
        logger.error("Faucet transaction failed")
        sys.exit(1)

    # Balance after
    balance_after = get_token_balance(w3, token_address, checksum_wallet, decimals)
    logger.info("%s balance after: %s (received: +%s)", asset.upper(), balance_after, balance_after - balance_before)


def main() -> None:
    parser = argparse.ArgumentParser(description="Get test tokens from Aave faucet on Base Sepolia")
    parser.add_argument("--dry-run", action="store_true", help="Show params without sending")
    parser.add_argument("--asset", type=str, default="usdc", help="Asset to mint: usdc or weth (default: usdc)")
    parser.add_argument("--amount", type=str, default="1000", help="Amount to mint in human units (default: 1000)")
    args = parser.parse_args()

    amount = Decimal(args.amount)
    if amount <= 0:
        logger.error("Amount must be positive, got %s", amount)
        sys.exit(1)

    faucet_mint(asset=args.asset, amount=amount, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
