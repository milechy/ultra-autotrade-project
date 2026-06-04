# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/tos/schemas.py
"""ToS 同意 API のリクエスト / レスポンススキーマ。"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ToSConsentRequest(BaseModel):
    """ToS 同意ログ POST リクエスト。

    is_demo_ack: 「デモ運用 / 実資金は動かさない」明示同意 (MVP では必須 True)。
    fully_read:  スクロール追跡で全文読了したことを示すクライアント側フラグ。
                 これが False の場合 422 を返し永続化を拒否する (active consent 強制)。
    """

    tos_version: str = Field(..., min_length=1, max_length=32)
    is_demo_ack: bool = Field(
        ..., description="デモ運用同意 (default uncheck から true への変更が必須)"
    )
    fully_read: bool = Field(..., description="ToS 全文読了 (スクロール追跡)")


class ToSConsentResponse(BaseModel):
    """ToS 同意ログ作成 / 取得レスポンス。"""

    id: int
    user_id: int
    tos_version: str
    consent_at: datetime
    consent_hash: str
    is_demo_ack: bool

    model_config = {"from_attributes": True}


class ToSConsentCurrentResponse(BaseModel):
    """現在の最新 ToS 同意ステータス。"""

    has_consent: bool
    latest: Optional[ToSConsentResponse] = None
