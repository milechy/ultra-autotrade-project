# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/market/schemas.py
"""市場価格 API のスキーマ定義。"""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class MarketPricesResponse(BaseModel):
    """GET /api/market/prices レスポンス。

    eth_usd は外部取引所がタイムアウト/失敗した場合に None (fail-open)。
    Decimal は pydantic v2 により JSON 上で文字列としてシリアライズされる
    (財務計算は Decimal 型のみ / float 禁止)。
    """

    eth_usd: Optional[Decimal] = None
    usd_jpy: Decimal
    updated_at: str  # ISO 8601
