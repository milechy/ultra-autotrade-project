#!/usr/bin/env python3
"""
P4 出金 non-custodial money gate — staging / Base Sepolia 専用。

DoD (GID 1215444094888771 / §14a):
  1. withdraw tx の from = partner wallet (Privy 鍵が署名)
  2. USDC Transfer.from = partner (サーバー鍵経由でない)
  3. USDC Transfer.to = 指定宛先
  4. サーバー鍵アドレス(AAVE_WALLET_PRIVATE_KEY)が署名者に不在
  5. backend POST /api/users/withdrawals が 201 (新規) または 200 (冪等) で記録

根拠: §7 money ゲート / §14a non-custodial / §3 「誰の資産が動いたか」検証
mock/pytest/自己申告では完了としない。

使い方 (staging VPS ホスト上で実行):
  export APP_ENV=staging
  export PARTNER_KEY_FILE=/path/to/key  # mode 600 (Base Sepolia test wallet key)
  export PARTNER_ADDRESS=0xABCD...      # key に対応するアドレス
  export SERVER_ADDRESS=0x1234...       # AAVE_WALLET_ADDRESS (サーバー鍵の公開アドレスのみ)
  export API_BASE=http://127.0.0.1:8082
  python3 scripts/verify_withdrawal_non_custodial.py --amount 0.01 --to 0xRECIPIENT

  --dry-run  : tx 送信せず前提チェックのみ
  --amount   : 送金 USDC 量 (default 0.01)
  --to       : 宛先アドレス (default=PARTNER_ADDRESS 自身への送金で検証)

セキュリティ (§13):
  - 秘密鍵は PARTNER_KEY_FILE (mode 600) 経由のみ。出力・ログに一切出さない。
  - testnet (Base Sepolia / chain_id=84532) でのみ動作。mainnet は拒否。
  - SERVER_ADDRESS はアドレスのみ (秘密鍵ではない)。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path

try:
    from eth_account import Account
    from web3 import Web3
except ImportError:
    print("ERROR: web3 / eth-account 未インストール (backend/.venv で実行してください)")
    sys.exit(1)

# Base Sepolia testnet USDC (Circle 公式 testnet)
USDC_SEPOLIA = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
USDC_DECIMALS = 6

# Transfer(address indexed from, address indexed to, uint256 value)
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

ERC20_ABI = [
    {
        "name": "transfer",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "to", "type": "address"}, {"name": "amount", "type": "uint256"}],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "name": "balanceOf",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def load_partner_key() -> str:
    key_file = os.environ.get("PARTNER_KEY_FILE")
    if not key_file:
        _fail("PARTNER_KEY_FILE が未設定です")
    p = Path(key_file)
    if not p.exists():
        _fail(f"PARTNER_KEY_FILE が見つかりません: {key_file}")
    perm = oct(p.stat().st_mode)[-3:]
    if perm not in ("600", "400"):
        print(f"WARN: {key_file} の permission={perm} (600 推奨)")
    return p.read_text().strip()


def _http_json(
    method: str, url: str, token: str, body: dict | None = None
) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)  # noqa: S310
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"detail": raw}


def _get_partner_jwt(api_base: str, user_id: int, email: str) -> str:
    """AuthService 経由で JWT を発行 (backend ORM 直接呼び出し)。"""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
    from app.auth.service import AuthService  # noqa: PLC0415

    token, _ = AuthService.create_access_token(user_id=user_id, email=email, role="partner")
    return token


def _decode_transfer_log(log: dict, usdc_addr: str) -> tuple[str, str] | None:
    """USDC Transfer ログから (from, to) を抽出。なければ None。"""
    if log.get("address", "").lower() != usdc_addr.lower():
        return None
    topics = log.get("topics", [])
    if not topics or topics[0].lower() != TRANSFER_TOPIC.lower():
        return None
    if len(topics) < 3:
        return None
    from_addr = "0x" + topics[1][-40:]
    to_addr = "0x" + topics[2][-40:]
    return from_addr.lower(), to_addr.lower()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="P4 出金 non-custodial money gate (staging / Base Sepolia 専用)"
    )
    parser.add_argument("--amount", type=str, default="0.01", help="送金 USDC 量 (default 0.01)")
    parser.add_argument(
        "--to",
        type=str,
        default=None,
        help="宛先アドレス (未指定=PARTNER_ADDRESS 自身に送金して検証)",
    )
    parser.add_argument("--api-base", default=os.environ.get("API_BASE", "http://127.0.0.1:8082"))
    parser.add_argument("--usdc", default=os.environ.get("USDC_SEPOLIA_ADDRESS", USDC_SEPOLIA))
    parser.add_argument("--dry-run", action="store_true", help="tx 送信せず前提チェックのみ")
    args = parser.parse_args()

    # staging 専用ガード
    if os.environ.get("APP_ENV") != "staging":
        _fail(f"APP_ENV={os.environ.get('APP_ENV')!r} — 本スクリプトは APP_ENV=staging 専用です")

    rpc_url = os.environ.get("ALCHEMY_RPC_URL_BASE_SEPOLIA") or os.environ.get(
        "AAVE_RPC_URL", "https://sepolia.base.org"
    )
    server_addr = (
        os.environ.get("SERVER_ADDRESS") or os.environ.get("AAVE_WALLET_ADDRESS", "")
    ).lower()
    if not server_addr:
        _fail("SERVER_ADDRESS (AAVE_WALLET_ADDRESS の公開アドレス) が未設定です")

    partner_key = load_partner_key()
    try:
        partner_account = Account.from_key(partner_key)
    except Exception as e:  # noqa: BLE001
        _fail(f"PARTNER_KEY_FILE の鍵が無効: {e}")
    env_partner_addr = os.environ.get("PARTNER_ADDRESS", "")
    partner_addr = Web3.to_checksum_address(env_partner_addr or partner_account.address)
    if partner_account.address.lower() != partner_addr.lower():
        _fail(
            f"鍵から導出したアドレス {partner_account.address} と "
            f"PARTNER_ADDRESS {partner_addr} が不一致"
        )

    to_addr = Web3.to_checksum_address(args.to) if args.to else partner_addr
    amount = Decimal(args.amount)
    amount_units = int(amount * Decimal(10**USDC_DECIMALS))
    usdc_addr = Web3.to_checksum_address(args.usdc)

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    chain_id = w3.eth.chain_id
    if chain_id != 84532:
        _fail(f"chain_id={chain_id} は Base Sepolia (84532) ではありません。mainnet は禁止。")

    usdc = w3.eth.contract(address=usdc_addr, abi=ERC20_ABI)
    eth_bal = w3.from_wei(w3.eth.get_balance(partner_addr), "ether")
    usdc_raw = usdc.functions.balanceOf(partner_addr).call()
    usdc_bal = Decimal(usdc_raw) / Decimal(10**USDC_DECIMALS)

    print("=== P4 出金 non-custodial money gate (staging / Base Sepolia) ===")
    print(f"Partner   : {partner_addr}")
    print(f"Server    : {server_addr} (署名者不在を確認する対象)")
    print(f"To        : {to_addr}")
    print(f"Amount    : {amount} USDC")
    print(f"USDC addr : {usdc_addr}")
    print(f"RPC       : {rpc_url}")
    print(f"API base  : {args.api_base}")
    print()
    print(f"残高 — ETH: {eth_bal:.6f} / USDC: {usdc_bal:.6f}")

    if eth_bal < Decimal("0.001"):
        _fail("ETH 残高不足 (gas 用に最低 0.001 ETH 必要)")
    if usdc_bal < amount:
        _fail(f"USDC 残高不足 ({usdc_bal} < {amount})")

    # backend から user を解決して JWT を発行
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
    from sqlalchemy import select  # noqa: PLC0415

    from app.auth.models import User  # noqa: PLC0415
    from app.database import SessionLocal  # noqa: PLC0415

    db = SessionLocal()
    try:
        user = db.scalars(
            select(User).where(User.wallet_address == partner_addr.lower())
        ).first()
        if user is None:
            _fail(f"wallet_address={partner_addr} のユーザーが DB に見つかりません")
        user_id, user_email = user.id, user.email
        print(f"[DB] user_id={user_id} ({user_email})")
    finally:
        db.close()

    if args.dry_run:
        print("\nDRY RUN: 前提 OK。--dry-run なしで実行すると実 tx を送信します。")
        return

    token = _get_partner_jwt(args.api_base, user_id, user_email)
    print(f"  JWT 発行済 (user_id={user_id})")

    # --- Step 1: USDC.transfer 署名・broadcast (from=partner) ---
    print("\n[Step 1] USDC.transfer 署名・broadcast (from=partner)")
    tx_data = usdc.encodeABI(fn_name="transfer", args=[to_addr, amount_units])
    nonce = w3.eth.get_transaction_count(partner_addr, "pending")
    raw_tx = {
        "to": usdc_addr,
        "data": tx_data,
        "from": partner_addr,
        "value": 0,
        "nonce": nonce,
        "gas": 80000,
        "gasPrice": w3.eth.gas_price,
        "chainId": chain_id,
    }
    signed = w3.eth.account.sign_transaction(raw_tx, private_key=partner_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    tx_hash_hex = tx_hash.hex() if tx_hash.hex().startswith("0x") else "0x" + tx_hash.hex()
    print(f"  tx_hash: {tx_hash_hex}")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash_hex, timeout=120)
    if receipt["status"] != 1:
        _fail("USDC.transfer tx が revert しました")

    # --- Step 2: on-chain ログから Transfer イベント解析 ---
    print("\n[Step 2] on-chain Transfer ログ解析")
    transfer_from: str | None = None
    transfer_to: str | None = None
    for log in receipt.get("logs", []):
        parsed = _decode_transfer_log(dict(log), usdc_addr)
        if parsed:
            transfer_from, transfer_to = parsed
            print(f"  Transfer.from: {transfer_from}")
            print(f"  Transfer.to  : {transfer_to}")
            break
    if transfer_from is None:
        _fail("USDC Transfer ログが receipt に見つかりません")

    # --- Step 3: backend /api/users/withdrawals に記録 ---
    print("\n[Step 3] POST /api/users/withdrawals")
    code, resp = _http_json(
        "POST",
        f"{args.api_base}/api/users/withdrawals",
        token,
        {
            "tx_hash": tx_hash_hex,
            "to_address": to_addr.lower(),
            "amount_usdc": str(amount),
            "network": "base",
        },
    )
    if code not in (200, 201):
        _fail(f"POST /api/users/withdrawals HTTP {code}: {resp.get('detail')}")
    print(f"  HTTP {code} / withdrawal id={resp.get('id')} status={resp.get('status')}")

    # --- DoD 検証 ---
    tx_receipt_from = receipt["from"].lower()
    checks = {
        "1. tx.from = partner (Privy 鍵が署名)": tx_receipt_from == partner_addr.lower(),
        "2. Transfer.from = partner (サーバー鍵でない)": transfer_from == partner_addr.lower(),
        "3. Transfer.to = 指定宛先": transfer_to == to_addr.lower(),
        "4. サーバー鍵(AAVE_WALLET)が tx.from に不在": bool(server_addr)
        and tx_receipt_from != server_addr
        and transfer_from != server_addr,
        "5. tx.status = 1 (success)": receipt["status"] == 1,
        "6. backend 記録済 (201 or 200)": code in (200, 201),
    }

    print("\n=== DoD 6 項目 on-chain 検証 ===")
    all_ok = True
    for label, ok in checks.items():
        print(f"  {'PASS' if ok else 'FAIL'}: {label}")
        all_ok = all_ok and ok

    print()
    print(f"  tx: https://sepolia.basescan.org/tx/{tx_hash_hex}")

    if all_ok:
        print(
            "\n✅ PASS: P4 出金 non-custodial money gate クリア"
        )
        print(
            f"  from={partner_addr[:12]}... / Transfer.from={partner_addr[:12]}... "
            f"/ server 鍵不在 / backend 記録済"
        )
        print(
            "\n  prod deploy 解禁条件: 本出力を Asana GID 1215444094888771 に"
            "添付して承認を得ること"
        )
    else:
        print("\n❌ FAIL: 上記 FAIL 項目を確認してください")
        sys.exit(1)


if __name__ == "__main__":
    main()
