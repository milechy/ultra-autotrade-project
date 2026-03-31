#!/usr/bin/env python3
# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# scripts/test_aave_arbitrum_sepolia.py
"""
Aave V3 Arbitrum Sepolia テストネット接続検証スクリプト。

実行前に以下の環境変数を設定してください:
  ALCHEMY_RPC_URL_ARBITRUM_SEPOLIA  - Alchemy の Arbitrum Sepolia RPC URL（必須）
  AAVE_WALLET_ADDRESS               - 読み取り専用確認用ウォレットアドレス（getUserReserveData 用）

使い方:
  python scripts/test_aave_arbitrum_sepolia.py

NOTE: このスクリプトは読み取り専用です。秘密鍵は不要です。
"""

from __future__ import annotations

import os
import sys
import time

# ---------------------------------------------------------------------------
# 設定値（chains.py と同期）
# ---------------------------------------------------------------------------
_POOL_ADDRESS = "0xBfC91D59fdAA134A4ED45f7B584cAf96D7792Eff"
_DATA_PROVIDER_ADDRESS = "0x29F1d9A68B77D0e8BefE6D2Cb3eE8cB4Ad6FADE0"
_ORACLE_ADDRESS = "0x3E17d8C99b6e73Dc2bBe30AAC4A0C5Bd0e0D261B"
_USDC_ADDRESS = "0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d"
_CHAIN_ID = 421614

# ---------------------------------------------------------------------------
# 最小 ABI 定義（必要な関数のみ）
# ---------------------------------------------------------------------------

_POOL_ABI = [
    {
        "name": "getReservesList",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "address[]"}],
    }
]

_DATA_PROVIDER_ABI = [
    {
        "name": "getUserReserveData",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "asset", "type": "address"},
            {"name": "user", "type": "address"},
        ],
        "outputs": [
            {"name": "currentATokenBalance", "type": "uint256"},
            {"name": "currentStableDebt", "type": "uint256"},
            {"name": "currentVariableDebt", "type": "uint256"},
            {"name": "principalStableDebt", "type": "uint256"},
            {"name": "scaledVariableDebt", "type": "uint256"},
            {"name": "stableBorrowRate", "type": "uint256"},
            {"name": "liquidityRate", "type": "uint256"},
            {"name": "stableRateLastUpdated", "type": "uint40"},
            {"name": "usageAsCollateralEnabled", "type": "bool"},
        ],
    }
]

_ORACLE_ABI = [
    {
        "name": "getAssetPrice",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "asset", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    }
]


def _get_env_or_exit(var_name: str) -> str:
    """環境変数を取得する。未設定の場合はエラーを表示して終了する。"""
    value = os.environ.get(var_name)
    if not value:
        print(f"[ERROR] 環境変数 {var_name!r} が設定されていません。")
        print("       .env.staging または export コマンドで設定してください。")
        sys.exit(1)
    return value


def main() -> None:
    print("=" * 60)
    print("Aave V3 Arbitrum Sepolia 接続検証スクリプト")
    print(f"Chain ID: {_CHAIN_ID}")
    print("=" * 60)

    # --- 依存ライブラリの確認 ---
    try:
        from web3 import Web3
    except ImportError:
        print("[ERROR] web3 がインストールされていません。")
        print("       pip install web3 を実行してください。")
        sys.exit(1)

    # --- 環境変数の取得 ---
    rpc_url = _get_env_or_exit("ALCHEMY_RPC_URL_ARBITRUM_SEPOLIA")
    wallet_address_raw = os.environ.get("AAVE_WALLET_ADDRESS", "")
    has_wallet = bool(wallet_address_raw)

    # --- Web3 接続 ---
    print(f"\n[1/4] RPC 接続中...")
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        print("[FAIL] RPC 接続失敗。URL を確認してください。")
        sys.exit(1)

    chain_id = w3.eth.chain_id
    block_number = w3.eth.block_number
    print(f"[OK]  接続成功")
    print(f"      chain_id    = {chain_id}")
    print(f"      block_number = {block_number}")
    if chain_id != _CHAIN_ID:
        print(f"[WARN] 期待 chain_id={_CHAIN_ID}、実際={chain_id}")

    time.sleep(1)

    # --- Pool.getReservesList() ---
    print(f"\n[2/4] Pool.getReservesList() 呼び出し...")
    try:
        pool = w3.eth.contract(
            address=Web3.to_checksum_address(_POOL_ADDRESS),
            abi=_POOL_ABI,
        )
        reserves = pool.functions.getReservesList().call()
        print(f"[OK]  リザーブ一覧 ({len(reserves)} 件):")
        for i, addr in enumerate(reserves, 1):
            print(f"      [{i}] {addr}")
    except Exception as exc:
        print(f"[FAIL] Pool.getReservesList() エラー: {exc}")

    time.sleep(1)

    # --- Oracle.getAssetPrice(USDC) ---
    print(f"\n[3/4] Oracle.getAssetPrice(USDC) 呼び出し...")
    try:
        oracle = w3.eth.contract(
            address=Web3.to_checksum_address(_ORACLE_ADDRESS),
            abi=_ORACLE_ABI,
        )
        usdc_price = oracle.functions.getAssetPrice(
            Web3.to_checksum_address(_USDC_ADDRESS)
        ).call()
        # Aave Oracle は USD 建て 8 桁精度で価格を返す
        usdc_price_usd = usdc_price / 10**8
        print(f"[OK]  USDC 価格 = {usdc_price_usd:.6f} USD (raw: {usdc_price})")
    except Exception as exc:
        print(f"[FAIL] Oracle.getAssetPrice() エラー: {exc}")

    time.sleep(1)

    # --- DataProvider.getUserReserveData() ---
    print(f"\n[4/4] DataProvider.getUserReserveData(USDC, wallet) 呼び出し...")
    if not has_wallet:
        print("[SKIP] AAVE_WALLET_ADDRESS が未設定のためスキップします。")
        print("       export AAVE_WALLET_ADDRESS=0x... を設定すると検証できます。")
    else:
        try:
            wallet_address = Web3.to_checksum_address(wallet_address_raw)
            data_provider = w3.eth.contract(
                address=Web3.to_checksum_address(_DATA_PROVIDER_ADDRESS),
                abi=_DATA_PROVIDER_ABI,
            )
            result = data_provider.functions.getUserReserveData(
                Web3.to_checksum_address(_USDC_ADDRESS),
                wallet_address,
            ).call()
            current_a_token_balance = result[0]
            current_variable_debt = result[2]
            usage_as_collateral = result[8]
            print(f"[OK]  getUserReserveData 結果:")
            print(f"      currentATokenBalance  = {current_a_token_balance}")
            print(f"      currentVariableDebt   = {current_variable_debt}")
            print(f"      usageAsCollateralEnabled = {usage_as_collateral}")
        except Exception as exc:
            print(f"[FAIL] DataProvider.getUserReserveData() エラー: {exc}")

    print("\n" + "=" * 60)
    print("検証完了")
    print("=" * 60)


if __name__ == "__main__":
    main()
