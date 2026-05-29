# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/proposals/router.py
"""提案API ルーター定義。"""

import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    require_active_user,
    require_admin,
    require_partner,
    require_viewer,
)
from app.auth.models import User
from app.auth.models import User as UserModel
from app.database import get_db

from .models import Proposal
from .schemas import (
    AdminProposalItem,
    AdminProposalListResponse,
    AdminProposalStats,
    ProposalCreate,
    ProposalListResponse,
    ProposalResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/proposals", tags=["proposals"])

# 再試行上限: この回数を超えたらデッドレター化 (status='failed') して再試行を停止する。
# 恒久エラー (ValueError/KeyError 等の設定起因) は 1回目で即 failed。
MAX_EXECUTION_ATTEMPTS = 3

# 恒久エラー (RPC 設定未完成 / チェーン未設定 等): 再試行しても無意味なので即 failed。
_PERMANENT_EXCEPTION_TYPES = (ValueError, KeyError)


def _is_permanent_error(exc: Exception) -> bool:
    """恒久エラー判定: True なら attempts カウントせず即 failed。"""
    return isinstance(exc, _PERMANENT_EXCEPTION_TYPES)


def _expire_old_proposals(db: Session, user_id: int) -> None:
    """期限切れのpending提案をexpiredに更新する。"""
    now = datetime.now(timezone.utc)
    stmt = select(Proposal).where(
        Proposal.user_id == user_id,
        Proposal.status == "pending",
        Proposal.expires_at < now,
    )
    expired = db.scalars(stmt).all()
    for p in expired:
        p.status = "expired"
    if expired:
        db.commit()


def _get_primary_chain() -> str:
    """AAVE_ACTIVE_CHAINS の先頭チェーンを返す。未設定時は "base"（本番は Base Mainnet 運用）。

    NOTE: 旧デフォルト "arbitrum_sepolia" から "base" に変更（2026-05-21）。
    chains.py の get_active_chains() のデフォルトと統一する。
    """
    raw = os.getenv("AAVE_ACTIVE_CHAINS", "base")
    return raw.split(",")[0].strip()


def _notify_aave_failure(proposal_id: int, error_message: str, failed_at: datetime) -> None:
    """Aave 実行失敗を管理者向けに Slack 通知する（失敗しても本処理を止めない）。"""
    try:
        from app.notifications.factory import get_notification_service  # noqa: PLC0415
        from app.notifications.schemas import (  # noqa: PLC0415
            NotificationChannel,
            NotificationMessage,
            NotificationSeverity,
        )

        message = NotificationMessage(
            channel=NotificationChannel.SLACK,
            severity=NotificationSeverity.ALERT,
            title=f"Aave execution failed (proposal #{proposal_id})",
            body=(
                f"proposal_id: {proposal_id}\n"
                f"reason: {error_message}\n"
                f"timestamp: {failed_at.isoformat()}"
            ),
        )
        get_notification_service().send(message)
    except Exception:  # noqa: BLE001 — 通知失敗で本処理を止めない
        logger.exception("proposal %d: failed to send Slack notification", proposal_id)


def _record_failed_transaction(
    proposal: Proposal, chain: str, error_message: str, db: Session
) -> None:
    """Aave 実行失敗時に transactions テーブルに失敗行を追加する。"""
    from app.transactions.models import Transaction  # noqa: PLC0415

    tx = Transaction(
        user_id=proposal.user_id,
        operation=proposal.operation,
        asset=proposal.asset,
        amount=proposal.amount,
        amount_usd=proposal.amount_usd,
        tx_hash=None,
        chain=chain,
        status="failed",
        ai_decision_id=proposal.ai_decision_id,
        is_dry_run=False,
        error_message=error_message,
    )
    db.add(tx)


def _execute_aave_for_proposal(proposal: Proposal, db: Session) -> None:
    """
    承認された提案に対して Aave 操作を実行し、proposal を更新する。

    - SUPPLY  → TradeAction.BUY (deposit)
    - WITHDRAW → TradeAction.SELL (withdraw)
    - BORROW / REPAY → 現フェーズでは NOOP（approved のまま）

    デッドレター化ロジック (2026-05-21 P0 対策):
    - MAX_EXECUTION_ATTEMPTS 超過 → 即 failed（Slack 通知付き）。再試行しない。
    - 恒久エラー (ValueError/KeyError = RPC/chain 設定起因) → attempts 加算なし・即 failed
    - 一時エラー → execution_attempts++ して failed

    Aave 実行失敗時は proposal.status を 'failed' に遷移させ、
    error_message と transactions(status='failed') を記録し、Slack 通知を送る。
    呼び出し元は db.commit() を実行する責務を持つ。
    """
    from app.aave.service import MultiChainAaveService  # noqa: PLC0415
    from app.ai.schemas import TradeAction  # noqa: PLC0415
    from app.transactions.models import Transaction  # noqa: PLC0415

    op_map: dict[str, TradeAction] = {
        "SUPPLY": TradeAction.BUY,
        "WITHDRAW": TradeAction.SELL,
    }
    trade_action = op_map.get(proposal.operation)
    if trade_action is None:
        # BORROW / REPAY は現フェーズでは直接実行しない
        logger.info(
            "proposal %d: operation %s skipped (not yet supported for direct execution)",
            proposal.id,
            proposal.operation,
        )
        return

    chain = _get_primary_chain()

    # --- デッドレター上限チェック (2026-05-21 P0 対策) ---
    if proposal.execution_attempts >= MAX_EXECUTION_ATTEMPTS:
        error_message = (
            f"dead-lettered after {proposal.execution_attempts} attempts "
            f"(MAX_EXECUTION_ATTEMPTS={MAX_EXECUTION_ATTEMPTS})"
        )
        logger.error(
            "proposal %d: %s — forcing failed (dead-letter)",
            proposal.id,
            error_message,
        )
        failed_at = datetime.now(timezone.utc)
        # 修正1: 既に failed 済みなら通知 flood を防ぐ (初回遷移時のみ通知)
        if proposal.status != "failed":
            _notify_aave_failure(proposal.id, error_message, failed_at)
        proposal.status = "failed"
        proposal.error_message = error_message
        proposal.executed_at = failed_at
        # 修正2: 監査 gap 解消 — transient 分岐と同様に failed トランザクションを記録する
        _record_failed_transaction(proposal, chain, error_message, db)
        return

    # proposal.user_id から wallet_address を解決して partner 別に伝播させる
    _user = db.get(UserModel, proposal.user_id)
    _wallet_address = (_user.wallet_address or "") if _user else ""
    logger.info(
        "proposal %d: user_id=%d wallet=%s",
        proposal.id,
        proposal.user_id,
        _wallet_address[:6] + "..." if len(_wallet_address) > 6 else _wallet_address or "(none)",
    )

    try:
        multi_service = MultiChainAaveService()
        result = multi_service.execute_rebalance(
            chain_name=chain,
            action=trade_action,
            amount=Decimal(str(proposal.amount_usd)),
            asset_symbol=proposal.asset,
            dry_run=False,
            wallet_address=_wallet_address,
        )

        # 成功: attempt カウントも記録（診断用）
        proposal.execution_attempts += 1
        proposal.tx_hash = result.tx_hash
        proposal.status = "executed"
        proposal.executed_at = datetime.now(timezone.utc)

        # 取引履歴に記録
        tx_status = "completed" if result.tx_hash else "pending"
        tx = Transaction(
            user_id=proposal.user_id,
            operation=proposal.operation,
            asset=proposal.asset,
            amount=proposal.amount,
            amount_usd=proposal.amount_usd,
            tx_hash=result.tx_hash,
            chain=chain,
            status=tx_status,
            ai_decision_id=proposal.ai_decision_id,
            is_dry_run=False,
        )
        db.add(tx)
        logger.info(
            "proposal %d: %s %s executed on %s — tx=%s status=%s (attempt=%d)",
            proposal.id,
            proposal.operation,
            proposal.asset,
            chain,
            result.tx_hash,
            result.status,
            proposal.execution_attempts,
        )
    except Exception as exc:  # noqa: BLE001
        error_message = f"{type(exc).__name__}: {exc}"
        failed_at = datetime.now(timezone.utc)

        if _is_permanent_error(exc):
            # 恒久エラー: attempts 加算なし・即 failed（再試行しても無意味）
            logger.error(
                "proposal %d: permanent Aave error — failing immediately (no retry): %s",
                proposal.id,
                exc,
                exc_info=True,
            )
        else:
            # 一時エラー: attempts++ して failed
            proposal.execution_attempts += 1
            logger.error(
                "proposal %d: Aave execution failed (attempt=%d/%d) — %s",
                proposal.id,
                proposal.execution_attempts,
                MAX_EXECUTION_ATTEMPTS,
                exc,
                exc_info=True,
            )

        proposal.status = "failed"
        proposal.error_message = error_message
        proposal.executed_at = failed_at
        _record_failed_transaction(proposal, chain, error_message, db)
        _notify_aave_failure(proposal.id, error_message, failed_at)


@router.get(
    "/admin/all", response_model=AdminProposalListResponse, summary="全ユーザー提案一覧（管理者）"
)
def admin_list_proposals(
    status_filter: Optional[str] = Query(None, alias="status"),
    user_id: Optional[int] = Query(None),
    operation: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _partner: User = Depends(require_partner),
    db: Session = Depends(get_db),
) -> AdminProposalListResponse:
    """全ユーザーの提案一覧をフィルター付きで返す（管理者専用）。"""
    stmt = select(Proposal)
    if status_filter:
        stmt = stmt.where(Proposal.status == status_filter)
    if user_id is not None:
        stmt = stmt.where(Proposal.user_id == user_id)
    if operation:
        stmt = stmt.where(Proposal.operation == operation)
    if date_from:
        stmt = stmt.where(Proposal.created_at >= date_from)
    if date_to:
        stmt = stmt.where(Proposal.created_at <= date_to)

    total_stmt = stmt.with_only_columns(Proposal.id)
    total = len(db.scalars(total_stmt).all())

    stmt = stmt.order_by(Proposal.created_at.desc()).offset((page - 1) * limit).limit(limit)
    proposals = db.scalars(stmt).all()

    # ユーザー情報をまとめて取得
    user_ids = list({p.user_id for p in proposals})
    users_map: dict[int, UserModel] = {}
    if user_ids:
        users = db.scalars(select(UserModel).where(UserModel.id.in_(user_ids))).all()
        users_map = {u.id: u for u in users}

    items = []
    for p in proposals:
        u = users_map.get(p.user_id)
        item = AdminProposalItem(
            **ProposalResponse.model_validate(p).model_dump(),
            username=u.username if u else None,
            email=u.email if u else None,
        )
        items.append(item)

    return AdminProposalListResponse(items=items, total=total, page=page, limit=limit)


@router.get("/admin/stats", response_model=AdminProposalStats, summary="提案KPI統計（管理者）")
def admin_proposal_stats(
    _partner: User = Depends(require_partner),
    db: Session = Depends(get_db),
) -> AdminProposalStats:
    """KPIカード用の件数を DB 集計で返す（ページネーション不要）。"""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    pending = db.scalar(select(func.count()).where(Proposal.status == "pending")) or 0
    today_approved = (
        db.scalar(
            select(func.count()).where(
                Proposal.status.in_(["approved", "executed"]),
                Proposal.approved_at >= today_start,
            )
        )
        or 0
    )
    today_rejected = (
        db.scalar(
            select(func.count()).where(
                Proposal.status == "rejected",
                Proposal.rejected_at >= today_start,
            )
        )
        or 0
    )
    expired = db.scalar(select(func.count()).where(Proposal.status == "expired")) or 0

    return AdminProposalStats(
        pending=pending,
        today_approved=today_approved,
        today_rejected=today_rejected,
        expired=expired,
    )


@router.get("/pending", response_model=ProposalListResponse, summary="保留中の提案リスト")
def list_pending_proposals(
    current_user: User = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> ProposalListResponse:
    """自分の保留中（pending）提案リストを返す。"""
    _expire_old_proposals(db, current_user.id)
    stmt = (
        select(Proposal)
        .where(
            Proposal.user_id == current_user.id,
            Proposal.status == "pending",
        )
        .order_by(Proposal.created_at.desc())
    )
    items = db.scalars(stmt).all()
    return ProposalListResponse(
        items=[ProposalResponse.model_validate(p) for p in items],
        total=len(items),
    )


@router.get("/history", response_model=ProposalListResponse, summary="提案履歴")
def list_proposal_history(
    current_user: User = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> ProposalListResponse:
    """承認・拒否・実行済みの提案履歴を返す。"""
    stmt = (
        select(Proposal)
        .where(
            Proposal.user_id == current_user.id,
            Proposal.status.in_(["approved", "rejected", "executed", "failed"]),
        )
        .order_by(Proposal.created_at.desc())
    )
    items = db.scalars(stmt).all()
    return ProposalListResponse(
        items=[ProposalResponse.model_validate(p) for p in items],
        total=len(items),
    )


@router.post("/{proposal_id}/approve", response_model=ProposalResponse, summary="提案承認・実行")
def approve_proposal(
    proposal_id: int,
    current_user: User = Depends(require_partner),
    db: Session = Depends(get_db),
) -> ProposalResponse:
    """提案を承認してAave操作を実行する（本人・admin・partner）。"""
    stmt = select(Proposal).where(Proposal.id == proposal_id)
    proposal = db.scalars(stmt).first()
    # admin/partner は他ユーザーの提案も操作可能。一般ユーザーは require_partner で弾かれる。
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    if proposal.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve proposal with status '{proposal.status}'",
        )

    # Step 1: 承認済みにマーク
    proposal.status = "approved"
    proposal.approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(proposal)

    # Step 2: Aave 操作を実行（失敗時は 'failed' に遷移）
    _execute_aave_for_proposal(proposal, db)
    db.commit()
    db.refresh(proposal)

    return ProposalResponse.model_validate(proposal)


@router.post("/{proposal_id}/reject", response_model=ProposalResponse, summary="提案拒否")
def reject_proposal(
    proposal_id: int,
    current_user: User = Depends(require_partner),
    db: Session = Depends(get_db),
) -> ProposalResponse:
    """提案を拒否する（本人・admin・partner）。"""
    stmt = select(Proposal).where(Proposal.id == proposal_id)
    proposal = db.scalars(stmt).first()
    # admin/partner は他ユーザーの提案も操作可能。一般ユーザーは require_partner で弾かれる。
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    if proposal.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reject proposal with status '{proposal.status}'",
        )
    proposal.status = "rejected"
    proposal.rejected_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(proposal)
    return ProposalResponse.model_validate(proposal)


@router.get("/{proposal_id}", response_model=ProposalResponse, summary="提案詳細")
def get_proposal(
    proposal_id: int,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> ProposalResponse:
    """指定IDの提案詳細を返す（本人またはadmin）。"""
    stmt = select(Proposal).where(Proposal.id == proposal_id)
    proposal = db.scalars(stmt).first()
    if proposal is None or (proposal.user_id != current_user.id and not current_user.is_admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    return ProposalResponse.model_validate(proposal)


@router.post(
    "",
    response_model=ProposalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="提案作成",
)
def create_proposal(
    request: ProposalCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ProposalResponse:
    """提案を作成する（内部呼び出し用）。"""
    expires_at = request.expires_at or (datetime.now(timezone.utc) + timedelta(hours=72))
    proposal = Proposal(
        user_id=request.user_id,
        ai_decision_id=request.ai_decision_id,
        operation=request.operation,
        asset=request.asset,
        amount=request.amount,
        amount_usd=request.amount_usd,
        reason=request.reason,
        expected_hf_after=request.expected_hf_after,
        estimated_gas_usd=request.estimated_gas_usd,
        expires_at=expires_at,
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return ProposalResponse.model_validate(proposal)
