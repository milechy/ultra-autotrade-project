#!/usr/bin/env python3
# Copyright (c) Ultra AutoTrade. All rights reserved.
"""
非カストディ Aave supply の DoD 1-4 を *既存の実 tx ハッシュ* から機械判定する CLI。

verify_non_custodial_staging.py は新規 tx を partner 鍵で *発行* して 1-3 を確認する
ライブ実証スクリプト。本スクリプトは対照的に、既に basescan 上に存在する supply tx
(例: P0-1 参照 tx 0xc819...) を入力に取り、RPC から calldata/receipt logs を取得して
DoD 1-4 を機械判定する。鍵不要・読み取り専用・冪等。

DoD (Asana P0-1 1215363789384766):
  1. from = 登録済 Privy Session Key 群 または partner wallet
  2. supply の onBehalfOf = 当該 partner の Privy wallet と完全一致
  3. aUSDC mint 先 = partner
  4. サーバー長期鍵 (0x04666D72...) が from / msg.sender / 全 internal tx 署名者に非出現

使い方:
  python3 scripts/verify_dod_onchain.py \
      --tx 0xc819b1407a9e9ecedc36b823543b423cf281c73e5573b8b2bca1d8bccf1aa2eb \
      --partner 0x7f93e7D52428A33cA36acD5D7B1C576d5182a0Ff \
      [--atoken 0x10F1A9D11CDf50041f3f8cB7191CBE2f31750ACC] \
      [--session-key 0x...] [--server-key 0x...] \
      [--rpc https://sepolia.base.org]

終了コード: DoD 1-4 全 PASS なら 0、いずれか FAIL なら 1。
"""

from __future__ import annotations

import argparse
import os
import sys

# backend/app をパスに追加 (scripts/ から見て ../backend)
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend"))

from app.aave.dod_verifier import (  # noqa: E402
    DEFAULT_SERVER_KEYS,
    evaluate_dod,
)


def _normalize_logs(receipt_logs: object) -> list[dict[str, object]]:
    """web3 の receipt.logs を dod_verifier が期待する dict 形へ正規化する。"""
    out: list[dict[str, object]] = []
    for log in receipt_logs:  # type: ignore[union-attr]
        topics = [t.hex() if hasattr(t, "hex") else str(t) for t in log["topics"]]
        out.append(
            {
                "address": str(log["address"]),
                "topics": topics,
                "data": log["data"].hex() if hasattr(log["data"], "hex") else str(log["data"]),
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Aave supply DoD 1-4 on-chain 機械判定")
    parser.add_argument("--tx", required=True, help="検証対象の supply tx ハッシュ")
    parser.add_argument("--partner", required=True, help="partner wallet アドレス")
    parser.add_argument("--atoken", default=None, help="aUSDC (aToken) アドレス (DoD3 を厳密化)")
    parser.add_argument(
        "--session-key", action="append", default=[], help="登録済 Privy session key (複数可)"
    )
    parser.add_argument(
        "--server-key",
        action="append",
        default=None,
        help="サーバー長期鍵 (複数可)。未指定なら既定 0x04666D72...",
    )
    parser.add_argument(
        "--rpc",
        default=os.environ.get("AAVE_RPC_URL_BASE_SEPOLIA", "https://sepolia.base.org"),
        help="RPC URL (既定: Base Sepolia)",
    )
    args = parser.parse_args()

    try:
        from web3 import Web3
    except ImportError:
        print("ERROR: web3 が未インストール。pip install web3", file=sys.stderr)
        return 2

    w3 = Web3(Web3.HTTPProvider(args.rpc))
    if not w3.is_connected():
        print(f"ERROR: RPC に接続できません: {args.rpc}", file=sys.stderr)
        return 2

    print("=== Aave supply DoD 1-4 on-chain 機械判定 ===")
    print(f"tx:      {args.tx}")
    print(f"partner: {args.partner}")
    print(f"rpc:     {args.rpc} (chain {w3.eth.chain_id})")
    print()

    try:
        tx = w3.eth.get_transaction(args.tx)
        receipt = w3.eth.get_transaction_receipt(args.tx)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: tx 取得失敗: {type(e).__name__}: {e}", file=sys.stderr)
        return 2

    if receipt["status"] != 1:
        print(f"ERROR: tx が revert (status={receipt['status']})", file=sys.stderr)
        return 1

    tx_input = tx["input"].hex() if hasattr(tx["input"], "hex") else str(tx["input"])
    server_keys = tuple(args.server_key) if args.server_key else DEFAULT_SERVER_KEYS

    result = evaluate_dod(
        tx_from=str(receipt["from"]),
        tx_input=tx_input,
        logs=_normalize_logs(receipt["logs"]),
        partner_wallet=args.partner,
        session_keys=args.session_key,
        atoken_address=args.atoken,
        server_keys=server_keys,
    )

    for c in result.checks:
        mark = "PASS" if c.passed else "FAIL"
        print(f"[{mark}] {c.name}: {c.detail}")

    print()
    if result.passed:
        print(f"✅ DoD 1-4 ALL PASS — basescan: https://sepolia.basescan.org/tx/{args.tx}")
        return 0
    print("❌ DoD FAIL — 上記 FAIL 項目を確認してください")
    return 1


if __name__ == "__main__":
    sys.exit(main())
