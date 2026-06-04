# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/proposals/router.py
"""提案API ルーター定義。"""

import csv
import io
import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
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
    PartnerUnsignedTxs,
    ProposalCreate,
    ProposalListResponse,
    ProposalResponse,
    SubmitTxRequest,
    UnsignedTx,
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


def _capture_partner_decision(
    db: Session,
    ai_decision_id: Optional[int],
    partner_approved: bool,
) -> None:
    """Hermes Phase 0: partner 承認/却下を ai_decision_outcomes に INSERT (fail-open)。

    ai_decision_id が NULL の提案 (手動作成等) は no-op。
    INSERT 失敗は WARNING に留め、呼び出し元の処理には影響させない。
    """
    if ai_decision_id is None:
        return
    try:
        from app.ai.models import AiDecisionOutcome  # noqa: PLC0415

        outcome = AiDecisionOutcome(
            decision_id=ai_decision_id,
            partner_approved=partner_approved,
        )
        db.add(outcome)
        db.commit()
        logger.info(
            "ai_decision_outcomes captured: decision_id=%d partner_approved=%s",
            ai_decision_id,
            partner_approved,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "_capture_partner_decision failed (fail-open, decision_id=%d): %s",
            ai_decision_id,
            exc,
        )
        try:
            db.rollback()
        except Exception:  # noqa: BLE001, S110
            pass


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


def _notify_missing_wallet(proposal_id: int, user_id: int) -> None:
    """user.wallet_address が NULL の状態で Aave 執行に進んだことを Slack で警告する。

    fallback として env AAVE_WALLET_ADDRESS が使われるが、partner 別資金分離の前提が
    破れているため (2026-05-28 PR #438 の橋口さん wallet 未登録パターン)、即時に
    管理者へ通知する。本処理は止めない (fail-safe)。
    """
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
            title=f"Aave wallet fallback (proposal #{proposal_id})",
            body=(
                f"proposal_id: {proposal_id}\n"
                f"user_id: {user_id}\n"
                "reason: user.wallet_address is NULL; "
                "falling back to AAVE_WALLET_ADDRESS env (partner separation broken)."
            ),
        )
        get_notification_service().send(message)
    except Exception:  # noqa: BLE001 — 通知失敗で本処理を止めない
        logger.exception(
            "proposal %d: failed to send wallet-fallback Slack notification", proposal_id
        )


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


def _lookup_fee_rate_for_user(db: Session, user_id: int) -> Decimal:
    """ユーザー tier に対応する fee_rate を fee_configs から取得する (fail-open)。

    FeeConfigV10 が未設定 / DB エラーの場合は Decimal('0') を返し、呼び出し元を止めない。
    fee_rate は月次バッチ (F-7) が手数料計算に使用するメタ情報として proposal に記録する。
    """
    from sqlalchemy import desc  # noqa: PLC0415

    from app.auth.models import InvestmentTier, normalize_tier  # noqa: PLC0415
    from app.fees.models import FeeConfigV10  # noqa: PLC0415

    _TIER_INDEX = {
        InvestmentTier.LOWER: 0,
        InvestmentTier.MIDDLE: 1,
        InvestmentTier.UPPER: 2,
    }

    try:
        user = db.scalars(select(User).where(User.id == user_id)).first()
        if user is None:
            logger.warning("_lookup_fee_rate: user_id=%d not found — defaulting to 0", user_id)
            return Decimal("0")

        tier = normalize_tier(user.tier, user_id=user_id)

        config = db.scalars(
            select(FeeConfigV10)
            .where(FeeConfigV10.is_active.is_(True))
            .order_by(desc(FeeConfigV10.effective_from))
            .limit(1)
        ).first()

        if config is None:
            logger.warning("_lookup_fee_rate: active FeeConfigV10 not found — defaulting to 0")
            return Decimal("0")

        rates = config.tier_fee_rates
        idx = _TIER_INDEX.get(tier, 0)
        if idx >= len(rates):
            logger.warning(
                "_lookup_fee_rate: tier index %d out of range (len=%d) — defaulting to 0",
                idx,
                len(rates),
            )
            return Decimal("0")

        return Decimal(str(rates[idx]))
    except Exception:  # noqa: BLE001
        logger.warning("_lookup_fee_rate: unexpected error — defaulting to 0", exc_info=True)
        return Decimal("0")


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

    # --- partner 別 wallet 伝播 (2026-05-28 Lane 13) ---
    # proposal owner の wallet_address を取得し、Aave 実行時に伝播する。
    # NULL の場合は env AAVE_WALLET_ADDRESS fallback + Slack 警告 (partner 別資金分離の前提が破れる)。
    user = db.scalars(select(User).where(User.id == proposal.user_id)).first()
    user_wallet: str | None = user.wallet_address if user is not None else None
    if user_wallet:
        masked_wallet = f"{user_wallet[:6]}...{user_wallet[-4:]}"
        logger.info(
            "proposal %d: executing as user_id=%d wallet=%s",
            proposal.id,
            proposal.user_id,
            masked_wallet,
        )
    else:
        logger.warning(
            "proposal %d: user_id=%d wallet_address is NULL — "
            "falling back to AAVE_WALLET_ADDRESS env (partner separation broken)",
            proposal.id,
            proposal.user_id,
        )
        _notify_missing_wallet(proposal.id, proposal.user_id)

    try:
        multi_service = MultiChainAaveService()
        result = multi_service.execute_rebalance(
            chain_name=chain,
            action=trade_action,
            amount=Decimal(str(proposal.amount_usd)),
            asset_symbol=proposal.asset,
            dry_run=False,
            wallet_address=user_wallet,
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


_JST = ZoneInfo("Asia/Tokyo")

# Cryptact 無料版フォーマット: Action マッピング
_OPERATION_TO_CRYPTACT_ACTION: dict[str, str] = {
    "SUPPLY": "LENDING",
    "WITHDRAW": "UNLENDING",
    "BORROW": "BORROW",
    "REPAY": "REPAY",
}


@router.get("/tax/cryptact-csv", summary="Cryptact無料版フォーマットCSVダウンロード")
def download_cryptact_csv(
    year: Optional[int] = Query(None, description="絞り込む年 (例: 2026)。省略時は全件"),
    current_user: User = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> Response:
    """
    実行済み提案 (status='executed') を Cryptact 無料版 CSV 形式で返す。

    CSV カラム: Timestamp, Action, Source, Base, Volume, Price, Counter, Fee, FeeCcy
    - Timestamp: JST (UTC+9) 形式 YYYY/MM/DD HH:MM:SS
    - Action: LENDING (SUPPLY) / UNLENDING (WITHDRAW)
    - Source: AAVE_V3
    - Base: 資産シンボル (USDC 等)
    - Volume: トークン数量 (Decimal)
    - Price: 空欄（Cryptact が自動補完）
    - Counter: USD
    - Fee: 手数料 USD (fee_amount。NULL の場合は 0)
    - FeeCcy: USD
    """
    stmt = select(Proposal).where(
        Proposal.user_id == current_user.id,
        Proposal.status == "executed",
        Proposal.executed_at.is_not(None),
    )
    if year is not None:
        stmt = stmt.where(func.extract("year", Proposal.executed_at) == year)
    stmt = stmt.order_by(Proposal.executed_at.asc())
    proposals = db.scalars(stmt).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["Timestamp", "Action", "Source", "Base", "Volume", "Price", "Counter", "Fee", "FeeCcy"]
    )

    for p in proposals:
        if p.executed_at is None:
            continue
        dt = p.executed_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        executed_jst = dt.astimezone(_JST)
        timestamp = executed_jst.strftime("%Y/%m/%d %H:%M:%S")
        action = _OPERATION_TO_CRYPTACT_ACTION.get(p.operation, p.operation)
        # Volume: Decimal文字列 → そのまま出力（Cryptactは文字列でも受容）
        volume = str(p.amount)
        fee = str(p.fee_amount) if p.fee_amount is not None else "0"
        writer.writerow([timestamp, action, "AAVE_V3", p.asset, volume, "", "USD", fee, "USD"])

    csv_bytes = buf.getvalue().encode("utf-8-sig")  # BOM付きUTF-8 (Excel対応)
    year_suffix = f"_{year}" if year else ""
    filename = f"cryptact_aave{year_suffix}.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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

    # Step 2: Aave 自動実行 (AUTO_EXECUTION_ENABLED=true の場合のみ)
    # non-custodial 方式2 では default=false。partner 手動署名 (submit_partner_tx) のみが実 tx を立てる。
    # AAVE_WALLET_PRIVATE_KEY が署名する経路はこのフラグで完全に無効化される。
    auto_execution_enabled = os.getenv("AUTO_EXECUTION_ENABLED", "false").lower() == "true"
    if auto_execution_enabled:
        _execute_aave_for_proposal(proposal, db)
        db.commit()
        db.refresh(proposal)
    else:
        logger.info(
            "proposal %d: AUTO_EXECUTION_ENABLED=false — skipping custodial auto-execution; "
            "waiting for partner manual approve via submit-tx",
            proposal.id,
        )

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


@router.get(
    "/{proposal_id}/build-tx",
    response_model=PartnerUnsignedTxs,
    response_model_by_alias=True,
    summary="パートナー署名用: 未署名トランザクション構築",
)
def build_partner_tx(
    proposal_id: int,
    current_user: User = Depends(require_partner),
    db: Session = Depends(get_db),
) -> PartnerUnsignedTxs:
    """
    パートナーが Privy で署名するための未署名 Aave トランザクションを構築して返す。

    approve_proposal の代わりにこのエンドポイントを呼び、フロントエンドで
    Privy sendTransaction() 経由でパートナー本人が署名・送信する。
    """
    from app.aave.service import MultiChainAaveService  # noqa: PLC0415

    stmt = select(Proposal).where(Proposal.id == proposal_id)
    proposal = db.scalars(stmt).first()
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    if proposal.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this proposal"
        )
    if proposal.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot build tx for proposal with status '{proposal.status}'",
        )

    # partner wallet 取得
    user = db.scalars(select(User).where(User.id == proposal.user_id)).first()
    if user is None or not user.wallet_address:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Partner wallet_address が未設定です。Privy で wallet を作成してください。",
        )
    wallet_address = user.wallet_address

    op_map: dict[str, str] = {"SUPPLY": "DEPOSIT", "WITHDRAW": "WITHDRAW"}
    if proposal.operation not in op_map:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Operation {proposal.operation} は partner 署名に非対応です",
        )

    chain = _get_primary_chain()
    try:
        multi_service = MultiChainAaveService()
        service = multi_service.get_service(chain)
        asset_symbol = proposal.asset or service._settings.default_asset_symbol

        if proposal.operation == "SUPPLY":
            txs = service._client.build_deposit_txs(
                asset_symbol=asset_symbol,
                amount=Decimal(str(proposal.amount_usd)),
                wallet_address=wallet_address,
            )
            return PartnerUnsignedTxs(
                proposal_id=proposal_id,
                operation=proposal.operation,
                wallet_address=wallet_address,
                approve_tx=UnsignedTx.model_validate(txs["approve_tx"]),
                supply_tx=UnsignedTx.model_validate(txs["supply_tx"]),
            )
        else:  # WITHDRAW
            txs = service._client.build_withdraw_tx(
                asset_symbol=asset_symbol,
                amount=Decimal(str(proposal.amount_usd)),
                wallet_address=wallet_address,
            )
            return PartnerUnsignedTxs(
                proposal_id=proposal_id,
                operation=proposal.operation,
                wallet_address=wallet_address,
                withdraw_tx=UnsignedTx.model_validate(txs["withdraw_tx"]),
            )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"tx 構築失敗: {exc}",
        ) from exc


def _verify_on_chain_receipt(
    tx_hash: str,
    expected_from: str,
    expected_to: str,
    rpc_url: str,
    poll_interval: float = 5.0,
    max_wait: float = 60.0,
) -> dict[str, object]:
    """
    on-chain tx_hash の receipt を取得して from/to/status を検証する。

    - status == 1 必須 (reverted は 422)
    - receipt['from'].lower() == expected_from.lower() 必須
    - receipt['to'].lower() == expected_to.lower() を確認 (可能な場合)
    - receipt が pending (None) なら poll_interval 秒おきに max_wait 秒まで再試行
    - max_wait 経過しても pending なら ValueError を送出 (呼び出し元で 400)

    :returns: receipt dict (AttributeDict)
    :raises ValueError: receipt が pending / status=0 / from/to 不一致
    """
    import time  # noqa: PLC0415

    try:
        from web3 import Web3  # noqa: PLC0415
    except ImportError as exc:
        raise ValueError("web3 ライブラリが未インストールです") from exc

    w3 = Web3(Web3.HTTPProvider(rpc_url))

    elapsed = 0.0
    receipt = None
    while elapsed <= max_wait:
        receipt = w3.eth.get_transaction_receipt(tx_hash)  # type: ignore[arg-type]
        if receipt is not None:
            break
        time.sleep(poll_interval)
        elapsed += poll_interval

    if receipt is None:
        raise ValueError(
            f"tx {tx_hash[:12]}... は {max_wait:.0f}秒経過後も pending です。"
            "しばらく待ってから再試行してください。"
        )

    if receipt["status"] != 1:
        raise ValueError(f"tx {tx_hash[:12]}... は reverted (status={receipt['status']}) です。")

    actual_from = receipt.get("from", "")
    if actual_from.lower() != expected_from.lower():
        raise ValueError(
            f"tx の from アドレスが一致しません: "
            f"expected={expected_from[:10]}... actual={actual_from[:10]}..."
        )

    actual_to = receipt.get("to", "")
    if actual_to and actual_to.lower() != expected_to.lower():
        raise ValueError(
            f"tx の to アドレスが一致しません: "
            f"expected={expected_to[:10]}... actual={actual_to[:10]}..."
        )

    return dict(receipt)


@router.post(
    "/{proposal_id}/submit-tx",
    response_model=ProposalResponse,
    summary="パートナー署名済みtx提出",
)
def submit_partner_tx(
    proposal_id: int,
    body: SubmitTxRequest,
    current_user: User = Depends(require_partner),
    db: Session = Depends(get_db),
) -> ProposalResponse:
    """
    パートナーが Privy で署名・送信した tx_hash を受け取り、on-chain receipt を検証して
    提案を executed に遷移させる。

    フロントエンドは approve tx と supply/withdraw tx を順に送信し、
    最後の tx_hash (supply/withdraw tx) をこのエンドポイントに送信する。

    検証フロー:
    1. tx_hash 形式チェック (regex)
    2. web3 get_transaction_receipt でポーリング (最大60秒)
    3. status==1 / from==partner_wallet / to==Aave Pool 確認
    4. 全通過後のみ proposal.status='executed' に遷移
    """
    from app.transactions.models import Transaction  # noqa: PLC0415

    stmt = select(Proposal).where(Proposal.id == proposal_id)
    proposal = db.scalars(stmt).first()
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    if proposal.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this proposal"
        )
    if proposal.status not in ("pending", "approved"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot submit tx for proposal with status '{proposal.status}'",
        )

    # tx_hash 形式チェック (0x + 64 hex chars)
    import re  # noqa: PLC0415

    if not re.fullmatch(r"0x[0-9a-fA-F]{64}", body.tx_hash):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid tx_hash format",
        )

    # on-chain receipt 検証
    chain_name = _get_primary_chain()
    try:
        from app.aave.chains import get_chain_config, get_rpc_url_for_chain  # noqa: PLC0415

        chain_cfg = get_chain_config(chain_name)
        rpc_url = get_rpc_url_for_chain(chain_cfg)
        pool_address = chain_cfg.pool_address
    except (ValueError, KeyError) as exc:
        logger.warning(
            "submit-tx: chain config unavailable (%s) — skipping on-chain receipt verification",
            exc,
        )
        rpc_url = None
        pool_address = None

    partner_wallet = body.wallet_address
    if rpc_url and pool_address:
        try:
            _verify_on_chain_receipt(
                tx_hash=body.tx_hash,
                expected_from=partner_wallet,
                expected_to=pool_address,
                rpc_url=rpc_url,
            )
            logger.info(
                "submit-tx: proposal %d receipt verified on-chain chain=%s tx=%s",
                proposal_id,
                chain_name,
                body.tx_hash[:12],
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"on-chain receipt 検証失敗: {exc}",
            ) from exc
    else:
        logger.warning(
            "submit-tx: proposal %d on-chain verification skipped (RPC/chain unavailable)",
            proposal_id,
        )

    now = datetime.now(timezone.utc)
    proposal.status = "executed"
    proposal.approved_at = proposal.approved_at or now
    proposal.executed_at = now
    proposal.tx_hash = body.tx_hash
    proposal.expected_from = partner_wallet
    proposal.expected_to = pool_address
    proposal.execution_attempts += 1
    # fee_model_v10 配線: 実行時点の tier 別 fee_rate を記録する (fail-open)
    # per-trade の fee_amount は月次バッチ (F-7) で計算するため 0 を設定する。
    proposal.fee_rate = _lookup_fee_rate_for_user(db, proposal.user_id)
    proposal.fee_amount = Decimal("0")

    tx = Transaction(
        user_id=proposal.user_id,
        operation=proposal.operation,
        asset=proposal.asset,
        amount=proposal.amount,
        amount_usd=proposal.amount_usd,
        tx_hash=body.tx_hash,
        chain=chain_name,
        status="completed",
        ai_decision_id=proposal.ai_decision_id,
        is_dry_run=False,
    )
    db.add(tx)
    db.commit()
    db.refresh(proposal)

    logger.info(
        "submit-tx: proposal %d executed by partner wallet=%s...%s tx=%s",
        proposal_id,
        partner_wallet[:6] if partner_wallet else "?",
        partner_wallet[-4:] if partner_wallet else "?",
        body.tx_hash[:12],
    )

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
