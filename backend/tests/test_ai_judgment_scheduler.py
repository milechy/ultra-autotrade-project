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
from app.auth.models import InvestmentTier, User  # noqa: E402
from app.automation.ai_judgment_scheduler import (  # noqa: E402
    _get_tier_interval_hours,
    _is_user_due_for_judgment,
    ai_judgment_loop,
    get_scheduler_status,
    run_ai_judgment_job,
    save_ai_decision,
)
from app.database import Base  # noqa: E402
from app.partner.allocation_models import FundAllocation  # noqa: E402
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


def _add_active_user(
    session,
    email: str = "user@example.com",
    execution_policy: str = "require_approval",
) -> User:
    """アクティブなテストユーザーを追加するヘルパー。"""
    user = User(
        email=email,
        username=email.split("@")[0],
        hashed_password="hashed",
        is_active=True,
        execution_policy=execution_policy,
    )
    session.add(user)
    session.flush()
    return user


def _add_fund_allocation(
    session,
    user: User,
    allocated_usd: Decimal = Decimal("10000"),
    partner_id: "int | None" = None,
) -> FundAllocation:
    """テストユーザー用の fund_allocations を追加するヘルパー。
    allocated_usd=$10,000, ratio=10% → proposal_amount=$1,000 (既存アサーションと一致)。
    """
    pid = partner_id if partner_id is not None else user.id
    alloc = FundAllocation(
        partner_id=pid,
        tester_name=f"test-{user.email}",
        tester_user_id=user.id,
        allocated_amount_usd=allocated_usd,
        status="active",
    )
    session.add(alloc)
    session.flush()
    return alloc


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


def test_save_ai_decision_with_rag_context_persists(db_session):
    """save_ai_decision が rag_context を rag_context_json に保存すること。"""
    from app.ai.schemas import RAGContext  # noqa: PLC0415

    result = _make_cross_validation_result(TradeAction.HOLD)
    rag_ctx = RAGContext(chunks=["chunk A", "chunk B"], query="btc", source_count=2)
    decision = save_ai_decision(db_session, result, "test query", rag_context=rag_ctx)
    db_session.commit()

    assert decision.rag_context_json is not None
    assert decision.rag_context_json["chunks"] == ["chunk A", "chunk B"]
    assert decision.rag_context_json["source_count"] == 2


def test_save_ai_decision_without_rag_context_saves_null(db_session):
    """save_ai_decision が rag_context=None の場合 rag_context_json=None を保存すること。"""
    result = _make_cross_validation_result(TradeAction.HOLD)
    decision = save_ai_decision(db_session, result, "test query")
    db_session.commit()

    assert decision.rag_context_json is None


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
    u1 = _add_active_user(db_session, "user1@example.com")
    u2 = _add_active_user(db_session, "user2@example.com")
    _add_fund_allocation(db_session, u1)
    _add_fund_allocation(db_session, u2)
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
    seller = _add_active_user(db_session, "seller@example.com")
    _add_fund_allocation(db_session, seller)
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


# ---------------------------------------------------------------------------
# execution_policy フィルタリングのテスト
# ---------------------------------------------------------------------------


def test_buy_creates_proposal_only_for_require_approval_users(db_session):
    """BUY 判定時、execution_policy='require_approval' のユーザーのみ Proposal が作成されること。"""
    approval_user = _add_active_user(
        db_session, "approval@example.com", execution_policy="require_approval"
    )
    _add_active_user(db_session, "auto@example.com", execution_policy="auto_execute")
    _add_active_user(db_session, "proposal@example.com", execution_policy="proposal_only")
    _add_fund_allocation(db_session, approval_user)
    db_session.commit()

    mock_result = _make_cross_validation_result(TradeAction.BUY)

    with (
        patch("app.automation.ai_judgment_scheduler.AIService") as MockAIService,
        patch("app.automation.ai_judgment_scheduler.KnowledgeService") as MockKnowledgeService,
    ):
        MockAIService.return_value.judge_with_rag.return_value = mock_result
        MockKnowledgeService.return_value.search.return_value = []

        result = run_ai_judgment_job(db=db_session)

    assert result["proposals_created"] == 1
    proposals = db_session.scalars(select(Proposal)).all()
    assert len(proposals) == 1
    assert proposals[0].user_id is not None


def test_auto_execute_user_gets_no_proposal_on_buy(db_session):
    """auto_execute ユーザーには BUY 判定でも Proposal が作成されないこと。"""
    _add_active_user(db_session, "auto@example.com", execution_policy="auto_execute")
    db_session.commit()

    mock_result = _make_cross_validation_result(TradeAction.BUY)

    with (
        patch("app.automation.ai_judgment_scheduler.AIService") as MockAIService,
        patch("app.automation.ai_judgment_scheduler.KnowledgeService") as MockKnowledgeService,
    ):
        MockAIService.return_value.judge_with_rag.return_value = mock_result
        MockKnowledgeService.return_value.search.return_value = []

        result = run_ai_judgment_job(db=db_session)

    assert result["proposals_created"] == 0
    proposals = db_session.scalars(select(Proposal)).all()
    assert len(proposals) == 0


# ---------------------------------------------------------------------------
# ティア別間隔のテスト（B-4）
# ---------------------------------------------------------------------------


def test_get_tier_interval_hours_upper_default():
    """UPPER ティアのデフォルト間隔は 4 時間であること。"""
    assert _get_tier_interval_hours(InvestmentTier.UPPER.value) == 4


def test_get_tier_interval_hours_general_default():
    """GENERAL ティアのデフォルト間隔は 8 時間であること。"""
    assert _get_tier_interval_hours(InvestmentTier.GENERAL.value) == 8


def test_get_tier_interval_hours_env_override(monkeypatch):
    """環境変数で間隔を上書きできること。"""
    monkeypatch.setenv("AI_JUDGMENT_INTERVAL_HOURS_UPPER", "6")
    monkeypatch.setenv("AI_JUDGMENT_INTERVAL_HOURS_GENERAL", "12")
    assert _get_tier_interval_hours(InvestmentTier.UPPER.value) == 6
    assert _get_tier_interval_hours(InvestmentTier.GENERAL.value) == 12


def test_is_user_due_first_time():
    """last_judgment_at が None のユーザーは常に判定対象。"""
    from datetime import datetime, timezone  # noqa: PLC0415

    user = User(
        email="first@example.com",
        username="first",
        hashed_password="x",
        tier=InvestmentTier.GENERAL.value,
        last_judgment_at=None,
    )
    now = datetime.now(timezone.utc)
    assert _is_user_due_for_judgment(user, now) is True


def test_is_user_due_upper_within_interval():
    """UPPER ユーザーが 4 時間未満の場合はスキップ。"""
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    now = datetime.now(timezone.utc)
    user = User(
        email="upper@example.com",
        username="upper",
        hashed_password="x",
        tier=InvestmentTier.UPPER.value,
        last_judgment_at=now - timedelta(hours=3),
    )
    assert _is_user_due_for_judgment(user, now) is False


def test_is_user_due_upper_past_interval():
    """UPPER ユーザーが 4 時間以上経過した場合は判定対象。"""
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    now = datetime.now(timezone.utc)
    user = User(
        email="upper2@example.com",
        username="upper2",
        hashed_password="x",
        tier=InvestmentTier.UPPER.value,
        last_judgment_at=now - timedelta(hours=4, minutes=1),
    )
    assert _is_user_due_for_judgment(user, now) is True


def test_is_user_due_general_within_interval():
    """GENERAL ユーザーが 8 時間未満の場合はスキップ。"""
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    now = datetime.now(timezone.utc)
    user = User(
        email="general@example.com",
        username="general",
        hashed_password="x",
        tier=InvestmentTier.GENERAL.value,
        last_judgment_at=now - timedelta(hours=5),
    )
    assert _is_user_due_for_judgment(user, now) is False


def test_is_user_due_general_past_interval():
    """GENERAL ユーザーが 8 時間以上経過した場合は判定対象。"""
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    now = datetime.now(timezone.utc)
    user = User(
        email="general2@example.com",
        username="general2",
        hashed_password="x",
        tier=InvestmentTier.GENERAL.value,
        last_judgment_at=now - timedelta(hours=8, minutes=1),
    )
    assert _is_user_due_for_judgment(user, now) is True


def test_buy_skips_general_user_within_interval(db_session):
    """BUY 判定時、GENERAL ユーザーが 8 時間未満の場合は Proposal を作成しないこと。"""
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    recent = datetime.now(timezone.utc) - timedelta(hours=5)
    user = User(
        email="general_recent@example.com",
        username="general_recent",
        hashed_password="x",
        is_active=True,
        execution_policy="require_approval",
        tier=InvestmentTier.GENERAL.value,
        last_judgment_at=recent,
    )
    db_session.add(user)
    db_session.commit()

    mock_result = _make_cross_validation_result(TradeAction.BUY)

    with (
        patch("app.automation.ai_judgment_scheduler.AIService") as MockAIService,
        patch("app.automation.ai_judgment_scheduler.KnowledgeService") as MockKnowledgeService,
    ):
        MockAIService.return_value.judge_with_rag.return_value = mock_result
        MockKnowledgeService.return_value.search.return_value = []

        result = run_ai_judgment_job(db=db_session)

    assert result["proposals_created"] == 0


def test_buy_includes_upper_user_within_general_interval(db_session):
    """BUY 判定時、UPPER ユーザーは 4 時間経過で Proposal が作成されること。"""
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    past_4h = datetime.now(timezone.utc) - timedelta(hours=4, minutes=5)
    user = User(
        email="upper_due@example.com",
        username="upper_due",
        hashed_password="x",
        is_active=True,
        execution_policy="require_approval",
        tier=InvestmentTier.UPPER.value,
        last_judgment_at=past_4h,
    )
    db_session.add(user)
    db_session.flush()
    _add_fund_allocation(db_session, user)
    db_session.commit()

    mock_result = _make_cross_validation_result(TradeAction.BUY)

    with (
        patch("app.automation.ai_judgment_scheduler.AIService") as MockAIService,
        patch("app.automation.ai_judgment_scheduler.KnowledgeService") as MockKnowledgeService,
    ):
        MockAIService.return_value.judge_with_rag.return_value = mock_result
        MockKnowledgeService.return_value.search.return_value = []

        result = run_ai_judgment_job(db=db_session)

    assert result["proposals_created"] == 1


def test_buy_updates_last_judgment_at(db_session):
    """Proposal 作成後、ユーザーの last_judgment_at が更新されること。"""
    user = User(
        email="update_check@example.com",
        username="update_check",
        hashed_password="x",
        is_active=True,
        execution_policy="require_approval",
        tier=InvestmentTier.UPPER.value,
        last_judgment_at=None,
    )
    db_session.add(user)
    db_session.flush()
    _add_fund_allocation(db_session, user)
    db_session.commit()

    mock_result = _make_cross_validation_result(TradeAction.BUY)

    with (
        patch("app.automation.ai_judgment_scheduler.AIService") as MockAIService,
        patch("app.automation.ai_judgment_scheduler.KnowledgeService") as MockKnowledgeService,
    ):
        MockAIService.return_value.judge_with_rag.return_value = mock_result
        MockKnowledgeService.return_value.search.return_value = []

        run_ai_judgment_job(db=db_session)

    db_session.refresh(user)
    assert user.last_judgment_at is not None


# ---------------------------------------------------------------------------
# F-6: tier 正規化のテスト
# ---------------------------------------------------------------------------


def test_create_proposals_uses_normalized_tier(db_session):
    """``user.tier`` が calculate_fee_by_market に渡される際 normalize_tier 経由になっていること。

    GENERAL ユーザーは LEGACY_TIER_MAP で LOWER に正規化されるため、
    呼び出し時の tier 引数は "LOWER" になる。
    """
    user = User(
        email="legacy_general@example.com",
        username="legacy_general",
        hashed_password="x",
        is_active=True,
        execution_policy="require_approval",
        tier=InvestmentTier.GENERAL.value,
        last_judgment_at=None,
    )
    db_session.add(user)
    db_session.flush()
    _add_fund_allocation(db_session, user)
    db_session.commit()

    mock_result = _make_cross_validation_result(TradeAction.BUY)

    with (
        patch("app.automation.ai_judgment_scheduler.AIService") as MockAIService,
        patch("app.automation.ai_judgment_scheduler.KnowledgeService") as MockKnowledgeService,
        patch("app.fees.trade_gate.calculate_fee_by_market") as mock_fee,
    ):
        MockAIService.return_value.judge_with_rag.return_value = mock_result
        MockKnowledgeService.return_value.search.return_value = []
        mock_fee.return_value.should_trade = True
        mock_fee.return_value.fee_rate = Decimal("0.05")
        mock_fee.return_value.fee_amount = Decimal("5.00")

        run_ai_judgment_job(db=db_session)

    assert mock_fee.call_count == 1
    call_kwargs = mock_fee.call_args.kwargs
    assert call_kwargs["tier"] == InvestmentTier.LOWER.value, (
        f"GENERAL は LOWER に正規化されるべきだが {call_kwargs['tier']!r} が渡された"
    )


# ---------------------------------------------------------------------------
# P0 Aave 注入 + cognitive_state 連携 (Asana 1214279097935851)
# ---------------------------------------------------------------------------


def test_run_ai_judgment_job_passes_aave_data(db_session):
    """fetch_aave_market_data_safe の戻り値が build_market_context に kwargs として渡ること。"""
    fake_aave = {
        "utilization_rate": Decimal("0.85"),
        "supply_apy": Decimal("4.2"),
        "borrow_apy": Decimal("5.8"),
        "health_factor": Decimal("2.1"),
    }
    mock_result = _make_cross_validation_result(TradeAction.HOLD)

    with (
        patch("app.automation.ai_judgment_scheduler.AIService") as MockAIService,
        patch("app.automation.ai_judgment_scheduler.KnowledgeService") as MockKnowledgeService,
        patch(
            "app.automation.ai_judgment_scheduler.fetch_aave_market_data_safe",
            return_value=fake_aave,
        ),
        patch("app.automation.ai_judgment_scheduler.build_market_context") as mock_build,
    ):
        MockAIService.return_value.judge_with_rag.return_value = mock_result
        MockKnowledgeService.return_value.search.return_value = []

        run_ai_judgment_job(db=db_session)

    call_kwargs = mock_build.call_args.kwargs
    assert call_kwargs["aave_utilization_rate"] == Decimal("0.85")
    assert call_kwargs["aave_supply_apy"] == Decimal("4.2")
    assert call_kwargs["aave_borrow_apy"] == Decimal("5.8")
    assert call_kwargs["health_factor"] == Decimal("2.1")


def test_run_ai_judgment_job_aave_failure_falls_back_to_none(db_session):
    """Aave 取得失敗時、全フィールド None で MarketContext が構築され job が継続すること。"""
    fake_aave = {
        "utilization_rate": None,
        "supply_apy": None,
        "borrow_apy": None,
        "health_factor": None,
    }
    mock_result = _make_cross_validation_result(TradeAction.HOLD)

    with (
        patch("app.automation.ai_judgment_scheduler.AIService") as MockAIService,
        patch("app.automation.ai_judgment_scheduler.KnowledgeService") as MockKnowledgeService,
        patch(
            "app.automation.ai_judgment_scheduler.fetch_aave_market_data_safe",
            return_value=fake_aave,
        ),
        patch("app.automation.ai_judgment_scheduler.build_market_context") as mock_build,
    ):
        MockAIService.return_value.judge_with_rag.return_value = mock_result
        MockKnowledgeService.return_value.search.return_value = []

        result = run_ai_judgment_job(db=db_session)

    # Job は完走すること (HOLD path 後方互換)
    assert result["action"] == "HOLD"
    assert result["decision_id"] is not None

    # 全フィールド None でも build_market_context は呼ばれる
    call_kwargs = mock_build.call_args.kwargs
    assert call_kwargs["aave_utilization_rate"] is None
    assert call_kwargs["aave_supply_apy"] is None
    assert call_kwargs["aave_borrow_apy"] is None
    assert call_kwargs["health_factor"] is None


def test_run_ai_judgment_job_passes_cognitive_state(db_session):
    """get_judgment_logger().get_cognitive_state() の戻り値が build_market_context に渡ること。"""
    from app.ai.judgment_log import CognitiveState  # noqa: PLC0415

    fake_state = CognitiveState(
        recent_actions=["HOLD", "HOLD", "HOLD"],
        recent_confidences=[55, 58, 60],
        last_action="HOLD",
        last_confidence=60,
        last_reason="待機継続",
        consecutive_holds=3,
        total_judgments=10,
    )
    mock_result = _make_cross_validation_result(TradeAction.HOLD)

    with (
        patch("app.automation.ai_judgment_scheduler.AIService") as MockAIService,
        patch("app.automation.ai_judgment_scheduler.KnowledgeService") as MockKnowledgeService,
        patch(
            "app.automation.ai_judgment_scheduler.fetch_aave_market_data_safe",
            return_value={
                "utilization_rate": None,
                "supply_apy": None,
                "borrow_apy": None,
                "health_factor": None,
            },
        ),
        patch("app.automation.ai_judgment_scheduler.get_judgment_logger") as mock_logger_factory,
        patch("app.automation.ai_judgment_scheduler.build_market_context") as mock_build,
    ):
        MockAIService.return_value.judge_with_rag.return_value = mock_result
        MockKnowledgeService.return_value.search.return_value = []
        mock_logger_factory.return_value.get_cognitive_state.return_value = fake_state

        run_ai_judgment_job(db=db_session)

    call_kwargs = mock_build.call_args.kwargs
    passed_state = call_kwargs["cognitive_state"]
    assert passed_state is fake_state
    assert passed_state.consecutive_holds == 3
    assert passed_state.total_judgments == 10
