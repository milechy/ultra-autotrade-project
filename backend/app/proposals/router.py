# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/proposals/router.py
"""提案API ルーター定義。"""

import asyncio
import csv
import io
import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.aave.balance import read_wallet_usdc_balance
from app.auth.dependencies import (
    require_active_user,
    require_admin,
    require_partner,
    require_viewer,
)
from app.auth.models import User, UserRole
from app.auth.models import User as UserModel
from app.database import get_db
from app.policy.engine import PolicyContext, get_policy_engine
from app.users.models import DelegationGrant, get_active_grant

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

# S2: awaiting_funds(入金待ち)の funding window(日)。承認=投資意図キャプチャ時に
# expires_at を now+この日数に書き換え、市場期限(72h)と分離する(docs/62 §11.2 案A)。
_FUNDING_WINDOW_DAYS = int(os.getenv("FUNDING_WINDOW_DAYS", "7"))

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


class TxRevertedError(ValueError):
    """on-chain tx が revert (receipt status=0) したことを表す。

    submit-tx の検証で revert を他の検証失敗 (from/to 不一致・pending タイムアウト) と
    区別し、**revert のみ** proposal を failed に遷移させるために使う (同じ tx を再 submit
    しても revert する恒久失敗)。ValueError を継承するので既存 `except ValueError` 経路とも
    後方互換 (revert 用 except を先に置く)。
    """


def _fail_proposal(proposal: Proposal, chain: str, error_message: str, db: Session) -> None:
    """proposal を failed に遷移させ、失敗 transaction 記録 + Slack 通知を行う共通処理。

    非カストディアル submit-tx の revert (B6) で使う。commit は呼び出し側。
    custodial 経路 (_execute_aave_for_proposal) は独自の dead-letter ロジックを持つため
    そちらは別管理 (将来寄せる余地あり)。
    """
    failed_at = datetime.now(timezone.utc)
    proposal.status = "failed"
    proposal.error_message = error_message
    proposal.executed_at = failed_at
    proposal.execution_attempts += 1
    _record_failed_transaction(proposal, chain, error_message, db)
    _notify_aave_failure(proposal.id, error_message, failed_at)


def _daily_traded_usd_for_user(
    user_id: int, db: Session, exclude_proposal_id: Optional[int] = None
) -> Decimal:
    """当日(UTC)に approved/executed になった当該ユーザーの提案額合計(USD)。

    risk_limiter %クランプ / HARD_STOP の日次%判定の分母加算に使う。
    PolicyEngine._check_velocity と同じ集計条件(approved/executed・当日・自分以外)を踏襲する。
    """
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    stmt = select(func.sum(Proposal.amount_usd)).where(
        Proposal.user_id == user_id,
        Proposal.status.in_(["approved", "executed"]),
        Proposal.approved_at >= day_start,
    )
    if exclude_proposal_id is not None:
        stmt = stmt.where(Proposal.id != exclude_proposal_id)
    raw = db.scalar(stmt)
    return Decimal(str(raw)) if raw is not None else Decimal("0")


def _resolve_privy_wallet_id(user: Optional[UserModel]) -> str:
    """委譲(SCW)送信に使う Privy **内部 wallet ID** を解決する（アドレスではない）。

    dev/shadow フェーズは env ``PRIVY_DELEGATED_WALLET_ID`` の単一 wallet（spike の
    ``SPIKE_SW_EOA_WALLET_ID`` を写す運用）。将来マルチユーザー本番化で per-user 列が入れば
    そちらを優先する（現状 users に privy_wallet_id 列は無い）。
    """
    pid = getattr(user, "privy_wallet_id", None)
    if pid:
        return str(pid)
    return os.getenv("PRIVY_DELEGATED_WALLET_ID", "")


def _should_use_scw_route(proposal: Proposal, grant: Optional[DelegationGrant]) -> bool:
    """委譲(SCW)経路で執行するか（dormant 既定 False）。

    True 条件: delegation policy 有効（フラグ+L0 signer+creds）かつ 有効 grant に
    privy_signer_id/privy_policy_id があり、operation が SUPPLY のとき。
    出金(WITHDRAW)は委譲対象外＝常に custodial(本人署名)維持。
    """
    if proposal.operation != "SUPPLY":
        return False
    from app.privy.delegation_service import is_delegation_policy_enabled  # noqa: PLC0415

    if not is_delegation_policy_enabled():
        return False
    if grant is None:
        return False
    return bool(grant.privy_signer_id and grant.privy_policy_id)


def _execute_supply_via_scw(
    proposal: Proposal, chain: str, grant: DelegationGrant, user: Optional[UserModel], db: Session
) -> Any:
    """委譲(SCW)経路で SUPPLY を執行し、custodial 互換の result(tx_hash/status) を返す。

    HARD_STOP / risk_limiter / Rule8 は呼び出し元が執行直前に通過済み（本関数は通さない）。
    amount は custodial 経路と同じく proposal.amount_usd を token 単位として渡す（既存挙動踏襲）。
    """
    from app.aave.service import MultiChainAaveService  # noqa: PLC0415
    from app.proposals.scw_executor import (  # noqa: PLC0415
        build_supply_calls,
        execute_calls_via_scw,
    )

    scw_address = grant.wallet_address or (user.smart_wallet_address if user else None)
    if not scw_address:
        raise ValueError("SCW route requires a smart wallet address (grant/user)")
    privy_wallet_id = _resolve_privy_wallet_id(user)

    client = MultiChainAaveService().get_service(chain).client
    deposit_txs = client.build_deposit_txs(
        proposal.asset, Decimal(str(proposal.amount_usd)), wallet_address=scw_address
    )
    calls = build_supply_calls(deposit_txs)
    return execute_calls_via_scw(
        privy_wallet_id=privy_wallet_id,
        chain_name=chain,
        calls=calls,
        idempotency_key=f"proposal-{proposal.id}",
    )


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

    from .execution_route import (
        DEFAULT_EXECUTION_ROUTE,
        ExecutionRoute,
        RouteMismatchError,
        assert_route,
        detect_route_mismatch,
        notify_route_mismatch,
    )

    # P0-2 誤執行ガード: Aave 自動実行は on-chain 経路専用。
    # CEX 選択 proposal がこの経路に入った場合は即時 EMERGENCY アラート + 例外で停止する
    # (呼び出し元 approve_proposal が 409 に変換し、手動介入必須)。
    try:
        assert_route(proposal, ExecutionRoute.ONCHAIN_AAVE)
    except RouteMismatchError:
        proposal.status = "failed"
        proposal.error_message = "route mismatch: CEX proposal entered on-chain execution path"
        raise

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

    # NULL wallet guard (Layer 1): wallet 未設定 partner は執行を拒否してデフォルト wallet 汚染を防ぐ
    if not _wallet_address:
        _error_msg = f"user {proposal.user_id} has no wallet_address configured — execution blocked"
        logger.error("proposal %d: %s", proposal.id, _error_msg)
        _blocked_at = datetime.now(timezone.utc)
        proposal.status = "failed"
        proposal.error_message = _error_msg
        proposal.executed_at = _blocked_at
        _record_failed_transaction(proposal, chain, _error_msg, db)
        _notify_aave_failure(proposal.id, _error_msg, _blocked_at)
        return

    # HARD_STOP 安全ゲート（スライス0-E2）: 執行直前にグローバル安全条件を確認する。
    # rule engine(HF<1.6/emergency stop/oracle/reserve) / StressController / MacroSafeMode /
    # CompoundRiskAssessor を経路非依存に評価する（safety_gate, スライス0-E1）。
    # 従来この execute 経路はこれらを通っておらず(gap E)、承認スキップの自動執行(Phase 2-D)でも
    # バイパスされないよう execute 直前に配置する。HARD_STOP は transient なため dead-letter せず、
    # proposal は 'approved' のまま据え置き(条件解消後に再執行可能)にする。
    from app.automation.safety_gate import evaluate_hard_stop  # noqa: PLC0415
    from app.automation.state import get_monitoring_service  # noqa: PLC0415

    _hf_for_gate: Optional[Decimal] = None
    try:
        from app.aave.monitor import get_health_factor as _gate_get_hf  # noqa: PLC0415

        _hf_for_gate = _gate_get_hf()
    except Exception as _hf_exc:  # noqa: BLE001
        logger.warning("proposal %d: HF fetch for safety gate failed: %s", proposal.id, _hf_exc)

    # 日次既執行額（HARD_STOP 日次%判定 / risk_limiter %クランプの分母加算用）。
    _daily_traded = _daily_traded_usd_for_user(
        proposal.user_id, db, exclude_proposal_id=proposal.id
    )
    # per-user 総資産の取得元は未実装（Phase 2-D 後続 sub-task）。None の間は %判定をスキップし、
    # PolicyEngine 絶対額上限 +（後続スライスの）Privy policy で担保する（fail-safe）。
    _total_assets: Optional[Decimal] = None

    _hard_stop = evaluate_hard_stop(
        get_monitoring_service(),
        _hf_for_gate,
        daily_traded_usd=_daily_traded,
        total_assets_usd=_total_assets,
    )
    if _hard_stop.blocked:
        logger.warning(
            "proposal %d: execution HELD by safety gate (source=%s, reason=%s) — "
            "status remains 'approved' for retry after condition clears",
            proposal.id,
            _hard_stop.source,
            _hard_stop.reason,
        )
        return

    # risk_limiter %クランプ（スライス2-D-A）: 単一/日次% と HF をハード上限に対し執行直前に再検査。
    # 違反は HARD_STOP と同様 transient 扱いで 'approved' 据え置き（条件変化後に再執行可能）。
    from app.aave.risk_limiter import check_trade_within_limits  # noqa: PLC0415

    _limit_violation = check_trade_within_limits(
        amount_usd=Decimal(str(proposal.amount_usd)),
        total_assets_usd=_total_assets,
        daily_traded_usd=_daily_traded,
        hf=_hf_for_gate,
    )
    if _limit_violation is not None:
        logger.warning(
            "proposal %d: execution HELD by risk_limiter (%s) — "
            "status remains 'approved' for retry after condition clears",
            proposal.id,
            _limit_violation,
        )
        return

    try:
        # 委譲(SCW)経路（2-D-C.2・dormant）: delegation policy 有効 かつ 当該ユーザーに
        # privy_signer_id/policy_id 付き有効 grant がある SUPPLY のみ SCW 経由で執行する。
        # それ以外（本番現状＝フラグ未設定）は従来の custodial EOA 直署名経路で挙動不変。
        _grant = get_active_grant(proposal.user_id, db)
        if _grant is not None and _should_use_scw_route(proposal, _grant):
            logger.info(
                "proposal %d: routing via delegated SCW path (policy_id present)", proposal.id
            )
            result = _execute_supply_via_scw(proposal, chain, _grant, _user, db)
        else:
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

        # 執行後の経路↔証跡整合チェック (§14a defense-in-depth)。
        # assert_route は「執行前」ガードなのに対し、ここは「執行後」に
        # 経路 (execution_route) と実際の証跡 (on-chain tx_hash / CEX order) の
        # 食い違いを検出する。on-chain 経路の正常系 (tx あり / CEX order なし) では
        # None を返し no-op。CEX order が誤って付くなど証跡破損 (誤執行の疑い) 時のみ
        # EMERGENCY 通知を出して手動介入を促す (tx は確定済みのため status は変えない)。
        _route = proposal.execution_route or DEFAULT_EXECUTION_ROUTE
        _evidence_mismatch = detect_route_mismatch(
            _route,
            has_onchain_tx=bool(proposal.tx_hash),
            has_cex_order=bool(proposal.cex_order_id),
        )
        if _evidence_mismatch:
            notify_route_mismatch(proposal.id, _route, _evidence_mismatch)
            logger.error(
                "proposal %d: post-execution route mismatch — %s",
                proposal.id,
                _evidence_mismatch,
            )

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


class ProtocolExecutionNotWiredError(Exception):
    """custodial 自動執行がまだ配線されていない protocol を指す。

    Lido/Pendle の on-chain 実行 (real ETH stake / PT swap の broadcast) は
    HUMAN-REVIEW-REQUIRED かつ Opus による安全レビュー対象 (CLAUDE.md v4 鉄則10)。
    本スライスでは dispatch 構造とテストのみ整備し、実 broadcast は意図的に未配線。
    """


def _execute_lido_for_proposal(proposal: Proposal, db: Session) -> None:
    """[Phase D / HUMAN-REVIEW 未配線] Lido STAKE_ETH の custodial 実行。

    実装方針 (HUMAN-REVIEW + Opus で配線すること):
      1. LidoClient.stake_eth(amount_wei) で stETH をステーク (real ETH 送金 = 要レビュー)
      2. receipt 確認 → proposal.status='executed' / tx_hash 保存
      3. 失敗時は _execute_aave_for_proposal と同様に status='failed' + 通知

    現状は実 broadcast を含まないため未配線として明示的に raise する。これにより
    auto_execution_enabled=true でも Lido 提案が誤って Aave 経路で実行されることを防ぐ。
    """
    raise ProtocolExecutionNotWiredError(
        f"Lido (proposal={proposal.id}, op={proposal.operation}) の custodial 自動執行は "
        "未配線です (HUMAN-REVIEW-REQUIRED)。"
    )


def _execute_pendle_for_proposal(proposal: Proposal, db: Session) -> None:
    """[Phase D / HUMAN-REVIEW 未配線] Pendle BUY_PT/SELL_PT の custodial 実行。

    実装方針 (HUMAN-REVIEW + Opus で配線すること):
      1. PendleService/RouterV4 で swap calldata 取得 (dry_run=True は安全・本番前確認用)
      2. PENDLE_ENABLE_ONCHAIN_WRITE=true かつ dry_run=False で broadcast (要レビュー)
      3. receipt 確認 → proposal.status='executed' / tx_hash 保存

    現状は実 broadcast を含まないため未配線として明示的に raise する。
    """
    raise ProtocolExecutionNotWiredError(
        f"Pendle (proposal={proposal.id}, op={proposal.operation}) の custodial 自動執行は "
        "未配線です (HUMAN-REVIEW-REQUIRED)。"
    )


def _dispatch_custodial_execution(proposal: Proposal, db: Session) -> None:
    """proposal.protocol で custodial 自動執行ハンドラを振り分ける。

    protocol 無指定 / "aave" は従来どおり Aave 経路。"lido"/"pendle" は専用ハンドラ
    (現状 HUMAN-REVIEW 未配線で raise)。protocol を見ずに常に Aave 実行していた
    潜在的な誤執行 (Lido/Pendle 提案を Aave operation として実行) を防ぐ。
    """
    protocol = (proposal.protocol or "aave").lower()
    if protocol in ("", "aave"):
        _execute_aave_for_proposal(proposal, db)
    elif protocol == "lido":
        _execute_lido_for_proposal(proposal, db)
    elif protocol == "pendle":
        _execute_pendle_for_proposal(proposal, db)
    else:
        raise ProtocolExecutionNotWiredError(
            f"未知の protocol '{protocol}' (proposal={proposal.id}) は自動執行非対応です。"
        )


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
    type: str = Query(
        "individual",
        description="出力モード: individual (個人=Cryptact) / corporate (法人=freee/弥生)",
    ),
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

    type=corporate (法人 freee/弥生) は corporate-CSV [4/4] で実装予定。
    会計マッピング(勘定科目・税区分)の税理士承認が適用されるまでは、個人データを
    法人フォーマットと偽って返さないよう 501 で明示的に拒否する (silent-wrong-data 防止)。
    円建ての基礎データ源は月次 fee_transactions (net_profit_jpy 等) を用いる方針で確定済み。
    """
    if type == "corporate":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "法人モード (freee/弥生 CSV) は準備中です。"
                "税理士承認の仕訳マッピング適用後に提供されます。"
            ),
        )

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
    """自分の保留中（pending）+ 入金待ち（awaiting_funds）提案リストを返す。

    S2: awaiting_funds も含めることで、フロントが入金待ちカードを表示し残高ポーリングで
    着金検知できる。`_expire_old_proposals` は pending のみ対象なので awaiting_funds の
    期限切れには影響しない（funding window の expire は funding_detection_loop が担当）。
    """
    _expire_old_proposals(db, current_user.id)
    stmt = (
        select(Proposal)
        .where(
            Proposal.user_id == current_user.id,
            Proposal.status.in_(["pending", "awaiting_funds"]),
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
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> ProposalResponse:
    """提案を承認してAave操作を実行する（本人・admin・partner）。

    VIEWER (一般消費者 = liff-chat ユーザー) は自分の提案のみ承認可能。
    admin/partner は運用代行として他ユーザーの提案も操作可能。
    """
    stmt = select(Proposal).where(Proposal.id == proposal_id)
    proposal = db.scalars(stmt).first()
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    # VIEWER は自分の提案のみ。admin/partner は全提案を操作可能。
    _is_privileged = current_user.role in (UserRole.ADMIN.value, UserRole.PARTNER.value)
    if not _is_privileged and proposal.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this proposal",
        )
    if proposal.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve proposal with status '{proposal.status}'",
        )

    # AUTO 執行フラグは PolicyContext (Rule8: AUTO 執行は有効委譲枠必須) より前に評価する。
    auto_execution_enabled = os.getenv("AUTO_EXECUTION_ENABLED", "false").lower() == "true"

    # Step 1: PolicyEngine hard rule 検算（承認前に必ず通す）
    ctx = PolicyContext(
        user_id=proposal.user_id,
        asset=proposal.asset,
        operation=proposal.operation,
        amount_usd=Decimal(str(proposal.amount_usd)),
        expected_hf_after=Decimal(str(proposal.expected_hf_after))
        if proposal.expected_hf_after is not None
        else None,
        proposal_id=proposal.id,
        is_auto_execution=auto_execution_enabled,
    )
    policy_result = get_policy_engine().check(ctx, db)
    if policy_result.blocked:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "POLICY_VIOLATION",
                "violations": policy_result.violations,
            },
        )

    # Step 2: 承認済みにマーク
    proposal.status = "approved"
    proposal.approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(proposal)

    # Step 2: Aave 自動実行 (AUTO_EXECUTION_ENABLED=true の場合のみ)
    # non-custodial 方式2 では default=false。partner 手動署名 (submit_partner_tx) のみが実 tx を立てる。
    # AAVE_WALLET_PRIVATE_KEY が署名する経路はこのフラグで完全に無効化される。
    # （auto_execution_enabled は上の PolicyContext 構築前に評価済み）
    if auto_execution_enabled:
        from .execution_route import RouteMismatchError  # noqa: PLC0415

        try:
            # protocol (aave/lido/pendle) で執行ハンドラを振り分ける。
            # Lido/Pendle は HUMAN-REVIEW 未配線のため ProtocolExecutionNotWiredError。
            _dispatch_custodial_execution(proposal, db)
        except RouteMismatchError as exc:
            db.commit()  # status='failed' / error_message を永続化
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"誤執行検出: {exc} (手動介入必須)",
            ) from exc
        except ProtocolExecutionNotWiredError as exc:
            # Lido/Pendle の custodial 自動執行は未配線 (HUMAN-REVIEW)。
            # approved のまま据置き、501 で明示する (Aave として誤実行しない)。
            logger.warning("proposal %d: custodial execution 未配線: %s", proposal.id, exc)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=str(exc),
            ) from exc
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
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> ProposalResponse:
    """提案を拒否する（本人・admin・partner）。

    VIEWER (一般消費者 = liff-chat ユーザー) は自分の提案のみ拒否可能。
    admin/partner は運用代行として他ユーザーの提案も操作可能。
    """
    stmt = select(Proposal).where(Proposal.id == proposal_id)
    proposal = db.scalars(stmt).first()
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    # VIEWER は自分の提案のみ。admin/partner は全提案を操作可能。
    _is_privileged = current_user.role in (UserRole.ADMIN.value, UserRole.PARTNER.value)
    if not _is_privileged and proposal.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this proposal",
        )
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


@router.post(
    "/{proposal_id}/await-funds",
    response_model=ProposalResponse,
    summary="入金待ち化（残高不足時の投資意図キャプチャ）",
)
def await_funds_proposal(
    proposal_id: int,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> ProposalResponse:
    """残高不足の SUPPLY 提案を `awaiting_funds`(入金待ち)に遷移させる (S2 / docs/62)。

    「承認＝投資意図のキャプチャ」。署名はまだ行わず、入金期限(funding window)内に
    着金すれば funding_detection_loop が approved 化して署名可能になる。
    市場期限(72h)とは分離するため expires_at を now+_FUNDING_WINDOW_DAYS に書き換える(案A)。
    VIEWER は自分の提案のみ。admin/partner は代行可。reject と同じ認可・遷移パターン。
    """
    stmt = select(Proposal).where(Proposal.id == proposal_id)
    proposal = db.scalars(stmt).first()
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    _is_privileged = current_user.role in (UserRole.ADMIN.value, UserRole.PARTNER.value)
    if not _is_privileged and proposal.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this proposal",
        )
    if proposal.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot await-funds proposal with status '{proposal.status}'",
        )
    now = datetime.now(timezone.utc)
    proposal.status = "awaiting_funds"
    # funding window: 市場期限と分離。入金待ち中は expires_at をこちらで上書き。
    proposal.expires_at = now + timedelta(days=_FUNDING_WINDOW_DAYS)
    db.commit()
    db.refresh(proposal)
    _notify_funding_requested(proposal)
    return ProposalResponse.model_validate(proposal)


def _notify_funding_requested(proposal: Proposal) -> None:
    """入金待ち化を「あと $X 入金してください」とユーザー通知する (best-effort)。"""
    try:
        from app.notifications.factory import get_notification_service  # noqa: PLC0415
        from app.notifications.templates import funding_requested_notification  # noqa: PLC0415

        payload = funding_requested_notification(
            operation=proposal.operation,
            asset=proposal.asset,
            required_usd=proposal.amount_usd,
        )
        msg = payload.notification_message.model_copy(update={"user_id": proposal.user_id})
        get_notification_service().send(msg)
    except Exception as exc:  # noqa: BLE001
        logger.warning("_notify_funding_requested failed for proposal %d: %s", proposal.id, exc)


def _resolve_onchain_token_amount(proposal: Proposal) -> Decimal:
    """proposal から **トークン建て** の on-chain 数量 (ETH / 入力トークン) を解決する。

    [安全ブロック / fail-closed] ``proposal.amount`` / ``proposal.amount_usd`` は提案生成時
    (ai_judgment_scheduler ``_resolve_proposal_amount``) で **両方とも USD 建て** に設定される
    (``amount = amount_usd = proposal_amount_usd``)。Aave は asset=USDC (1 USDC≒1 USD) のため
    amount_usd をそのままトークン数量として扱えるが、Lido(ETH) / Pendle(stETH 等) では
    1 token ≫ 1 USD のため、USD 値を token 数量として on-chain tx に載せると ETH 価格倍
    (~数千倍) 過大ステークになる。

    現状システムには USD→token のスポット価格換算が無い (price oracle 未配線)。誤った数量の
    未署名 tx を partner に署名させるのは「誰の資産が動くか」観点で危険なため、ここで明示的に
    501 を返して **未署名 tx を一切組み立てない**。

    フォローアップ (いずれか):
      1. 提案生成時に ``proposal.amount`` を token 建てで保存する (本命の修正)、または
      2. 本関数で ETH/USD 等のスポット価格 (app.partner.wallet_balance_service._fetch_eth_usd_price
         / app.market) を用いて USD→token 換算する。

    実装後は本関数が token 建て Decimal を返し、下流の build_stake_tx / build_buy_pt_tx 配線が
    そのまま有効化される。
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "Lido/Pendle の非カストディアル未署名 tx 構築には token 建て数量が必要ですが、"
            "現状 proposal.amount は USD 建てで保存されており USD→token 価格換算が未配線です。"
            "誤った数量での署名を防ぐため fail-closed (HUMAN-REVIEW: 価格換算 or token 建て amount 保存を実装)。"
        ),
    )


def _build_lido_partner_tx(proposal: Proposal, wallet_address: str) -> PartnerUnsignedTxs:
    """Lido STAKE_ETH の非カストディアル未署名 tx を構築する。

    サーバー鍵 (``LIDO_WALLET_PRIVATE_KEY``) を一切参照せず、``LidoClient.build_stake_tx``
    で未署名 submit tx を組み立てて返す (submit は msg.sender=partner に stETH を mint するため
    着金先も partner 本人)。partner が Privy で本人署名・送信する。

    数量は ``_resolve_onchain_token_amount`` で ETH 建てに解決する (現状 fail-closed 501)。
    """
    if proposal.operation != "STAKE_ETH":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Lido は STAKE_ETH のみ partner 署名に対応します (指定: {proposal.operation})",
        )
    from app.protocols.lido.client import _WEI_PER_ETH, get_lido_client  # noqa: PLC0415
    from app.protocols.lido.config import get_lido_config  # noqa: PLC0415

    amount_eth = _resolve_onchain_token_amount(proposal)  # token(ETH) 建て / 未配線時は 501
    amount_wei = int(amount_eth * _WEI_PER_ETH)
    if amount_wei <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="STAKE_ETH の数量が 0 以下です",
        )
    try:
        client = get_lido_client(get_lido_config())
        stake_tx = client.build_stake_tx(amount_wei=amount_wei, from_address=wallet_address)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lido stake tx 構築失敗: {exc}",
        ) from exc
    return PartnerUnsignedTxs(
        proposal_id=proposal.id,
        operation=proposal.operation,
        wallet_address=wallet_address,
        stake_tx=UnsignedTx.model_validate(stake_tx),
    )


def _build_pendle_partner_tx(proposal: Proposal, wallet_address: str) -> PartnerUnsignedTxs:
    """Pendle BUY_PT の非カストディアル未署名 tx を構築する。

    サーバー鍵 (``PENDLE_WALLET_PRIVATE_KEY``) を参照せず、Hosted SDK が生成した
    swapExactTokenForPt calldata を未署名 tx として返す。receiver/from は partner 本人に固定し
    (PT が本人着金)、SDK calldata の宛先が Router であることを照合する (``build_buy_pt_tx`` 内
    fail-closed)。

    market は ``PENDLE_MARKET_ADDRESS``、入力トークンは ``PENDLE_UNDERLYING_TOKEN_ADDRESS``。
    数量は ``_resolve_onchain_token_amount`` で入力トークン建てに解決する (現状 fail-closed 501)。
    """
    if proposal.operation != "BUY_PT":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Pendle は BUY_PT のみ partner 署名に対応します (指定: {proposal.operation})",
        )
    from app.protocols.pendle.client import (  # noqa: PLC0415
        PendleBuildTxError,
        get_pendle_router_v4_client,
    )
    from app.protocols.pendle.config import get_pendle_config  # noqa: PLC0415

    amount_in = _resolve_onchain_token_amount(proposal)  # 入力トークン建て / 未配線時は 501
    if amount_in <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="BUY_PT の数量が 0 以下です",
        )
    config = get_pendle_config()
    try:
        client = get_pendle_router_v4_client(config)
        buy_pt_tx = asyncio.run(
            client.build_buy_pt_tx(
                market_address=config.market_address,
                token_in=config.underlying_token_address,
                amount_in=amount_in,
                from_address=wallet_address,
            )
        )
    except PendleBuildTxError as exc:
        # calldata 取得失敗 / Router 不一致は fail-closed。未署名 tx を返さない。
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Pendle BUY_PT tx 構築失敗: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pendle BUY_PT tx 構築失敗: {exc}",
        ) from exc
    return PartnerUnsignedTxs(
        proposal_id=proposal.id,
        operation=proposal.operation,
        wallet_address=wallet_address,
        buy_pt_tx=UnsignedTx.model_validate(buy_pt_tx),
    )


@router.get(
    "/{proposal_id}/build-tx",
    response_model=PartnerUnsignedTxs,
    response_model_by_alias=True,
    summary="パートナー署名用: 未署名トランザクション構築",
)
def build_partner_tx(
    proposal_id: int,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> PartnerUnsignedTxs:
    """
    パートナーが Privy で署名するための未署名 Aave トランザクションを構築して返す。

    approve_proposal の代わりにこのエンドポイントを呼び、フロントエンドで
    Privy sendTransaction() 経由でパートナー本人が署名・送信する。
    """
    from app.aave.client import verify_supply_onbehalf, verify_withdraw_to  # noqa: PLC0415
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

    # 実行ウォレット取得。
    # Smart Wallet (AA) ユーザーは smart_wallet_address で onBehalfOf/to を構築する
    # (Aave ポジション保有者 = SCW。slice3b)。未設定の EOA ユーザーは従来どおり wallet_address。
    user = db.scalars(select(User).where(User.id == proposal.user_id)).first()
    wallet_address = (
        user.smart_wallet_address
        if user is not None and user.smart_wallet_address
        else (user.wallet_address if user is not None else None)
    )
    if user is None or not wallet_address:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="wallet_address / smart_wallet_address が未設定です。Privy で wallet を作成してください。",
        )

    # protocol で非カストディアル経路を振り分ける。Lido (STAKE_ETH) / Pendle (BUY_PT) は
    # サーバー鍵 broadcast せず、未署名 tx を返して partner が Privy 本人署名する。
    # protocol 無指定 / "aave" は従来どおり Aave SUPPLY/WITHDRAW。
    protocol = (proposal.protocol or "aave").lower()
    if protocol == "lido":
        return _build_lido_partner_tx(proposal, wallet_address)
    if protocol == "pendle":
        return _build_pendle_partner_tx(proposal, wallet_address)

    op_map: dict[str, str] = {"SUPPLY": "DEPOSIT", "WITHDRAW": "WITHDRAW"}
    if proposal.operation not in op_map:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Operation {proposal.operation} は partner 署名に非対応です",
        )

    # B1: SUPPLY は USDC 残高不足を build-tx 前に検出し、無駄ガス・on-chain revert を防ぐ。
    # 残高取得失敗 (None) は fail-open（ガード skip）— submit-tx の revert→failed が安全網。
    # WITHDRAW は aToken 引出なので USDC 残高ガード対象外。
    if proposal.operation == "SUPPLY":
        _balance = read_wallet_usdc_balance(wallet_address)
        _need = Decimal(str(proposal.amount_usd))
        if _balance is not None and _balance < _need:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"USDC 残高不足: 必要 {_need} USDC に対しウォレット残高 {_balance} USDC。"
                    "入金してから再度お試しください。"
                ),
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
        else:  # WITHDRAW
            txs = service._client.build_withdraw_tx(
                asset_symbol=asset_symbol,
                amount=Decimal(str(proposal.amount_usd)),
                wallet_address=wallet_address,
            )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"tx 構築失敗: {exc}",
        ) from exc

    # 署名前 hook (補完層): サーバーが生成済み calldata を実デコードし、
    # onBehalfOf (supply) / to (withdraw) が本人 wallet でなければ未署名 tx を
    # 返さず reject する。build-tx 側固定 (主担保) の二重チェックであり、
    # 万一 encode 経路に欠陥が混入しても他人宛て tx を組ませない。
    # (P0-3 / Asana 1215364095372268)
    if proposal.operation == "SUPPLY":
        if not verify_supply_onbehalf(txs["supply_tx"]["data"], wallet_address):
            logger.error(
                "build-tx onBehalfOf 検証失敗: proposal=%s wallet=%s...%s",
                proposal_id,
                wallet_address[:6],
                wallet_address[-4:],
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="onBehalfOf 検証失敗: supply tx の onBehalfOf が本人 wallet と不一致",
            )
        return PartnerUnsignedTxs(
            proposal_id=proposal_id,
            operation=proposal.operation,
            wallet_address=wallet_address,
            approve_tx=UnsignedTx.model_validate(txs["approve_tx"]),
            supply_tx=UnsignedTx.model_validate(txs["supply_tx"]),
        )
    else:  # WITHDRAW
        if not verify_withdraw_to(txs["withdraw_tx"]["data"], wallet_address):
            logger.error(
                "build-tx withdraw to 検証失敗: proposal=%s wallet=%s...%s",
                proposal_id,
                wallet_address[:6],
                wallet_address[-4:],
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="to 検証失敗: withdraw tx の to が本人 wallet と不一致",
            )
        return PartnerUnsignedTxs(
            proposal_id=proposal_id,
            operation=proposal.operation,
            wallet_address=wallet_address,
            withdraw_tx=UnsignedTx.model_validate(txs["withdraw_tx"]),
        )


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
        raise TxRevertedError(
            f"tx {tx_hash[:12]}... は reverted (status={receipt['status']}) です。"
        )

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
    current_user: User = Depends(require_active_user),
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

    from .execution_route import ExecutionRoute, RouteMismatchError, assert_route

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

    # P0-2 誤執行ガード: submit-tx は on-chain Aave 経路専用。
    # CEX 選択 proposal が on-chain (basescan) tx で執行されようとした場合は
    # 即時 EMERGENCY アラート + 409 で自動進行を止め、手動介入を必須化する。
    try:
        assert_route(proposal, ExecutionRoute.ONCHAIN_AAVE)
    except RouteMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"誤執行検出: {exc} (手動介入必須)",
        ) from exc

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

    # 実行主体の判定 (slice3b): Smart Wallet (AA) ユーザーは bundler の UserOp receipt で、
    # EOA ユーザーは従来の on-chain tx receipt で検証する。
    proposal_user = db.scalars(select(User).where(User.id == proposal.user_id)).first()
    scw_address = proposal_user.smart_wallet_address if proposal_user is not None else None

    if scw_address:
        # AA 経路: body.tx_hash は userOpHash。bundler で success / sender(=SCW) を検証 (fail-closed)。
        bundler_url = os.getenv("BUNDLER_RPC_URL", "")
        if not bundler_url:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="BUNDLER_RPC_URL が未設定です (Smart Wallet 実行の検証不可)。",
            )
        from .userop_verify import (  # noqa: PLC0415
            UserOpRevertedError,
            UserOpVerificationError,
            verify_userop_receipt,
        )

        try:
            verify_userop_receipt(
                body.tx_hash, expected_sender=scw_address, bundler_url=bundler_url
            )
        except UserOpRevertedError as exc:
            # B6: SCW(UserOp) revert も恒久失敗 → failed 遷移＋記録＋通知。
            # pending / sender 不一致は下の except で従来どおり pending 維持 (再 submit 可)。
            _fail_proposal(proposal, chain_name, f"UserOp revert: {exc}", db)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"UserOp receipt 検証失敗 (revert): {exc}",
            ) from exc
        except UserOpVerificationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"UserOp receipt 検証失敗: {exc}",
            ) from exc
        partner_wallet = scw_address
        logger.info(
            "submit-tx: proposal %d UserOp verified via bundler chain=%s userOp=%s",
            proposal_id,
            chain_name,
            body.tx_hash[:12],
        )
    elif rpc_url and pool_address:
        partner_wallet = body.wallet_address
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
        except TxRevertedError as exc:
            # B6: revert は恒久失敗。proposal を failed に遷移＋記録＋通知 (無言失敗の解消)。
            # from/to 不一致・pending は別 tx で再 submit 可能なので下の except で pending 維持。
            _fail_proposal(proposal, chain_name, f"on-chain revert: {exc}", db)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"on-chain receipt 検証失敗 (revert): {exc}",
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"on-chain receipt 検証失敗: {exc}",
            ) from exc
    else:
        partner_wallet = body.wallet_address
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
    from .execution_route import DEFAULT_EXECUTION_ROUTE, ExecutionRoute  # noqa: PLC0415

    expires_at = request.expires_at or (datetime.now(timezone.utc) + timedelta(hours=72))
    # P0-2: 執行経路を作成時に確定 (以後 immutable)。未指定時は on-chain Aave (後方互換)。
    execution_route = request.execution_route or DEFAULT_EXECUTION_ROUTE
    if execution_route not in ExecutionRoute.values():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid execution_route '{execution_route}'",
        )
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
        execution_route=execution_route,
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return ProposalResponse.model_validate(proposal)
