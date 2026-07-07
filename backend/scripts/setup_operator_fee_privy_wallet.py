#!/usr/bin/env python3
# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/scripts/setup_operator_fee_privy_wallet.py
"""operator fee wallet を Privy Server Wallet 化するセットアップツール（1回実施）。

生鍵 ``OPERATOR_FEE_WALLET_KEY`` を env から排除し、手数料徴収 wallet を Privy Server
Wallet 化するための policy 作成 + server wallet 作成を行う。作成後に得られる wallet ID /
address を env（``OPERATOR_FEE_PRIVY_WALLET_ID`` / ``OPERATOR_FEE_WALLET_ADDRESS``）へ
保存し、``FEE_SIGNING_MODE=privy`` に切り替えることで生鍵経路を置換する。

⚠️ これは Privy アプリへの **設定変更**である。実施前に必ず小林さんに確認すること。
既定は ``--dry-run``（Privy に投げず body を表示するのみ）。実行は ``--apply`` を明示。

前提:
  - key quorum(L0) 登録済み → ``PRIVY_SERVER_SIGNER_ID``（未登録なら
    ``privy_register_key_quorum.py`` を先に実施）
  - ``PRIVY_APP_ID`` / ``PRIVY_APP_SECRET``（Basic auth）
  - aToken(aUSDC) アドレスは Aave data provider から解決（``--atoken`` で明示も可）

使い方::

    # 1) policy body を確認（Privy に投げない）
    PRIVY_APP_ID=... PRIVY_APP_SECRET=... \
      python backend/scripts/setup_operator_fee_privy_wallet.py --chain base_sepolia --atoken 0x...

    # 2) 実際に policy + wallet を作成
    PRIVY_APP_ID=... PRIVY_APP_SECRET=... PRIVY_SERVER_SIGNER_ID=... \
      python backend/scripts/setup_operator_fee_privy_wallet.py \
        --chain base_sepolia --atoken 0x... --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# backend/ を import パスに追加（リポジトリ直叩き実行に対応）
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from app.privy.policy_mapper import PolicyMappingError, build_operator_fee_policy  # noqa: E402
from app.privy.rest_client import PrivyRestClient, PrivyRestError  # noqa: E402


def _resolve_atoken(chain_name: str) -> str:
    """Aave data provider から aUSDC の aToken アドレスを解決する（--atoken 省略時）。"""
    from app.fees.fee_transfer_service import FeeTransferConfig, FeeTransferService  # noqa: PLC0415

    cfg = FeeTransferConfig.from_env(chain_name)
    svc = FeeTransferService(cfg)
    w3 = svc._get_w3()  # noqa: SLF001 — セットアップ用途で内部 helper を利用
    atoken = svc._get_atoken_address(w3)  # noqa: SLF001
    if not atoken:
        raise RuntimeError(
            "aToken アドレスを解決できません（RPC / data_provider / usdc の env を確認）。"
            "--atoken で明示指定してください。"
        )
    return atoken


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Set up operator fee Privy server wallet.")
    p.add_argument("--chain", default="base_sepolia", help="執行チェーン名（base / base_sepolia）")
    p.add_argument("--atoken", default="", help="aUSDC の aToken アドレス（省略時は RPC で解決）")
    p.add_argument("--apply", action="store_true", help="実際に Privy へ作成する（既定は dry-run）")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)

    app_id = os.getenv("PRIVY_APP_ID", "")
    app_secret = os.getenv("PRIVY_APP_SECRET", "")
    if not app_id or not app_secret:
        print("ERROR: PRIVY_APP_ID / PRIVY_APP_SECRET が未設定です。", file=sys.stderr)
        return 2

    atoken = args.atoken.strip()
    if not atoken:
        try:
            atoken = _resolve_atoken(args.chain)
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: aToken 解決失敗: {exc}", file=sys.stderr)
            return 2

    try:
        policy = build_operator_fee_policy(atoken_address=atoken, chain_name=args.chain)
    except PolicyMappingError as exc:
        print(f"ERROR: policy 写像失敗: {exc}", file=sys.stderr)
        return 2

    print("=== operator fee wallet Privy 化セットアップ ===")
    print(f"chain           : {args.chain}")
    print(f"aToken(aUSDC)   : {atoken}")
    print("policy body     :")
    print(json.dumps(policy, indent=2, ensure_ascii=False))

    if not args.apply:
        print("\n[dry-run] Privy には投げていません。--apply で policy + wallet を作成します。")
        return 0

    signer_id = os.getenv("PRIVY_SERVER_SIGNER_ID", "").strip()
    if not signer_id:
        print(
            "ERROR: PRIVY_SERVER_SIGNER_ID が未設定です。"
            "（先に privy_register_key_quorum.py で L0 登録）",
            file=sys.stderr,
        )
        return 2

    client = PrivyRestClient(app_id=app_id, app_secret=app_secret)

    # 1) policy 作成
    try:
        policy_result = client.create_policy(policy)
    except PrivyRestError as exc:
        print(f"ERROR: policy 作成失敗: {exc}", file=sys.stderr)
        return 1
    policy_id = str(policy_result.get("id", "")).strip()
    if not policy_id:
        print("ERROR: Privy が policy id を返しませんでした。", file=sys.stderr)
        return 1
    print(f"\n✅ policy 作成成功: policy_id={policy_id}")

    # 2) server wallet 作成（policy + signer を紐付け）
    wallet_body = {
        "chain_type": "ethereum",
        "policy_ids": [policy_id],
        "authorization_key_ids": [signer_id],
    }
    try:
        wallet_result = client.create_wallet(wallet_body)
    except PrivyRestError as exc:
        print(f"ERROR: server wallet 作成失敗: {exc}", file=sys.stderr)
        return 1
    wallet_id = str(wallet_result.get("id", "")).strip()
    wallet_address = str(wallet_result.get("address", "")).strip()
    print("\n✅ server wallet 作成成功")
    print(f"OPERATOR_FEE_PRIVY_WALLET_ID={wallet_id}")
    print(f"OPERATOR_FEE_WALLET_ADDRESS={wallet_address}")
    print(
        "\n→ backend env に上記 2 値 + FEE_SIGNING_MODE=privy を保存してください。\n"
        "  旧 OPERATOR_FEE_WALLET_KEY(生鍵) は Privy 経路確立の検証後に env から削除する。\n"
        "  ⚠️ ユーザーの aToken allowance は新 operator address 宛に再承認が必要な点に注意。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
