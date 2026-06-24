# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/users/registration_webhook.py
"""
新規ユーザー登録完了後に ScrapingForce へ Webhook を非同期送信するモジュール。

fire-and-forget: 送信失敗してもユーザー登録レスポンスには影響しない。
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

_WEBHOOK_URL = "https://sf.ultra-auto-trade.com/api/webhooks/uat-registration"
_TIMEOUT = 10.0


async def send_registration_webhook(
    email: str,
    uat_user_id: int,
    referral_code: str | None,
    registered_at: str,
) -> None:
    """登録完了 Webhook を ScrapingForce へ非同期送信する（fire-and-forget）。

    UAT_WEBHOOK_SECRET 未設定時は警告ログのみで送信をスキップする。
    送信失敗時も例外を握りつぶし、呼び出し元には影響を与えない。
    """
    secret = os.getenv("UAT_WEBHOOK_SECRET")
    if not secret:
        logger.warning("UAT_WEBHOOK_SECRET not set, skipping registration webhook")
        return

    payload = {
        "email": email,
        "uat_user_id": uat_user_id,
        "referral_code": referral_code,
        "registered_at": registered_at,
    }
    headers = {"x-uat-webhook-secret": secret}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(_WEBHOOK_URL, json=payload, headers=headers)
        if resp.status_code >= 400:
            logger.warning(
                "Registration webhook returned %d for user_id=%d",
                resp.status_code,
                uat_user_id,
            )
        else:
            logger.info("Registration webhook sent for user_id=%d", uat_user_id)
    except Exception:
        logger.warning(
            "Registration webhook failed for user_id=%d",
            uat_user_id,
            exc_info=True,
        )
