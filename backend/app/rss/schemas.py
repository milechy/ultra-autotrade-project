# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/rss/schemas.py

"""
RSS モジュールのスキーマ定義。

API リクエスト／レスポンスおよび内部データ転送オブジェクトを定義する。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RSSFeedConfig(BaseModel):
    """RSS フィード設定。"""

    name: str = Field(..., description="フィード名（例: CoinPost）")
    url: str = Field(..., description="RSS フィード URL")
    enabled: bool = Field(True, description="取得を有効にするか")


class RSSEntry(BaseModel):
    """RSS フィードの1エントリ。"""

    title: str
    url: str
    published_at: Optional[datetime] = None
    summary: Optional[str] = None


class RSSFetchResult(BaseModel):
    """RSS 取得結果レスポンス。"""

    results: dict[str, int] = Field(default_factory=dict, description="フィード名 → 登録件数")
    total: int = Field(0, description="合計登録件数")
