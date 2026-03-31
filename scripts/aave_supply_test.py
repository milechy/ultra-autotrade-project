#!/usr/bin/env python3
"""
Supply USDC to Aave V3 Pool on Base Sepolia and check health factor.

Requirements: web3>=6.0, python-dotenv, eth-account

Usage:
    python scripts/aave_supply_test.py [--dry-run] [--amount 100] [--asset usdc]
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
AAVE_POOL_BASE_SEPOLIA = "0x8bAB6d1b75f19e9eD9fCe8b9BD338844fF79aE27"

ASSET_ADDRESSES = {
    "usdc": "0xba50cd2a20f6da35d788639e581bca8d0b5d4d5f",
    "weth": "0x4200000000000000000000000000000000000006",
}

_POOL_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "asset", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
            {"internalType": "address", "name": "onBehalfOf", "type": "address"},
            {"internalType": "uint16", "name": "referralCode", "type": "uint16"},
        ],
        "name": "supply",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "asset", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
            {"internalType": "address", "name": "to", "type": "address"},
        ],
        "name": "withdraw",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "user", "type": "address"}],
        "name": "getUserAccountData",
        "outputs": [
            {"internalType": "uint256", "name": "totalCollateralBase", "type": "uint256"},
            {"internalType": "uint256", "name": "totalDebtBase", "type": "uint256"},
            {"internalType": "uint256", "name": "availableBorrowsBase", "type": "uint256"},
            {"internalType": "uint256", "name": "currentLiquidationThreshold", "type": "uint256"},
            {"internalType": "uint256", "name": "ltv", "type": "uint256"},
            {"internalType": "uint256", "name": "healthFactor", "type": "uint256"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]

_ERC20_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "spender", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
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


def get_health_factor(pool, wallet_address: str) -> Decimal:
    """Get health factor from Aave Pool.getUserAccountData()."""
    from web3 import Web3
    result = pool.functions.getUserAccountData(Web3.to_checksum_address(wallet_address)).call()
    hf_raw: int = result[5]
    total_debt: int = result[1]
    if hf_raw >= 2**256 - 1 or (hf_raw == 0 and total_debt == 0):
        return Decimal("inf")
    return Decimal(hf_raw) / Decimal(10**18)


def get_token_balance(w3, token_address: str, wallet_address: str) -> tuple[Decimal, int]:
    """Return (balance in human units, decimals)."""
    from web3 import Web3
    token = w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=_ERC20_ABI)
    decimals = token.functions.decimals().call()
    balance_raw = token.functions.balanceOf(Web3.to_checksum_address(wallet_address)).call()
    return Decimal(balance_raw) / Decimal(10 ** decimals), decimals


def aave_supply(asset: str, amount: Decimal, dry_run: bool) -> dict:
    """Supply tokens to Aave V3 Pool on Base Sepolia. Returns result dict."""
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

    pool = w3.eth.contract(
        address=Web3.to_checksum_address(AAVE_POOL_BASE_SEPOLIA),
        abi=_POOL_ABI,
    )
    token = w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=_ERC20_ABI)

    logger.info("Wallet: %s", mask_address(checksum_wallet))
    logger.info("Pool: %s", mask_address(AAVE_POOL_BASE_SEPOLIA))
    logger.info("Asset: %s (%s)", asset.upper(), mask_address(token_address))

    # Before state
    balance_before, decimals = get_token_balance(w3, token_address, checksum_wallet)
    hf_before = get_health_factor(pool, checksum_wallet)
    logger.info("%s balance before: %s", asset.upper(), balance_before)
    logger.info("Health factor before: %s", hf_before)

    amount_raw = int(amount * Decimal(10 ** decimals))
    logger.info("Supplying %s %s (%s raw)", amount, asset.upper(), amount_raw)

    if dry_run:
        logger.info("[DRY RUN] Would approve %s raw to pool, then call supply()", amount_raw)
        logger.info("[DRY RUN] No transaction sent.")
        return {"dry_run": True, "hf_before": str(hf_before)}

    # Fetch nonce once; increment manually to avoid RPC lag between transactions
    nonce = w3.eth.get_transaction_count(checksum_wallet)

    # Step 1: Approve
    approve_tx = token.functions.approve(
        Web3.to_checksum_address(AAVE_POOL_BASE_SEPOLIA),
        amount_raw,
    ).build_transaction({
        "from": checksum_wallet,
        "nonce": nonce,
        "gas": 100000,
        "gasPrice": w3.eth.gas_price,
    })
    signed_approve = w3.eth.account.sign_transaction(approve_tx, private_key=account.key)
    approve_hash = w3.eth.send_raw_transaction(signed_approve.raw_transaction)
    logger.info("Approve tx sent: 0x%s", approve_hash.hex())
    w3.eth.wait_for_transaction_receipt(approve_hash, timeout=120)
    logger.info("Approve confirmed")

    # Step 2: Supply
    supply_tx = pool.functions.supply(
        Web3.to_checksum_address(token_address),
        amount_raw,
        checksum_wallet,
        0,  # referralCode
    ).build_transaction({
        "from": checksum_wallet,
        "nonce": nonce + 1,
        "gas": 300000,
        "gasPrice": w3.eth.gas_price,
    })
    signed_supply = w3.eth.account.sign_transaction(supply_tx, private_key=account.key)
    supply_hash = w3.eth.send_raw_transaction(signed_supply.raw_transaction)
    logger.info("Supply tx sent: 0x%s", supply_hash.hex())
    logger.info("Track: https://sepolia.basescan.org/tx/0x%s", supply_hash.hex())

    receipt = w3.eth.wait_for_transaction_receipt(supply_hash, timeout=120)
    status = "SUCCESS" if receipt["status"] == 1 else "FAILED"
    logger.info("Supply tx status: %s (block=%s)", status, receipt["blockNumber"])

    if receipt["status"] != 1:
        logger.error("Supply transaction failed")
        sys.exit(1)

    # After state
    balance_after, _ = get_token_balance(w3, token_address, checksum_wallet)
    hf_after = get_health_factor(pool, checksum_wallet)
    logger.info("%s balance after: %s (change: %s)", asset.upper(), balance_after, balance_after - balance_before)
    logger.info("Health factor after: %s", hf_after)

    return {
        "dry_run": False,
        "supply_tx": supply_hash.hex(),
        "hf_before": str(hf_before),
        "hf_after": str(hf_after),
        "balance_before": str(balance_before),
        "balance_after": str(balance_after),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Supply tokens to Aave V3 on Base Sepolia")
    parser.add_argument("--dry-run", action="store_true", help="Show params without sending")
    parser.add_argument("--amount", type=str, default="100", help="Amount to supply in human units (default: 100)")
    parser.add_argument("--asset", type=str, default="usdc", help="Asset to supply: usdc or weth (default: usdc)")
    args = parser.parse_args()

    amount = Decimal(args.amount)
    if amount <= 0:
        logger.error("Amount must be positive, got %s", amount)
        sys.exit(1)

    result = aave_supply(asset=args.asset, amount=amount, dry_run=args.dry_run)
    logger.info("Result: %s", result)


if __name__ == "__main__":
    main()
