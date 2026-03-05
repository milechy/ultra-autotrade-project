# backend/app/dca/schemas.py

"""
DCA（ドルコスト平均法）モジュールの Pydantic スキーマ定義。
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Optional

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
