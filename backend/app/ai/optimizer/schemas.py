# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""オプティマイザー モジュールの Pydantic スキーマ定義。"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class Protocol(str, Enum):
    """運用プロトコルの列挙型。"""

    AAVE = "aave"
    LIDO = "lido"
    LIDO_AAVE = "lido_aave"  # 複合: stETH → Aave
    PENDLE_PT = "pendle_pt"
    PENDLE_YT = "pendle_yt"
    IDLE = "idle"  # 未投資（現金）


class Recommendation(str, Enum):
    """推奨度の列挙型。"""

    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    AVOID = "AVOID"


class StrategyCandidate(BaseModel):
    """評価対象の戦略候補。"""

    protocol: Protocol
    asset: str  # "USDC", "ETH", "stETH"
    expected_apy: Decimal  # 年間利回り（例: 3.5 → 3.5%）
    gas_cost_usd: Decimal  # ガスコスト見積もり（USD）
    bridge_cost_usd: Decimal = Decimal("0")
    risk_penalty: Decimal  # リスクペナルティ 0-1（高いほどリスク大）
    liquidity_available: Decimal  # 利用可能流動性（USD）
    maturity_days: Optional[int] = None  # Pendle 満期日数
    peg_deviation: Optional[Decimal] = None  # stETH/ETH ペグ乖離率 %

    @field_validator(
        "expected_apy",
        "gas_cost_usd",
        "bridge_cost_usd",
        "risk_penalty",
        "liquidity_available",
        mode="before",
    )
    @classmethod
    def to_decimal(cls, v: object) -> Decimal:
        """数値を Decimal に変換する。"""
        return Decimal(str(v))


class NetBenefitResult(BaseModel):
    """期待ネット利益の計算結果。"""

    protocol: Protocol
    asset: str
    expected_net_benefit: Decimal  # ネット利益（USD、年換算）
    gross_yield: Decimal  # グロス利回り（USD）
    total_cost: Decimal  # 合計コスト（ガス + ブリッジ）
    risk_adjusted_yield: Decimal  # リスク調整後利回り
    rank: int  # 1 = 最良
    recommendation: Recommendation


class AllocationEntry(BaseModel):
    """ポートフォリオ内の単一配分。"""

    protocol: Protocol
    asset: str
    allocation_pct: Decimal  # 0-100
    amount_usd: Decimal
    expected_apy: Decimal


class AllocationRecommendation(BaseModel):
    """ポートフォリオ配分推奨。"""

    allocations: list[AllocationEntry]
    total_expected_apy: Decimal
    total_risk_score: Decimal
    explanation: str


class StrategyComparison(BaseModel):
    """戦略比較レポート。"""

    candidates: list[NetBenefitResult]
    recommended: NetBenefitResult
    idle_benefit: Decimal  # 何もしない場合の機会コスト
    comparison_timestamp: str


class OptimizerRequest(BaseModel):
    """オプティマイザー API リクエスト。"""

    investment_usd: Decimal = Field(..., description="投資額（USD）")
    risk_mode: str = Field(
        "conservative", description="リスクモード: conservative/balanced/aggressive"
    )
    holding_days: int = Field(30, description="保有予定日数")

    @field_validator("investment_usd", mode="before")
    @classmethod
    def to_decimal(cls, v: object) -> Decimal:
        """数値を Decimal に変換する。"""
        return Decimal(str(v))


class OptimizerResponse(BaseModel):
    """オプティマイザー API レスポンス。"""

    comparison: StrategyComparison
    allocation: AllocationRecommendation
    report: str
