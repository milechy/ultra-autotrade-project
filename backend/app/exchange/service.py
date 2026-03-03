# backend/app/exchange/service.py

"""
Exchange サービス層（ルールエンジン）。

責務:
- HOLD → 即時 SKIPPED
- 日次取引上限チェック
- クールダウン期間チェック
- 最大注文金額チェック
- dry_run チェック
- 取引所クライアントへの注文委譲
- 取引ログの管理
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Tuple, Union

from app.ai.schemas import TradeAction

from .client import ExchangeClientError, DummyExchangeClient, BybitSandboxClient
from .config import ExchangeSettings, get_exchange_settings
from .schemas import ExchangeStatusResponse, OrderRequest, OrderResult, OrderSide, OrderStatus

logger = logging.getLogger(__name__)

# クライアントの型エイリアス（Protocol を使わずに Union で表現）
_ExchangeClient = Union[BybitSandboxClient, DummyExchangeClient]


class ExchangeService:
    """
    AI 判定結果から取引注文を生成・実行するサービス層。

    ルールチェックを順番に適用し、問題がなければ取引所クライアントに注文を委譲する。
    全てのルールはインメモリで管理する（PoC フェーズ）。
    """

    def __init__(
        self,
        client: _ExchangeClient,
        *,
        settings: Optional[ExchangeSettings] = None,
    ) -> None:
        self._client = client
        self._settings = settings or get_exchange_settings()
        # (side, timestamp) のタプルリスト。インプロセスで当日分を保持する。
        self._trade_log: List[Tuple[str, datetime]] = []

    # ---- 公開 API ------------------------------------------------------

    def execute_trade(self, request: OrderRequest) -> OrderResult:
        """
        注文リクエストを受け取り、ルールチェック後に取引を実行する。

        処理フロー:
        1. HOLD → SKIPPED
        2. 日次取引上限チェック
        3. クールダウンチェック
        4. 最大注文金額チェック
        5. dry_run チェック
        6. ティッカー取得 → USD を数量に変換
        7. 成行注文送信
        """
        now = datetime.now(timezone.utc)
        symbol = request.symbol or self._settings.default_symbol

        # 1. HOLD → 即時 SKIPPED
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

        # 2. 日次取引上限チェック
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

        # 3. クールダウンチェック
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

        # 4. 最大注文金額チェック
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

        # 5. dry_run チェック
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

        # 6. ティッカー取得 → USD を数量に変換
        try:
            ticker = self._client.fetch_ticker(symbol)
            price = Decimal(str(ticker["last"]))
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

        # 7. アクションを side にマッピングして成行注文送信
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
        取引所の接続状態および本日の取引状況を返す。

        接続チェックに失敗した場合も例外は投げず、connected=False として返す。
        """
        now = datetime.now(timezone.utc)
        daily_count = self._get_daily_trade_count(now)
        last_trade = self._get_last_trade_at()

        # 残高取得を試みて接続確認とする
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

    # ---- 内部ヘルパー --------------------------------------------------

    def _get_daily_trade_count(self, now: datetime) -> int:
        """
        本日（UTC 日付）に実行した取引件数を返す。
        """
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return sum(1 for _, ts in self._trade_log if ts >= start_of_day)

    def _get_last_trade_at(self) -> Optional[datetime]:
        """
        最後に取引を実行した時刻を返す。取引がなければ None。
        """
        if not self._trade_log:
            return None
        return self._trade_log[-1][1]
