# backend/app/dca/router.py

"""
DCA（ドルコスト平均法）の HTTP エンドポイント。

- POST /dca/execute  — DCA積立を即時1回実行する（手動トリガー）
- GET  /dca/config   — 現在のDCA設定を返す
- POST /dca/config   — DCA設定を更新する（インメモリ）
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

import app.dca.config as dca_config_module
from app.exchange.client import DummyExchangeClient
from app.exchange.service import ExchangeService

from .config import get_dca_config
from .grid_bot import GridBotService, GridConfig, get_grid_config_from_env
from .schemas import (
    DCAConfig,
    DCAExecutionResult,
    GridConfigRequest,
    GridLevelResponse,
    GridStatusResponse,
)
from .service import DCAService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dca", tags=["dca"])


def _get_dca_service() -> DCAService:
    """DCAService の依存性注入ファクトリ。"""
    client = DummyExchangeClient()
    exchange_service = ExchangeService(client=client)
    return DCAService(exchange_service=exchange_service)


@router.post("/execute", response_model=DCAExecutionResult)
def execute_dca(
    service: DCAService = Depends(_get_dca_service),
) -> DCAExecutionResult:
    """DCA積立を即時1回実行する（手動トリガー）。"""
    config = get_dca_config()
    return service.execute(config)


@router.get("/config", response_model=DCAConfig)
def get_config() -> DCAConfig:
    """現在のDCA設定を返す。"""
    return get_dca_config()


@router.post("/config", response_model=DCAConfig)
def update_config(new_config: DCAConfig) -> DCAConfig:
    """DCA設定を更新する（インメモリ。再起動で環境変数にリセット）。"""
    dca_config_module._dca_config = new_config
    logger.info(
        "DCA config updated: enabled=%s, amount_usd=%s, frequency=%s, dry_run=%s",
        new_config.enabled,
        new_config.amount_usd,
        new_config.frequency.value,
        new_config.dry_run,
    )
    return new_config


def _get_grid_service() -> GridBotService:
    """GridBotService の依存性注入ファクトリ。"""
    client = DummyExchangeClient()
    exchange_service = ExchangeService(client=client)
    return GridBotService(exchange_service=exchange_service)


def _to_grid_status_response(status: object) -> GridStatusResponse:
    """GridStatus → GridStatusResponse に変換する。"""
    from .grid_bot import GridStatus

    assert isinstance(status, GridStatus)
    return GridStatusResponse(
        enabled=status.enabled,
        symbol=status.symbol,
        upper_price=status.upper_price,
        lower_price=status.lower_price,
        grid_count=status.grid_count,
        current_price=status.current_price,
        levels=[
            GridLevelResponse(
                price=lvl.price,
                side=lvl.side,
                order_id=lvl.order_id,
                filled=lvl.filled,
            )
            for lvl in status.levels
        ],
        total_orders=status.total_orders,
        filled_orders=status.filled_orders,
        pnl_usd=status.pnl_usd,
    )


@router.post("/grid/execute", response_model=GridStatusResponse)
def execute_grid(
    body: GridConfigRequest,
    service: GridBotService = Depends(_get_grid_service),
) -> GridStatusResponse:
    """グリッドボットを設定・実行する。"""
    config = GridConfig(
        upper_price=body.upper_price,
        lower_price=body.lower_price,
        grid_count=body.grid_count,
        symbol=body.symbol,
        amount_per_grid_usd=body.amount_per_grid_usd,
        enabled=body.enabled,
        dry_run=body.dry_run,
    )
    status = service.execute(config)
    return _to_grid_status_response(status)


@router.get("/grid/status", response_model=GridStatusResponse)
def get_grid_status(
    service: GridBotService = Depends(_get_grid_service),
) -> GridStatusResponse:
    """現在のグリッドステータスを返す（注文は発注しない）。"""
    config = get_grid_config_from_env()
    status = service.get_status(config)
    return _to_grid_status_response(status)


@router.get("/grid/config", response_model=GridConfigRequest)
def get_grid_config() -> GridConfigRequest:
    """環境変数からグリッド設定を取得して返す。"""
    config = get_grid_config_from_env()
    return GridConfigRequest(
        upper_price=config.upper_price,
        lower_price=config.lower_price,
        grid_count=config.grid_count,
        symbol=config.symbol,
        amount_per_grid_usd=config.amount_per_grid_usd,
        enabled=config.enabled,
        dry_run=config.dry_run,
    )
