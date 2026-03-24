# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_ai_judgment_scheduler.py
"""AI判定スケジューラーのテスト。"""

import os
import tempfile
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-ai-judgment-scheduler")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin@example.com")

from app.ai.models import AIDecision  # noqa: E402
from app.ai.schemas import (  # noqa: E402
    CrossValidationResult,
    LLMDecision,
    LLMProvider,
    TradeAction,
)
from app.auth.models import User  # noqa: E402
from app.automation.ai_judgment_scheduler import (  # noqa: E402
    run_ai_judgment_job,
    save_ai_decision,
)
from app.database import Base  # noqa: E402
from app.proposals.models import Proposal  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_db():
    """SQLite in-memory DB を使った一時セッションファクトリを提供するフィクスチャ。"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    yield TestSessionLocal
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


@pytest.fixture()
def db_session(test_db):
    """テスト用 DB セッションを提供し、テスト後にロールバックして閉じる。"""
    session = test_db()
    try:
        yield session
    finally:
        session.close()


def _make_cross_validation_result(action: TradeAction) -> CrossValidationResult:
    """テスト用の CrossValidationResult を生成するヘルパー。"""
    primary = LLMDecision(
        provider=LLMProvider.CLAUDE,
        action=action,
        confidence=80,
        reason="テスト判定",
    )
    return CrossValidationResult(
        primary=primary,
        secondary=None,
        agreed=True,
        final_action=action,
        final_confidence=80,
        final_reason="テスト判定理由",
    )


def _add_active_user(session, email: str = "user@example.com") -> User:
    """アクティブなテストユーザーを追加するヘルパー。"""
    user = User(
        email=email,
        username=email.split("@")[0],
        hashed_password="hashed",
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


# ---------------------------------------------------------------------------
# save_ai_decision のテスト
# ---------------------------------------------------------------------------


def test_save_ai_decision_creates_record(db_session):
    """save_ai_decision が ai_decisions に1件レコードを作成すること。"""
    result = _make_cross_validation_result(TradeAction.HOLD)
    decision = save_ai_decision(db_session, result, "test query")
    db_session.commit()

    assert decision.id is not None
    assert decision.action == "HOLD"
    assert decision.confidence == 80
    assert decision.query == "test query"
    assert decision.primary_provider == LLMProvider.CLAUDE.value
    assert decision.secondary_provider is None
    assert decision.agreed is True


# ---------------------------------------------------------------------------
# run_ai_judgment_job のテスト
# ---------------------------------------------------------------------------


def test_run_job_hold_no_proposals(db_session):
    """HOLD 判定のとき Proposal が作成されないこと。"""
    mock_result = _make_cross_validation_result(TradeAction.HOLD)

    with (
        patch("app.automation.ai_judgment_scheduler.AIService") as MockAIService,
        patch("app.automation.ai_judgment_scheduler.KnowledgeService") as MockKnowledgeService,
    ):
        MockAIService.return_value.judge_with_rag.return_value = mock_result
        MockKnowledgeService.return_value.search.return_value = []

        result = run_ai_judgment_job(db=db_session)

    assert result["action"] == "HOLD"
    assert result["proposals_created"] == 0
    assert result["decision_id"] is not None

    proposals = db_session.scalars(select(Proposal)).all()
    assert len(proposals) == 0


def test_run_job_buy_creates_proposals(db_session):
    """BUY 判定のとき、アクティブユーザー数分の Proposal が作成されること。"""
    _add_active_user(db_session, "user1@example.com")
    _add_active_user(db_session, "user2@example.com")
    db_session.commit()

    mock_result = _make_cross_validation_result(TradeAction.BUY)

    with (
        patch("app.automation.ai_judgment_scheduler.AIService") as MockAIService,
        patch("app.automation.ai_judgment_scheduler.KnowledgeService") as MockKnowledgeService,
    ):
        MockAIService.return_value.judge_with_rag.return_value = mock_result
        MockKnowledgeService.return_value.search.return_value = []

        result = run_ai_judgment_job(db=db_session)

    assert result["action"] == "BUY"
    assert result["proposals_created"] == 2

    proposals = db_session.scalars(select(Proposal)).all()
    assert len(proposals) == 2
    for p in proposals:
        assert p.operation == "SUPPLY"
        assert p.asset == "USDC"
        assert p.amount == Decimal("1000")
        assert p.amount_usd == Decimal("1000.00")


def test_run_job_saves_to_ai_decisions(db_session):
    """run_ai_judgment_job 実行後、ai_decisions に1件保存されること。"""
    mock_result = _make_cross_validation_result(TradeAction.HOLD)

    with (
        patch("app.automation.ai_judgment_scheduler.AIService") as MockAIService,
        patch("app.automation.ai_judgment_scheduler.KnowledgeService") as MockKnowledgeService,
    ):
        MockAIService.return_value.judge_with_rag.return_value = mock_result
        MockKnowledgeService.return_value.search.return_value = []

        run_ai_judgment_job(db=db_session)

    decisions = db_session.scalars(select(AIDecision)).all()
    assert len(decisions) == 1
    assert decisions[0].action == "HOLD"
    assert decisions[0].confidence == 80


def test_run_job_sell_creates_withdraw_proposals(db_session):
    """SELL 判定のとき、operation='WITHDRAW' の Proposal が作成されること。"""
    _add_active_user(db_session, "seller@example.com")
    db_session.commit()

    mock_result = _make_cross_validation_result(TradeAction.SELL)

    with (
        patch("app.automation.ai_judgment_scheduler.AIService") as MockAIService,
        patch("app.automation.ai_judgment_scheduler.KnowledgeService") as MockKnowledgeService,
    ):
        MockAIService.return_value.judge_with_rag.return_value = mock_result
        MockKnowledgeService.return_value.search.return_value = []

        result = run_ai_judgment_job(db=db_session)

    assert result["action"] == "SELL"
    assert result["proposals_created"] == 1

    proposals = db_session.scalars(select(Proposal)).all()
    assert len(proposals) == 1
    assert proposals[0].operation == "WITHDRAW"
