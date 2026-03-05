# backend/app/dca/service.py

"""
DCA（ドルコスト平均法）積立サービス。

- DCAService.execute(): DCA積立を1回実行する（fail-safe）
"""

from __future__ import annotations

import logging

from app.ai.schemas import TradeAction
from app.exchange.schemas import OrderRequest, OrderStatus
from app.exchange.service import ExchangeService

from .schemas import DCAConfig, DCAExecutionResult

logger = logging.getLogger(__name__)


class DCAService:
    """DCA（ドルコスト平均法）積立サービス。"""

    def __init__(self, exchange_service: ExchangeService) -> None:
        self._exchange_service = exchange_service

    def execute(self, config: DCAConfig) -> DCAExecutionResult:
        """DCA積立を1回実行する。失敗時も例外を投げない（fail-safe）。"""
        if not config.enabled:
            logger.info("DCA skipped: disabled")
            return DCAExecutionResult(
                executed=False,
                symbol=config.symbol,
                amount_usd=config.amount_usd,
                message="DCA is disabled",
            )

        # OrderRequest を構築（常に BUY）
        order_request = OrderRequest(
            action=TradeAction.BUY,
            symbol=config.symbol,
            amount_usd=config.amount_usd,
            dry_run=config.dry_run,
        )

        try:
            result = self._exchange_service.execute_trade(order_request)

            executed = result.status == OrderStatus.SUCCESS
            return DCAExecutionResult(
                executed=executed,
                symbol=config.symbol,
                amount_usd=config.amount_usd,
                order_id=result.order_id,
                message=result.message or "DCA executed",
            )
        except Exception as exc:
            logger.error("DCA execution failed: %s", exc)
            return DCAExecutionResult(
                executed=False,
                symbol=config.symbol,
                amount_usd=config.amount_usd,
                message=f"DCA execution failed: {exc}",
            )
