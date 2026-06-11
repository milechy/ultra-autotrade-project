# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Lido Finance FastAPI ルーター。
⚠️ このルーターは feature/phase2-protocols ブランチ専用。
main.py への登録は dev マージ時に行う。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.dependencies import require_admin

from .client import get_lido_client
from .config import get_lido_config
from .schemas import (
    LidoAprResponse,
    LidoClaimRequest,
    LidoClaimResponse,
    LidoStakeRequest,
    LidoStakeResponse,
    LidoStatus,
    LidoWithdrawalRequestsResponse,
    LidoWithdrawalStatusResponse,
    LidoWithdrawRequest,
    LidoWithdrawResponse,
)
from .service import ClaimNotReadyError, LidoService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/protocols/lido", tags=["lido"])


def _get_service() -> LidoService:
    config = get_lido_config()
    client = get_lido_client(config)
    return LidoService(client=client, config=config)


@router.get("/status", response_model=LidoStatus)
async def get_lido_status() -> LidoStatus:
    """Lido ステータス取得（残高・APR・peg乖離）。"""
    service = _get_service()
    try:
        return await service.get_status()
    except Exception as exc:
        logger.exception("Lido status 取得失敗")
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/stake",
    response_model=LidoStakeResponse,
    dependencies=[Depends(require_admin)],
)
async def stake_eth(request: LidoStakeRequest) -> LidoStakeResponse:
    """ETH → stETH ステーキング実行。dry_run=True（デフォルト）でシミュレーション。

    実資金 write エンドポイントのため admin RBAC 必須（require_admin）。
    """
    service = _get_service()
    try:
        return await service.stake(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Lido stake 失敗")
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/withdraw",
    response_model=LidoWithdrawResponse,
    dependencies=[Depends(require_admin)],
)
async def withdraw_steth(request: LidoWithdrawRequest) -> LidoWithdrawResponse:
    """stETH → ETH 引き出しリクエスト送信。dry_run=True（デフォルト）でシミュレーション。

    Lido の引き出しは非同期（リクエスト→待機→クレーム）。
    このエンドポイントはリクエスト送信のみ。クレームは待機期間（1〜5日）後に実行。
    実資金 write エンドポイントのため admin RBAC 必須（require_admin）。
    """
    service = _get_service()
    try:
        return await service.withdraw(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Lido withdraw 失敗")
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/apr", response_model=LidoAprResponse)
async def get_lido_apr() -> LidoAprResponse:
    """現在の Lido staking APR を返す。"""
    service = _get_service()
    try:
        return await service.get_apr()
    except Exception as exc:
        logger.exception("Lido APR 取得失敗")
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/claim",
    response_model=LidoClaimResponse,
    dependencies=[Depends(require_admin)],
)
async def claim_withdrawal(request: LidoClaimRequest) -> LidoClaimResponse:
    """引き出しクレーム実行（checkpoint hints 方式）。dry_run=True（デフォルト）でシミュレーション。

    Lido WithdrawalQueue の finalized 済みリクエストに対してクレームを実行する。
    待機期間（1〜5日）が完了してから呼ぶこと。
    複数の request_ids を一括クレームできる。

    セキュリティ:
    - 実資金 write エンドポイントのため admin RBAC 必須（require_admin）。
    - dry_run=False の実 claim 実行前に getWithdrawalStatus で
      ``is_finalized && not is_claimed`` を precheck し、満たさなければ
      tx を送らず 409 を返す（fail-closed / レビュー C2-(b)）。

    [M1 注記 / ガス境界] 現状の checkpoint-hints 実装はガス有界だが、
    本番（production）での dry_run=False 解禁は、claimWithdrawals に
    findCheckpointHints 由来の hints を完全供給する経路の検証が完了してから行うこと。
    hint 方式が未検証の状態では production の実 claim を有効化しない（レビュー M1）。
    """
    service = _get_service()
    try:
        return await service.claim(request)
    except ClaimNotReadyError as exc:
        # finalize 未完 / claim 済み → fail-closed で 409。tx は未送信。
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Lido claim 失敗")
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/withdrawal-status", response_model=LidoWithdrawalStatusResponse)
async def get_withdrawal_status(
    request_ids: str = Query(
        ..., description="カンマ区切りの withdrawal request ID 一覧 (例: 1,2,3)"
    ),
) -> LidoWithdrawalStatusResponse:
    """withdrawal request のステータス一覧を取得する。

    request_ids パラメータにカンマ区切りの ID 一覧を渡す。
    例: GET /api/protocols/lido/withdrawal-status?request_ids=1,2,3
    """
    service = _get_service()
    try:
        parsed_ids = [int(rid.strip()) for rid in request_ids.split(",") if rid.strip()]
        if not parsed_ids:
            raise HTTPException(status_code=422, detail="request_ids は空にできません")
        return await service.get_withdrawal_status(parsed_ids)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"request_ids のパース失敗: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Lido withdrawal-status 取得失敗")
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/withdrawal-requests", response_model=LidoWithdrawalRequestsResponse)
async def get_withdrawal_requests(address: str) -> LidoWithdrawalRequestsResponse:
    """指定アドレスの未クレーム引き出しリクエスト ID 一覧を返す。"""
    service = _get_service()
    try:
        return await service.get_withdrawal_requests(address)
    except Exception as exc:
        logger.exception("Lido withdrawal-requests 取得失敗")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
