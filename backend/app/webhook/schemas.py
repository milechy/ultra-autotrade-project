from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class WebhookSource(str, Enum):
    """Webhook 送信元の種別。"""

    TRADINGVIEW = "tradingview"
    GENERIC = "generic"


class TradingViewPayload(BaseModel):
    """TradingView Alert Webhook のペイロード。"""

    ticker: Optional[str] = Field(None, description="シンボル（例: BTCUSDT）")
    action: Optional[str] = Field(None, description="buy / sell / hold など")
    price: Optional[float] = Field(None, description="アラート発火時の価格")
    message: Optional[str] = Field(None, description="アラートメッセージ本文")
    time: Optional[str] = Field(None, description="発火時刻（ISO8601）")


class GenericWebhookPayload(BaseModel):
    """汎用 Webhook ペイロード。"""

    title: Optional[str] = Field(None, description="タイトル")
    content: str = Field(..., description="本文テキスト（必須）")
    source: Optional[str] = Field(None, description="送信元識別子")
    url: Optional[str] = Field(None, description="参照URL（任意）")


class WebhookReceiveResponse(BaseModel):
    """Webhook 受信レスポンス。"""

    received: bool = Field(True)
    knowledge_item_id: Optional[int] = Field(None, description="登録されたKnowledgeItem ID")
    message: str = Field(..., description="処理結果メッセージ")
