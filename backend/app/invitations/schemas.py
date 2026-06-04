# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/invitations/schemas.py
"""
招待コード関連の Pydantic スキーマ。
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class InvitationCreateRequest(BaseModel):
    """招待コード作成リクエスト。"""

    expires_at: datetime = Field(..., description="有効期限（UTC）")
    max_uses: int = Field(default=1, ge=1, le=100, description="最大使用回数")


class InvitationResponse(BaseModel):
    """招待コードレスポンス。"""

    id: int
    code: str
    type: str = "invite"
    partner_id: Optional[int] = None
    expires_at: datetime
    max_uses: int
    used_count: int
    created_at: datetime
    invited_user_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class InvitationValidateResponse(BaseModel):
    """招待コード検証レスポンス。"""

    valid: bool
    type: Optional[str] = None
    partner_id: Optional[int] = None
    expires_at: Optional[datetime] = None
    uses_remaining: Optional[int] = None
