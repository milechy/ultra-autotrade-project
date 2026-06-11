# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Pendle Finance 設定モジュール。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal


def _get_env_decimal(name: str, default: str) -> Decimal:
    """環境変数から Decimal 値を読み込む。未設定またはパース失敗時はデフォルト値を返す。"""
    raw = os.getenv(name, default)
    try:
        return Decimal(raw)
    except Exception:
        return Decimal(default)


@dataclass
class PendleConfig:
    """Pendle Finance 接続設定。"""

    # Pendle Router V4 コントラクトアドレス（正式アドレス）
    router_address: str = field(
        default_factory=lambda: os.getenv(
            "PENDLE_ROUTER_ADDRESS",
            "0x888888888889758F76e7103c6CbF23ABbF58F946",
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
    # オンチェーン書き込み許可フラグ（Phase 2 の tx 送信を二段ガードする土台）。
    # default false。tx 送信は本フラグ True かつ wallet_private_key が揃った場合のみ許可。
    # Phase 1（本実装）は calldata 取得までで、本フラグ True でも tx は送信しない。
    enable_onchain_write: bool = field(
        default_factory=lambda: os.getenv("PENDLE_ENABLE_ONCHAIN_WRITE", "false").lower() == "true"
    )
    # 単一トレード上限（ポートフォリオに対する割合。デフォルト 10%）
    max_single_trade_pct: Decimal = field(
        default_factory=lambda: _get_env_decimal("PENDLE_MAX_SINGLE_TRADE_PCT", "0.10")
    )

    def token_decimals(self, token: str) -> int:
        """トークン識別子から decimals を解決する。

        非18桁トークン（USDC/USDT=6、WBTC=8）の桁ズレ事故を防ぐためのマップ。
        シンボル（大文字小文字無視）で照合し、未知トークンは 18 を返す。
        """
        return _TOKEN_DECIMALS.get(token.upper(), 18)


# トークンシンボル → decimals マップ。
# 非18桁トークンの送金額桁ズレ（USDC で 10^12 倍ズレ）を防ぐ。
_TOKEN_DECIMALS: dict[str, int] = {
    "USDC": 6,
    "USDT": 6,
    "WBTC": 8,
}


def get_pendle_config() -> PendleConfig:
    """環境変数から PendleConfig を生成して返す。"""
    return PendleConfig()
