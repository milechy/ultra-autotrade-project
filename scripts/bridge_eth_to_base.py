#!/usr/bin/env python3
"""
Bridge ETH from Ethereum Sepolia → Base Sepolia via L1StandardBridge.

Requirements: web3>=6.0, python-dotenv, eth-account

Usage:
    python scripts/bridge_eth_to_base.py [--dry-run] [--amount 0.05]
"""

import argparse
import logging
import os
import sys
import time
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env.staging")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Contract addresses
# L1StandardBridge on Ethereum Sepolia (Base bridge)
# Verify: https://docs.base.org/docs/base-contracts/
L1_STANDARD_BRIDGE = "0xfd0Bf71F60660E2f608ed56e1659C450eB113120"

# Minimal ABI for depositETH
_L1_BRIDGE_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "_to", "type": "address"},
            {"internalType": "uint32", "name": "_minGasLimit", "type": "uint32"},
            {"internalType": "bytes", "name": "_extraData", "type": "bytes"},
        ],
        "name": "depositETH",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function",
    },
]


def mask_address(addr: str) -> str:
    """Mask address to first 6 + last 4 chars for safe logging."""
    if len(addr) < 10:
        return addr
    return f"{addr[:6]}...{addr[-4:]}"


def get_eth_balance(w3, address: str) -> Decimal:
    """Get ETH balance in ETH units."""
    balance_wei = w3.eth.get_balance(w3.eth.default_account if not address else address)
    return Decimal(str(w3.from_wei(balance_wei, "ether")))


def bridge_eth(amount: Decimal, dry_run: bool) -> None:
    """Bridge ETH from Ethereum Sepolia to Base Sepolia."""
    try:
        from web3 import Web3
        from eth_account import Account
    except ImportError as exc:
        logger.error("Missing dependency: %s. Install: pip install web3 eth-account", exc)
        sys.exit(1)

    rpc_url_eth = os.environ.get("AAVE_RPC_URL_ETH_SEPOLIA", "")
    rpc_url_base = os.environ.get("AAVE_RPC_URL_BASE_SEPOLIA", "")
    private_key = os.environ.get("AAVE_PRIVATE_KEY", "")
    wallet_address = os.environ.get("AAVE_WALLET_ADDRESS", "")

    for name, val in [
        ("AAVE_RPC_URL_ETH_SEPOLIA", rpc_url_eth),
        ("AAVE_PRIVATE_KEY", private_key),
        ("AAVE_WALLET_ADDRESS", wallet_address),
    ]:
        if not val:
            logger.error("Missing env var: %s", name)
            sys.exit(1)

    # Connect to Ethereum Sepolia
    w3_eth = Web3(Web3.HTTPProvider(rpc_url_eth))
    if not w3_eth.is_connected():
        logger.error("Cannot connect to Ethereum Sepolia RPC")
        sys.exit(1)

    account = Account.from_key(private_key)
    checksum_wallet = Web3.to_checksum_address(wallet_address)

    logger.info("Wallet: %s", mask_address(checksum_wallet))
    logger.info("Bridge amount: %s ETH", amount)

    # Show ETH balance on Ethereum Sepolia
    eth_balance_before = Decimal(str(w3_eth.from_wei(w3_eth.eth.get_balance(checksum_wallet), "ether")))
    logger.info("ETH Sepolia balance before: %s ETH", eth_balance_before)

    # Show Base Sepolia balance if RPC configured
    if rpc_url_base:
        try:
            w3_base = Web3(Web3.HTTPProvider(rpc_url_base))
            if w3_base.is_connected():
                base_balance_before = Decimal(str(w3_base.from_wei(w3_base.eth.get_balance(checksum_wallet), "ether")))
                logger.info("Base Sepolia balance before: %s ETH", base_balance_before)
        except Exception as e:
            logger.warning("Could not fetch Base Sepolia balance: %s", e)

    amount_wei = int(amount * Decimal(10**18))

    bridge_contract = w3_eth.eth.contract(
        address=Web3.to_checksum_address(L1_STANDARD_BRIDGE),
        abi=_L1_BRIDGE_ABI,
    )

    tx_params = {
        "from": checksum_wallet,
        "value": amount_wei,
        "nonce": w3_eth.eth.get_transaction_count(checksum_wallet),
        "gas": 300000,
        "gasPrice": w3_eth.eth.gas_price,
    }

    logger.info("Transaction params:")
    logger.info("  to (bridge): %s", mask_address(L1_STANDARD_BRIDGE))
    logger.info("  value: %s ETH (%s wei)", amount, amount_wei)
    logger.info("  gas: %s", tx_params["gas"])
    logger.info("  gasPrice: %s gwei", w3_eth.from_wei(tx_params["gasPrice"], "gwei"))

    if dry_run:
        logger.info("[DRY RUN] Would call depositETH(to=%s, minGasLimit=200000, extraData=0x)", mask_address(checksum_wallet))
        logger.info("[DRY RUN] No transaction sent.")
        return

    # Build and send transaction
    tx = bridge_contract.functions.depositETH(
        checksum_wallet,  # _to
        200000,           # _minGasLimit
        b"",              # _extraData
    ).build_transaction(tx_params)

    signed_tx = w3_eth.eth.account.sign_transaction(tx, private_key=account.key)
    tx_hash = w3_eth.eth.send_raw_transaction(signed_tx.raw_transaction)
    logger.info("Transaction sent: 0x%s", tx_hash.hex())
    logger.info("Track: https://sepolia.etherscan.io/tx/0x%s", tx_hash.hex())

    logger.info("Waiting for L1 receipt...")
    receipt = w3_eth.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    status = "SUCCESS" if receipt["status"] == 1 else "FAILED"
    logger.info("L1 tx status: %s (block=%s)", status, receipt["blockNumber"])

    if receipt["status"] != 1:
        logger.error("L1 transaction failed")
        sys.exit(1)

    # Show updated Ethereum Sepolia balance
    eth_balance_after = Decimal(str(w3_eth.from_wei(w3_eth.eth.get_balance(checksum_wallet), "ether")))
    logger.info("ETH Sepolia balance after: %s ETH (change: %s ETH)", eth_balance_after, eth_balance_after - eth_balance_before)

    logger.info("L2 finality takes 5-15 minutes. Use aave_e2e_base.py to poll for arrival.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bridge ETH from Ethereum Sepolia to Base Sepolia")
    parser.add_argument("--dry-run", action="store_true", help="Show tx params without sending")
    parser.add_argument("--amount", type=str, default="0.05", help="Amount of ETH to bridge (default: 0.05)")
    args = parser.parse_args()

    amount = Decimal(args.amount)
    if amount <= 0:
        logger.error("Amount must be positive, got %s", amount)
        sys.exit(1)

    bridge_eth(amount=amount, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
