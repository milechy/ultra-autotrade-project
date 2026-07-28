#!/usr/bin/env python3
"""
staging-v4 の全テストウォレット(role=viewer かつ smart_wallet_address 設定済)に
Base Sepolia テストネットUSDCを$200まで補充する。

scripts/aave_faucet_base.py と同じ Aave テストネットfaucetコントラクト
(mint(token, to, amount)) を使うが、operator自身ではなく任意の宛先(to)を
指定できるよう一般化したもの。実資金ではなくテストネットのfake USDCのみを扱う。

Usage:
    python scripts/fund_test_wallets_base_sepolia.py [--dry-run] [--target-usd 200]
"""

import argparse
import logging
import os
import sys
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env.staging-v4")
load_dotenv(Path(__file__).parent.parent / ".env.staging")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# scripts/aave_faucet_base.py と同一のfaucetコントラクト・資産定義
AAVE_FAUCET_BASE_SEPOLIA = "0xD9145b5F45Ad4519c7ACcD6E0A4A82e83bB8A6Dc"
USDC_ADDRESS = "0xba50cd2a20f6da35d788639e581bca8d0b5d4d5f"
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
    """アドレスを先頭6文字+末尾4文字にマスクしてログ出力する。"""
    if len(addr) < 10:
        return addr
    return f"{addr[:6]}...{addr[-4:]}"


def fetch_target_wallets() -> list[tuple[int, str, str]]:
    """DB から role=viewer かつ smart_wallet_address 設定済のユーザーを取得する。

    :returns: [(user_id, email, smart_wallet_address), ...]
    """
    from sqlalchemy import text  # noqa: PLC0415

    from app.database import SessionLocal  # noqa: PLC0415

    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                "SELECT id, email, smart_wallet_address FROM users "
                "WHERE role = 'viewer' AND smart_wallet_address IS NOT NULL "
                "ORDER BY id"
            )
        ).all()
        return [(r[0], r[1], r[2]) for r in rows]
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="staging-v4 テストウォレットへ Base Sepolia テストネットUSDCを補充"
    )
    parser.add_argument("--dry-run", action="store_true", help="送金せず対象と金額のみ表示")
    parser.add_argument(
        "--target-usd", type=str, default="200", help="補充先の目標USDC残高 (default: 200)"
    )
    args = parser.parse_args()

    if os.getenv("APP_ENV", "").strip().lower() == "production":
        logger.error("APP_ENV=production では実行不可(本スクリプトはstaging専用)")
        sys.exit(1)

    try:
        from web3 import Web3
        from eth_account import Account
    except ImportError as exc:
        logger.error("Missing dependency: %s", exc)
        sys.exit(1)

    rpc_url = os.environ.get("ALCHEMY_RPC_URL_BASE_SEPOLIA") or os.environ.get(
        "AAVE_RPC_URL_BASE_SEPOLIA", ""
    )
    private_key = os.environ.get("AAVE_WALLET_PRIVATE_KEY", "") or os.environ.get(
        "AAVE_PRIVATE_KEY", ""
    )
    operator_address = os.environ.get("AAVE_WALLET_ADDRESS", "")

    for name, val in [
        ("ALCHEMY_RPC_URL_BASE_SEPOLIA / AAVE_RPC_URL_BASE_SEPOLIA", rpc_url),
        ("AAVE_WALLET_PRIVATE_KEY / AAVE_PRIVATE_KEY", private_key),
        ("AAVE_WALLET_ADDRESS", operator_address),
    ]:
        if not val:
            logger.error("Missing env var: %s", name)
            sys.exit(1)

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        logger.error("Cannot connect to Base Sepolia RPC")
        sys.exit(1)

    account = Account.from_key(private_key)
    operator_checksum = Web3.to_checksum_address(operator_address)
    target_usd = Decimal(args.target_usd)

    usdc = w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=_ERC20_ABI)
    faucet = w3.eth.contract(
        address=Web3.to_checksum_address(AAVE_FAUCET_BASE_SEPOLIA), abi=_FAUCET_ABI
    )

    wallets = fetch_target_wallets()
    logger.info("対象ウォレット: %d件", len(wallets))

    nonce = w3.eth.get_transaction_count(operator_checksum)

    for user_id, email, wallet_address in wallets:
        checksum_addr = Web3.to_checksum_address(wallet_address)
        balance_raw = usdc.functions.balanceOf(checksum_addr).call()
        balance = Decimal(balance_raw) / Decimal(10**USDC_DECIMALS)

        if balance >= target_usd:
            logger.info(
                "user_id=%d %s: 残高 %s USDC >= 目標 %s USDC → スキップ",
                user_id,
                mask_address(checksum_addr),
                balance,
                target_usd,
            )
            continue

        top_up = target_usd - balance
        amount_raw = int(top_up * Decimal(10**USDC_DECIMALS))

        logger.info(
            "user_id=%d (%s) %s: 残高 %s USDC → +%s USDC 補充",
            user_id,
            email,
            mask_address(checksum_addr),
            balance,
            top_up,
        )

        if args.dry_run:
            logger.info("[DRY RUN] 送金しません")
            continue

        tx = faucet.functions.mint(
            Web3.to_checksum_address(USDC_ADDRESS),
            checksum_addr,
            amount_raw,
        ).build_transaction(
            {
                "from": operator_checksum,
                "nonce": nonce,
                "gas": 200000,
                "gasPrice": w3.eth.gas_price,
            }
        )
        signed_tx = w3.eth.account.sign_transaction(tx, private_key=account.key)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        logger.info("Tx送信: 0x%s", tx_hash.hex())
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        status = "SUCCESS" if receipt["status"] == 1 else "FAILED"
        logger.info("Tx結果: %s (block=%s)", status, receipt["blockNumber"])
        if receipt["status"] != 1:
            logger.error("Mint失敗 user_id=%d — nonceは進めず次のウォレットへ", user_id)
            continue
        nonce += 1

    logger.info("完了")


if __name__ == "__main__":
    main()
