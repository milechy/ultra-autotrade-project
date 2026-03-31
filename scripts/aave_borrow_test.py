#!/usr/bin/env python3
"""
Borrow USDC from Aave V3 Pool on Base Sepolia and verify balances / health factor.

Requirements: web3>=6.0, python-dotenv, eth-account

Usage:
    python scripts/aave_borrow_test.py [--dry-run] [--amount 10] [--asset usdc]

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

# Variable rate mode for Aave V3
INTEREST_RATE_MODE_VARIABLE = 2

# getUserAccountData returns USD amounts in base units (8 decimals)
USD_BASE_DECIMALS = 8

_POOL_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "asset", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
            {"internalType": "uint256", "name": "interestRateMode", "type": "uint256"},
            {"internalType": "uint16", "name": "referralCode", "type": "uint16"},
            {"internalType": "address", "name": "onBehalfOf", "type": "address"},
        ],
        "name": "borrow",
        "outputs": [],
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
    {
        "inputs": [{"internalType": "address", "name": "asset", "type": "address"}],
        "name": "getReserveData",
        "outputs": [
            {
                "components": [
                    {"internalType": "uint256", "name": "configuration", "type": "uint256"},
                    {"internalType": "uint128", "name": "liquidityIndex", "type": "uint128"},
                    {"internalType": "uint128", "name": "currentLiquidityRate", "type": "uint128"},
                    {"internalType": "uint128", "name": "variableBorrowIndex", "type": "uint128"},
                    {"internalType": "uint128", "name": "currentVariableBorrowRate", "type": "uint128"},
                    {"internalType": "uint128", "name": "currentStableBorrowRate", "type": "uint128"},
                    {"internalType": "uint40", "name": "lastUpdateTimestamp", "type": "uint40"},
                    {"internalType": "uint16", "name": "id", "type": "uint16"},
                    {"internalType": "address", "name": "aTokenAddress", "type": "address"},
                    {"internalType": "address", "name": "stableDebtTokenAddress", "type": "address"},
                    {"internalType": "address", "name": "variableDebtTokenAddress", "type": "address"},
                    {"internalType": "address", "name": "interestRateStrategyAddress", "type": "address"},
                    {"internalType": "uint128", "name": "accruedToTreasury", "type": "uint128"},
                    {"internalType": "uint128", "name": "unbacked", "type": "uint128"},
                    {"internalType": "uint128", "name": "isolationModeTotalDebt", "type": "uint128"},
                ],
                "internalType": "struct DataTypes.ReserveData",
                "name": "",
                "type": "tuple",
            }
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


def get_available_borrows_usd(pool, wallet_address: str) -> Decimal:
    """Return availableBorrowsBase in USD (human units, 8 decimals → Decimal)."""
    from web3 import Web3
    result = pool.functions.getUserAccountData(Web3.to_checksum_address(wallet_address)).call()
    available_raw: int = result[2]
    return Decimal(available_raw) / Decimal(10**USD_BASE_DECIMALS)


def get_token_balance(w3, token_address: str, wallet_address: str) -> tuple[Decimal, int]:
    """Return (balance in human units, decimals)."""
    from web3 import Web3
    token = w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=_ERC20_ABI)
    decimals = token.functions.decimals().call()
    balance_raw = token.functions.balanceOf(Web3.to_checksum_address(wallet_address)).call()
    return Decimal(balance_raw) / Decimal(10 ** decimals), decimals


def get_variable_debt_token_address(pool, asset_address: str) -> str:
    """Fetch variableDebtTokenAddress for the given asset from Pool.getReserveData()."""
    from web3 import Web3
    reserve_data = pool.functions.getReserveData(
        Web3.to_checksum_address(asset_address)
    ).call()
    # variableDebtTokenAddress is at index 10 in the ReserveData tuple
    return reserve_data[10]


def aave_borrow(asset: str, amount: Decimal, dry_run: bool) -> dict:
    """Borrow tokens from Aave V3 Pool on Base Sepolia. Returns result dict."""
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

    # --- 前提条件チェック: aUSDC 残高（担保）---
    a_usdc_before, _ = get_token_balance(w3, a_usdc_address, checksum_wallet)
    logger.info("aUSDC balance (collateral): %s", a_usdc_before)

    if a_usdc_before <= Decimal("0"):
        logger.error(
            "aUSDC 残高が 0 です。先に aave_supply_test.py で USDC を Supply してください。"
        )
        sys.exit(1)

    # --- 前提条件チェック: 借入可能残高 ---
    available_borrows_usd = get_available_borrows_usd(pool, checksum_wallet)
    logger.info("Available borrows (USD):    %s", available_borrows_usd)

    if available_borrows_usd <= Decimal("0"):
        logger.error(
            "借入可能残高が 0 USD です。担保が不足しているか、既に上限まで借入済みです。"
        )
        sys.exit(1)

    # USDC ≈ 1 USD なので amount ≈ amount USD。安全マージン 90% で上限チェック
    safe_limit = available_borrows_usd * Decimal("0.9")
    if amount > safe_limit:
        logger.error(
            "Borrow 量 (%s) が安全上限 (%s USDC, available %s USD の90%%) を超えています。",
            amount,
            safe_limit,
            available_borrows_usd,
        )
        sys.exit(1)

    # --- Before state ---
    usdc_before, usdc_decimals = get_token_balance(w3, token_address, checksum_wallet)
    hf_before = get_health_factor(pool, checksum_wallet)
    logger.info("%s balance before:  %s", asset.upper(), usdc_before)
    logger.info("Health factor before: %s", hf_before)

    # variableDebtToken アドレスを Pool から動的取得
    variable_debt_token_address = get_variable_debt_token_address(pool, token_address)
    logger.info("variableDebtToken: %s", mask_address(variable_debt_token_address))
    debt_before, _ = get_token_balance(w3, variable_debt_token_address, checksum_wallet)
    logger.info("Variable debt before: %s", debt_before)

    amount_raw = int(amount * Decimal(10**usdc_decimals))
    logger.info(
        "Borrowing %s %s (%s raw) at variable rate",
        amount,
        asset.upper(),
        amount_raw,
    )

    if dry_run:
        logger.info(
            "[DRY RUN] Would call Pool.borrow(asset, %s, interestRateMode=2, referralCode=0, wallet)",
            amount_raw,
        )
        logger.info("[DRY RUN] No transaction sent.")
        return {
            "dry_run": True,
            "hf_before": str(hf_before),
            "a_usdc_before": str(a_usdc_before),
            "usdc_before": str(usdc_before),
            "debt_before": str(debt_before),
            "available_borrows_usd": str(available_borrows_usd),
        }

    # Fetch nonce（borrow は1トランザクションのみ — increment 不要）
    nonce = w3.eth.get_transaction_count(checksum_wallet)

    # Pool.borrow(asset, amount, interestRateMode, referralCode, onBehalfOf) — Approve 不要
    borrow_tx = pool.functions.borrow(
        Web3.to_checksum_address(token_address),
        amount_raw,
        INTEREST_RATE_MODE_VARIABLE,
        0,  # referralCode
        checksum_wallet,
    ).build_transaction({
        "from": checksum_wallet,
        "nonce": nonce,
        "gas": 400000,
        "gasPrice": w3.eth.gas_price,
    })
    signed_borrow = w3.eth.account.sign_transaction(borrow_tx, private_key=account.key)
    borrow_hash = w3.eth.send_raw_transaction(signed_borrow.raw_transaction)
    logger.info("Borrow tx sent: 0x%s", borrow_hash.hex())
    logger.info("Track: https://sepolia.basescan.org/tx/0x%s", borrow_hash.hex())

    receipt = w3.eth.wait_for_transaction_receipt(borrow_hash, timeout=120)
    status = "SUCCESS" if receipt["status"] == 1 else "FAILED"
    logger.info("Borrow tx status: %s (block=%s)", status, receipt["blockNumber"])

    if receipt["status"] != 1:
        logger.error("Borrow transaction failed")
        sys.exit(1)

    # --- After state ---
    usdc_after, _ = get_token_balance(w3, token_address, checksum_wallet)
    debt_after, _ = get_token_balance(w3, variable_debt_token_address, checksum_wallet)
    hf_after = get_health_factor(pool, checksum_wallet)

    logger.info("%s balance after:   %s (change: %s)", asset.upper(), usdc_after, usdc_after - usdc_before)
    logger.info("Variable debt after:  %s (change: %s)", debt_after, debt_after - debt_before)
    logger.info("Health factor after:  %s", hf_after)

    # 検証: USDC が増え、variable debt が増え、HF が有限値になること
    if usdc_after <= usdc_before:
        logger.warning(
            "WARN: USDC balance did not increase after borrow (before=%s, after=%s)",
            usdc_before,
            usdc_after,
        )
    if debt_after <= debt_before:
        logger.warning(
            "WARN: Variable debt did not increase after borrow (before=%s, after=%s)",
            debt_before,
            debt_after,
        )
    if hf_after == Decimal("inf"):
        logger.warning("WARN: Health factor is still inf — borrow may not have registered")
    elif hf_after < Decimal("1.6"):
        logger.warning(
            "WARN: Health factor %s is below safety threshold 1.6 — HARD STOP in live system",
            hf_after,
        )
    else:
        logger.info("Health factor %s is above safety threshold 1.6 — OK", hf_after)

    return {
        "dry_run": False,
        "borrow_tx": borrow_hash.hex(),
        "hf_before": str(hf_before),
        "hf_after": str(hf_after),
        "usdc_before": str(usdc_before),
        "usdc_after": str(usdc_after),
        "debt_before": str(debt_before),
        "debt_after": str(debt_after),
        "available_borrows_usd": str(available_borrows_usd),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Borrow tokens from Aave V3 on Base Sepolia")
    parser.add_argument("--dry-run", action="store_true", help="Show params without sending tx")
    parser.add_argument(
        "--amount",
        type=str,
        default="10",
        help="Amount to borrow in human units (default: 10)",
    )
    parser.add_argument(
        "--asset",
        type=str,
        default="usdc",
        help="Asset to borrow: usdc or weth (default: usdc)",
    )
    args = parser.parse_args()

    amount = Decimal(args.amount)
    if amount <= Decimal("0"):
        logger.error("Amount must be positive, got %s", amount)
        sys.exit(1)

    result = aave_borrow(asset=args.asset, amount=amount, dry_run=args.dry_run)
    logger.info("Result: %s", result)


if __name__ == "__main__":
    main()
