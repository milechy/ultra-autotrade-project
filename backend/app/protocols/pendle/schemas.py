# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Pendle Finance Pydantic スキーマ定義。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_serializer, field_validator


class PendleMarketInfo(BaseModel):
    """Pendle マーケット情報。"""

    market_address: str
    underlying_asset: str
    maturity: datetime
    days_to_maturity: int
    implied_apy: Decimal = Field(..., description="implied APY（%）")
    pt_price: Decimal = Field(..., description="PT 価格（0〜1、ディスカウント）")
    yt_price: Decimal = Field(..., description="YT 価格（0〜1）")
    tvl_usd: Decimal = Field(..., description="TVL（USD）")


class PendleMintRequest(BaseModel):
    """PT/YT ミントリクエスト。"""

    asset: str = Field(..., description="入力アセット（例: stETH アドレス）")
    amount: Decimal = Field(..., gt=Decimal("0"), description="ミント量")
    strategy: Literal["pt_fixed", "yt_leverage"] = Field(
        ..., description="'pt_fixed'（固定利回り）または 'yt_leverage'（利回りレバレッジ）"
    )
    market_address: str = Field(..., description="対象マーケットアドレス")
    dry_run: bool = Field(True, description="Trueの場合シミュレーションのみ（デフォルト）")

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount(cls, v: object) -> Decimal:
        return Decimal(str(v))


class PendleMintResponse(BaseModel):
    """PT/YT ミントレスポンス。"""

    operation: str = Field(..., description="'MINT_PT' or 'MINT_YT'")
    input_amount: Decimal
    pt_received: Optional[Decimal] = None
    yt_received: Optional[Decimal] = None
    implied_fixed_yield: Decimal = Field(..., description="implied 固定利回り（%）")
    maturity: datetime
    tx_hash: Optional[str] = None
    dry_run: bool


class PendleRedeemRequest(BaseModel):
    """PT/YT リデームリクエスト。"""

    token_type: Literal["PT", "YT"] = Field(..., description="'PT' または 'YT'")
    amount: Decimal = Field(..., gt=Decimal("0"), description="リデーム量")
    market_address: str = Field(..., description="対象マーケットアドレス")
    dry_run: bool = Field(True, description="Trueの場合シミュレーションのみ（デフォルト）")

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount(cls, v: object) -> Decimal:
        return Decimal(str(v))


class PendleRedeemResponse(BaseModel):
    """PT/YT リデームレスポンス。"""

    operation: str = Field(..., description="'REDEEM_PT' or 'REDEEM_YT'")
    redeemed_amount: Decimal
    underlying_received: Decimal
    tx_hash: Optional[str] = None
    dry_run: bool


class StrategyEvaluation(BaseModel):
    """戦略評価結果。"""

    strategy: str
    recommended: bool
    expected_apy: Decimal = Field(..., description="期待 APY（%）")
    risk_level: str = Field(..., description="'low', 'medium', 'high'")
    details: str


class StrategyComparison(BaseModel):
    """戦略比較結果。"""

    strategies: list[StrategyEvaluation]
    best_strategy: str
    amount: Decimal


class CompoundResult(BaseModel):
    """複合戦略実行結果。"""

    steps: list[str]
    final_position: str
    total_expected_apy: Decimal
    dry_run: bool


# --- RouterV4 スキーマ ---


class RouterV4SwapRequest(BaseModel):
    """RouterV4 swap リクエスト（buy/sell YT または PT）。"""

    market_address: str = Field(..., description="対象マーケットアドレス")
    token_in: str = Field(..., description="入力トークンアドレス")
    token_out: str = Field(..., description="出力トークンアドレス")
    amount_in: Decimal = Field(..., gt=Decimal("0"), description="入力量")
    slippage: Decimal = Field(
        default=Decimal("0.005"),
        gt=Decimal("0"),
        le=Decimal("0.05"),
        description="スリッページ（0.005 = 0.5%）。0 < slippage <= 0.05（5%）",
    )
    receiver: str = Field(..., description="受取アドレス")
    portfolio_value_usd: Optional[Decimal] = Field(
        default=None, ge=Decimal("0"), description="ポートフォリオ総額（USD）。10%上限チェック用"
    )
    amount_in_usd: Optional[Decimal] = Field(
        default=None,
        ge=Decimal("0"),
        description="トレード金額（USD）。portfolio_value_usd と併用必須（未指定時は fail-closed で拒否）",
    )

    @field_validator("amount_in", mode="before")
    @classmethod
    def validate_amount_in(cls, v: object) -> Decimal:
        return Decimal(str(v))

    @field_validator("slippage", mode="before")
    @classmethod
    def validate_slippage(cls, v: object) -> Decimal:
        return Decimal(str(v))


class RouterV4Approval(BaseModel):
    """RouterV4 SDK が要求する ERC20 approval（Phase 2 への橋渡し用に保持）。"""

    token: Optional[str] = Field(default=None, description="approve 対象トークンアドレス")
    spender: Optional[str] = Field(default=None, description="spender（Router であるべき）")
    amount: Optional[str] = Field(default=None, description="approve 量（生値）")


class RouterV4SwapResult(BaseModel):
    """RouterV4 swap 結果。"""

    success: bool
    tx_hash: Optional[str] = None
    amount_out: Optional[Decimal] = None
    calldata: Optional[str] = None
    # SDK が返した tx.to（Router 照合済み）。Phase 2 の tx 送信先として保持。
    to: Optional[str] = None
    approvals: list[RouterV4Approval] = Field(default_factory=list)
    error: Optional[str] = None


class RouterV4AddLiquidityRequest(BaseModel):
    """RouterV4 add_liquidity リクエスト。"""

    market_address: str = Field(..., description="対象マーケットアドレス")
    token_in: str = Field(..., description="入力トークンアドレス")
    amount_in: Decimal = Field(..., gt=Decimal("0"), description="入力量")
    slippage: Decimal = Field(
        default=Decimal("0.005"),
        gt=Decimal("0"),
        le=Decimal("0.05"),
        description="スリッページ（0.005 = 0.5%）。0 < slippage <= 0.05（5%）",
    )
    receiver: str = Field(..., description="受取アドレス")
    portfolio_value_usd: Optional[Decimal] = Field(
        default=None, ge=Decimal("0"), description="ポートフォリオ総額（USD）。10%上限チェック用"
    )
    amount_in_usd: Optional[Decimal] = Field(
        default=None,
        ge=Decimal("0"),
        description="トレード金額（USD）。portfolio_value_usd と併用必須（未指定時は fail-closed で拒否）",
    )

    @field_validator("amount_in", mode="before")
    @classmethod
    def validate_amount_in(cls, v: object) -> Decimal:
        return Decimal(str(v))

    @field_validator("slippage", mode="before")
    @classmethod
    def validate_slippage(cls, v: object) -> Decimal:
        return Decimal(str(v))


class RouterV4AddLiquidityResult(BaseModel):
    """RouterV4 add_liquidity 結果。"""

    success: bool
    tx_hash: Optional[str] = None
    lp_amount: Optional[Decimal] = None
    calldata: Optional[str] = None
    # SDK が返した tx.to（Router 照合済み）。Phase 2 の tx 送信先として保持。
    to: Optional[str] = None
    approvals: list[RouterV4Approval] = Field(default_factory=list)
    error: Optional[str] = None


# --- Positions スキーマ ---


class PendlePosition(BaseModel):
    """Pendle PT/YT ポジション情報。

    Decimal フィールドはフロントエンド契約上すべて文字列で返却する。
    （frontend/lib/api/pendle.ts PendlePosition インターフェース準拠）
    """

    id: str
    market_address: str
    underlying_asset: str
    pt_amount: Decimal
    yt_amount: Decimal
    pt_price_usd: Decimal
    yt_price_usd: Decimal
    implied_apy: Decimal
    maturity: datetime
    days_to_maturity: int
    fetched_at: datetime

    @field_serializer("pt_amount", "yt_amount", "pt_price_usd", "yt_price_usd", "implied_apy")
    def serialize_decimal(self, v: Decimal) -> str:
        return str(v)


class PendlePositionResponse(BaseModel):
    """Pendle ポジション一覧レスポンス。

    total_value_usd はフロントエンド契約上文字列で返却する。
    """

    positions: list[PendlePosition]
    total_value_usd: Decimal

    @field_serializer("total_value_usd")
    def serialize_total(self, v: Decimal) -> str:
        return str(v)
