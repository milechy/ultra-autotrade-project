# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/automation/rate_limiter_schemas.py
"""レート制限 API レスポンススキーマ。"""

from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel, Field


class ApiRateLimitEntry(BaseModel):
    """1つのAPIのレート制限状態。"""

    api_name: str = Field(..., description="API識別子（例: claude_calls）")
    display_name: str = Field(..., description="表示名（例: Claude API (calls/min)）")
    current: int = Field(..., ge=0, description="現在のウィンドウ内使用数")
    limit: int = Field(..., ge=1, description="ウィンドウ内の上限")
    window_seconds: int = Field(..., ge=1, description="ウィンドウ幅（秒）")
    usage_pct: float = Field(..., ge=0.0, le=100.0, description="使用率（%）")
    reset_in_seconds: float = Field(..., ge=0.0, description="リセットまでの残り秒数")


class RateLimitStatus(BaseModel):
    """GET /automation/rate-limits のレスポンス。"""

    generated_at: datetime = Field(..., description="取得時刻（UTC）")
    apis: List[ApiRateLimitEntry] = Field(..., description="各APIの制限状態")
