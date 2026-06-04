#!/usr/bin/env python3
"""
Proposal lifecycle E2E 実証スクリプト (staging / Base Sepolia testnet 専用)。

non-custodial 方式2 の **API ライフサイクル**を 1 本で実証する:
  build-tx API → partner 鍵で署名 → broadcast → submit-tx API → executed 遷移
  → on-chain 検証 (status=1 / from=partner / onBehalfOf=partner / サーバー鍵不在)。

既存の verify_non_custodial_staging.py は approve/supply を **ローカル構築**するため
backend の build-tx / submit-tx API も proposal lifecycle も通らない。本スクリプトは
`GET /api/proposals/{id}/build-tx` の返す未署名 tx を署名・broadcast し、
`POST /api/proposals/{id}/submit-tx` で executed 遷移まで検証する = §7 money ゲート
(「誰の資産が動いたか」) を実 tx で固定する恒久 E2E。

【重要】これは API/on-chain lifecycle の実証であり、実 partner の Privy 署名経路の
実証ではない。実 partner (Privy embedded wallet) は秘密鍵がサーバーに無く、CLI からは
署名できない (= non-custodial 設計の正)。本スクリプトは CLI が鍵を持つ testnet 専用
test wallet を使い、API + on-chain メカニクスを検証する。実 partner 経路の検証は
LINE LIFF + Privy セットアップ後に別途行う。

セキュリティ (§13):
  - 秘密鍵は PARTNER_KEY_FILE (mode 600) 経由でのみ読み込み、ログ/出力に一切出さない。
  - サーバー鍵 (AAVE_WALLET_*) は本スクリプトの署名に一切使わない (fund は別スクリプト)。
  - testnet (Base Sepolia / chain_id=84532) でのみ動作。本番では起動拒否。

前提:
  - PARTNER_KEY_FILE に test wallet 秘密鍵 (mode 600)。fund 済 (ETH gas + USDC>=amount)。
    通常は run_proposal_lifecycle_e2e.sh が wallet 生成 → fund → 本スクリプト実行を orchestrate。
  - .env.staging-new 相当の env がロード済 (DATABASE_URL / APP_ENV=staging /
    ALCHEMY_RPC_URL_BASE_SEPOLIA or AAVE_RPC_URL / AAVE_WALLET_ADDRESS)。
  - backend パッケージが import 可能 (PYTHONPATH=backend、backend/.venv)。

使い方:
  export PARTNER_KEY_FILE=/tmp/.partner_test_key_xxx
  export PARTNER_ADDRESS=0x...
  python3 scripts/verify_proposal_lifecycle_staging.py [--amount 1.0] [--api-base http://127.0.0.1:8082]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
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
    """PARTNER_KEY_FILE (mode 600) から秘密鍵を読む。CLI arg からは取らない (§13)。"""
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
    """API を叩いて (status_code, json) を返す。"""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)  # noqa: S310 (localhost API)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (localhost API)
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
    """build-tx が返す未署名 tx (to/data/from/chainId/value) に nonce/gas/gasPrice を補い、
    partner 鍵で署名・broadcast して tx_hash (0x...) を返す。"""
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
    """supply calldata から onBehalfOf (第3引数) を抽出。
    layout: selector(4) + asset(32) + amount(32) + onBehalfOf(32) + referralCode(32)。"""
    raw = supply_data[2:] if supply_data.startswith("0x") else supply_data
    if raw[:8].lower() != SUPPLY_SELECTOR[2:]:
        return ""
    # onBehalfOf = 3rd 32-byte word (offset 8 + 64*2 = 136 hex chars), 末尾 40 hex = address
    word = raw[8 + 64 * 2 : 8 + 64 * 3]
    return "0x" + word[-40:]


def main() -> None:
    parser = argparse.ArgumentParser(description="Proposal lifecycle E2E (staging 専用)")
    parser.add_argument("--amount", type=float, default=1.0, help="SUPPLY USDC 量")
    parser.add_argument("--api-base", default=os.environ.get("API_BASE", "http://127.0.0.1:8082"))
    parser.add_argument("--dry-run", action="store_true", help="DB/tx を作らず前提確認のみ")
    args = parser.parse_args()

    # --- testnet ガード ---
    app_env = os.environ.get("APP_ENV", "")
    if app_env != "staging":
        _fail(f"APP_ENV={app_env!r} — 本スクリプトは staging 専用です (本番では実行禁止)")

    rpc_url = os.environ.get("ALCHEMY_RPC_URL_BASE_SEPOLIA") or os.environ.get(
        "AAVE_RPC_URL", "https://sepolia.base.org"
    )
    server_addr = os.environ.get("AAVE_WALLET_ADDRESS", "")
    amount = Decimal(str(args.amount))
    amount_wei = int(amount * Decimal(10**USDC_DECIMALS))

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

    print("=== Proposal lifecycle E2E (staging / Base Sepolia) ===")
    print(f"Partner: {partner_addr}")
    print(f"Server : {server_addr} (署名には一切使わない)")
    print(f"Amount : {amount} USDC / API: {args.api_base}")
    print()

    usdc = w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=ERC20_ABI)
    eth_bal = w3.from_wei(w3.eth.get_balance(partner_addr), "ether")
    usdc_bal = Decimal(usdc.functions.balanceOf(partner_addr).call()) / Decimal(10**USDC_DECIMALS)
    print(f"Partner ETH : {eth_bal:.6f}")
    print(f"Partner USDC: {usdc_bal:.6f}")
    if eth_bal < Decimal("0.001"):
        _fail("ETH 残高不足 (gas 用に最低 0.001 ETH 必要 — fund 未実施?)")
    if usdc_bal < amount:
        _fail(f"USDC 残高不足 ({usdc_bal} < {amount} — fund 未実施?)")

    if args.dry_run:
        print("DRY RUN: 前提 OK。--dry-run なしで実行すると DB write + 実 tx を送信します。")
        return

    # --- backend ORM で test partner user + proposal 作成 ---
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
    from app.auth.models import User  # noqa: PLC0415
    from app.auth.service import AuthService  # noqa: PLC0415
    from app.database import SessionLocal  # noqa: PLC0415
    from app.proposals.models import Proposal  # noqa: PLC0415

    ts = int(time.time())
    db = SessionLocal()
    try:
        user = User(
            email=f"e2e-lifecycle-{ts}@ultra-autotrade.com",
            username=f"e2e-lifecycle-{ts}",
            hashed_password="!e2e-no-login!",  # noqa: S106 (ログイン不可のダミー、token は直生成)
            role="partner",
            is_active=True,
            wallet_address=partner_addr,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        proposal = Proposal(
            user_id=user.id,
            operation="SUPPLY",
            asset="USDC",
            amount=amount,
            amount_usd=amount,
            reason="proposal lifecycle on-chain E2E (staging, testnet)",
            status="pending",
            expires_at=datetime.now(UTC) + timedelta(hours=72),
        )
        db.add(proposal)
        db.commit()
        db.refresh(proposal)
        user_id, proposal_id, user_email = user.id, proposal.id, user.email
    finally:
        db.close()

    print(f"\n[DB] test partner user_id={user_id} / proposal_id={proposal_id}")
    token, _ = AuthService.create_access_token(user_id=user_id, email=user_email, role="partner")

    # --- build-tx API ---
    print("\n[Step 1] GET build-tx")
    code, build = _http_json("GET", f"{args.api_base}/api/proposals/{proposal_id}/build-tx", token)
    if code != 200:
        _fail(f"build-tx HTTP {code}: {build.get('detail')}")
    approve_tx = build.get("approve_tx")
    supply_tx = build.get("supply_tx")
    if not approve_tx or not supply_tx:
        _fail(f"build-tx に approve_tx/supply_tx がありません: {build}")
    on_behalf = _decode_on_behalf_of(supply_tx["data"])
    print(f"  build-tx 200 / supply onBehalfOf(decode)={on_behalf}")
    if on_behalf.lower() != partner_addr.lower():
        _fail(f"build-tx の onBehalfOf が partner でない: {on_behalf} != {partner_addr}")

    # --- approve broadcast ---
    print("\n[Step 2] approve 署名・broadcast (from=partner)")
    approve_hash = _sign_and_send(w3, approve_tx, partner_key, partner_addr, chain_id, gas=100000)
    print(f"  approve tx: {approve_hash}")
    r_approve = w3.eth.wait_for_transaction_receipt(approve_hash, timeout=120)
    if r_approve["status"] != 1:
        _fail("approve tx が revert しました")
    # allowance ポーリング (public RPC ステートラグ対策)
    pool_cs = Web3.to_checksum_address(POOL_ADDRESS)
    for _ in range(15):
        if usdc.functions.allowance(partner_addr, pool_cs).call() >= amount_wei:
            break
        time.sleep(2)
    else:
        _fail("allowance が反映されません")

    # --- supply broadcast ---
    print("\n[Step 3] supply 署名・broadcast (from=partner, onBehalfOf=partner)")
    supply_hash = _sign_and_send(w3, supply_tx, partner_key, partner_addr, chain_id, gas=300000)
    print(f"  supply tx: {supply_hash}")
    r_supply = w3.eth.wait_for_transaction_receipt(supply_hash, timeout=120)
    if r_supply["status"] != 1:
        _fail("supply tx が revert しました")

    # --- submit-tx API ---
    print("\n[Step 4] POST submit-tx")
    code, sub = _http_json(
        "POST",
        f"{args.api_base}/api/proposals/{proposal_id}/submit-tx",
        token,
        {"tx_hash": supply_hash, "wallet_address": partner_addr},
    )
    if code != 200:
        _fail(f"submit-tx HTTP {code}: {sub.get('detail')}")
    executed = sub.get("status") == "executed"
    print(f"  submit-tx 200 / proposal.status={sub.get('status')}")

    # --- on-chain 5 項目検証 ---
    print("\n=== on-chain 5 項目検証 ===")
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
    all_ok = True
    for label, ok in checks.items():
        print(f"  {'PASS' if ok else 'FAIL'}: {label}")
        all_ok = all_ok and ok

    print()
    print(f"  approve: https://sepolia.basescan.org/tx/{approve_hash}")
    print(f"  supply : https://sepolia.basescan.org/tx/{supply_hash}")
    print(f"\n  cleanup: test user_id={user_id} / proposal_id={proposal_id} は staging DB に残置")
    print("  (検証用。不要なら手動削除。本番 DB には一切作成していない)")

    if all_ok:
        print("\n✅ PASS: API lifecycle 完走 + on-chain non-custodial メカニクス実証")
        print("  partner の USDC が partner 帰属で Aave supply、サーバー鍵は非署名。")
    else:
        print("\n❌ FAIL: 上記 FAIL 項目を確認")
        sys.exit(1)


if __name__ == "__main__":
    main()
