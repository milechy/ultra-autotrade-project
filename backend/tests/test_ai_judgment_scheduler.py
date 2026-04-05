# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_ai_judgment_scheduler.py
"""AI判定スケジューラーのテスト。"""

import asyncio
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
    ai_judgment_loop,
    get_scheduler_status,
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


def test_run_job_passes_market_context_to_judge_with_rag(db_session):
    """run_ai_judgment_job が market_context を judge_with_rag に渡すこと。"""
    from unittest.mock import MagicMock  # noqa: PLC0415

    mock_result = _make_cross_validation_result(TradeAction.HOLD)
    mock_market_ctx = MagicMock()

    with (
        patch("app.automation.ai_judgment_scheduler.AIService") as MockAIService,
        patch("app.automation.ai_judgment_scheduler.KnowledgeService") as MockKnowledgeService,
        patch(
            "app.automation.ai_judgment_scheduler.build_market_context",
            return_value=mock_market_ctx,
        ),
    ):
        MockAIService.return_value.judge_with_rag.return_value = mock_result
        MockKnowledgeService.return_value.search.return_value = []

        run_ai_judgment_job(db=db_session)

    call_kwargs = MockAIService.return_value.judge_with_rag.call_args
    assert call_kwargs.kwargs.get("market_context") is mock_market_ctx


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


# ---------------------------------------------------------------------------
# ai_judgment_loop のテスト
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scheduler_runs_immediately_on_start():
    """起動直後（interval sleep前）にrun_ai_judgment_jobが呼ばれること。"""
    call_order: list[tuple] = []

    async def fake_sleep(seconds: float) -> None:
        call_order.append(("sleep", seconds))
        if seconds > 0:
            raise asyncio.CancelledError  # stop the loop after first interval sleep

    def fake_run_job() -> dict:
        call_order.append(("job",))
        return {"action": "HOLD", "confidence": 70, "proposals_created": 0, "decision_id": 1}

    with (
        patch("app.automation.ai_judgment_scheduler.run_ai_judgment_job", side_effect=fake_run_job),
        patch("asyncio.sleep", side_effect=fake_sleep),
    ):
        try:
            await ai_judgment_loop(interval_hours=1)
        except asyncio.CancelledError:
            pass

    # The job must have been called before the long sleep
    assert ("job",) in call_order
    # The first non-zero sleep should come AFTER the job
    first_job_idx = call_order.index(("job",))
    first_long_sleep_idx = next(
        i for i, item in enumerate(call_order) if item[0] == "sleep" and item[1] > 0
    )
    assert first_job_idx < first_long_sleep_idx


@pytest.mark.asyncio
async def test_scheduler_repeats_after_interval():
    """初回実行後にinterval_hours間隔で繰り返すこと。"""
    job_call_count = 0
    sleep_call_count = 0

    async def fake_sleep(seconds: float) -> None:
        nonlocal sleep_call_count
        sleep_call_count += 1
        if sleep_call_count >= 3:  # stop after 3rd sleep (0 + interval + interval)
            raise asyncio.CancelledError

    def fake_run_job() -> dict:
        nonlocal job_call_count
        job_call_count += 1
        return {
            "action": "HOLD",
            "confidence": 70,
            "proposals_created": 0,
            "decision_id": job_call_count,
        }

    with (
        patch("app.automation.ai_judgment_scheduler.run_ai_judgment_job", side_effect=fake_run_job),
        patch("asyncio.sleep", side_effect=fake_sleep),
    ):
        try:
            await ai_judgment_loop(interval_hours=1)
        except asyncio.CancelledError:
            pass

    assert job_call_count >= 2  # ran at least twice


# ---------------------------------------------------------------------------
# get_scheduler_status のテスト
# ---------------------------------------------------------------------------


def test_get_scheduler_status_has_last_error_key():
    """get_scheduler_status が last_error キーを含むこと。"""
    status = get_scheduler_status()
    assert "last_error" in status


# ---------------------------------------------------------------------------
# ai_judgment_loop の on_error コールバックテスト
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scheduler_calls_on_error_on_failure():
    """AI判定が失敗した場合、on_error コールバックが呼ばれること。"""
    import app.automation.ai_judgment_scheduler as sched_module

    errors_received: list[Exception] = []

    def fake_on_error(exc: Exception) -> None:
        errors_received.append(exc)

    sleep_call_count = 0

    async def fake_sleep(seconds: float) -> None:
        nonlocal sleep_call_count
        sleep_call_count += 1
        if sleep_call_count >= 2:
            raise asyncio.CancelledError

    def failing_job() -> dict:
        raise RuntimeError("fake AI failure")

    # Reset state before test
    sched_module._last_error_msg = None

    with (
        patch("app.automation.ai_judgment_scheduler.run_ai_judgment_job", side_effect=failing_job),
        patch("asyncio.sleep", side_effect=fake_sleep),
    ):
        try:
            await ai_judgment_loop(interval_hours=1, on_error=fake_on_error)
        except asyncio.CancelledError:
            pass

    assert len(errors_received) >= 1
    assert isinstance(errors_received[0], RuntimeError)
    assert sched_module._last_error_msg is not None
    assert "RuntimeError" in sched_module._last_error_msg


@pytest.mark.asyncio
async def test_scheduler_clears_error_on_success():
    """成功時に _last_error_msg が None にリセットされること。"""
    import app.automation.ai_judgment_scheduler as sched_module

    sched_module._last_error_msg = "previous error"
    sleep_call_count = 0

    async def fake_sleep(seconds: float) -> None:
        nonlocal sleep_call_count
        sleep_call_count += 1
        if sleep_call_count >= 2:
            raise asyncio.CancelledError

    def success_job() -> dict:
        return {"action": "HOLD", "confidence": 70, "proposals_created": 0, "decision_id": 1}

    with (
        patch("app.automation.ai_judgment_scheduler.run_ai_judgment_job", side_effect=success_job),
        patch("asyncio.sleep", side_effect=fake_sleep),
    ):
        try:
            await ai_judgment_loop(interval_hours=1)
        except asyncio.CancelledError:
            pass

    assert sched_module._last_error_msg is None


@pytest.mark.asyncio
async def test_scheduler_on_error_failure_does_not_crash_loop():
    """on_error コールバック自体が例外を投げても、ループが継続すること。"""
    job_call_count = 0
    sleep_call_count = 0

    async def fake_sleep(seconds: float) -> None:
        nonlocal sleep_call_count
        sleep_call_count += 1
        if sleep_call_count >= 4:
            raise asyncio.CancelledError

    def failing_job() -> dict:
        nonlocal job_call_count
        job_call_count += 1
        raise RuntimeError("job error")

    def bad_callback(exc: Exception) -> None:
        raise ValueError("callback also fails")

    with (
        patch("app.automation.ai_judgment_scheduler.run_ai_judgment_job", side_effect=failing_job),
        patch("asyncio.sleep", side_effect=fake_sleep),
    ):
        try:
            await ai_judgment_loop(interval_hours=1, on_error=bad_callback)
        except asyncio.CancelledError:
            pass

    # Loop continued despite callback failure
    assert job_call_count >= 2


# ---------------------------------------------------------------------------
# Fix 1: build_market_context() fault tolerance
# ---------------------------------------------------------------------------


def test_run_job_continues_when_build_market_context_fails(db_session):
    """build_market_context() が例外を投げても AI 判定が実行されること。"""
    mock_result = _make_cross_validation_result(TradeAction.HOLD)

    with (
        patch("app.automation.ai_judgment_scheduler.AIService") as MockAIService,
        patch("app.automation.ai_judgment_scheduler.KnowledgeService") as MockKnowledgeService,
        patch(
            "app.automation.ai_judgment_scheduler.build_market_context",
            side_effect=RuntimeError("geo feed down"),
        ),
    ):
        MockAIService.return_value.judge_with_rag.return_value = mock_result
        MockKnowledgeService.return_value.search.return_value = []

        result = run_ai_judgment_job(db=db_session)

    # Job must still succeed with degraded context
    assert result["action"] == "HOLD"
    assert result["decision_id"] is not None

    # judge_with_rag must have been called with degraded dict context
    call_kwargs = MockAIService.return_value.judge_with_rag.call_args
    market_context_arg = call_kwargs.kwargs.get("market_context")
    assert isinstance(market_context_arg, dict)
    assert market_context_arg.get("degraded") is True
    assert "geo feed down" in market_context_arg.get("reason", "")


def test_run_job_degraded_context_has_required_keys(db_session):
    """降格コンテキストが geopolitical_events と market_data キーを持つこと。"""
    mock_result = _make_cross_validation_result(TradeAction.HOLD)

    with (
        patch("app.automation.ai_judgment_scheduler.AIService") as MockAIService,
        patch("app.automation.ai_judgment_scheduler.KnowledgeService") as MockKnowledgeService,
        patch(
            "app.automation.ai_judgment_scheduler.build_market_context",
            side_effect=ConnectionError("network unreachable"),
        ),
    ):
        MockAIService.return_value.judge_with_rag.return_value = mock_result
        MockKnowledgeService.return_value.search.return_value = []

        run_ai_judgment_job(db=db_session)

    call_kwargs = MockAIService.return_value.judge_with_rag.call_args
    ctx = call_kwargs.kwargs.get("market_context")
    assert ctx["geopolitical_events"] == []
    assert ctx["market_data"] == {}
