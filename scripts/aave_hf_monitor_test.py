#!/usr/bin/env python3
"""
HF 閾値テスト: 段階的 Borrow で SAFE_MODE / HARD_STOP トリガーを確認する。

Requirements: web3>=6.0, python-dotenv, eth-account

Usage:
    python scripts/aave_hf_monitor_test.py [--dry-run]
                                            [--step1-amount 15]
                                            [--step2-amount 5]
                                            [--asset usdc]

前提条件:
    - .env.staging に AAVE_RPC_URL_BASE_SEPOLIA / AAVE_PRIVATE_KEY /
      AAVE_WALLET_ADDRESS / AAVE_A_USDC_ADDRESS が設定済みであること
    - Aave V3 Base Sepolia に USDC を Supply 済みで aUSDC 残高があること
    - Borrow 済みで HF が有限値であること（aave_borrow_test.py を先に実行）
    - Repay 用の USDC 残高が十分あること（総 debt 分）
    - ガス代用の Base Sepolia ETH があること

テストフロー:
    Step 0: 現在の HF を取得・モード判定
    Step 1: 追加 Borrow で HF を 2.0 付近に → SAFE_MODE 閾値接近を確認
    Step 2: 追加 Borrow で HF を 1.65 付近に → HARD_STOP 閾値接近を確認
    Cleanup: Repay で全 debt を返済して HF を安全な値に戻す

閾値 (backend/app/aave/config.py と同じデフォルト値):
    SAFE_MODE  : HF < 1.8
    HARD_STOP  : HF < 1.6
    SAFETY_FLOOR: HF 1.55 未満には絶対に下げない
"""

import argparse
import logging
import os
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

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

# HF 閾値 (backend/app/aave/config.py の AAVE_MIN_HEALTH_FACTOR / AAVE_WARN_HEALTH_FACTOR と同じ)
HF_SAFE_MODE_THRESHOLD = Decimal("1.8")  # HF < 1.8 → SAFE_MODE (BUY blocked)
HF_HARD_STOP_THRESHOLD = Decimal("1.6")  # HF < 1.6 → HARD_STOP (all blocked)
HF_SAFETY_FLOOR = Decimal("1.55")  # 絶対安全フロア — これを下回る Borrow は拒否

# Variable rate mode
INTEREST_RATE_MODE_VARIABLE = 2

# getUserAccountData の USD 単位 (8 decimals)
USD_BASE_DECIMALS = 8

# Pool.repay の「全額返済」sentinel 値 (uint256 max)
REPAY_ALL = 2**256 - 1

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
        "inputs": [
            {"internalType": "address", "name": "asset", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
            {"internalType": "uint256", "name": "interestRateMode", "type": "uint256"},
            {"internalType": "address", "name": "onBehalfOf", "type": "address"},
        ],
        "name": "repay",
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
                    {
                        "internalType": "uint128",
                        "name": "currentVariableBorrowRate",
                        "type": "uint128",
                    },  # noqa: E501
                    {
                        "internalType": "uint128",
                        "name": "currentStableBorrowRate",
                        "type": "uint128",
                    },  # noqa: E501
                    {"internalType": "uint40", "name": "lastUpdateTimestamp", "type": "uint40"},
                    {"internalType": "uint16", "name": "id", "type": "uint16"},
                    {"internalType": "address", "name": "aTokenAddress", "type": "address"},
                    {
                        "internalType": "address",
                        "name": "stableDebtTokenAddress",
                        "type": "address",
                    },  # noqa: E501
                    {
                        "internalType": "address",
                        "name": "variableDebtTokenAddress",
                        "type": "address",
                    },  # noqa: E501
                    {
                        "internalType": "address",
                        "name": "interestRateStrategyAddress",
                        "type": "address",
                    },  # noqa: E501
                    {"internalType": "uint128", "name": "accruedToTreasury", "type": "uint128"},
                    {"internalType": "uint128", "name": "unbacked", "type": "uint128"},
                    {
                        "internalType": "uint128",
                        "name": "isolationModeTotalDebt",
                        "type": "uint128",
                    },  # noqa: E501
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


# ---------------------------------------------------------------------------
# ヘルパー関数
# ---------------------------------------------------------------------------


def mask_address(addr: str) -> str:
    """Mask address to first 6 + last 4 chars for safe logging."""
    if len(addr) < 10:
        return addr
    return f"{addr[:6]}...{addr[-4:]}"


def get_token_balance(w3: Any, token_address: str, wallet_address: str) -> tuple[Decimal, int]:
    """Return (balance in human units, decimals)."""
    from web3 import Web3

    token = w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=_ERC20_ABI)
    decimals = token.functions.decimals().call()
    balance_raw = token.functions.balanceOf(Web3.to_checksum_address(wallet_address)).call()
    return Decimal(balance_raw) / Decimal(10**decimals), decimals


def get_account_data(pool: Any, wallet_address: str) -> dict[str, Any]:
    """
    getUserAccountData の結果を dict で返す。

    Returns:
        {
            "total_collateral_usd": Decimal,  # USD (8 decimals → human)
            "total_debt_usd": Decimal,
            "available_borrows_usd": Decimal,
            "liquidation_threshold_bps": int,  # basis points (e.g. 7800 = 78%)
            "health_factor": Decimal,           # inf if no debt
        }
    """
    from web3 import Web3

    result = pool.functions.getUserAccountData(Web3.to_checksum_address(wallet_address)).call()

    total_collateral_base: int = result[0]
    total_debt_base: int = result[1]
    available_borrows_base: int = result[2]
    liquidation_threshold: int = result[3]
    hf_raw: int = result[5]

    if hf_raw >= 2**256 - 1 or (hf_raw == 0 and total_debt_base == 0):
        hf = Decimal("inf")
    else:
        hf = Decimal(hf_raw) / Decimal(10**18)

    return {
        "total_collateral_usd": Decimal(total_collateral_base) / Decimal(10**USD_BASE_DECIMALS),
        "total_debt_usd": Decimal(total_debt_base) / Decimal(10**USD_BASE_DECIMALS),
        "available_borrows_usd": Decimal(available_borrows_base) / Decimal(10**USD_BASE_DECIMALS),
        "liquidation_threshold_bps": liquidation_threshold,
        "health_factor": hf,
        # raw values for HF projection math
        "_total_collateral_base": total_collateral_base,
        "_liquidation_threshold": liquidation_threshold,
        "_total_debt_base": total_debt_base,
    }


def evaluate_mode(hf: Decimal) -> str:
    """
    HF から動作モードを判定する。

    backend/app/aave/config.py の AAVE_WARN_HEALTH_FACTOR / AAVE_MIN_HEALTH_FACTOR
    デフォルト値と同じ閾値を使用。
    """
    if hf == Decimal("inf"):
        return "NORMAL (no debt)"
    if hf < HF_HARD_STOP_THRESHOLD:
        return "HARD_STOP"
    if hf < HF_SAFE_MODE_THRESHOLD:
        return "SAFE_MODE"
    return "NORMAL"


def log_hf_status(hf: Decimal, label: str) -> None:
    """HF と推定モードをログ出力する。"""
    mode = evaluate_mode(hf)
    hf_str = str(hf) if hf != Decimal("inf") else "∞"
    if mode == "HARD_STOP":
        logger.warning(
            "[%s] HF=%s → MODE=HARD_STOP (< %.1f) — 全操作ブロック",
            label,
            hf_str,
            HF_HARD_STOP_THRESHOLD,
        )
    elif mode == "SAFE_MODE":
        logger.warning(
            "[%s] HF=%s → MODE=SAFE_MODE (< %.1f) — BUY ブロック、SELL のみ許可",
            label,
            hf_str,
            HF_SAFE_MODE_THRESHOLD,
        )
    else:
        logger.info("[%s] HF=%s → MODE=%s", label, hf_str, mode)


def compute_safe_borrow_amount(
    account_data: dict[str, Any],
    requested_amount: Decimal,
    safety_floor: Decimal = HF_SAFETY_FLOOR,
) -> Decimal:
    """
    リクエスト量が safety_floor を下回らないようにキャップして返す。

    HF = (totalCollateralBase × liquidationThreshold / 10000) / totalDebtBase
    target_debt = effective_collateral / safety_floor
    max_additional_borrow = target_debt - current_debt

    USDC ≈ $1 なので amount_usd ≈ amount_usdc と近似している。
    """
    total_collateral_base: int = account_data["_total_collateral_base"]
    lt_bps: int = account_data["_liquidation_threshold"]
    total_debt_base: int = account_data["_total_debt_base"]

    if total_collateral_base == 0 or lt_bps == 0:
        logger.warning("担保なし — Borrow 不可")
        return Decimal("0")

    # effective collateral (USD base units)
    effective_collateral = Decimal(total_collateral_base) * Decimal(lt_bps) / Decimal(10000)

    # safety_floor に対応する最大 debt
    max_debt_at_floor = effective_collateral / safety_floor

    # 現在 debt から追加可能な最大量
    current_debt = Decimal(total_debt_base)
    max_additional_base = max_debt_at_floor - current_debt

    if max_additional_base <= Decimal("0"):
        logger.warning(
            "現在の HF=%s は既に safety_floor=%.2f に近いか下回っています — Borrow 不可",
            account_data["health_factor"],
            safety_floor,
        )
        return Decimal("0")

    # USD base → human (8 decimals)
    max_additional_usd = max_additional_base / Decimal(10**USD_BASE_DECIMALS)

    if requested_amount > max_additional_usd:
        logger.warning(
            "Borrow 量 %s USDC が安全上限 %s USDC (floor=%.2f) を超えるため、上限にキャップします",
            requested_amount,
            max_additional_usd.quantize(Decimal("0.001")),
            safety_floor,
        )
        return max_additional_usd
    return requested_amount


def get_variable_debt_token_address(pool: Any, asset_address: str) -> str:
    """Pool.getReserveData() から variableDebtTokenAddress を取得する (index 10)。"""
    from web3 import Web3

    reserve_data = pool.functions.getReserveData(Web3.to_checksum_address(asset_address)).call()
    return str(reserve_data[10])


def send_borrow_tx(
    pool: Any,
    w3: Any,
    account: Any,
    token_address: str,
    amount: Decimal,
    decimals: int,
    checksum_wallet: str,
    private_key: bytes,
) -> str:
    """Pool.borrow() を送信してレシートを確認し、tx_hash を返す。"""
    from web3 import Web3

    amount_raw = int(amount * Decimal(10**decimals))
    nonce = w3.eth.get_transaction_count(checksum_wallet, "pending")
    borrow_tx = pool.functions.borrow(
        Web3.to_checksum_address(token_address),
        amount_raw,
        INTEREST_RATE_MODE_VARIABLE,
        0,
        checksum_wallet,
    ).build_transaction(
        {
            "from": checksum_wallet,
            "nonce": nonce,
            "gas": 400000,
            "gasPrice": w3.eth.gas_price,
        }
    )
    signed = w3.eth.account.sign_transaction(borrow_tx, private_key=private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    logger.info("Borrow tx sent: 0x%s", tx_hash.hex())
    logger.info("Track: https://sepolia.basescan.org/tx/0x%s", tx_hash.hex())
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    status = "SUCCESS" if receipt["status"] == 1 else "FAILED"
    logger.info("Borrow tx status: %s (block=%s)", status, receipt["blockNumber"])
    if receipt["status"] != 1:
        logger.error("Borrow transaction failed")
        sys.exit(1)
    logger.info("RPC 反映待機 (3s)...")
    time.sleep(3)
    return str(tx_hash.hex())


def send_repay_all_tx(
    pool: Any,
    token: Any,
    w3: Any,
    account: Any,
    token_address: str,
    decimals: int,
    total_debt_usd: Decimal,
    checksum_wallet: str,
    private_key: bytes,
) -> str:
    """
    全 variable debt を返済する。

    1. USDC 残高が total_debt より多いことを確認
    2. approve(Pool, total_debt_raw + margin)
    3. repay(asset, REPAY_ALL, 2, wallet)
    """
    from web3 import Web3

    # USDC 残高チェック（保守的に debt + 1 USDC のマージンを確保）
    usdc_balance_raw = token.functions.balanceOf(checksum_wallet).call()
    usdc_balance = Decimal(usdc_balance_raw) / Decimal(10**decimals)
    required = total_debt_usd + Decimal("1")
    if usdc_balance < required:
        logger.error(
            "USDC 残高 %s が Repay に必要な %s を下回っています。Repay できません。",
            usdc_balance,
            required,
        )
        sys.exit(1)

    logger.info("USDC balance for repay: %s (debt ≈ %s)", usdc_balance, total_debt_usd)

    # Approve: total_debt_raw に小さなマージンを加えた値
    approve_amount_raw = usdc_balance_raw  # 全残高を approve して確実に全 debt をカバー

    # Step 1: Approve — nonce は 'pending' で取得（前の tx が pending 中でも正しい値を得る）
    approve_nonce = w3.eth.get_transaction_count(checksum_wallet, "pending")
    approve_tx = token.functions.approve(
        Web3.to_checksum_address(AAVE_POOL_BASE_SEPOLIA),
        approve_amount_raw,
    ).build_transaction(
        {
            "from": checksum_wallet,
            "nonce": approve_nonce,
            "gas": 100000,
            "gasPrice": w3.eth.gas_price,
        }
    )
    signed_approve = w3.eth.account.sign_transaction(approve_tx, private_key=private_key)
    approve_hash = w3.eth.send_raw_transaction(signed_approve.raw_transaction)
    logger.info("Repay approve tx sent: 0x%s", approve_hash.hex())
    w3.eth.wait_for_transaction_receipt(approve_hash, timeout=120)
    logger.info("Repay approve confirmed")

    # Step 2: Repay all (uint256 max)
    # approve 確定後に nonce を再取得（手動インクリメント不要）
    repay_nonce = w3.eth.get_transaction_count(checksum_wallet, "pending")
    repay_tx = pool.functions.repay(
        Web3.to_checksum_address(token_address),
        REPAY_ALL,
        INTEREST_RATE_MODE_VARIABLE,
        checksum_wallet,
    ).build_transaction(
        {
            "from": checksum_wallet,
            "nonce": repay_nonce,
            "gas": 400000,
            "gasPrice": w3.eth.gas_price,
        }
    )
    signed_repay = w3.eth.account.sign_transaction(repay_tx, private_key=private_key)
    repay_hash = w3.eth.send_raw_transaction(signed_repay.raw_transaction)
    logger.info("Repay tx sent: 0x%s", repay_hash.hex())
    logger.info("Track: https://sepolia.basescan.org/tx/0x%s", repay_hash.hex())
    receipt = w3.eth.wait_for_transaction_receipt(repay_hash, timeout=120)
    status = "SUCCESS" if receipt["status"] == 1 else "FAILED"
    logger.info("Repay tx status: %s (block=%s)", status, receipt["blockNumber"])
    if receipt["status"] != 1:
        logger.error("Repay transaction failed")
        sys.exit(1)
    logger.info("RPC 反映待機 (3s)...")
    time.sleep(3)
    return str(repay_hash.hex())


# ---------------------------------------------------------------------------
# メインテスト関数
# ---------------------------------------------------------------------------


def run_hf_monitor_test(
    asset: str,
    step1_amount: Decimal,
    step2_amount: Decimal,
    dry_run: bool,
) -> dict[str, Any]:
    """
    HF 監視テストのメインフロー。

    Returns: テスト結果の dict
    """
    try:
        from eth_account import Account
        from web3 import Web3
    except ImportError as exc:
        logger.error("Missing dependency: %s. Install: pip install web3 eth-account", exc)
        sys.exit(1)

    asset = asset.lower()
    if asset not in ASSET_ADDRESSES:
        logger.error("Unknown asset '%s'. Supported: %s", asset, list(ASSET_ADDRESSES.keys()))
        sys.exit(1)

    rpc_url = os.environ.get("AAVE_RPC_URL_BASE_SEPOLIA", "")
    private_key_hex = os.environ.get("AAVE_PRIVATE_KEY", "")
    wallet_address = os.environ.get("AAVE_WALLET_ADDRESS", "")
    a_usdc_address = os.environ.get("AAVE_A_USDC_ADDRESS", "")

    for name, val in [
        ("AAVE_RPC_URL_BASE_SEPOLIA", rpc_url),
        ("AAVE_PRIVATE_KEY", private_key_hex),
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

    account = Account.from_key(private_key_hex)
    checksum_wallet = Web3.to_checksum_address(wallet_address)
    token_address = ASSET_ADDRESSES[asset]

    pool = w3.eth.contract(
        address=Web3.to_checksum_address(AAVE_POOL_BASE_SEPOLIA),
        abi=_POOL_ABI,
    )
    token = w3.eth.contract(
        address=Web3.to_checksum_address(token_address),
        abi=_ERC20_ABI,
    )

    logger.info("=" * 60)
    logger.info("Aave HF Monitor Test — Base Sepolia")
    logger.info("=" * 60)
    logger.info("Wallet:     %s", mask_address(checksum_wallet))
    logger.info("Pool:       %s", mask_address(AAVE_POOL_BASE_SEPOLIA))
    logger.info("Asset:      %s (%s)", asset.upper(), mask_address(token_address))
    logger.info("aUSDC:      %s", mask_address(a_usdc_address))
    logger.info(
        "Thresholds: SAFE_MODE < %.1f | HARD_STOP < %.1f | FLOOR=%.2f",
        HF_SAFE_MODE_THRESHOLD,
        HF_HARD_STOP_THRESHOLD,
        HF_SAFETY_FLOOR,
    )
    logger.info("Dry-run:    %s", dry_run)

    # variableDebtToken アドレスを取得
    variable_debt_token_address = get_variable_debt_token_address(pool, token_address)
    logger.info("variableDebtToken: %s", mask_address(variable_debt_token_address))

    # ----------------------------------------------------------------
    # Step 0: 現在の状態確認
    # ----------------------------------------------------------------
    logger.info("-" * 60)
    logger.info("Step 0: 現在の状態確認")

    acc = get_account_data(pool, checksum_wallet)
    hf0 = acc["health_factor"]

    if hf0 == Decimal("inf"):
        logger.error(
            "HF が ∞ です（debt ゼロ）。先に aave_borrow_test.py で USDC を Borrow してください。"
        )
        sys.exit(1)

    a_usdc_balance, _ = get_token_balance(w3, a_usdc_address, checksum_wallet)
    usdc_balance, usdc_decimals = get_token_balance(w3, token_address, checksum_wallet)
    debt_balance, _ = get_token_balance(w3, variable_debt_token_address, checksum_wallet)

    logger.info("aUSDC balance (collateral):  %s", a_usdc_balance)
    logger.info("USDC balance (wallet):       %s", usdc_balance)
    logger.info("Variable debt balance:       %s", debt_balance)
    logger.info("Total collateral (USD):      %s", acc["total_collateral_usd"])
    logger.info("Total debt (USD):            %s", acc["total_debt_usd"])
    logger.info("Available borrows (USD):     %s", acc["available_borrows_usd"])
    log_hf_status(hf0, "Step 0")

    if a_usdc_balance <= Decimal("0"):
        logger.error("aUSDC 残高が 0 です。担保がありません。")
        sys.exit(1)

    # ----------------------------------------------------------------
    # Step 1: HF を 2.0 付近まで下げる
    # ----------------------------------------------------------------
    logger.info("-" * 60)
    logger.info("Step 1: 追加 Borrow ≈%s %s — HF を 2.0 付近に", step1_amount, asset.upper())

    acc1 = get_account_data(pool, checksum_wallet)
    safe_step1 = compute_safe_borrow_amount(acc1, step1_amount)

    if safe_step1 <= Decimal("0"):
        logger.warning("Step 1 Borrow をスキップします（安全量 0）")
        hf1 = hf0
        step1_tx = None
    elif dry_run:
        logger.info(
            "[DRY RUN] Would call Pool.borrow(asset, %s %s, interestRateMode=2, ...)",
            safe_step1,
            asset.upper(),
        )
        hf1 = hf0  # dry-run では HF は変わらない（表示のみ）
        step1_tx = None
    else:
        step1_tx = send_borrow_tx(
            pool,
            w3,
            account,
            token_address,
            safe_step1,
            usdc_decimals,
            checksum_wallet,
            account.key,
        )
        acc1_after = get_account_data(pool, checksum_wallet)
        hf1 = acc1_after["health_factor"]
        debt1 = acc1_after["total_debt_usd"]
        logger.info("Total debt after Step 1:  %s USD", debt1)

    log_hf_status(hf1, "Step 1")
    if hf1 != Decimal("inf") and hf1 < HF_SAFE_MODE_THRESHOLD:
        logger.warning(
            "⚠ SAFE_MODE トリガー確認: HF %s < %.1f → backend では BUY がブロックされます",
            hf1,
            HF_SAFE_MODE_THRESHOLD,
        )

    # ----------------------------------------------------------------
    # Step 2: HF を 1.65 付近まで下げる
    # ----------------------------------------------------------------
    logger.info("-" * 60)
    logger.info("Step 2: 追加 Borrow ≈%s %s — HF を 1.65 付近に", step2_amount, asset.upper())

    acc2 = get_account_data(pool, checksum_wallet)
    safe_step2 = compute_safe_borrow_amount(acc2, step2_amount)

    if safe_step2 <= Decimal("0"):
        logger.warning("Step 2 Borrow をスキップします（安全量 0）")
        hf2 = hf1
        step2_tx = None
    elif dry_run:
        logger.info(
            "[DRY RUN] Would call Pool.borrow(asset, %s %s, interestRateMode=2, ...)",
            safe_step2,
            asset.upper(),
        )
        hf2 = hf1
        step2_tx = None
    else:
        step2_tx = send_borrow_tx(
            pool,
            w3,
            account,
            token_address,
            safe_step2,
            usdc_decimals,
            checksum_wallet,
            account.key,
        )
        acc2_after = get_account_data(pool, checksum_wallet)
        hf2 = acc2_after["health_factor"]
        debt2 = acc2_after["total_debt_usd"]
        logger.info("Total debt after Step 2:  %s USD", debt2)

    log_hf_status(hf2, "Step 2")
    if hf2 != Decimal("inf") and hf2 < HF_HARD_STOP_THRESHOLD:
        logger.warning(
            "⚠ HARD_STOP トリガー確認: HF %s < %.1f → backend では全操作がブロックされます",
            hf2,
            HF_HARD_STOP_THRESHOLD,
        )
    elif hf2 != Decimal("inf") and hf2 < HF_SAFE_MODE_THRESHOLD:
        logger.warning(
            "⚠ SAFE_MODE トリガー確認: HF %s < %.1f → backend では BUY がブロックされます",
            hf2,
            HF_SAFE_MODE_THRESHOLD,
        )

    # ----------------------------------------------------------------
    # Cleanup: 全 debt を Repay して HF を安全な値に戻す
    # ----------------------------------------------------------------
    logger.info("-" * 60)
    logger.info("Cleanup: Repay で全 debt を返済")

    acc_final = get_account_data(pool, checksum_wallet)
    total_debt_usd = acc_final["total_debt_usd"]

    if total_debt_usd <= Decimal("0"):
        logger.info("Debt がありません。Repay スキップ。")
        repay_tx = None
        hf_final = Decimal("inf")
    elif dry_run:
        logger.info(
            "[DRY RUN] Would approve %s USDC to Pool, then call"
            " Pool.repay(asset, MAX_UINT256, 2, wallet)",
            total_debt_usd,
        )
        repay_tx = None
        hf_final = hf2  # dry-run では変わらない
    else:
        repay_tx = send_repay_all_tx(
            pool,
            token,
            w3,
            account,
            token_address,
            usdc_decimals,
            total_debt_usd,
            checksum_wallet,
            account.key,
        )
        acc_after_repay = get_account_data(pool, checksum_wallet)
        hf_final = acc_after_repay["health_factor"]
        debt_final = acc_after_repay["total_debt_usd"]
        logger.info("Total debt after Repay:   %s USD", debt_final)

        if debt_final > Decimal("0.01"):
            logger.warning(
                "WARN: Repay 後もわずかな debt が残っています (%s USD) — 利息蓄積の可能性",
                debt_final,
            )

    log_hf_status(hf_final, "Cleanup")

    # ----------------------------------------------------------------
    # サマリー
    # ----------------------------------------------------------------
    logger.info("=" * 60)
    logger.info("テスト結果サマリー")
    logger.info("  Step 0 HF: %s → %s", hf0, evaluate_mode(hf0))
    logger.info("  Step 1 HF: %s → %s", hf1, evaluate_mode(hf1))
    logger.info("  Step 2 HF: %s → %s", hf2, evaluate_mode(hf2))
    logger.info("  Final  HF: %s → %s", hf_final, evaluate_mode(hf_final))
    if not dry_run:
        logger.info("  Step 1 tx: 0x%s", step1_tx or "skipped")
        logger.info("  Step 2 tx: 0x%s", step2_tx or "skipped")
        logger.info("  Repay tx:  0x%s", repay_tx or "skipped")

    passed = hf_final == Decimal("inf") or hf_final > HF_SAFE_MODE_THRESHOLD
    overall = "PASS (HF restored to safe level)" if passed else "WARN (HF not fully restored)"
    logger.info("  Overall:   %s", overall)
    logger.info("=" * 60)

    return {
        "dry_run": dry_run,
        "hf_step0": str(hf0),
        "hf_step1": str(hf1),
        "hf_step2": str(hf2),
        "hf_final": str(hf_final),
        "mode_step0": evaluate_mode(hf0),
        "mode_step1": evaluate_mode(hf1),
        "mode_step2": evaluate_mode(hf2),
        "mode_final": evaluate_mode(hf_final),
        "step1_tx": step1_tx,
        "step2_tx": step2_tx,
        "repay_tx": repay_tx,
        "passed": passed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="HF 閾値テスト: 段階的 Borrow で SAFE_MODE / HARD_STOP トリガーを確認"
    )
    parser.add_argument("--dry-run", action="store_true", help="Show params without sending tx")
    parser.add_argument(
        "--step1-amount",
        type=str,
        default="15",
        help="Step 1 の追加 Borrow 量 (default: 15 USDC → HF ≈ 2.0)",
    )
    parser.add_argument(
        "--step2-amount",
        type=str,
        default="5",
        help="Step 2 の追加 Borrow 量 (default: 5 USDC → HF ≈ 1.65)",
    )
    parser.add_argument(
        "--asset",
        type=str,
        default="usdc",
        help="Borrow/Repay 対象アセット (default: usdc)",
    )
    args = parser.parse_args()

    step1_amount = Decimal(args.step1_amount)
    step2_amount = Decimal(args.step2_amount)

    for name, val in [("step1-amount", step1_amount), ("step2-amount", step2_amount)]:
        if val <= Decimal("0"):
            logger.error("%s must be positive, got %s", name, val)
            sys.exit(1)

    result = run_hf_monitor_test(
        asset=args.asset,
        step1_amount=step1_amount,
        step2_amount=step2_amount,
        dry_run=args.dry_run,
    )
    logger.info("Result: %s", result)


if __name__ == "__main__":
    main()
