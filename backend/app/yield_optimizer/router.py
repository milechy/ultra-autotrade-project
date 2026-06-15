# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/yield_optimizer/router.py
"""
Yield Optimizer API ルーター。

エンドポイント:
  GET  /api/yield-optimizer/positions   — 全 Vault ポジション取得 (viewer 以上)
  GET  /api/yield-optimizer/vaults      — 利用可能な Vault 一覧 (viewer 以上)
  POST /api/yield-optimizer/deposit     — Morpho Vault 入金 (admin 専用)
  POST /api/yield-optimizer/withdraw    — Morpho Vault 出金 (admin 専用)
  GET  /api/yield-optimizer/idle-report — アイドル資本レポート (viewer 以上)

NOTE (Tier S ゲート): このルーターは main.py への include_router を含まない。
本番配線は以下を main.py に追加してください (人間によるレビュー・マージ後):

  # backend/app/main.py 内 (include_router 最後尾付近)
  from app.yield_optimizer.router import router as yield_optimizer_router
  app.include_router(yield_optimizer_router)  # Yield Optimizer: Privy Earn / Morpho Vaults

ENABLE_IDLE_CAPITAL_CHECK=1 の場合、scheduled_tasks.py の idle_capital_check_loop が
15分間隔でアイドル資本レポートをログ出力する。
startup 配線は main.py の startup_scheduled_tasks に追加が必要 (Tier S 編集)。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import require_admin, require_viewer
from app.auth.models import User

from .idle_detector import IdleCapitalDetector, get_idle_threshold
from .morpho_client import MorphoClient
from .schemas import (
    DepositRequest,
    IdleCapitalReport,
    PositionListResponse,
    TxResult,
    VaultListResponse,
    WithdrawRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/yield-optimizer", tags=["yield-optimizer"])


# ------------------------------------------------------------------ DI helpers


def _get_morpho_client() -> MorphoClient:
    """MorphoClient を生成する (DI 用)。"""
    return MorphoClient()


def _get_idle_detector() -> IdleCapitalDetector:
    """IdleCapitalDetector を生成する (DI 用)。"""
    try:
        from app.exchange.client import BybitSandboxClient  # noqa: PLC0415
        from app.exchange.config import get_exchange_settings  # noqa: PLC0415

        settings = get_exchange_settings()
        exchange_client: BybitSandboxClient | None = BybitSandboxClient(settings=settings)
    except Exception as exc:
        logger.warning("_get_idle_detector: exchange client init failed (fail-open): %s", exc)
        exchange_client = None

    morpho_client: MorphoClient | None = MorphoClient()
    threshold = get_idle_threshold()
    return IdleCapitalDetector(
        exchange_client=exchange_client,
        morpho_client=morpho_client,
        idle_threshold=threshold,
    )


# ------------------------------------------------------------------ endpoints


@router.get(
    "/positions",
    response_model=PositionListResponse,
    summary="全 Vault ポジション一覧を取得する (viewer 以上)",
)
def get_positions(
    current_user: User = Depends(require_viewer),
) -> PositionListResponse:
    """
    Privy Earn / Morpho Vault 内のポジション一覧を返す。

    Privy API 障害時は空ポジションリストを返す (fail-open)。
    """
    client = _get_morpho_client()
    positions = client.get_all_positions()

    total_deposited = Decimal("0")
    total_earned = Decimal("0")
    for pos in positions:
        try:
            total_deposited += Decimal(pos.deposited_amount)
            total_earned += Decimal(pos.earned_usd)
        except Exception as exc:  # noqa: BLE001
            logger.debug("get_positions: skipping malformed position decimal: %s", exc)

    return PositionListResponse(
        positions=positions,
        total_deposited_usdc=str(total_deposited),
        total_earned_usd=str(total_earned),
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get(
    "/vaults",
    response_model=VaultListResponse,
    summary="利用可能な Morpho Vault 一覧を取得する (viewer 以上)",
)
def list_vaults(
    current_user: User = Depends(require_viewer),
) -> VaultListResponse:
    """
    Morpho Vault 一覧と最高 APY Vault を返す。

    Privy API 障害時は空リストを返す (fail-open)。
    """
    client = _get_morpho_client()
    return client.get_vault_list_response()


@router.post(
    "/deposit",
    response_model=TxResult,
    status_code=status.HTTP_201_CREATED,
    summary="Morpho Vault へ USDC を入金する (admin 専用)",
)
def deposit(
    body: DepositRequest,
    current_user: User = Depends(require_admin),
) -> TxResult:
    """
    Morpho Vault へ USDC を入金する。

    - admin ロールのみ実行可能。
    - Privy Wallet Actions "Earn" API を呼び出して deposit tx を発行する。
    - 資金移動をともなう操作: 本番実行前に必ず確認すること。

    HUMAN-REVIEW-REQUIRED: 資金移動操作。本番適用前に承認必須。
    """
    client = _get_morpho_client()
    try:
        result = client.deposit_to_vault(
            vault_address=body.vault_address,
            amount_usdc=body.amount_usdc,
        )
    except RuntimeError as exc:
        logger.error("deposit: failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Privy Earn deposit failed: {exc}",
        ) from exc
    except Exception as exc:
        logger.error("deposit: unexpected error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Privy Earn API error: {exc}",
        ) from exc

    return result


@router.post(
    "/withdraw",
    response_model=TxResult,
    status_code=status.HTTP_201_CREATED,
    summary="Morpho Vault から USDC を引き出す (admin 専用)",
)
def withdraw(
    body: WithdrawRequest,
    current_user: User = Depends(require_admin),
) -> TxResult:
    """
    Morpho Vault から USDC を引き出す。

    - admin ロールのみ実行可能。
    - 資金移動をともなう操作: 本番実行前に必ず確認すること。

    HUMAN-REVIEW-REQUIRED: 資金移動操作。本番適用前に承認必須。
    """
    client = _get_morpho_client()
    try:
        result = client.withdraw_from_vault(
            vault_address=body.vault_address,
            amount=body.amount,
        )
    except RuntimeError as exc:
        logger.error("withdraw: failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Privy Earn withdraw failed: {exc}",
        ) from exc
    except Exception as exc:
        logger.error("withdraw: unexpected error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Privy Earn API error: {exc}",
        ) from exc

    return result


@router.get(
    "/idle-report",
    response_model=IdleCapitalReport,
    summary="アイドル資本レポートを返す (viewer 以上)",
)
def idle_report(
    current_user: User = Depends(require_viewer),
) -> IdleCapitalReport:
    """
    Bybit USDC 空き残高と Morpho 運用中金額を比較してアイドル資本レポートを返す。

    Bybit API 障害時は bybit_free_usdc=0 として fail-open。
    """
    detector = _get_idle_detector()
    return detector.build_report()
