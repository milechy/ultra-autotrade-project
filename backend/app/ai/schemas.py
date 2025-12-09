# backend/app/ai/schemas.py
"""
/ai/analyze 用の Pydantic スキーマ定義。

- Request: NotionNewsItem の配列をそのまま受け取り、解析対象とする
- Response: AI による判定結果（BUY/SELL/HOLD など）を返す
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from app.notion.schemas import NotionNewsItem

class TradeAction(str, Enum):
    """AI 判定で返すアクションの列挙型。"""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class AIAnalysisRequest(BaseModel):
    """
    /ai/analyze のリクエストボディ。

    Phase2 では `/notion/ingest` のレスポンス `items` をそのまま
    `items` に渡すことを想定している。
    """

    items: List[NotionNewsItem] = Field(
        ...,
        description="/notion/ingest から取得した NotionNewsItem の配列。",
    )


class AIAnalysisResult(BaseModel):
    """
    1件のニュースに対する AI 判定結果。
    """

    id: str = Field(..., description="Notion ページ ID（入力 NotionNewsItem.id を踏襲）")
    url: str = Field(..., description="ニュースの URL")
    action: TradeAction = Field(..., description="BUY / SELL / HOLD のいずれか")
    confidence: int = Field(
        ...,
        ge=0,
        le=100,
        description="AI 判定の信頼度スコア（0〜100）。安全弁ロジックで 40 未満は HOLD 優先。",
    )
    sentiment: Optional[str] = Field(
        None,
        description="ニュース全体のセンチメント（positive / negative / neutral などの自由テキスト）。",
    )
    summary: Optional[str] = Field(
        None,
        description="ニュース本文の要約。Notion の Summary プロパティに対応させる想定。",
    )
    reason: Optional[str] = Field(
        None,
        description="なぜこのアクションになったのかを説明する短い文章（OctoBot / レポート用）。",
    )
    timestamp: datetime = Field(
        ...,
        description="この判定を行った時刻（UTC）。ISO8601 文字列として入出力される。",
    )


class AIAnalysisResponse(BaseModel):
    """
    /ai/analyze のレスポンス全体。
    """

    results: List[AIAnalysisResult] = Field(
        ...,
        description="AI 判定結果の配列。入力 `items` と 1:1 に対応する。",
    )
    count: int = Field(..., description="results に含まれる件数。")

