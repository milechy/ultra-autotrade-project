# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/dca/schemas.py

"""
DCA（ドルコスト平均法）モジュールの Pydantic スキーマ定義。
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class DCAFrequency(str, Enum):
    """積立頻度。"""

    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"


class DCAConfig(BaseModel):
    """DCA設定。"""

    enabled: bool = Field(True, description="DCAを有効にするか")
    symbol: str = Field("BTC/USDT", description="積立対象シンボル")
    amount_usd: Decimal = Field(..., gt=0, description="1回あたりの積立金額（USD）")
    frequency: DCAFrequency = Field(DCAFrequency.DAILY, description="積立頻度")
    dry_run: bool = Field(True, description="True=注文しない（デフォルトは安全側）")


class DCAExecutionResult(BaseModel):
    """DCA実行結果。"""

    executed: bool = Field(..., description="実際に注文したか")
    symbol: str
    amount_usd: Decimal
    order_id: Optional[str] = None
    message: str


class GridConfigRequest(BaseModel):
    """グリッドボット設定リクエスト。"""

    upper_price: Decimal = Field(..., gt=0, description="グリッド上限価格")
    lower_price: Decimal = Field(..., gt=0, description="グリッド下限価格")
    grid_count: int = Field(10, ge=2, le=100, description="グリッド数")
    symbol: str = Field("BTC/USDT", description="取引シンボル")
    amount_per_grid_usd: Decimal = Field(
        Decimal("10"), gt=0, description="各グリッドの取引金額(USD)"
    )
    enabled: bool = Field(True)
    dry_run: bool = Field(True)


class GridLevelResponse(BaseModel):
    """グリッドレベルの状態レスポンス。"""

    price: Decimal
    side: str
    order_id: Optional[str] = None
    filled: bool


class GridStatusResponse(BaseModel):
    """グリッドボットのステータスレスポンス。"""

    enabled: bool
    symbol: str
    upper_price: Decimal
    lower_price: Decimal
    grid_count: int
    current_price: Optional[Decimal] = None
    levels: List[GridLevelResponse]
    total_orders: int
    filled_orders: int
    pnl_usd: Decimal
