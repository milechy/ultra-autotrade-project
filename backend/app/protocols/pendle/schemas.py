# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Pendle Finance Pydantic スキーマ定義。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


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
