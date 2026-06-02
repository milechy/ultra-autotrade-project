#!/usr/bin/env python3
# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/scripts/test_fee_transfer_staging.py
"""F-S6: staging (Base Sepolia) on-chain fee transfer 実 tx 検証スクリプト。

事前準備:
  1. テスト用ウォレット (TEST_USER_WALLET / TEST_USER_PRIVATE_KEY) に Base Sepolia USDC を用意
     - USDC faucet: https://faucet.circle.com/  (Base Sepolia を選択)
  2. テスト用 operator wallet (OPERATOR_FEE_WALLET_ADDRESS / OPERATOR_FEE_WALLET_KEY) を作成
     - Base Sepolia ETH (gas 用) が必要: https://www.alchemy.com/faucets/base-sepolia
  3. ユーザーウォレットが Aave Base Sepolia に USDC を供給済み (aUSDC 所持)
  4. ユーザーウォレットが operator wallet に aUSDC allowance を付与済み

実行:
  export ALCHEMY_RPC_URL_BASE_SEPOLIA="https://base-sepolia.g.alchemy.com/v2/<KEY>"
  export OPERATOR_FEE_WALLET_ADDRESS="0x..."
  export OPERATOR_FEE_WALLET_KEY="0x..."
  export TEST_USER_WALLET="0x..."
  export TEST_USER_PRIVATE_KEY="0x..."  # ユーザーウォレット秘密鍵 (grant allowance 用)
  export FEE_TRANSFER_ENABLED="true"

  cd backend
  source .venv/bin/activate
  python scripts/test_fee_transfer_staging.py

  # basescan で確認:
  # https://sepolia.basescan.org/tx/0x<tx_hash>

Non-custodial 設計確認ポイント:
  - from: TEST_USER_WALLET (ユーザーの aToken 保有者)
  - to:   OPERATOR_FEE_WALLET_ADDRESS (operator 受け取り先)
  - 署名: OPERATOR_FEE_WALLET_KEY (operator 自身の鍵) が transferFrom を call
  - ユーザーの秘密鍵は allowance 付与にのみ使用 (本番では Privy 経由で browser 署名)
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal

from web3 import Web3

# Base Sepolia 定数
USDC_ADDRESS = "0xba50cd2a20f6da35d788639e581bca8d0b5d4d5f"
POOL_ADDRESS = "0x8bAB6d1b75f19e9eD9fCe8b9BD338844fF79aE27"
DATA_PROVIDER_ADDRESS = "0xBc9f5b7E248451CdD7cA54e717a2BFe1F32b566b"
CHAIN_ID = 84532
FEE_USD_TEST = Decimal("0.01")  # 0.01 USDC (最小テスト金額)

ERC20_ABI = [
    {
        "name": "approve",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "name": "allowance",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "balanceOf",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "decimals",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint8"}],
    },
    {
        "name": "transferFrom",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "from", "type": "address"},
            {"name": "to", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
]

DATA_PROVIDER_ABI = [
    {
        "name": "getReserveTokensAddresses",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "asset", "type": "address"}],
        "outputs": [
            {"name": "aTokenAddress", "type": "address"},
            {"name": "stableDebtTokenAddress", "type": "address"},
            {"name": "variableDebtTokenAddress", "type": "address"},
        ],
    },
]


def main() -> None:
    rpc_url = os.getenv("ALCHEMY_RPC_URL_BASE_SEPOLIA", "")
    operator_addr = os.getenv("OPERATOR_FEE_WALLET_ADDRESS", "")
    operator_key = os.getenv("OPERATOR_FEE_WALLET_KEY", "")
    user_wallet = os.getenv("TEST_USER_WALLET", "")
    user_key = os.getenv("TEST_USER_PRIVATE_KEY", "")

    missing = [
        k
        for k, v in [
            ("ALCHEMY_RPC_URL_BASE_SEPOLIA", rpc_url),
            ("OPERATOR_FEE_WALLET_ADDRESS", operator_addr),
            ("OPERATOR_FEE_WALLET_KEY", operator_key),
            ("TEST_USER_WALLET", user_wallet),
        ]
        if not v
    ]
    if missing:
        print(f"[ERROR] 環境変数未設定: {missing}")
        print("  設定方法は本スクリプト冒頭のコメントを参照してください。")
        sys.exit(1)

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        print(f"[ERROR] RPC 接続失敗: {rpc_url[:60]}...")
        sys.exit(1)

    print(f"[OK] Base Sepolia RPC 接続成功 (chain_id={w3.eth.chain_id})")

    # aUSDC アドレス取得
    dp = w3.eth.contract(
        address=w3.to_checksum_address(DATA_PROVIDER_ADDRESS),
        abi=DATA_PROVIDER_ABI,
    )
    atoken_address = dp.functions.getReserveTokensAddresses(
        w3.to_checksum_address(USDC_ADDRESS)
    ).call()[0]
    print(f"[OK] aUSDC address: {atoken_address}")

    atoken = w3.eth.contract(
        address=w3.to_checksum_address(atoken_address),
        abi=ERC20_ABI,
    )
    decimals = atoken.functions.decimals().call()
    user_cs = w3.to_checksum_address(user_wallet)
    op_cs = w3.to_checksum_address(operator_addr)

    balance = atoken.functions.balanceOf(user_cs).call()
    balance_usd = Decimal(balance) / Decimal(10**decimals)
    print(f"[OK] ユーザー aUSDC 残高: {balance_usd:.6f} USDC (raw={balance})")

    if balance == 0:
        print("[WARN] aUSDC 残高ゼロ。Aave への供給が必要です。")
        print("  1. https://faucet.circle.com/ で Base Sepolia USDC を入手")
        print("  2. https://app.aave.com/ で Base Sepolia に切り替えて USDC を供給")
        sys.exit(1)

    # Step 1: allowance 確認 / 付与
    current_allowance = atoken.functions.allowance(user_cs, op_cs).call()
    test_units = int(FEE_USD_TEST * Decimal(10**decimals))
    print(f"\n[INFO] current allowance: {current_allowance} raw (need {test_units})")

    if current_allowance < test_units:
        if not user_key:
            print("[ERROR] allowance 不足。TEST_USER_PRIVATE_KEY を設定してください。")
            print("  本番では Privy browser 署名で付与。staging では直接鍵で付与。")
            sys.exit(1)

        print(f"[INFO] allowance 付与中: {test_units} raw → operator {op_cs[:10]}...")
        user_account = w3.eth.account.from_key(user_key)
        nonce = w3.eth.get_transaction_count(user_account.address, "pending")
        approve_tx = atoken.functions.approve(op_cs, test_units * 10).build_transaction(
            {
                "from": user_account.address,
                "nonce": nonce,
                "chainId": CHAIN_ID,
                "gas": 80000,
                "gasPrice": w3.eth.gas_price,
            }
        )
        signed_approve = w3.eth.account.sign_transaction(approve_tx, private_key=user_key)
        approve_hash = w3.eth.send_raw_transaction(signed_approve.raw_transaction)
        print(f"[INFO] approve tx 送信: {approve_hash.hex()}")
        w3.eth.wait_for_transaction_receipt(approve_hash, timeout=60)
        print(f"[OK] approve 確認: https://sepolia.basescan.org/tx/{approve_hash.hex()}")
    else:
        print(f"[OK] allowance 十分: {current_allowance} raw")

    # Step 2: FeeTransferService で transferFrom 実行
    print(f"\n[INFO] fee transfer 実行: {FEE_USD_TEST} USDC を operator に送付")
    print(f"  from: {user_cs}")
    print(f"  to:   {op_cs}")
    print(f"  amount: {test_units} raw ({FEE_USD_TEST} USDC)")

    from app.fees.fee_transfer_service import FeeTransferConfig, FeeTransferService  # noqa: PLC0415

    cfg = FeeTransferConfig(
        enabled=True,
        operator_wallet_address=operator_addr,
        operator_wallet_key=operator_key,
        rpc_url=rpc_url,
        data_provider_address=DATA_PROVIDER_ADDRESS,
        usdc_address=USDC_ADDRESS,
        chain_id=CHAIN_ID,
    )
    svc = FeeTransferService(cfg)
    result = svc.transfer_fee(
        user_id=999,  # staging test user
        user_wallet=user_wallet,
        fee_amount_jpy=FEE_USD_TEST * Decimal("150"),  # 1.5 JPY @ 150
        subscription_amount_jpy=Decimal("0"),
        yield_excess_jpy=Decimal("0"),
        usd_jpy_rate=Decimal("150"),
    )

    print(f"\n[RESULT] status: {result.status}")
    print(f"         tx_hash: {result.tx_hash}")
    print(f"         fee_usd: {result.fee_usd}")
    print(f"         atoken_units: {result.atoken_units}")
    if result.error:
        print(f"         error: {result.error}")
    for line in result.debug_log:
        print(f"         debug: {line}")

    if result.status == "sent" and result.tx_hash:
        print("\n[SUCCESS] basescan で確認:")
        print(f"  https://sepolia.basescan.org/tx/{result.tx_hash}")
        print("\n確認すべき項目:")
        print(f"  1. from: {user_cs}")
        print(f"  2. to:   {op_cs}")
        print(f"  3. token: aUSDC ({atoken_address})")
        print(f"  4. amount: {test_units} raw = {FEE_USD_TEST} USDC")
        print("  5. tx status: Success (1)")
    elif result.status == "no_allowance":
        print("[FAIL] allowance 不足。前の approve ステップを確認してください。")
        sys.exit(1)
    else:
        print(f"[FAIL] 送金失敗: {result.error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
