# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""マルチプロトコルヘルス監視 FastAPI ルーター。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from .protocol_monitor import ProtocolMonitor
from .schemas import ProtocolHealth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/protocols/health", tags=["protocol-health"])


def _get_monitor() -> ProtocolMonitor:
    return ProtocolMonitor()


@router.get("", response_model=list[ProtocolHealth])
async def get_all_health() -> list[ProtocolHealth]:
    """全プロトコル（Aave / Lido / Pendle）のヘルスチェック結果を一括返却する。"""
    monitor = _get_monitor()
    try:
        return await monitor.check_all()
    except Exception as exc:
        logger.exception("プロトコル全体ヘルスチェック失敗")
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/aave", response_model=ProtocolHealth)
async def get_aave_health() -> ProtocolHealth:
    """Aave V3 ヘルスチェック結果を返す。"""
    monitor = _get_monitor()
    try:
        return await monitor.check_aave_health()
    except Exception as exc:
        logger.exception("Aave ヘルスチェック失敗")
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/lido", response_model=ProtocolHealth)
async def get_lido_health() -> ProtocolHealth:
    """Lido ヘルスチェック結果を返す。"""
    monitor = _get_monitor()
    try:
        return await monitor.check_lido_health()
    except Exception as exc:
        logger.exception("Lido ヘルスチェック失敗")
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/pendle", response_model=ProtocolHealth)
async def get_pendle_health() -> ProtocolHealth:
    """Pendle ヘルスチェック結果を返す。"""
    monitor = _get_monitor()
    try:
        return await monitor.check_pendle_health()
    except Exception as exc:
        logger.exception("Pendle ヘルスチェック失敗")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
