#!/usr/bin/env python3
"""
ブラウザ partner 承認パス 実機検証スクリプト (staging / Base Sepolia 専用)。

PR #549 の「ブラウザ partner 承認」修正を、既存の pending SUPPLY proposals に対して
API 経由で end-to-end 検証する。

  /auth/wallet/connect 相当の JWT 取得
  → GET /api/proposals/{id}/build-tx (未署名 tx 取得)
  → approve tx 署名・broadcast
  → supply tx 署名・broadcast
  → POST /api/proposals/{id}/submit-tx
  → on-chain receipt 検証 (from==partner / onBehalfOf==partner / status==1 / server鍵不在)

使い方 (staging VPS 上で):
  export PARTNER_KEY_FILE=/path/to/key_file_user25  # mode 600
  export PARTNER_ADDRESS=0xd248...   # user_id=25 wallet
  python3 scripts/verify_browser_partner_approval.py --proposal-id 3

  # user_id=26 / proposal_id=4:
  export PARTNER_KEY_FILE=/path/to/key_file_user26
  export PARTNER_ADDRESS=0xf004...
  python3 scripts/verify_browser_partner_approval.py --proposal-id 4

既存 user/proposal は DB から取得。user/proposal の新規作成は行わない。

セキュリティ (§13):
  - 秘密鍵は PARTNER_KEY_FILE (mode 600) 経由のみ。ログ/出力に一切出さない。
  - testnet (Base Sepolia / chain_id=84532) でのみ動作。本番拒否。
  - AAVE_WALLET_* はこのスクリプトの署名に使わない。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path

try:
    from eth_account import Account
    from web3 import Web3
except ImportError:
    print("ERROR: web3 / eth-account が未インストール (backend/.venv で実行してください)")
    sys.exit(1)

POOL_ADDRESS = "0x8bAB6d1b75f19e9eD9fCe8b9BD338844fF79aE27"
USDC_ADDRESS = "0xba50cd2a20f6da35d788639e581bca8d0b5d4d5f"
USDC_DECIMALS = 6
SUPPLY_SELECTOR = "0x617ba037"  # supply(address,uint256,address,uint16)

ERC20_ABI = [
    {
        "name": "allowance",
        "type": "function",
        "inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "balanceOf",
        "type": "function",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]


def _fail(msg: str) -> None:
    print(f"ERROR: {msg}")
    sys.exit(1)


def load_partner_key() -> str:
    """PARTNER_KEY_FILE (mode 600) から秘密鍵を読む。"""
    key_file = os.environ.get("PARTNER_KEY_FILE")
    if not key_file:
        _fail("PARTNER_KEY_FILE が未設定です (秘密鍵は環境変数直接でなくファイル経由)")
    p = Path(key_file)
    if not p.exists():
        _fail(f"PARTNER_KEY_FILE が見つかりません: {key_file}")
    perm = oct(p.stat().st_mode)[-3:]
    if perm not in ("600", "400"):
        print(f"WARN: {key_file} のパーミッションが {perm} (600 推奨)")
    return p.read_text().strip()


def _http_json(method: str, url: str, token: str, body: dict | None = None) -> tuple[int, dict]:
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


def _sign_and_send(
    w3: Web3, unsigned: dict, partner_key: str, partner_addr: str, chain_id: int, gas: int
) -> str:
    nonce = w3.eth.get_transaction_count(Web3.to_checksum_address(partner_addr), "pending")
    tx = {
        "to": Web3.to_checksum_address(unsigned["to"]),
        "data": unsigned["data"],
        "from": Web3.to_checksum_address(partner_addr),
        "value": int(unsigned.get("value", "0x0"), 16)
        if isinstance(unsigned.get("value"), str)
        else int(unsigned.get("value", 0)),
        "nonce": nonce,
        "gas": gas,
        "gasPrice": w3.eth.gas_price,
        "chainId": chain_id,
    }
    signed = w3.eth.account.sign_transaction(tx, private_key=partner_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    return "0x" + tx_hash.hex() if not tx_hash.hex().startswith("0x") else tx_hash.hex()


def _decode_on_behalf_of(supply_data: str) -> str:
    """supply calldata から onBehalfOf (第3引数) を抽出。"""
    raw = supply_data[2:] if supply_data.startswith("0x") else supply_data
    if raw[:8].lower() != SUPPLY_SELECTOR[2:]:
        return ""
    word = raw[8 + 64 * 2 : 8 + 64 * 3]
    return "0x" + word[-40:]


def main() -> None:
    parser = argparse.ArgumentParser(description="ブラウザ partner 承認パス 実機検証 (staging 専用)")
    parser.add_argument("--proposal-id", type=int, required=True, help="検証対象 proposal ID (例: 3)")
    parser.add_argument("--api-base", default=os.environ.get("API_BASE", "http://127.0.0.1:8082"))
    parser.add_argument("--dry-run", action="store_true", help="前提確認のみ (tx 送信しない)")
    args = parser.parse_args()

    # staging ガード
    app_env = os.environ.get("APP_ENV", "")
    if app_env != "staging":
        _fail(f"APP_ENV={app_env!r} — 本スクリプトは staging 専用です")

    rpc_url = os.environ.get("ALCHEMY_RPC_URL_BASE_SEPOLIA") or os.environ.get(
        "AAVE_RPC_URL", "https://sepolia.base.org"
    )
    server_addr = os.environ.get("AAVE_WALLET_ADDRESS", "")

    partner_key = load_partner_key()
    try:
        partner_account = Account.from_key(partner_key)
    except Exception as e:  # noqa: BLE001
        _fail(f"鍵が無効です: {e}")
    partner_addr = Web3.to_checksum_address(
        os.environ.get("PARTNER_ADDRESS") or partner_account.address
    )
    if partner_account.address.lower() != partner_addr.lower():
        _fail(f"鍵のアドレスと PARTNER_ADDRESS 不一致: {partner_account.address} != {partner_addr}")

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    chain_id = w3.eth.chain_id
    if chain_id != 84532:
        _fail(f"chain_id={chain_id} は Base Sepolia (84532) ではありません")

    print("=== ブラウザ partner 承認パス 実機検証 (PR #549 / staging / Base Sepolia) ===")
    print(f"Proposal ID : {args.proposal_id}")
    print(f"Partner     : {partner_addr}")
    print(f"Server      : {server_addr} (署名には使わない)")
    print(f"API         : {args.api_base}")
    print()

    # ETH/USDC 残高確認
    usdc = w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=ERC20_ABI)
    eth_bal = w3.from_wei(w3.eth.get_balance(partner_addr), "ether")
    usdc_bal = Decimal(usdc.functions.balanceOf(partner_addr).call()) / Decimal(10**USDC_DECIMALS)
    print(f"Partner ETH : {eth_bal:.6f}")
    print(f"Partner USDC: {usdc_bal:.6f}")
    if eth_bal < Decimal("0.001"):
        _fail("ETH 残高不足 (gas 用に最低 0.001 ETH 必要)")
    if usdc_bal < Decimal("1.0"):
        _fail(f"USDC 残高不足 ({usdc_bal} < 1.0 — fund 未実施?)")

    # backend ORM で user/proposal 情報取得 + JWT 発行
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
    from app.auth.models import User  # noqa: PLC0415
    from app.auth.service import AuthService  # noqa: PLC0415
    from app.database import SessionLocal  # noqa: PLC0415
    from app.proposals.models import Proposal  # noqa: PLC0415
    from sqlalchemy import select  # noqa: PLC0415

    db = SessionLocal()
    try:
        proposal = db.scalars(
            select(Proposal).where(Proposal.id == args.proposal_id)
        ).first()
        if proposal is None:
            _fail(f"proposal id={args.proposal_id} が見つかりません")
        if proposal.status != "pending":
            _fail(
                f"proposal id={args.proposal_id} は status='{proposal.status}' (pending でないと実行不可)"
            )
        if proposal.operation not in ("SUPPLY",):
            _fail(f"本スクリプトは SUPPLY のみ対応 (operation={proposal.operation})")

        user = db.scalars(select(User).where(User.id == proposal.user_id)).first()
        if user is None:
            _fail(f"proposal.user_id={proposal.user_id} のユーザーが見つかりません")
        if not user.wallet_address:
            _fail(f"user_id={user.id} の wallet_address が未設定です")

        # partner wallet と鍵の整合確認
        if user.wallet_address.lower() != partner_addr.lower():
            _fail(
                f"DB の wallet_address={user.wallet_address[:10]}... と "
                f"PARTNER_ADDRESS={partner_addr[:10]}... が一致しません"
            )

        amount = Decimal(str(proposal.amount_usd))
        amount_wei = int(amount * Decimal(10**USDC_DECIMALS))
        user_id, user_email = user.id, user.email
        print(f"[DB] user_id={user_id} ({user_email}) / proposal_id={proposal.id}")
        print(f"     operation={proposal.operation} / asset={proposal.asset} / amount={amount} USDC")
    finally:
        db.close()

    if usdc_bal < amount:
        _fail(f"USDC 残高不足 ({usdc_bal} < {amount})")

    if args.dry_run:
        print("\nDRY RUN: 前提 OK。--dry-run なしで実行すると実 tx を送信します。")
        return

    # JWT 発行 (AuthService 経由 — /auth/wallet/connect 相当)
    token, _ = AuthService.create_access_token(user_id=user_id, email=user_email, role="partner")
    print(f"  JWT 発行済 (user_id={user_id})")

    # --- Step 1: build-tx API ---
    print(f"\n[Step 1] GET build-tx (proposal_id={args.proposal_id})")
    code, build = _http_json(
        "GET", f"{args.api_base}/api/proposals/{args.proposal_id}/build-tx", token
    )
    if code != 200:
        _fail(f"build-tx HTTP {code}: {build.get('detail')}")
    approve_tx = build.get("approve_tx")
    supply_tx = build.get("supply_tx")
    if not approve_tx or not supply_tx:
        _fail(f"build-tx に approve_tx/supply_tx がありません: {list(build.keys())}")
    on_behalf = _decode_on_behalf_of(supply_tx["data"])
    print(f"  build-tx 200 / supply onBehalfOf(decode)={on_behalf}")
    if on_behalf.lower() != partner_addr.lower():
        _fail(f"build-tx の onBehalfOf が partner でない: {on_behalf} != {partner_addr}")

    # --- Step 2: approve broadcast ---
    print("\n[Step 2] approve 署名・broadcast (from=partner)")
    approve_hash = _sign_and_send(w3, approve_tx, partner_key, partner_addr, chain_id, gas=100000)
    print(f"  approve tx: {approve_hash}")
    r_approve = w3.eth.wait_for_transaction_receipt(approve_hash, timeout=120)
    if r_approve["status"] != 1:
        _fail("approve tx が revert しました")
    pool_cs = Web3.to_checksum_address(POOL_ADDRESS)
    for _ in range(15):
        if usdc.functions.allowance(partner_addr, pool_cs).call() >= amount_wei:
            break
        time.sleep(2)
    else:
        _fail("allowance が反映されません")

    # --- Step 3: supply broadcast ---
    print("\n[Step 3] supply 署名・broadcast (from=partner, onBehalfOf=partner)")
    supply_hash = _sign_and_send(w3, supply_tx, partner_key, partner_addr, chain_id, gas=300000)
    print(f"  supply tx: {supply_hash}")
    r_supply = w3.eth.wait_for_transaction_receipt(supply_hash, timeout=120)
    if r_supply["status"] != 1:
        _fail("supply tx が revert しました")

    # --- Step 4: submit-tx API ---
    print("\n[Step 4] POST submit-tx")
    code, sub = _http_json(
        "POST",
        f"{args.api_base}/api/proposals/{args.proposal_id}/submit-tx",
        token,
        {"tx_hash": supply_hash, "wallet_address": partner_addr},
    )
    if code != 200:
        _fail(f"submit-tx HTTP {code}: {sub.get('detail')}")
    executed = sub.get("status") == "executed"
    print(f"  submit-tx 200 / proposal.status={sub.get('status')}")

    # --- on-chain DoD 検証 ---
    server_l = (server_addr or "").lower()
    checks = {
        "1. approve/supply from = partner": r_approve["from"].lower() == partner_addr.lower()
        and r_supply["from"].lower() == partner_addr.lower(),
        "2. supply onBehalfOf = partner": on_behalf.lower() == partner_addr.lower(),
        "3. supply.to = Aave Pool": str(r_supply.get("to", "")).lower() == POOL_ADDRESS.lower(),
        "4. サーバー鍵 (AAVE_WALLET) が署名者でない": bool(server_l)
        and server_l != partner_addr.lower()
        and r_supply["from"].lower() != server_l
        and r_approve["from"].lower() != server_l,
        "5. status = 1 (approve + supply)": r_approve["status"] == 1 and r_supply["status"] == 1,
        "6. proposal executed 遷移": executed,
    }
    print("\n=== on-chain DoD 5 項目検証 ===")
    all_ok = True
    for label, ok in checks.items():
        print(f"  {'PASS' if ok else 'FAIL'}: {label}")
        all_ok = all_ok and ok

    print()
    print(f"  approve: https://sepolia.basescan.org/tx/{approve_hash}")
    print(f"  supply : https://sepolia.basescan.org/tx/{supply_hash}")

    if all_ok:
        print(f"\n✅ PASS: proposal_id={args.proposal_id} / PR #549 ブラウザ partner 承認 on-chain 検証完了")
        print(f"  from={partner_addr[:10]}... / onBehalfOf={partner_addr[:10]}... / status=1 / server鍵不在")
    else:
        print("\n❌ FAIL: 上記 FAIL 項目を確認")
        sys.exit(1)


if __name__ == "__main__":
    main()
