#!/usr/bin/env python3
"""
Full E2E orchestrator for Aave V3 on Base Sepolia.

Requirements: web3>=6.0, python-dotenv, eth-account

Usage:
    python scripts/aave_e2e_base.py [--dry-run] [--skip-bridge] [--skip-faucet]

Steps:
  1. Check ETH balance on Base Sepolia
  2. If < 0.01 ETH and not --skip-bridge: bridge from Ethereum Sepolia (wait up to 5 min)
  3. If USDC < 10 and not --skip-faucet: mint from faucet
  4. Supply 100 USDC to Aave
  5. Check HF
  6. Withdraw 50 USDC
  7. Final HF check
  8. Print summary table
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

# Contract addresses (Base Sepolia)
# Verify: https://docs.aave.com/developers/deployed-contracts/v3-testnet-addresses
AAVE_POOL_BASE_SEPOLIA = "0x07eA79F68B2B3df564D0A34F8e19791a8a4Ee29"
AAVE_FAUCET_BASE_SEPOLIA = "0xC959483DBa39aa9E78757139af0e9a2EDEb3f42D"
USDC_BASE_SEPOLIA = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
USDC_DECIMALS = 6

# L1StandardBridge on Ethereum Sepolia
L1_STANDARD_BRIDGE = "0xfd0Bf71F60660E2f608ed56e1659C450eB113120"

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
]

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


def get_eth_balance_base(w3_base, wallet: str) -> Decimal:
    """Get ETH balance on Base Sepolia."""
    from web3 import Web3
    bal = w3_base.eth.get_balance(Web3.to_checksum_address(wallet))
    return Decimal(str(w3_base.from_wei(bal, "ether")))


def get_usdc_balance(w3_base, wallet: str) -> Decimal:
    """Get USDC balance on Base Sepolia."""
    from web3 import Web3
    token = w3_base.eth.contract(address=Web3.to_checksum_address(USDC_BASE_SEPOLIA), abi=_ERC20_ABI)
    raw = token.functions.balanceOf(Web3.to_checksum_address(wallet)).call()
    return Decimal(raw) / Decimal(10 ** USDC_DECIMALS)


def get_health_factor(pool, wallet: str) -> Decimal:
    """Get health factor from Aave Pool."""
    from web3 import Web3
    result = pool.functions.getUserAccountData(Web3.to_checksum_address(wallet)).call()
    hf_raw: int = result[5]
    total_debt: int = result[1]
    if hf_raw >= 2**256 - 1 or (hf_raw == 0 and total_debt == 0):
        return Decimal("inf")
    return Decimal(hf_raw) / Decimal(10**18)


def step_bridge(w3_eth, account, checksum_wallet: str, dry_run: bool) -> bool:
    """Bridge 0.05 ETH from Ethereum Sepolia to Base Sepolia. Returns True on success."""
    from web3 import Web3
    bridge_amount = Decimal("0.05")
    amount_wei = int(bridge_amount * Decimal(10**18))
    logger.info("[BRIDGE] Bridging %s ETH from Ethereum Sepolia to Base Sepolia", bridge_amount)

    bridge = w3_eth.eth.contract(
        address=Web3.to_checksum_address(L1_STANDARD_BRIDGE),
        abi=_L1_BRIDGE_ABI,
    )

    if dry_run:
        logger.info("[DRY RUN] Would bridge %s ETH", bridge_amount)
        return True

    tx = bridge.functions.depositETH(
        checksum_wallet,
        200000,
        b"",
    ).build_transaction({
        "from": checksum_wallet,
        "value": amount_wei,
        "nonce": w3_eth.eth.get_transaction_count(checksum_wallet),
        "gas": 300000,
        "gasPrice": w3_eth.eth.gas_price,
    })
    signed = w3_eth.eth.account.sign_transaction(tx, private_key=account.key)
    tx_hash = w3_eth.eth.send_raw_transaction(signed.raw_transaction)
    logger.info("[BRIDGE] L1 tx sent: 0x%s", tx_hash.hex())
    receipt = w3_eth.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if receipt["status"] != 1:
        logger.error("[BRIDGE] L1 tx failed")
        return False
    logger.info("[BRIDGE] L1 confirmed. Waiting up to 5 min for Base Sepolia ETH...")
    return True


def poll_base_eth(w3_base, wallet: str, min_eth: Decimal, timeout_secs: int = 300) -> bool:
    """Poll Base Sepolia ETH balance until >= min_eth or timeout. Returns True if reached."""
    from web3 import Web3
    checksum = Web3.to_checksum_address(wallet)
    deadline = time.time() + timeout_secs
    while time.time() < deadline:
        bal = get_eth_balance_base(w3_base, checksum)
        logger.info("[POLL] Base Sepolia ETH: %s (need >= %s)", bal, min_eth)
        if bal >= min_eth:
            return True
        time.sleep(15)
    return False


def step_faucet(w3_base, account, checksum_wallet: str, amount: Decimal, dry_run: bool) -> bool:
    """Mint USDC from Aave faucet. Returns True on success."""
    from web3 import Web3
    amount_raw = int(amount * Decimal(10 ** USDC_DECIMALS))
    logger.info("[FAUCET] Minting %s USDC from Aave faucet", amount)

    if dry_run:
        logger.info("[DRY RUN] Would mint %s USDC", amount)
        return True

    faucet = w3_base.eth.contract(
        address=Web3.to_checksum_address(AAVE_FAUCET_BASE_SEPOLIA),
        abi=_FAUCET_ABI,
    )
    tx = faucet.functions.mint(
        Web3.to_checksum_address(USDC_BASE_SEPOLIA),
        checksum_wallet,
        amount_raw,
    ).build_transaction({
        "from": checksum_wallet,
        "nonce": w3_base.eth.get_transaction_count(checksum_wallet),
        "gas": 200000,
        "gasPrice": w3_base.eth.gas_price,
    })
    signed = w3_base.eth.account.sign_transaction(tx, private_key=account.key)
    tx_hash = w3_base.eth.send_raw_transaction(signed.raw_transaction)
    logger.info("[FAUCET] Tx sent: 0x%s", tx_hash.hex())
    receipt = w3_base.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if receipt["status"] != 1:
        logger.error("[FAUCET] Faucet tx failed")
        return False
    logger.info("[FAUCET] Mint confirmed")
    return True


def step_supply(w3_base, pool, account, checksum_wallet: str, amount: Decimal, dry_run: bool) -> str | None:
    """Approve and supply USDC to Aave Pool. Returns tx hash or None."""
    from web3 import Web3
    amount_raw = int(amount * Decimal(10 ** USDC_DECIMALS))
    token = w3_base.eth.contract(address=Web3.to_checksum_address(USDC_BASE_SEPOLIA), abi=_ERC20_ABI)
    logger.info("[SUPPLY] Supplying %s USDC to Aave", amount)

    if dry_run:
        logger.info("[DRY RUN] Would approve and supply %s USDC", amount)
        return "dry_run"

    # Approve
    approve_tx = token.functions.approve(
        Web3.to_checksum_address(AAVE_POOL_BASE_SEPOLIA),
        amount_raw,
    ).build_transaction({
        "from": checksum_wallet,
        "nonce": w3_base.eth.get_transaction_count(checksum_wallet),
        "gas": 100000,
        "gasPrice": w3_base.eth.gas_price,
    })
    signed_a = w3_base.eth.account.sign_transaction(approve_tx, private_key=account.key)
    approve_hash = w3_base.eth.send_raw_transaction(signed_a.raw_transaction)
    w3_base.eth.wait_for_transaction_receipt(approve_hash, timeout=120)
    logger.info("[SUPPLY] Approve confirmed")

    # Supply
    supply_tx = pool.functions.supply(
        Web3.to_checksum_address(USDC_BASE_SEPOLIA),
        amount_raw,
        checksum_wallet,
        0,
    ).build_transaction({
        "from": checksum_wallet,
        "nonce": w3_base.eth.get_transaction_count(checksum_wallet),
        "gas": 300000,
        "gasPrice": w3_base.eth.gas_price,
    })
    signed_s = w3_base.eth.account.sign_transaction(supply_tx, private_key=account.key)
    supply_hash = w3_base.eth.send_raw_transaction(signed_s.raw_transaction)
    logger.info("[SUPPLY] Tx sent: 0x%s", supply_hash.hex())
    receipt = w3_base.eth.wait_for_transaction_receipt(supply_hash, timeout=120)
    if receipt["status"] != 1:
        logger.error("[SUPPLY] Supply tx failed")
        return None
    logger.info("[SUPPLY] Supply confirmed")
    return supply_hash.hex()


def step_withdraw(w3_base, pool, account, checksum_wallet: str, amount: Decimal, dry_run: bool) -> str | None:
    """Withdraw USDC from Aave Pool. Returns tx hash or None."""
    from web3 import Web3
    amount_raw = int(amount * Decimal(10 ** USDC_DECIMALS))
    logger.info("[WITHDRAW] Withdrawing %s USDC from Aave", amount)

    if dry_run:
        logger.info("[DRY RUN] Would withdraw %s USDC", amount)
        return "dry_run"

    withdraw_tx = pool.functions.withdraw(
        Web3.to_checksum_address(USDC_BASE_SEPOLIA),
        amount_raw,
        checksum_wallet,
    ).build_transaction({
        "from": checksum_wallet,
        "nonce": w3_base.eth.get_transaction_count(checksum_wallet),
        "gas": 300000,
        "gasPrice": w3_base.eth.gas_price,
    })
    signed_w = w3_base.eth.account.sign_transaction(withdraw_tx, private_key=account.key)
    withdraw_hash = w3_base.eth.send_raw_transaction(signed_w.raw_transaction)
    logger.info("[WITHDRAW] Tx sent: 0x%s", withdraw_hash.hex())
    receipt = w3_base.eth.wait_for_transaction_receipt(withdraw_hash, timeout=120)
    if receipt["status"] != 1:
        logger.error("[WITHDRAW] Withdraw tx failed")
        return None
    logger.info("[WITHDRAW] Withdraw confirmed")
    return withdraw_hash.hex()


def run_e2e(dry_run: bool, skip_bridge: bool, skip_faucet: bool) -> None:
    """Execute full E2E flow."""
    try:
        from web3 import Web3
        from eth_account import Account
    except ImportError as exc:
        logger.error("Missing dependency: %s. Install: pip install web3 eth-account", exc)
        sys.exit(1)

    rpc_url_base = os.environ.get("AAVE_RPC_URL_BASE_SEPOLIA", "")
    rpc_url_eth = os.environ.get("AAVE_RPC_URL_ETH_SEPOLIA", "")
    private_key = os.environ.get("AAVE_PRIVATE_KEY", "")
    wallet_address = os.environ.get("AAVE_WALLET_ADDRESS", "")

    for name, val in [
        ("AAVE_RPC_URL_BASE_SEPOLIA", rpc_url_base),
        ("AAVE_PRIVATE_KEY", private_key),
        ("AAVE_WALLET_ADDRESS", wallet_address),
    ]:
        if not val:
            logger.error("Missing env var: %s", name)
            sys.exit(1)

    w3_base = Web3(Web3.HTTPProvider(rpc_url_base))
    if not w3_base.is_connected():
        logger.error("Cannot connect to Base Sepolia RPC")
        sys.exit(1)

    account = Account.from_key(private_key)
    checksum_wallet = Web3.to_checksum_address(wallet_address)
    pool = w3_base.eth.contract(address=Web3.to_checksum_address(AAVE_POOL_BASE_SEPOLIA), abi=_POOL_ABI)

    logger.info("=" * 60)
    logger.info("Aave V3 Base Sepolia E2E Test")
    logger.info("=" * 60)
    logger.info("Wallet: %s", mask_address(checksum_wallet))
    logger.info("Dry run: %s | Skip bridge: %s | Skip faucet: %s", dry_run, skip_bridge, skip_faucet)

    results: dict = {
        "wallet": mask_address(checksum_wallet),
        "dry_run": dry_run,
    }

    # Step 1: Check ETH balance on Base Sepolia
    eth_balance = get_eth_balance_base(w3_base, checksum_wallet)
    logger.info("[1] Base Sepolia ETH balance: %s ETH", eth_balance)
    results["eth_balance_base"] = str(eth_balance)

    # Step 2: Bridge if needed
    if eth_balance < Decimal("0.01") and not skip_bridge:
        if not rpc_url_eth:
            logger.warning("[2] AAVE_RPC_URL_ETH_SEPOLIA not set, skipping bridge")
        else:
            w3_eth = Web3(Web3.HTTPProvider(rpc_url_eth))
            if not w3_eth.is_connected():
                logger.error("[2] Cannot connect to Ethereum Sepolia RPC")
                sys.exit(1)
            bridge_ok = step_bridge(w3_eth, account, checksum_wallet, dry_run)
            if not bridge_ok:
                logger.error("[2] Bridge failed")
                sys.exit(1)
            if not dry_run:
                arrived = poll_base_eth(w3_base, checksum_wallet, Decimal("0.01"), timeout_secs=300)
                if not arrived:
                    logger.error("[2] ETH did not arrive on Base Sepolia within 5 min")
                    sys.exit(1)
                eth_balance = get_eth_balance_base(w3_base, checksum_wallet)
                logger.info("[2] ETH arrived on Base Sepolia: %s ETH", eth_balance)
            results["bridge"] = "completed"
    else:
        logger.info("[2] Skipping bridge (ETH sufficient or --skip-bridge)")
        results["bridge"] = "skipped"

    # Step 3: Faucet if USDC < 10
    usdc_balance = get_usdc_balance(w3_base, checksum_wallet)
    logger.info("[3] USDC balance: %s", usdc_balance)
    if usdc_balance < Decimal("10") and not skip_faucet:
        faucet_ok = step_faucet(w3_base, account, checksum_wallet, Decimal("1000"), dry_run)
        if not faucet_ok:
            logger.error("[3] Faucet failed")
            sys.exit(1)
        if not dry_run:
            usdc_balance = get_usdc_balance(w3_base, checksum_wallet)
            logger.info("[3] USDC after faucet: %s", usdc_balance)
        results["faucet"] = "completed"
    else:
        logger.info("[3] Skipping faucet (USDC sufficient or --skip-faucet)")
        results["faucet"] = "skipped"

    # Step 4: Supply 100 USDC
    hf_before_supply = get_health_factor(pool, checksum_wallet)
    logger.info("[4] HF before supply: %s", hf_before_supply)
    supply_tx = step_supply(w3_base, pool, account, checksum_wallet, Decimal("100"), dry_run)
    if supply_tx is None:
        logger.error("[4] Supply failed")
        sys.exit(1)
    results["supply_tx"] = supply_tx

    # Step 5: HF after supply
    hf_after_supply = get_health_factor(pool, checksum_wallet)
    logger.info("[5] HF after supply: %s", hf_after_supply)
    results["hf_after_supply"] = str(hf_after_supply)

    # Step 6: Withdraw 50 USDC
    withdraw_tx = step_withdraw(w3_base, pool, account, checksum_wallet, Decimal("50"), dry_run)
    if withdraw_tx is None:
        logger.error("[6] Withdraw failed")
        sys.exit(1)
    results["withdraw_tx"] = withdraw_tx

    # Step 7: Final HF check
    hf_final = get_health_factor(pool, checksum_wallet)
    logger.info("[7] Final HF: %s", hf_final)
    results["hf_final"] = str(hf_final)

    # Step 8: Summary table
    print()
    print("=" * 60)
    print("E2E SUMMARY")
    print("=" * 60)
    print(f"  Wallet:            {results['wallet']}")
    print(f"  Dry run:           {results['dry_run']}")
    print(f"  Base ETH balance:  {results.get('eth_balance_base', 'N/A')}")
    print(f"  Bridge:            {results.get('bridge', 'N/A')}")
    print(f"  Faucet:            {results.get('faucet', 'N/A')}")
    print(f"  Supply tx:         {results.get('supply_tx', 'N/A')}")
    print(f"  HF after supply:   {results.get('hf_after_supply', 'N/A')}")
    print(f"  Withdraw tx:       {results.get('withdraw_tx', 'N/A')}")
    print(f"  HF final:          {results.get('hf_final', 'N/A')}")
    print("=" * 60)
    print("E2E COMPLETE")


def main() -> None:
    parser = argparse.ArgumentParser(description="Full E2E Aave V3 test on Base Sepolia")
    parser.add_argument("--dry-run", action="store_true", help="Show params without sending any transactions")
    parser.add_argument("--skip-bridge", action="store_true", help="Skip bridging ETH to Base Sepolia")
    parser.add_argument("--skip-faucet", action="store_true", help="Skip Aave faucet USDC minting")
    args = parser.parse_args()

    try:
        run_e2e(dry_run=args.dry_run, skip_bridge=args.skip_bridge, skip_faucet=args.skip_faucet)
    except SystemExit:
        raise
    except Exception as exc:
        logger.error("Unexpected error: %s: %s", type(exc).__name__, exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
