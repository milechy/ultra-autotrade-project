# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Lido Finance 設定モジュール。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class LidoConfig:
    """Lido Finance 接続設定。"""

    # Lido stETH コントラクトアドレス（Holesky testnet）
    steth_contract_address: str = field(
        default_factory=lambda: os.getenv(
            "LIDO_STETH_CONTRACT_ADDRESS",
            "0x3F1c547b21f65e10480dE3ad8E19fAAc46C95034",  # Holesky testnet stETH
        )
    )
    # ウィドドラウアル NFT コントラクト（Holesky testnet）
    withdrawal_queue_address: str = field(
        default_factory=lambda: os.getenv(
            "LIDO_WITHDRAWAL_QUEUE_ADDRESS",
            "0xc7cc160b58F8Bb0baC94b80847E2CF2800565C50",  # Holesky testnet
        )
    )
    rpc_url: str = field(
        default_factory=lambda: os.getenv(
            "LIDO_RPC_URL",
            "https://ethereum-holesky.publicnode.com",
        )
    )
    chain: str = field(default_factory=lambda: os.getenv("LIDO_CHAIN", "holesky"))
    # Lido 公式 API ベース URL（staking APR 取得用）
    api_base_url: str = field(
        default_factory=lambda: os.getenv("LIDO_API_URL", "https://eth-api.lido.fi")
    )
    wallet_address: str = field(default_factory=lambda: os.getenv("LIDO_WALLET_ADDRESS", ""))
    wallet_private_key: str = field(
        default_factory=lambda: os.getenv("LIDO_WALLET_PRIVATE_KEY", "")
    )
    # サンドボックスモード（True の場合 DummyLidoClient を使用）
    sandbox: bool = field(
        default_factory=lambda: os.getenv("LIDO_SANDBOX", "false").lower() == "true"
    )
    # peg 乖離警告閾値（2%）
    peg_deviation_warn_pct: float = 2.0
    # 最小ステーキング量（Wei）: 0.001 ETH
    min_stake_wei: int = 1_000_000_000_000_000


def get_lido_config() -> LidoConfig:
    """環境変数から LidoConfig を生成して返す。"""
    return LidoConfig()
