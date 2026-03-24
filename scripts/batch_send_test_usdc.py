#!/usr/bin/env python3
# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# scripts/batch_send_test_usdc.py
"""
テスターのウォレットアドレスにテスト USDC を一括送金するスクリプト。

対応チェーン:
  - Arbitrum Sepolia (chain_id=421614)
  - Base Sepolia (chain_id=84532)

環境変数:
  SENDER_PRIVATE_KEY  - 送金元ウォレットの秘密鍵
  ARB_SEPOLIA_RPC     - Arbitrum Sepolia の RPC エンドポイント
  BASE_SEPOLIA_RPC    - Base Sepolia の RPC エンドポイント

使用例:
  # アドレスを引数で指定
  python batch_send_test_usdc.py --chain arb --addresses 0xABC... 0xDEF...

  # ファイルから読み込み（1アドレス/行）
  python batch_send_test_usdc.py --chain base --file addresses.txt

  # 実際には送金せず確認のみ
  python batch_send_test_usdc.py --chain arb --file addresses.txt --dry-run
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from web3 import Web3

load_dotenv(Path(__file__).parent.parent / ".env.staging")

# USDC コントラクトアドレス
USDC_CONTRACTS: dict[str, str] = {
    "arb": "0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d",  # Arbitrum Sepolia
    "base": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",  # Base Sepolia
}

CHAIN_IDS: dict[str, int] = {
    "arb": 421614,
    "base": 84532,
}

CHAIN_NAMES: dict[str, str] = {
    "arb": "Arbitrum Sepolia",
    "base": "Base Sepolia",
}

# ERC20 transfer() のみ定義した minimal ABI
ERC20_TRANSFER_ABI = [
    {
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# デフォルト送金量: 100 USDC (6 decimals)
DEFAULT_AMOUNT_UNITS = 100_000_000


def load_addresses_from_file(file_path: str) -> list[str]:
    """ファイルから1行1アドレスでウォレットアドレスを読み込む。"""
    path = Path(file_path)
    if not path.exists():
        print(f"[ERROR] File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    addresses = []
    for line in path.read_text().splitlines():
        addr = line.strip()
        if addr and not addr.startswith("#"):
            addresses.append(addr)
    return addresses


def validate_address(addr: str) -> str:
    """チェックサム付きアドレスに変換して検証する。"""
    try:
        return Web3.to_checksum_address(addr)
    except ValueError:
        print(f"[ERROR] Invalid address: {addr}", file=sys.stderr)
        sys.exit(1)


def send_usdc(
    w3: Web3,
    contract: object,
    sender_address: str,
    private_key: str,
    recipient: str,
    amount_units: int,
    chain_id: int,
    dry_run: bool,
) -> str | None:
    """
    USDC を送金する。

    Returns:
        送金成功時はトランザクションハッシュ、dry_run 時は None
    """
    if dry_run:
        print(f"  [DRY-RUN] Would send {amount_units / 1_000_000:.2f} USDC → {recipient}")
        return None

    nonce = w3.eth.get_transaction_count(sender_address, "pending")
    tx = contract.functions.transfer(recipient, amount_units).build_transaction(
        {
            "chainId": chain_id,
            "gas": 100_000,
            "gasPrice": w3.eth.gas_price,
            "nonce": nonce,
            "from": sender_address,
        }
    )

    # 秘密鍵はログに出さない
    signed = w3.eth.account.sign_transaction(tx, private_key=private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

    if receipt["status"] == 1:
        return tx_hash.hex()
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch send test USDC to tester wallets")
    parser.add_argument(
        "--chain",
        choices=["arb", "base"],
        required=True,
        help="Target chain: arb (Arbitrum Sepolia) or base (Base Sepolia)",
    )
    parser.add_argument(
        "--addresses",
        nargs="*",
        default=[],
        help="Recipient wallet addresses (space-separated)",
    )
    parser.add_argument(
        "--file",
        default=None,
        help="File containing one wallet address per line",
    )
    parser.add_argument(
        "--amount",
        type=int,
        default=DEFAULT_AMOUNT_UNITS,
        help=f"Amount in USDC base units (6 decimals). Default: {DEFAULT_AMOUNT_UNITS} = 100 USDC",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be sent without actually sending",
    )
    args = parser.parse_args()

    # アドレス収集
    addresses: list[str] = list(args.addresses)
    if args.file:
        addresses.extend(load_addresses_from_file(args.file))
    if not addresses:
        print("[ERROR] No addresses provided. Use --addresses or --file.", file=sys.stderr)
        sys.exit(1)

    # 環境変数（.env.staging との互換フォールバック）
    private_key = os.environ.get("SENDER_PRIVATE_KEY") or os.environ.get(
        "AAVE_WALLET_PRIVATE_KEY", ""
    )
    if not private_key and not args.dry_run:
        print(
            "[ERROR] SENDER_PRIVATE_KEY (or AAVE_WALLET_PRIVATE_KEY) env var is not set.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.chain == "arb":
        rpc_url = os.environ.get("ARB_SEPOLIA_RPC") or os.environ.get(
            "ALCHEMY_RPC_URL_ARBITRUM_SEPOLIA", ""
        )
        rpc_env_desc = "ARB_SEPOLIA_RPC / ALCHEMY_RPC_URL_ARBITRUM_SEPOLIA"
    else:
        rpc_url = (
            os.environ.get("BASE_SEPOLIA_RPC")
            or os.environ.get("ALCHEMY_RPC_URL_BASE_SEPOLIA")
            or os.environ.get("AAVE_RPC_URL_BASE_SEPOLIA", "")
        )
        rpc_env_desc = "BASE_SEPOLIA_RPC / ALCHEMY_RPC_URL_BASE_SEPOLIA / AAVE_RPC_URL_BASE_SEPOLIA"
    if not rpc_url:
        print(f"[ERROR] RPC URL not set. Check: {rpc_env_desc}", file=sys.stderr)
        sys.exit(1)

    chain_id = CHAIN_IDS[args.chain]
    chain_name = CHAIN_NAMES[args.chain]
    usdc_address = USDC_CONTRACTS[args.chain]

    print(f"Chain    : {chain_name} (chain_id={chain_id})")
    print(f"USDC     : {usdc_address}")
    print(f"Amount   : {args.amount / 1_000_000:.2f} USDC per address")
    print(f"Addresses: {len(addresses)}")
    print(f"Dry-run  : {args.dry_run}")
    print()

    # Web3 接続
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        if args.dry_run:
            print(f"[WARN] Cannot connect to RPC (dry-run: continuing anyway): {rpc_url}")
        else:
            print(f"[ERROR] Cannot connect to RPC: {rpc_url}", file=sys.stderr)
            sys.exit(1)

    # 送金元アドレス
    if not args.dry_run:
        sender_account = w3.eth.account.from_key(private_key)
        sender_address = sender_account.address
        print(f"Sender   : {sender_address}")
    else:
        fallback_addr = os.environ.get("AAVE_WALLET_ADDRESS", "")
        sender_address = fallback_addr or "0x0000000000000000000000000000000000000000"
        if fallback_addr:
            print(f"Sender   : {sender_address} (from AAVE_WALLET_ADDRESS, dry-run)")

    # コントラクト初期化
    usdc_contract = w3.eth.contract(
        address=Web3.to_checksum_address(usdc_address),
        abi=ERC20_TRANSFER_ABI,
    )

    # 送金元残高確認
    if not args.dry_run:
        balance = usdc_contract.functions.balanceOf(sender_address).call()
        total_needed = args.amount * len(addresses)
        print(
            f"Balance  : {balance / 1_000_000:.2f} USDC (need {total_needed / 1_000_000:.2f} USDC)"
        )
        if balance < total_needed:
            print("[ERROR] Insufficient USDC balance.", file=sys.stderr)
            sys.exit(1)
        print()

    # 一括送金
    success_count = 0
    fail_count = 0

    for i, raw_addr in enumerate(addresses, start=1):
        recipient = validate_address(raw_addr)
        print(f"[{i}/{len(addresses)}] Sending to {recipient} ...", end=" ")

        try:
            tx_hash = send_usdc(
                w3=w3,
                contract=usdc_contract,
                sender_address=sender_address,
                private_key=private_key,
                recipient=recipient,
                amount_units=args.amount,
                chain_id=chain_id,
                dry_run=args.dry_run,
            )
            if args.dry_run:
                success_count += 1
            elif tx_hash:
                print(f"OK (tx={tx_hash[:20]}...)")
                success_count += 1
            else:
                print("FAILED (tx reverted)")
                fail_count += 1
        except Exception as exc:
            print(f"ERROR: {exc}")
            fail_count += 1

    print()
    print(f"Done. Success: {success_count}, Failed: {fail_count}")
    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
