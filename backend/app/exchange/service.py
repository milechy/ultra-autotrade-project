# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/exchange/service.py

"""
Exchange service layer (rule engine).

Responsibilities:
- HOLD → immediate SKIPPED
- Daily trade limit check
- Cooldown period check
- Maximum order amount check
- Dry-run check
- Delegate order execution to exchange client
- Manage trade log
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, List, Optional, Tuple

from app.ai.schemas import TradeAction

from .client import ExchangeClientError
from .config import ExchangeSettings, get_exchange_settings
from .schemas import ExchangeStatusResponse, OrderRequest, OrderResult, OrderSide, OrderStatus

logger = logging.getLogger(__name__)

# Client type alias (OKXClient / KrakenClient use Any to avoid circular imports)
_ExchangeClient = (
    Any  # BybitSandboxClient | BitFlyerClient | DummyExchangeClient | OKXClient | KrakenClient
)


class ExchangeService:
    """
    Service layer that generates and executes trade orders from AI judgment results.

    Applies rule checks in sequence; delegates to the exchange client if all checks pass.
    All rules are managed in-memory (PoC phase).
    """

    def __init__(
        self,
        client: _ExchangeClient,
        *,
        settings: Optional[ExchangeSettings] = None,
    ) -> None:
        self._client = client
        self._settings = settings or get_exchange_settings()
        # List of (side, timestamp) tuples. Holds today's trades in-process.
        self._trade_log: List[Tuple[str, datetime]] = []

    # ---- Public API ------------------------------------------------------

    def execute_trade(self, request: OrderRequest) -> OrderResult:
        """
        Accept an order request, run rule checks, then execute the trade.

        Processing flow:
        1. HOLD → SKIPPED
        2. Daily trade limit check
        3. Cooldown check
        4. Maximum order amount check
        5. Dry-run check
        6. Fetch ticker → convert USD to quantity
        7. Submit market order
        """
        now = datetime.now(timezone.utc)
        symbol = request.symbol or self._settings.default_symbol

        # 1. HOLD → immediate SKIPPED
        if request.action == TradeAction.HOLD:
            logger.info(
                "Trade skipped: action is HOLD",
                extra={"action": "HOLD", "symbol": symbol, "status": "SKIPPED"},
            )
            return OrderResult(
                status=OrderStatus.SKIPPED,
                symbol=symbol,
                amount_usd=request.amount_usd,
                message="Action is HOLD - no trade executed",
                timestamp=now,
            )

        # 2. Daily trade limit check
        daily_count = self._get_daily_trade_count(now)
        if daily_count >= self._settings.daily_trade_limit:
            logger.warning(
                "Trade skipped: daily trade limit reached",
                extra={
                    "daily_count": daily_count,
                    "limit": self._settings.daily_trade_limit,
                    "symbol": symbol,
                    "status": "SKIPPED",
                },
            )
            return OrderResult(
                status=OrderStatus.SKIPPED,
                symbol=symbol,
                amount_usd=request.amount_usd,
                message=(
                    f"Daily trade limit reached ({daily_count}/{self._settings.daily_trade_limit})"
                ),
                timestamp=now,
            )

        # 3. Cooldown check
        last_trade = self._get_last_trade_at()
        if last_trade is not None:
            elapsed = (now - last_trade).total_seconds()
            if elapsed < self._settings.cooldown_seconds:
                remaining = int(self._settings.cooldown_seconds - elapsed)
                logger.info(
                    "Trade skipped: cooldown period active",
                    extra={
                        "elapsed_seconds": int(elapsed),
                        "cooldown_seconds": self._settings.cooldown_seconds,
                        "remaining_seconds": remaining,
                        "symbol": symbol,
                        "status": "SKIPPED",
                    },
                )
                return OrderResult(
                    status=OrderStatus.SKIPPED,
                    symbol=symbol,
                    amount_usd=request.amount_usd,
                    message=f"Cooldown period active ({remaining}s remaining)",
                    timestamp=now,
                )

        # 4. Maximum order amount check
        if request.amount_usd > self._settings.max_order_usd:
            logger.warning(
                "Trade skipped: amount exceeds max order USD",
                extra={
                    "amount_usd": str(request.amount_usd),
                    "max_order_usd": str(self._settings.max_order_usd),
                    "symbol": symbol,
                    "status": "SKIPPED",
                },
            )
            return OrderResult(
                status=OrderStatus.SKIPPED,
                symbol=symbol,
                amount_usd=request.amount_usd,
                message=(
                    f"Amount {request.amount_usd} exceeds max order USD {self._settings.max_order_usd}"
                ),
                timestamp=now,
            )

        # 5. Dry-run check
        if request.dry_run:
            logger.info(
                "Trade skipped: dry run mode",
                extra={"action": request.action.value, "symbol": symbol, "status": "SKIPPED"},
            )
            return OrderResult(
                status=OrderStatus.SKIPPED,
                symbol=symbol,
                amount_usd=request.amount_usd,
                message="Dry run - order not executed",
                timestamp=now,
            )

        # 6. Fetch ticker → convert USD to quantity
        try:
            ticker = self._client.fetch_ticker(symbol)
            price = Decimal(str(ticker["last"]))
            # For BTC/JPY: convert amount_usd to JPY first, then calculate BTC quantity
            if "/JPY" in symbol:
                amount_jpy = request.amount_usd * Decimal(str(self._settings.usd_to_jpy_rate))
                quantity = float(amount_jpy / price)
            else:
                quantity = float(request.amount_usd / price)
        except ExchangeClientError as exc:
            logger.error(
                "Failed to fetch ticker for price conversion: %s",
                exc,
                extra={"symbol": symbol, "status": "FAILED"},
            )
            return OrderResult(
                status=OrderStatus.FAILED,
                symbol=symbol,
                amount_usd=request.amount_usd,
                message=f"Failed to fetch ticker: {exc}",
                timestamp=now,
            )

        # 7. Map action to side and submit market order
        side = "buy" if request.action == TradeAction.BUY else "sell"

        try:
            order = self._client.create_market_order(symbol, side, quantity)
            self._trade_log.append((side, now))

            logger.info(
                "Trade executed successfully",
                extra={
                    "order_id": str(order.get("id", "")),
                    "action": request.action.value,
                    "side": side,
                    "symbol": symbol,
                    "amount_usd": str(request.amount_usd),
                    "price": str(price),
                    "status": "SUCCESS",
                },
            )

            return OrderResult(
                order_id=str(order.get("id", "")),
                status=OrderStatus.SUCCESS,
                side=OrderSide(side),
                symbol=symbol,
                amount_usd=request.amount_usd,
                price=price,
                message="Order executed successfully",
                timestamp=now,
            )

        except Exception as exc:
            logger.error(
                "Trade execution failed: %s",
                exc,
                extra={
                    "action": request.action.value,
                    "side": side,
                    "symbol": symbol,
                    "amount_usd": str(request.amount_usd),
                    "status": "FAILED",
                },
            )
            return OrderResult(
                status=OrderStatus.FAILED,
                symbol=symbol,
                amount_usd=request.amount_usd,
                message=f"Execution failed: {exc}",
                timestamp=now,
            )

    def get_status(self) -> ExchangeStatusResponse:
        """
        Return exchange connection status and today's trade summary.

        On connection check failure, returns connected=False without raising an exception.
        """
        now = datetime.now(timezone.utc)
        daily_count = self._get_daily_trade_count(now)
        last_trade = self._get_last_trade_at()

        # Attempt to fetch balance as a connectivity check
        balance_usdt: Optional[Decimal] = None
        connected = False
        try:
            balance = self._client.fetch_balance()
            usdt_info = balance.get("USDT", {})
            raw_total = usdt_info.get("total")
            if raw_total is not None:
                balance_usdt = Decimal(str(raw_total))
            connected = True
        except Exception as exc:
            logger.warning("Exchange connection check failed: %s", exc)

        return ExchangeStatusResponse(
            sandbox_mode=self._settings.sandbox,
            connected=connected,
            balance_usdt=balance_usdt,
            daily_trades_used=daily_count,
            daily_trade_limit=self._settings.daily_trade_limit,
            last_trade_at=last_trade,
        )

    def get_price_change_24h(self, symbol: Optional[str] = None) -> Optional[Decimal]:
        """
        24 時間の価格変動率を取得する（小数表現、例: -0.12 = -12%）。

        ccxt の fetch_ticker が返す percentage フィールドを使用する。
        percentage はパーセント表現（例: -12.5）なので 100 で割って小数に変換する。
        取得失敗時は None を返す（例外をキャッチしてログに記録）。

        Args:
            symbol: 取引シンボル（省略時は設定のデフォルトシンボル）

        Returns:
            Decimal | None: 小数表現の変動率（-0.12 = -12%）
        """
        target = symbol or self._settings.default_symbol
        try:
            ticker = self._client.fetch_ticker(target)
            raw = ticker.get("percentage")
            if raw is None:
                # Bybit の info フィールドにある priceChangePercent を試みる
                info = ticker.get("info", {})
                raw = info.get("priceChangePercent")
            if raw is None:
                logger.debug(
                    "price_change_24h: percentage field not found in ticker for %s", target
                )
                return None
            return Decimal(str(raw)) / Decimal("100")
        except Exception as exc:
            logger.warning("Failed to get price_change_24h for %s: %s", target, exc)
            return None

    # ---- Internal helpers --------------------------------------------------

    def _get_daily_trade_count(self, now: datetime) -> int:
        """
        Return the number of trades executed today (UTC date).
        """
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return sum(1 for _, ts in self._trade_log if ts >= start_of_day)

    def _get_last_trade_at(self) -> Optional[datetime]:
        """
        Return the timestamp of the last executed trade, or None if no trades exist.
        """
        if not self._trade_log:
            return None
        return self._trade_log[-1][1]
