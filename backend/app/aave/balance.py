# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/aave/balance.py
"""Wallet USDC 残高の読み取りユーティリティ（共有）。

提案金額の sizing（`automation.ai_judgment_scheduler`）と build-tx 前の残高ガード
（`proposals.router`）の双方で使う。チェーン別 USDC アドレス・RPC は `app.aave.chains`
に集約されており、ここでは mainnet 直書きしない。

NOTE: `monitor.get_aave_balance` は `AAVE_CLIENT_TYPE != "web3"` 時にモック値を返すため
残高ガード用途には使わない（このモジュールは web3 失敗時に None を返し fail-safe）。
"""

import logging
from decimal import Decimal
from typing import Any, Optional

logger = logging.getLogger(__name__)

# USDC は 6 decimals。ERC20 balanceOf の最小 ABI。
USDC_DECIMALS = 6
_ERC20_BALANCE_OF_ABI: list[dict[str, Any]] = [
    {
        "constant": True,
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }
]


def read_wallet_usdc_balance(wallet_address: str) -> Optional[Decimal]:
    """active chain 上の wallet USDC 残高 (USDC 単位の人間可読 Decimal) を返す。

    AAVE_ACTIVE_CHAINS の先頭チェーン (production=base / staging=base_sepolia) の USDC
    コントラクトに対し web3 で balanceOf する (web3.py の .call() は同期)。
    web3 未導入 / RPC URL 未設定 / 不正アドレス / RPC 失敗時は **None** を返し、
    呼び出し側で skip させる (安全側: 残高不明のまま値を捏造しない / ガードを fail-open)。
    """
    try:
        from web3 import Web3  # noqa: PLC0415

        from app.aave.chains import (  # noqa: PLC0415
            get_active_chains,
            get_rpc_url_for_chain,
        )

        chain = get_active_chains()[0]
        usdc_addr = chain.tokens.get("USDC")
        if not usdc_addr:
            logger.warning("[usdc_balance] USDC address missing for %s", chain.chain_name)
            return None
        rpc_url = get_rpc_url_for_chain(chain)
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        contract = w3.eth.contract(
            address=w3.to_checksum_address(usdc_addr),
            abi=_ERC20_BALANCE_OF_ABI,
        )
        raw_balance = contract.functions.balanceOf(w3.to_checksum_address(wallet_address)).call()
        return Decimal(raw_balance) / Decimal(10**USDC_DECIMALS)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[usdc_balance] wallet USDC balance read failed for %s: %s",
            wallet_address,
            exc,
        )
        return None
