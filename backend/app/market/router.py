# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/market/router.py
"""市場価格 API ルーター定義。

GET /api/market/prices — ETH/USD (取引所 ccxt) と USD/JPY (open.er-api.com) を返す。
両者とも fail-open: 外部取得に失敗しても 200 を返す
(ETH/USD は None、USD/JPY は環境変数フォールバック)。
"""

import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import httpx
from fastapi import APIRouter, Depends

from app.auth.dependencies import require_active_user
from app.auth.models import User
from app.exchange.router import get_exchange_service
from app.exchange.service import ExchangeService

from .schemas import MarketPricesResponse

router = APIRouter(prefix="/api/market", tags=["market"])

# USD/JPY モジュールレベルキャッシュ (TTL 300秒): {"usd_jpy": (timestamp, rate)}。
# time.monotonic() は表示用途 (財務計算ではない) のため float 許容。
_usd_jpy_cache: dict[str, tuple[float, Decimal]] = {}
_USD_JPY_TTL_SECONDS = 300


async def _get_usd_jpy() -> Decimal:
    """USD/JPY レートを取得する (TTL 300秒キャッシュ / fail-open)。

    取得失敗時は環境変数 USD_TO_JPY_RATE (デフォルト 150) にフォールバックする。
    """
    now = time.monotonic()
    cached = _usd_jpy_cache.get("usd_jpy")
    if cached is not None:
        ts, rate = cached
        if now - ts < _USD_JPY_TTL_SECONDS:
            return rate
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("https://open.er-api.com/v6/latest/USD")
            resp.raise_for_status()
            rate = Decimal(str(resp.json()["rates"]["JPY"]))
            _usd_jpy_cache["usd_jpy"] = (now, rate)
            return rate
    except Exception:
        return Decimal(str(os.getenv("USD_TO_JPY_RATE", "150")))


def _get_eth_usd(service: ExchangeService) -> Optional[Decimal]:
    """ETH/USD を取引所 ticker から取得する (fail-open)。

    取得失敗 (タイムアウト等) 時は None を返し、呼び出し側は 200 を返す。
    """
    try:
        ticker = service._client.fetch_ticker("ETH/USDT")
        return Decimal(str(ticker["last"]))
    except Exception:
        return None


@router.get("/prices", response_model=MarketPricesResponse, summary="市場価格 (ETH/USD, USD/JPY)")
async def get_market_prices(
    current_user: User = Depends(require_active_user),
    service: ExchangeService = Depends(get_exchange_service),
) -> MarketPricesResponse:
    """ETH/USD と USD/JPY を返す。外部取得失敗時も 200 (fail-open)。"""
    eth_usd = _get_eth_usd(service)
    usd_jpy = await _get_usd_jpy()
    return MarketPricesResponse(
        eth_usd=eth_usd,
        usd_jpy=usd_jpy,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
