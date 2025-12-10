# backend/app/notion/schemas.py

"""
Notion から取得したデータを内部で扱うためのスキーマ定義。
"""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field


class NotionNewsItem(BaseModel):
    """
    Notion の 1 レコードを表現する内部モデル。

    docs/09_notion_schema.md のプロパティと 1:1 で対応させる。
    """

    id: str = Field(..., description="Notion ページ ID")
    url: str = Field(..., description="ニュースの URL")
    summary: Optional[str] = Field(None, description="ニュースの要約テキスト")
    sentiment: Optional[str] = Field(
        None,
        description="Sentiment（select 値）: Positive / Negative / Neutral など",
    )
    action: Optional[str] = Field(
        None, description="Action（select 値）: BUY / SELL / HOLD"
    )
    confidence: Optional[float] = Field(
        None,
        ge=0,
        le=100,
        description="AI 判定の信頼度スコア（0-100）",
    )
    status: Optional[str] = Field(
        None,
        description="Status（select 値）: 未処理 / 処理済 など",
    )
    timestamp: Optional[datetime] = Field(
        None,
        description="Timestamp（date プロパティ）。ニュースの日時 or 登録日時。",
    )


class NotionIngestResponse(BaseModel):
    """
    /notion/ingest のレスポンス全体を表現するモデル。

    Phase1 では「Notion からこういう形のデータが取れる」ことがゴール。
    """

    items: List[NotionNewsItem]
    count: int

