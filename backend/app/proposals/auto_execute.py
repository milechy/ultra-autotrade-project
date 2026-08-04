# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/proposals/auto_execute.py
"""「完全おまかせ」(execution_policy=AUTO_EXECUTE) ユーザー向けの無承認自動実行。

AI 判定 tick で生成された pending proposal のうち、AUTO_EXECUTE ポリシーかつ有効な
委譲(SCW) grant を持つユーザーの分だけを対象に、人間の承認クリックを介さず
``_run_approval_and_execution(is_auto_execution=True)`` を呼んで即時実行する。

対象外（grant なし / WITHDRAW 等 SCW 非対応 operation）の proposal は 'pending' の
まま何もしない — 既存のユーザー向け手動承認フローに委ねる。委譲(SCW)経路にも
HARD_STOP・risk_limiter・PolicyEngine Rule8（有効委譲枠必須）・emergency stop は
（``_run_approval_and_execution`` 経由で）等しく適用される。

2026-07-16、実装計画: `.claude-uata/plans/floating-imagining-key.md` §1 参照。
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.constants import ExecutionPolicy
from app.auth.models import User
from app.users.models import get_active_grant

from .execution_route import RouteMismatchError
from .models import Proposal
from .router import (
    DepositBelowMinimumError,
    PolicyViolationError,
    ProtocolExecutionNotWiredError,
    _run_approval_and_execution,
    _should_use_scw_route,
)

logger = logging.getLogger(__name__)


def _notify_auto_execution_issue(proposal_id: int, reason: str) -> None:
    """無承認自動実行がスキップ/失敗した際に管理者へ Slack 通知する（best-effort）。"""
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
            title=f"AUTO_EXECUTE auto-execution issue (proposal #{proposal_id})",
            body=f"proposal_id: {proposal_id}\nreason: {reason}",
        )
        get_notification_service().send(message)
    except Exception as exc:  # noqa: BLE001
        logger.warning("auto_execute notification failed (non-fatal): %s", exc)


def run_auto_execution_for_ai_decision(db: Session, ai_decision_id: int) -> dict[str, int]:
    """指定 AIDecision に紐づく pending proposal のうち、AUTO_EXECUTE ユーザー分を即時実行する。

    :returns: {"auto_executed": int, "auto_execute_skipped": int, "auto_execute_failed": int}
    """
    auto_executed = 0
    auto_execute_skipped = 0
    auto_execute_failed = 0

    targets = db.scalars(
        select(Proposal)
        .join(User, User.id == Proposal.user_id)
        .where(
            Proposal.ai_decision_id == ai_decision_id,
            Proposal.status == "pending",
            User.execution_policy == ExecutionPolicy.AUTO_EXECUTE.value,
        )
    ).all()

    for proposal in targets:
        # NOTE: db.begin_nested() は使わない。_run_approval_and_execution は自身の判断で
        # 複数回 db.commit() する設計（approve_proposal と共有、HTTPの1リクエスト=1トランザクション
        # 前提）のため、外側で SAVEPOINT を張ると commit() 時にネストしたトランザクションが
        # 閉じてしまい "Can't operate on closed transaction" になる（_create_proposals_for_users
        # とは前提が異なる）。DepositBelowMinimumError/PolicyViolationError は proposal へ
        # 書き込む前に raise される、RouteMismatchError/ProtocolExecutionNotWiredError は
        # 自身の db.commit() 済みで raise される — いずれも rollback 不要。真に未想定な例外
        # (DB エラー等) のときのみ明示的に db.rollback() して次の proposal へ安全に進む。
        try:
            grant = get_active_grant(proposal.user_id, db)
            if grant is None or not _should_use_scw_route(proposal, grant):
                # 委譲grantなし、または SCW 対象外 operation (WITHDRAW 等) →
                # 自動実行しない。'pending' のまま既存の手動フローに委ねる。
                logger.info(
                    "proposal %d: auto-execution skipped (no eligible delegation route, "
                    "operation=%s)",
                    proposal.id,
                    proposal.operation,
                )
                auto_execute_skipped += 1
                # 可観測性 (2026-08-04 PR1): 既に検知はしていた分岐に通知を足すだけ。
                # 握り潰しをやめる — この分岐は AUTO_EXECUTE ユーザーの委譲枠欠如の
                # 一次検出点でもある (ai_judgment_scheduler._check_observability_invariants
                # と役割が重複するが、こちらは「実際に実行タイミングでスキップされた」
                # 事実そのものを通知する)。
                _notify_auto_execution_issue(
                    proposal.id,
                    f"no active delegation grant or ineligible route "
                    f"(user_id={proposal.user_id}, operation={proposal.operation}) "
                    "— proposal remains pending",
                )
                continue

            try:
                _run_approval_and_execution(proposal, db, is_auto_execution=True)
                auto_executed += 1
            except (DepositBelowMinimumError, PolicyViolationError) as exc:
                logger.warning(
                    "proposal %d: auto-execution blocked before approval: %s",
                    proposal.id,
                    exc,
                )
                auto_execute_failed += 1
                _notify_auto_execution_issue(proposal.id, str(exc))
            except ProtocolExecutionNotWiredError as exc:
                # Lido/Pendle 等の custodial 未配線 protocol。approved のまま据置き
                # （_run_approval_and_execution 内で処理済み）。監査用に通知のみ行う。
                logger.warning(
                    "proposal %d: auto-execution hit unwired protocol: %s", proposal.id, exc
                )
                auto_execute_failed += 1
                _notify_auto_execution_issue(proposal.id, str(exc))
            except RouteMismatchError as exc:
                # P0-2 誤執行検出（'failed' 化済み）。EMERGENCY 相当のため必ず通知する。
                logger.error(
                    "proposal %d: auto-execution hit route mismatch (手動介入必須): %s",
                    proposal.id,
                    exc,
                )
                auto_execute_failed += 1
                _notify_auto_execution_issue(proposal.id, f"route mismatch: {exc}")
        except Exception as exc:  # noqa: BLE001
            # 1件の未想定例外（DB エラー等）が他 proposal の自動実行を止めないようにする。
            logger.error(
                "proposal %d: auto-execution failed with unexpected error (skipping, "
                "continuing to next proposal): %s",
                proposal.id,
                exc,
            )
            auto_execute_failed += 1
            try:
                db.rollback()
            except Exception:  # noqa: BLE001, S110
                pass
            _notify_auto_execution_issue(proposal.id, str(exc))

    if auto_executed or auto_execute_skipped or auto_execute_failed:
        logger.info(
            "[auto_execute] ai_decision_id=%d executed=%d skipped=%d failed=%d",
            ai_decision_id,
            auto_executed,
            auto_execute_skipped,
            auto_execute_failed,
        )

    return {
        "auto_executed": auto_executed,
        "auto_execute_skipped": auto_execute_skipped,
        "auto_execute_failed": auto_execute_failed,
    }
