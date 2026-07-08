# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/webhook/router.py

"""
Webhook 受信 API エンドポイント。

POST /webhook/tradingview  - TradingView アラートを受信して Knowledge Hub に登録
POST /webhook/generic      - 汎用 Webhook を受信して Knowledge Hub に登録
"""

import logging
import os
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.fees.onramp.webhook_signature import StripeSignatureError, verify_stripe_signature
from app.knowledge.router import get_knowledge_service
from app.knowledge.schemas import KnowledgeCreateRequest, KnowledgeItemType
from app.knowledge.service import KnowledgeService
from app.webhook.config import get_webhook_secret
from app.webhook.schemas import (
    GenericWebhookPayload,
    TradingViewPayload,
    WebhookReceiveResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])


def _verify_webhook_secret(request_secret: Optional[str]) -> None:
    """X-Webhook-Secret ヘッダーを検証する。"""
    configured_secret = get_webhook_secret()
    if configured_secret is None:
        # 未設定時はスキップ（開発時の利便性）
        return
    if request_secret != configured_secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")


@router.post("/tradingview", response_model=WebhookReceiveResponse)
def receive_tradingview(
    payload: TradingViewPayload,
    x_webhook_secret: Optional[str] = Header(None, alias="X-Webhook-Secret"),
    db: Session = Depends(get_db),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> WebhookReceiveResponse:
    """
    TradingView アラート Webhook を受信して Knowledge Hub に登録する。

    - X-Webhook-Secret ヘッダーで認証（WEBHOOK_SECRET 環境変数が設定されている場合）
    - ticker / action / price / message をテキスト形式でフォーマットして登録
    """
    _verify_webhook_secret(x_webhook_secret)

    # ペイロードからテキストを構築する
    parts = [f"[TradingView] {payload.ticker or ''} {payload.action or ''} @ {payload.price}"]
    if payload.message:
        parts.append(payload.message)
    text = "\n".join(parts)

    title = f"TradingView: {payload.ticker or 'Alert'}"

    try:
        item = service.create_item(
            db,
            KnowledgeCreateRequest(
                title=title,
                item_type=KnowledgeItemType.TEXT,
                raw_text=text,
            ),
        )
        logger.info(
            "TradingView webhook registered",
            extra={"knowledge_item_id": item.id, "ticker": payload.ticker},
        )
        return WebhookReceiveResponse(
            received=True,
            knowledge_item_id=item.id,
            message="TradingView webhook registered successfully",
        )
    except Exception as exc:
        logger.error("Failed to register TradingView webhook: %s", exc)
        return WebhookReceiveResponse(
            received=True,
            knowledge_item_id=None,
            message=f"Registration failed: {exc}",
        )


@router.post("/generic", response_model=WebhookReceiveResponse)
def receive_generic(
    payload: GenericWebhookPayload,
    x_webhook_secret: Optional[str] = Header(None, alias="X-Webhook-Secret"),
    db: Session = Depends(get_db),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> WebhookReceiveResponse:
    """
    汎用 Webhook を受信して Knowledge Hub に登録する。

    - X-Webhook-Secret ヘッダーで認証（WEBHOOK_SECRET 環境変数が設定されている場合）
    - url が設定されている場合は URL 種別、それ以外はテキスト種別で登録
    """
    _verify_webhook_secret(x_webhook_secret)

    title = payload.title or f"Webhook: {payload.source or 'generic'}"

    if payload.url:
        request = KnowledgeCreateRequest(
            title=title,
            item_type=KnowledgeItemType.URL,
            source_url=payload.url,
        )
    else:
        request = KnowledgeCreateRequest(
            title=title,
            item_type=KnowledgeItemType.TEXT,
            raw_text=payload.content,
        )

    try:
        item = service.create_item(db, request)
        logger.info(
            "Generic webhook registered",
            extra={"knowledge_item_id": item.id, "source": payload.source},
        )
        return WebhookReceiveResponse(
            received=True,
            knowledge_item_id=item.id,
            message="Generic webhook registered successfully",
        )
    except Exception as exc:
        logger.error("Failed to register generic webhook: %s", exc)
        return WebhookReceiveResponse(
            received=True,
            knowledge_item_id=None,
            message=f"Registration failed: {exc}",
        )


@router.post("/stripe")
async def receive_stripe(request: Request) -> dict[str, Any]:
    """Stripe webhook 受信 (F-7)。

    本体の月額サブスク課金は StripeBillingAdapter.charge_subscription の同期
    PaymentIntent 確認フローが担う (finalize_month_core 内で完結)。本 endpoint は
    非同期に発生し得る異常系 (カード失敗 / キャンセル等) を可視化するログ用途。
    Stripe-Signature (HMAC-SHA256) は app.fees.onramp.webhook_signature の
    純関数を流用して検証する (raw body 必須、JSON パース前のバイト列で検証)。
    """
    import json  # noqa: PLC0415

    payload = await request.body()
    signature_header = request.headers.get("stripe-signature", "")
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()

    try:
        verify_stripe_signature(
            payload=payload,
            signature_header=signature_header,
            secret=secret,
            timestamp_now=int(time.time()),
        )
    except StripeSignatureError as exc:
        logger.warning("Stripe webhook signature verification failed: %s", exc)
        raise HTTPException(status_code=400, detail="invalid signature") from exc

    try:
        event = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="invalid payload") from exc

    event_type = event.get("type", "")
    event_id = event.get("id", "")
    logger.info("Stripe webhook received: type=%s id=%s", event_type, event_id)

    if event_type in ("payment_intent.payment_failed", "payment_intent.canceled"):
        obj = event.get("data", {}).get("object", {})
        logger.warning(
            "Stripe payment failure: pi_id=%s customer=%s amount=%s metadata=%s",
            obj.get("id"),
            obj.get("customer"),
            obj.get("amount"),
            obj.get("metadata"),
        )

    return {"received": True}
