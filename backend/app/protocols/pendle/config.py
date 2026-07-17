# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Pendle Finance 設定モジュール。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal


def _get_env_decimal(name: str, default: str) -> Decimal:
    """環境変数から Decimal 値を読み込む。未設定またはパース失敗時はデフォルト値を返す。

    ``Decimal("inf")`` / ``NaN`` は **パースに成功してしまう**（`Decimal("inf")` は有効値）。
    これが金額上限に入ると `amount > inf` が常に False になりガードが無言で無効化されるため、
    有限値でなければ default に倒す（安全レビュー P1）。
    """
    raw = os.getenv(name, default)
    try:
        value = Decimal(raw)
    except Exception:
        return Decimal(default)
    if not value.is_finite():
        return Decimal(default)
    return value


#: `PENDLE_MAX_TRADE_USD_CAP` の **env で越えられない絶対上限**（USD）。
#:
#: Pendle broadcast 経路では CLAUDE.md Rule 3/4（単一10%/日次30%）が実際には効いておらず
#: （`_pendle_execution_blocked` が risk_limiter に total_assets=None を渡すため）、
#: **本 cap が事実上唯一の絶対額ガード**。そこに env のタイポ（`20` → `200`）を捕まえる第二層が
#: 無いのは、唯一のガードを 1 文字のミスに委ねることになる。
#: `risk_limiter.SINGLE_TRADE_PCT_HARD_MAX` と同じ発想の hard clamp を置く。
#: **これを引き上げる前に total_assets の配線を行うこと**（cap を上げた瞬間、その取引額を縛る
#: ものが文字通り何も無くなる）。
PENDLE_MAX_TRADE_USD_HARD_MAX = Decimal("100")


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
    # PT トークンの decimals。**PT は 18 桁とは限らない**（PT-yoUSD-24SEP2026 は 6 桁。PT は
    # 原資産の桁を継ぐため stablecoin PT は 6 になる）。underlying_token_decimals と同じ理由で
    # 明示が要る: pt_token_address は *アドレス* なので token_decimals(symbol) では解決できない。
    # ここを誤ると SELL_PT で **売却数量そのものが 10^12 倍ズレる**（BUY_PT は受取量の表示ズレ）。
    # 市場ごとに異なるため env で設定する（既定 6 = stablecoin PT 想定）。
    pt_token_decimals: int = field(
        default_factory=lambda: int(os.getenv("PENDLE_PT_TOKEN_DECIMALS", "6"))
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
    # [Phase D / D5] 流動性ガード: 1 投入 ≤ プール流動性(tvl_usd)の割合（デフォルト 5%）。
    # 薄い PT プールを 1 回の swap で壊さないための物理制約。
    max_pool_liquidity_pct: Decimal = field(
        default_factory=lambda: _get_env_decimal("PENDLE_MAX_POOL_LIQUIDITY_PCT", "0.05")
    )
    # [Phase D / D5] 流動性ガード: 1 投入の絶対上限（USD）。プール流動性%と併せて被害上限を縛る。
    #
    # **既定を 5000 → 20 に引き下げた（2026-07-17 安全レビュー H3）**。理由: Pendle 経路では
    # CLAUDE.md Rule 3/4（単一 10% / 日次 30%）が **実際には効いていない**
    # （`_pendle_execution_blocked` が risk_limiter に total_assets=None を渡すため、
    # risk_limiter が両方の % 判定をスキップする。Aave SCW 経路も同じ既存問題）。
    # つまり金額の歯止めは事実上「プール流動性% と本上限」だけで、本上限が唯一の絶対額。
    # そこに 5000 を既定で与えると、env 設定を忘れた運用者に $5,000 の枠が黙って開く。
    # 「運用者が設定を憶えていること」を安全装置にしない ＝ 忘れたら小さい方に倒す。
    # 実運用で引き上げる場合は PENDLE_MAX_TRADE_USD_CAP を明示設定すること。
    # hard clamp: env がこれを超える値を指定しても `PENDLE_MAX_TRADE_USD_HARD_MAX` で頭打ちにする。
    max_trade_usd_cap: Decimal = field(
        default_factory=lambda: min(
            _get_env_decimal("PENDLE_MAX_TRADE_USD_CAP", "20"),
            PENDLE_MAX_TRADE_USD_HARD_MAX,
        )
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
