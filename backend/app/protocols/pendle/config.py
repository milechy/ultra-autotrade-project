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
    # BUY_PT で支払う入力トークン（underlying）アドレス。非カストディアル build-tx で
    # swapExactTokenForPt の tokenIn として使用する（partner が保有・approve 済み前提）。
    underlying_token_address: str = field(
        default_factory=lambda: os.getenv(
            "PENDLE_UNDERLYING_TOKEN_ADDRESS",
            "0x0000000000000000000000000000000000000003",  # dummy address
        )
    )
    # 入力トークン (underlying) の decimals。stablecoin PT では USDC=6 を明示する。
    # underlying_token_address は *アドレス* のため token_decimals(symbol) では解決できず、
    # 明示しないと 18 に既定化して桁ズレ（USDC で 10^12 倍）を起こす。
    underlying_token_decimals: int = field(
        default_factory=lambda: int(os.getenv("PENDLE_UNDERLYING_TOKEN_DECIMALS", "6"))
    )
    # PT トークンのコントラクトアドレス。SELL_PT(満期出口 redeem)で PT→Router の approve 宛先
    # として使う（Privy policy の allowlist にも要る）。市場ごとに異なるため env で設定する。
    pt_token_address: str = field(
        default_factory=lambda: os.getenv(
            "PENDLE_PT_TOKEN_ADDRESS",
            "0x0000000000000000000000000000000000000004",  # dummy address
        )
    )
    # 入力トークンが USD ペッグの stablecoin (USDC 等) か。True の場合のみ proposal.amount_usd
    # をそのまま入力トークン数量として扱う (1 USDC≒1 USD)。False (既定) は USD→token 価格換算が
    # 未配線のため自動執行を fail-closed で拒否する (ETH や非ステーブル PT の誤数量署名防止)。
    # [Phase D] yoUSD 等 stablecoin PT market を対象にする環境でのみ true を設定する。
    stable_underlying: bool = field(
        default_factory=lambda: os.getenv("PENDLE_STABLE_UNDERLYING", "false").lower() == "true"
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
