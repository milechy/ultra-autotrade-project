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
from .schemas import DCAConfig, DCAExecutionResult
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
