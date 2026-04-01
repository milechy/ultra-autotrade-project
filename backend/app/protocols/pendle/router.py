# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Pendle Finance FastAPI ルーター。
⚠️ このルーターは feature/phase2-protocols ブランチ専用。
main.py への登録は dev マージ時に行う。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from .client import get_pendle_client
from .config import get_pendle_config
from .schemas import (
    PendleMarketInfo,
    PendleMintRequest,
    PendleMintResponse,
    PendleRedeemRequest,
    PendleRedeemResponse,
    StrategyComparison,
)
from .service import PendleService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/protocols/pendle", tags=["pendle"])


def _get_service() -> PendleService:
    config = get_pendle_config()
    client = get_pendle_client(config)
    return PendleService(client=client, config=config)


@router.get("/markets", response_model=list[PendleMarketInfo])
async def list_markets() -> list[PendleMarketInfo]:
    """利用可能なマーケット一覧を返す（現在は stETH マーケットのみ）。"""
    service = _get_service()
    try:
        config = get_pendle_config()
        market_info = await service.get_market_info(config.market_address)
        return [market_info]
    except Exception as exc:
        logger.exception("Pendle markets 取得失敗")
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/market/{address}", response_model=PendleMarketInfo)
async def get_market(address: str) -> PendleMarketInfo:
    """指定アドレスのマーケット詳細情報を返す。"""
    service = _get_service()
    try:
        return await service.get_market_info(address)
    except Exception as exc:
        logger.exception("Pendle market 取得失敗: address=%s", address)
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/mint", response_model=PendleMintResponse)
async def mint_tokens(request: PendleMintRequest) -> PendleMintResponse:
    """PT または YT のミント実行。dry_run=True（デフォルト）でシミュレーション。"""
    service = _get_service()
    try:
        return await service.mint(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Pendle mint 失敗")
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/redeem", response_model=PendleRedeemResponse)
async def redeem_tokens(request: PendleRedeemRequest) -> PendleRedeemResponse:
    """PT または YT のリデーム実行。dry_run=True（デフォルト）でシミュレーション。"""
    service = _get_service()
    try:
        return await service.redeem(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Pendle redeem 失敗")
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/strategies", response_model=StrategyComparison)
async def get_strategies(amount: str = "1.0") -> StrategyComparison:
    """利用可能な戦略の比較を返す。"""
    from decimal import Decimal  # noqa: PLC0415

    from ..lido.client import get_lido_client as get_lido  # noqa: PLC0415
    from ..lido.config import get_lido_config  # noqa: PLC0415
    from .strategy import LidoPendleCompoundStrategy  # noqa: PLC0415

    try:
        amount_decimal = Decimal(amount)
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail="Invalid amount format. Use numeric string."
        ) from exc

    try:
        lido_config = get_lido_config()
        lido_client = get_lido(lido_config)
        pendle_config = get_pendle_config()
        pendle_client = get_pendle_client(pendle_config)

        strategy = LidoPendleCompoundStrategy(
            lido_client=lido_client,
            pendle_client=pendle_client,
        )
        return await strategy.compare_strategies(
            amount=amount_decimal,
            market_address=pendle_config.market_address,
        )
    except Exception as exc:
        logger.exception("Pendle strategies 取得失敗")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
