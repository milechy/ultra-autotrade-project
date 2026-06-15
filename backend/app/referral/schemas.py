# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/referral/schemas.py
"""RAS Lane 2 Pydantic スキーマ。

法務未クリアのため、レスポンスには ``wallet_address`` / ``tx_hash`` を含めない。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ReferralCodeResponse(BaseModel):
    """紹介コード取得レスポンス。"""

    referral_code: str
    share_url: str


class ReferredUserResponse(BaseModel):
    """紹介経由で登録されたユーザーの一覧アイテム。"""

    id: int
    email_masked: str  # "y***@example.com" 形式
    role: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReferralTransactionResponse(BaseModel):
    """紹介ユーザーの取引履歴アイテム。

    ※ ``wallet_address`` / ``tx_hash`` は法務未クリアのため意図的に含めない。
    """

    type: Literal["deposit", "withdraw", "borrow", "repay"]
    amount: str  # Decimal を文字列で返却 (CLAUDE.md ルール)
    occurred_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReferralEarningsResponse(BaseModel):
    """紹介キャンペーン収益サマリー。

    金額は Decimal を文字列で返却 (CLAUDE.md §21)。
    """

    referral_count: int
    current_month_reward_jpy: str
    total_payout_jpy: str
    campaign_rate: str  # e.g. "0.1000" (10%)
    campaign_expires_month: str | None  # "2027-01-01" 形式 or None


class ReferredUserDetail(BaseModel):
    """LIFF 紹介パネル用: 紹介済みユーザーのサマリー。"""

    name: str
    joined_at: datetime
    status: str  # "active" | "registered"
    reward_jpy: str  # ¥1,500 bonus は別タスク: 現在は常に "0"


class ReferralInfoResponse(BaseModel):
    """LIFF 紹介パネル用: /api/referral/earnings レスポンス。

    frontend/lib/api/referral.ts の ReferralInfo インターフェースと一致させること。
    """

    referral_count: int
    current_month_reward_jpy: str
    total_payout_jpy: str
    campaign_rate: str
    referral_code: str
    referred_users: list[ReferredUserDetail]
