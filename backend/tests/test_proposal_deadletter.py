# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_proposal_deadletter.py
"""Stream 2 execution retry 暴走対策: デッドレター化ロジックのテスト。

2026-05-21 P0 post-mortem 対策:
- 3回失敗した proposal は execution_attempts=3 で status='failed' に強制遷移し再試行されない
- ValueError/KeyError (恒久エラー = RPC/chain 設定起因) は attempts 加算なし・即 failed
- MAX_EXECUTION_ATTEMPTS 超過時は dead-lettered エラーメッセージを記録する
- AI judgment scheduler は pending 提案が既存のユーザーに重複提案を作成しない
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-deadletter")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "deadletter_admin@example.com")

from app.database import Base  # noqa: E402
from app.proposals.models import Proposal  # noqa: E402
from app.proposals.router import (  # noqa: E402
    MAX_EXECUTION_ATTEMPTS,
    _execute_aave_for_proposal,
    _is_permanent_error,
)


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestSession()
    try:
        yield db
    finally:
        db.close()
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


def _make_proposal(db: Session, execution_attempts: int = 0) -> Proposal:
    """テスト用 approved 提案を作成して DB に保存する。"""
    p = Proposal(
        user_id=1,
        operation="SUPPLY",
        asset="USDC",
        amount=Decimal("100.000000000000000000"),
        amount_usd=Decimal("100.00"),
        reason="test",
        status="approved",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        execution_attempts=execution_attempts,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


# ---------------------------------------------------------------------------
# 恒久エラー判定
# ---------------------------------------------------------------------------


def test_is_permanent_error_value_error() -> None:
    """ValueError は恒久エラーと判定される。"""
    assert _is_permanent_error(ValueError("AAVE_RPC_URL が必須です"))


def test_is_permanent_error_key_error() -> None:
    """KeyError は恒久エラーと判定される。"""
    assert _is_permanent_error(KeyError("arbitrum_sepolia"))


def test_is_permanent_error_runtime_error() -> None:
    """RuntimeError は恒久エラーではない（一時エラー）。"""
    assert not _is_permanent_error(RuntimeError("connection timeout"))


# ---------------------------------------------------------------------------
# デッドレター上限チェック
# ---------------------------------------------------------------------------


def test_dead_letter_at_max_attempts(db_session: Session) -> None:
    """execution_attempts == MAX_EXECUTION_ATTEMPTS の時点で即 failed（dead-lettered）。"""
    proposal = _make_proposal(db_session, execution_attempts=MAX_EXECUTION_ATTEMPTS)

    with (
        patch("app.proposals.router._notify_aave_failure") as mock_notify,
        patch("app.aave.service.MultiChainAaveService.execute_rebalance") as mock_exec,
    ):
        _execute_aave_for_proposal(proposal, db_session)

    assert proposal.status == "failed"
    assert "dead-lettered" in (proposal.error_message or "")
    assert str(MAX_EXECUTION_ATTEMPTS) in (proposal.error_message or "")
    # Aave 実行は呼ばれない
    mock_exec.assert_not_called()
    # Slack 通知は呼ばれる
    mock_notify.assert_called_once()


def test_no_dead_letter_below_max_attempts(db_session: Session) -> None:
    """execution_attempts < MAX_EXECUTION_ATTEMPTS ならデッドレターにならない（Aave を試行する）。"""
    proposal = _make_proposal(db_session, execution_attempts=MAX_EXECUTION_ATTEMPTS - 1)

    with (
        patch("app.proposals.router._notify_aave_failure"),
        patch("app.proposals.router._record_failed_transaction"),
        patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
            side_effect=RuntimeError("transient error"),
        ) as mock_exec,
    ):
        _execute_aave_for_proposal(proposal, db_session)

    # Aave が呼ばれたことを確認
    mock_exec.assert_called_once()
    # attempts がインクリメントされる
    assert proposal.execution_attempts == MAX_EXECUTION_ATTEMPTS
    assert proposal.status == "failed"


# ---------------------------------------------------------------------------
# 恒久エラー: attempts 加算なし・即 failed
# ---------------------------------------------------------------------------


def test_permanent_error_does_not_increment_attempts(db_session: Session) -> None:
    """ValueError 発生時は execution_attempts を加算せず即 failed。"""
    proposal = _make_proposal(db_session, execution_attempts=0)

    with (
        patch("app.proposals.router._notify_aave_failure"),
        patch("app.proposals.router._record_failed_transaction"),
        patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
            side_effect=ValueError("AAVE_RPC_URL が必須です"),
        ),
    ):
        _execute_aave_for_proposal(proposal, db_session)

    assert proposal.status == "failed"
    # attempts は 0 のまま（永続エラーは加算しない）
    assert proposal.execution_attempts == 0
    assert "ValueError" in (proposal.error_message or "")


def test_permanent_key_error_does_not_increment_attempts(db_session: Session) -> None:
    """KeyError 発生時も execution_attempts を加算しない。"""
    proposal = _make_proposal(db_session, execution_attempts=1)

    with (
        patch("app.proposals.router._notify_aave_failure"),
        patch("app.proposals.router._record_failed_transaction"),
        patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
            side_effect=KeyError("arbitrum_sepolia"),
        ),
    ):
        _execute_aave_for_proposal(proposal, db_session)

    assert proposal.status == "failed"
    # attempts は変わらない
    assert proposal.execution_attempts == 1


# ---------------------------------------------------------------------------
# 一時エラー: attempts 加算
# ---------------------------------------------------------------------------


def test_transient_error_increments_attempts(db_session: Session) -> None:
    """RuntimeError は一時エラーとして attempts を 1 加算する。"""
    proposal = _make_proposal(db_session, execution_attempts=0)

    with (
        patch("app.proposals.router._notify_aave_failure"),
        patch("app.proposals.router._record_failed_transaction"),
        patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
            side_effect=RuntimeError("RPC timeout"),
        ),
    ):
        _execute_aave_for_proposal(proposal, db_session)

    assert proposal.status == "failed"
    assert proposal.execution_attempts == 1


# ---------------------------------------------------------------------------
# 成功時 attempts も記録
# ---------------------------------------------------------------------------


def test_success_increments_attempts(db_session: Session) -> None:
    """成功時も execution_attempts をインクリメントする（診断用）。"""
    from app.aave.schemas import AaveOperationResult, AaveOperationStatus, AaveOperationType

    proposal = _make_proposal(db_session, execution_attempts=0)
    fake_result = AaveOperationResult(
        operation=AaveOperationType.DEPOSIT,
        status=AaveOperationStatus.SUCCESS,
        asset_symbol="USDC",
        amount=Decimal("100.00"),
        tx_hash="0xdeadbeef",
    )

    with patch(
        "app.aave.service.MultiChainAaveService.execute_rebalance",
        return_value=fake_result,
    ):
        _execute_aave_for_proposal(proposal, db_session)

    assert proposal.status == "executed"
    assert proposal.execution_attempts == 1


# ---------------------------------------------------------------------------
# 3回失敗 → failed・再試行されない（シナリオテスト）
# ---------------------------------------------------------------------------


def test_three_failures_lead_to_dead_letter(db_session: Session) -> None:
    """3回連続 transient 失敗後: attempts=3 = MAX_EXECUTION_ATTEMPTS → dead-lettered。

    シナリオ:
    1. 1回目失敗 → attempts=1, status=failed
    2. (再 approve で pending に戻したと仮定) 2回目失敗 → attempts=2, status=failed
    3. 3回目: attempts=MAX → dead-lettered、Aave 呼び出しなし
    """
    proposal = _make_proposal(db_session, execution_attempts=0)

    # 1回目 (attempts=0 → 1)
    with (
        patch("app.proposals.router._notify_aave_failure"),
        patch("app.proposals.router._record_failed_transaction"),
        patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
            side_effect=RuntimeError("transient"),
        ),
    ):
        _execute_aave_for_proposal(proposal, db_session)

    assert proposal.execution_attempts == 1
    assert proposal.status == "failed"

    # 2回目 (proposals.execution_attempts=1 → 2)
    proposal.status = "approved"  # 再 approve シミュレーション
    with (
        patch("app.proposals.router._notify_aave_failure"),
        patch("app.proposals.router._record_failed_transaction"),
        patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
            side_effect=RuntimeError("transient"),
        ),
    ):
        _execute_aave_for_proposal(proposal, db_session)

    assert proposal.execution_attempts == 2
    assert proposal.status == "failed"

    # 3回目: dead-letter (attempts=2 < MAX=3, なのでまだ Aave を試行)
    proposal.status = "approved"
    with (
        patch("app.proposals.router._notify_aave_failure"),
        patch("app.proposals.router._record_failed_transaction"),
        patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
            side_effect=RuntimeError("transient"),
        ),
    ):
        _execute_aave_for_proposal(proposal, db_session)

    assert proposal.execution_attempts == MAX_EXECUTION_ATTEMPTS
    assert proposal.status == "failed"

    # 4回目: attempts=MAX → dead-letter（Aave 呼び出しなし）
    proposal.status = "approved"
    with (
        patch("app.proposals.router._notify_aave_failure") as mock_notify,
        patch("app.aave.service.MultiChainAaveService.execute_rebalance") as mock_exec,
    ):
        _execute_aave_for_proposal(proposal, db_session)

    assert proposal.status == "failed"
    assert "dead-lettered" in (proposal.error_message or "")
    mock_exec.assert_not_called()
    mock_notify.assert_called_once()
    # attempts は変わらない（dead-letter フローでは加算しない）
    assert proposal.execution_attempts == MAX_EXECUTION_ATTEMPTS


# ---------------------------------------------------------------------------
# ai_judgment_scheduler: 既存 pending があれば新規作成しない
# ---------------------------------------------------------------------------


def test_scheduler_skips_user_with_existing_pending_proposal(db_session: Session) -> None:
    """ユーザーに pending 提案が既存の場合、新規提案を作成しない。"""

    from app.auth.constants import ExecutionPolicy
    from app.auth.models import User
    from app.automation.ai_judgment_scheduler import _create_proposals_for_users

    # アクティブユーザー作成
    user = User(
        email="test@example.com",
        username="testuser",
        hashed_password="hashed",
        is_active=True,
        role="viewer",
        execution_policy=ExecutionPolicy.REQUIRE_APPROVAL.value,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    # 既存 pending 提案を挿入
    existing = Proposal(
        user_id=user.id,
        operation="SUPPLY",
        asset="USDC",
        amount=Decimal("100.000000000000000000"),
        amount_usd=Decimal("100.00"),
        reason="existing",
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(existing)
    db_session.commit()

    # AI decision モック
    decision = MagicMock()
    decision.id = 1

    result = MagicMock()
    from app.ai.schemas import TradeAction

    result.final_action = TradeAction.BUY
    result.final_reason = "test"
    result.final_confidence = 80

    # _resolve_proposal_amount と calculate_fee_by_market をモック
    with (
        patch(
            "app.automation.ai_judgment_scheduler._resolve_proposal_amount",
            return_value=Decimal("100"),
        ),
        patch(
            "app.automation.ai_judgment_scheduler._is_user_due_for_judgment",
            return_value=True,
        ),
        patch(
            "app.fees.trade_gate.calculate_fee_by_market",
        ) as mock_fee,
    ):
        mock_fee.return_value = MagicMock(
            should_trade=True, fee_rate=Decimal("0"), fee_amount=Decimal("0")
        )
        count = _create_proposals_for_users(db_session, decision, result)

    # 既存 pending があるので作成されない
    assert count == 0

    # DB の提案数は 1 のまま（新規作成されていない）
    from sqlalchemy import func as sqla_func  # noqa: PLC0415

    total = db_session.scalar(
        select(sqla_func.count(Proposal.id)).where(Proposal.user_id == user.id)
    )
    assert total == 1
