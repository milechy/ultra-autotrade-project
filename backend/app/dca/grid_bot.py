# backend/app/dca/grid_bot.py
"""
Grid Trading Bot。

- グリッド取引ロジック: 上限価格と下限価格の間に均等グリッドラインを配置
- 各ラインで買い/売り注文を管理
- Decimal型のみ使用（float禁止）
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

from app.ai.schemas import TradeAction
from app.exchange.schemas import OrderRequest, OrderStatus
from app.exchange.service import ExchangeService

logger = logging.getLogger(__name__)


@dataclass
class GridConfig:
    """グリッドボットの設定。"""

    upper_price: Decimal  # グリッド上限価格
    lower_price: Decimal  # グリッド下限価格
    grid_count: int = 10  # グリッド数（デフォルト10）
    symbol: str = "BTC/USDT"
    amount_per_grid_usd: Decimal = field(
        default_factory=lambda: Decimal("10")
    )  # 各グリッドの取引金額
    enabled: bool = True
    dry_run: bool = True


@dataclass
class GridLevel:
    """グリッドの個別レベル。"""

    price: Decimal
    side: str  # "buy" or "sell"
    order_id: Optional[str] = None
    filled: bool = False


@dataclass
class GridStatus:
    """グリッドボットの現在ステータス。"""

    enabled: bool
    symbol: str
    upper_price: Decimal
    lower_price: Decimal
    grid_count: int
    current_price: Optional[Decimal]
    levels: List[GridLevel]
    total_orders: int
    filled_orders: int
    pnl_usd: Decimal  # 簡易損益（実際のP&L計算は複雑なのでゼロで返す）


class GridBotService:
    """グリッドトレーディングボットサービス。"""

    def __init__(self, exchange_service: ExchangeService) -> None:
        self._exchange_service = exchange_service
        self._levels: List[GridLevel] = []
        self._current_config: Optional[GridConfig] = None

    def calculate_levels(
        self, upper: Decimal, lower: Decimal, count: int, current_price: Decimal
    ) -> List[GridLevel]:
        """
        グリッドラインを均等に計算する。

        - upper〜lower を count 等分
        - current_price より上のライン → "sell"（利確）
        - current_price より下のライン → "buy"（仕込み）
        - Decimal型のみ使用
        """
        if count < 2:
            raise ValueError("grid_count must be >= 2")
        if upper <= lower:
            raise ValueError("upper_price must be > lower_price")

        step = (upper - lower) / Decimal(count)
        levels = []
        for i in range(count + 1):
            price = lower + step * Decimal(i)
            side = "sell" if price > current_price else "buy"
            levels.append(GridLevel(price=price, side=side))
        return levels

    def execute(self, config: GridConfig) -> GridStatus:
        """
        グリッドを設定・注文を配置する（fail-safe）。
        """
        if not config.enabled:
            logger.info("Grid bot skipped: disabled")
            return GridStatus(
                enabled=False,
                symbol=config.symbol,
                upper_price=config.upper_price,
                lower_price=config.lower_price,
                grid_count=config.grid_count,
                current_price=None,
                levels=[],
                total_orders=0,
                filled_orders=0,
                pnl_usd=Decimal("0"),
            )

        self._current_config = config

        # 現在価格取得
        try:
            ticker = self._exchange_service._client.fetch_ticker(config.symbol)
            current_price = Decimal(str(ticker["last"]))
        except Exception as exc:
            logger.error("Failed to fetch ticker for grid setup: %s", exc)
            current_price = (config.upper_price + config.lower_price) / Decimal("2")

        # グリッドライン計算
        self._levels = self.calculate_levels(
            config.upper_price, config.lower_price, config.grid_count, current_price
        )

        # 各レベルに注文配置（buy レベルのみ実際に発注、sell は価格アラートとして管理）
        for level in self._levels:
            if level.side == "buy":
                request = OrderRequest(
                    action=TradeAction.BUY,
                    symbol=config.symbol,
                    amount_usd=config.amount_per_grid_usd,
                    dry_run=config.dry_run,
                    reason=f"Grid buy at {level.price}",
                )
                try:
                    result = self._exchange_service.execute_trade(request)
                    if result.status == OrderStatus.SUCCESS:
                        level.order_id = result.order_id
                        level.filled = True
                        logger.info(
                            "Grid buy order placed at %s: order_id=%s",
                            level.price,
                            result.order_id,
                        )
                except Exception as exc:
                    logger.error("Grid order failed at %s: %s", level.price, exc)

        filled = sum(1 for lvl in self._levels if lvl.filled)
        return GridStatus(
            enabled=True,
            symbol=config.symbol,
            upper_price=config.upper_price,
            lower_price=config.lower_price,
            grid_count=config.grid_count,
            current_price=current_price,
            levels=self._levels,
            total_orders=len(self._levels),
            filled_orders=filled,
            pnl_usd=Decimal("0"),
        )

    def get_status(self, config: GridConfig) -> GridStatus:
        """現在のグリッドステータスを返す（注文は発注しない）。"""
        try:
            ticker = self._exchange_service._client.fetch_ticker(config.symbol)
            current_price: Optional[Decimal] = Decimal(str(ticker["last"]))
        except Exception:
            current_price = None

        filled = sum(1 for lvl in self._levels if lvl.filled)
        return GridStatus(
            enabled=config.enabled,
            symbol=config.symbol,
            upper_price=config.upper_price,
            lower_price=config.lower_price,
            grid_count=config.grid_count,
            current_price=current_price,
            levels=self._levels,
            total_orders=len(self._levels),
            filled_orders=filled,
            pnl_usd=Decimal("0"),
        )


def get_grid_config_from_env() -> GridConfig:
    """環境変数からGridConfigを構築する。"""
    enabled = os.getenv("GRID_ENABLED", "false").lower() in ("true", "1", "yes")
    upper = Decimal(os.getenv("GRID_UPPER", "60000"))
    lower = Decimal(os.getenv("GRID_LOWER", "40000"))
    count = int(os.getenv("GRID_COUNT", "10"))
    symbol = os.getenv("GRID_SYMBOL", "BTC/USDT")
    amount = Decimal(os.getenv("GRID_AMOUNT_USD", "10"))
    dry_run = os.getenv("GRID_DRY_RUN", "true").lower() in ("true", "1", "yes")
    return GridConfig(
        upper_price=upper,
        lower_price=lower,
        grid_count=count,
        symbol=symbol,
        amount_per_grid_usd=amount,
        enabled=enabled,
        dry_run=dry_run,
    )
