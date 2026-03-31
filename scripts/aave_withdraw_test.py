#!/usr/bin/env python3
"""
Withdraw USDC from Aave V3 Pool on Base Sepolia and verify balances.

Requirements: web3>=6.0, python-dotenv, eth-account

Usage:
    python scripts/aave_withdraw_test.py [--dry-run] [--amount 50] [--asset usdc]

前提条件:
    - .env.staging に AAVE_RPC_URL_BASE_SEPOLIA / AAVE_PRIVATE_KEY /
      AAVE_WALLET_ADDRESS / AAVE_A_USDC_ADDRESS が設定済みであること
    - Aave V3 Base Sepolia に USDC を Supply 済みで aUSDC 残高があること
    - ガス代用の Base Sepolia ETH があること
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


def aave_withdraw(asset: str, amount: Decimal, dry_run: bool) -> dict:
    """Withdraw tokens from Aave V3 Pool on Base Sepolia. Returns result dict."""
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
    a_usdc_address = os.environ.get("AAVE_A_USDC_ADDRESS", "")

    for name, val in [
        ("AAVE_RPC_URL_BASE_SEPOLIA", rpc_url),
        ("AAVE_PRIVATE_KEY", private_key),
        ("AAVE_WALLET_ADDRESS", wallet_address),
        ("AAVE_A_USDC_ADDRESS", a_usdc_address),
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

    logger.info("Wallet:    %s", mask_address(checksum_wallet))
    logger.info("Pool:      %s", mask_address(AAVE_POOL_BASE_SEPOLIA))
    logger.info("Asset:     %s (%s)", asset.upper(), mask_address(token_address))
    logger.info("aUSDC:     %s", mask_address(a_usdc_address))

    # --- 前提条件チェック: aUSDC 残高 ---
    a_usdc_before, a_usdc_decimals = get_token_balance(w3, a_usdc_address, checksum_wallet)
    logger.info("aUSDC balance before: %s", a_usdc_before)

    if a_usdc_before <= Decimal("0"):
        logger.error(
            "aUSDC 残高が 0 です。先に aave_supply_test.py で USDC を Supply してください。"
        )
        sys.exit(1)

    if amount > a_usdc_before:
        logger.error(
            "Withdraw 量 (%s) が aUSDC 残高 (%s) を超えています。", amount, a_usdc_before
        )
        sys.exit(1)

    # Before state
    usdc_before, usdc_decimals = get_token_balance(w3, token_address, checksum_wallet)
    hf_before = get_health_factor(pool, checksum_wallet)
    logger.info("%s balance before:  %s", asset.upper(), usdc_before)
    logger.info("Health factor before: %s", hf_before)

    amount_raw = int(amount * Decimal(10 ** usdc_decimals))
    logger.info("Withdrawing %s %s (%s raw)", amount, asset.upper(), amount_raw)

    if dry_run:
        logger.info("[DRY RUN] Would call Pool.withdraw(asset, %s, wallet)", amount_raw)
        logger.info("[DRY RUN] No transaction sent.")
        return {
            "dry_run": True,
            "hf_before": str(hf_before),
            "a_usdc_before": str(a_usdc_before),
            "usdc_before": str(usdc_before),
        }

    # Fetch nonce (withdraw は1トランザクションのみなので increment 不要)
    nonce = w3.eth.get_transaction_count(checksum_wallet)

    # Pool.withdraw(asset, amount, to) — Approve 不要
    withdraw_tx = pool.functions.withdraw(
        Web3.to_checksum_address(token_address),
        amount_raw,
        checksum_wallet,
    ).build_transaction({
        "from": checksum_wallet,
        "nonce": nonce,
        "gas": 300000,
        "gasPrice": w3.eth.gas_price,
    })
    signed_withdraw = w3.eth.account.sign_transaction(withdraw_tx, private_key=account.key)
    withdraw_hash = w3.eth.send_raw_transaction(signed_withdraw.raw_transaction)
    logger.info("Withdraw tx sent: 0x%s", withdraw_hash.hex())
    logger.info("Track: https://sepolia.basescan.org/tx/0x%s", withdraw_hash.hex())

    receipt = w3.eth.wait_for_transaction_receipt(withdraw_hash, timeout=120)
    status = "SUCCESS" if receipt["status"] == 1 else "FAILED"
    logger.info("Withdraw tx status: %s (block=%s)", status, receipt["blockNumber"])

    if receipt["status"] != 1:
        logger.error("Withdraw transaction failed")
        sys.exit(1)

    # After state
    usdc_after, _ = get_token_balance(w3, token_address, checksum_wallet)
    a_usdc_after, _ = get_token_balance(w3, a_usdc_address, checksum_wallet)
    hf_after = get_health_factor(pool, checksum_wallet)

    logger.info("%s balance after:   %s (change: %s)", asset.upper(), usdc_after, usdc_after - usdc_before)
    logger.info("aUSDC balance after:  %s (change: %s)", a_usdc_after, a_usdc_after - a_usdc_before)
    logger.info("Health factor after:  %s", hf_after)

    # 検証: USDC が増え、aUSDC が減っていることを確認
    if usdc_after <= usdc_before:
        logger.warning("WARN: USDC balance did not increase after withdraw (before=%s, after=%s)", usdc_before, usdc_after)
    if a_usdc_after >= a_usdc_before:
        logger.warning("WARN: aUSDC balance did not decrease after withdraw (before=%s, after=%s)", a_usdc_before, a_usdc_after)

    return {
        "dry_run": False,
        "withdraw_tx": withdraw_hash.hex(),
        "hf_before": str(hf_before),
        "hf_after": str(hf_after),
        "usdc_before": str(usdc_before),
        "usdc_after": str(usdc_after),
        "a_usdc_before": str(a_usdc_before),
        "a_usdc_after": str(a_usdc_after),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Withdraw tokens from Aave V3 on Base Sepolia")
    parser.add_argument("--dry-run", action="store_true", help="Show params without sending tx")
    parser.add_argument("--amount", type=str, default="50", help="Amount to withdraw in human units (default: 50)")
    parser.add_argument("--asset", type=str, default="usdc", help="Asset to withdraw: usdc or weth (default: usdc)")
    args = parser.parse_args()

    amount = Decimal(args.amount)
    if amount <= Decimal("0"):
        logger.error("Amount must be positive, got %s", amount)
        sys.exit(1)

    result = aave_withdraw(asset=args.asset, amount=amount, dry_run=args.dry_run)
    logger.info("Result: %s", result)


if __name__ == "__main__":
    main()
