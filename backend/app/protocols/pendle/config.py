# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Pendle Finance 設定モジュール。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class PendleConfig:
    """Pendle Finance 接続設定。"""

    # Pendle Router V4 コントラクトアドレス
    router_address: str = field(
        default_factory=lambda: os.getenv(
            "PENDLE_ROUTER_ADDRESS",
            "0x0000000000000000000000000000000000000001",  # dummy address
        )
    )
    # ターゲットマーケット（stETH）アドレス
    market_address: str = field(
        default_factory=lambda: os.getenv(
            "PENDLE_MARKET_ADDRESS",
            "0x0000000000000000000000000000000000000002",  # dummy address
        )
    )
    # RPC エンドポイント（Arbitrum Sepolia）
    rpc_url: str = field(
        default_factory=lambda: os.getenv(
            "PENDLE_RPC_URL",
            "https://sepolia-rollup.arbitrum.io/rpc",
        )
    )
    chain: str = field(default_factory=lambda: os.getenv("PENDLE_CHAIN", "sepolia"))
    wallet_address: str = field(default_factory=lambda: os.getenv("PENDLE_WALLET_ADDRESS", ""))
    wallet_private_key: str = field(
        default_factory=lambda: os.getenv("PENDLE_WALLET_PRIVATE_KEY", "")
    )
    # サンドボックスモード（True の場合 DummyPendleClient を使用）
    sandbox: bool = field(
        default_factory=lambda: os.getenv("PENDLE_SANDBOX", "false").lower() == "true"
    )
    # 満期まで最低日数（この日数未満の場合はオペレーションを拒否）
    min_days_to_maturity: int = 7
    # implied APY 警告閾値（この値を超えると警告ログを出力）
    max_implied_apy_pct: Decimal = field(default_factory=lambda: Decimal("100.0"))


def get_pendle_config() -> PendleConfig:
    """環境変数から PendleConfig を生成して返す。"""
    return PendleConfig()
