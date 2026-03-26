# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""マルチプロトコル Risk Engine スキーマ定義。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """リスクレベル列挙型。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ProtocolHealth(BaseModel):
    """プロトコルのヘルス状態。"""

    protocol: str  # "aave", "lido", "pendle"
    risk_level: RiskLevel
    tvl_usd: Decimal
    tvl_change_24h_pct: Decimal  # 24時間 TVL 変化率（%）
    is_operational: bool
    last_checked: datetime
    alerts: list[str]  # アクティブなアラート一覧


class PegStatus(BaseModel):
    """stETH/ETH ペグ状態。"""

    current_ratio: Decimal  # 1.0 = 完全ペグ
    deviation_pct: Decimal  # 乖離率（%）
    risk_level: RiskLevel
    last_checked: datetime


class MaturityAlert(BaseModel):
    """Pendle 満期アラート。"""

    market_address: str
    asset: str
    maturity_date: datetime
    days_remaining: int
    risk_level: RiskLevel
    action_required: str  # "none", "monitor", "prepare_exit", "exit_now"


class EvacuationStep(BaseModel):
    """避難計画の単一ステップ。"""

    protocol: str
    action: str  # "withdraw", "redeem_pt", "redeem_yt", "unstake"
    asset: str
    amount: Decimal
    destination: str  # "USDC"
    order: int  # 実行順序


class EvacuationPlan(BaseModel):
    """自動避難計画。"""

    trigger_reason: str
    steps: list[EvacuationStep]
    estimated_gas_cost_usd: Decimal
    estimated_time_minutes: int
    priority: str  # "immediate", "within_1h", "within_24h"


class EvacuationResult(BaseModel):
    """避難実行結果。"""

    plan: EvacuationPlan
    executed: bool
    dry_run: bool
    steps_completed: int
    steps_total: int
    errors: list[str]


class CompoundRiskAssessment(BaseModel):
    """マルチプロトコル複合リスク評価。"""

    overall_risk: RiskLevel
    protocol_risks: list[ProtocolHealth]
    peg_status: Optional[PegStatus] = None
    maturity_alerts: list[MaturityAlert]
    total_exposure_usd: Decimal
    risk_score: Decimal = Field(..., description="リスクスコア 0-100（0=安全, 100=危険）")
    recommendations: list[str]  # 推奨アクション（専門用語なし）
    should_evacuate: bool
    evacuation_reason: Optional[str] = None
