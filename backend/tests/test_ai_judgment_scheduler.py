# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_ai_judgment_scheduler.py
"""AI判定スケジューラーのテスト。"""

import asyncio
import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

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


def _add_executed_proposal(
    session,
    user: User,
    amount_usd: Decimal,
    operation: str = "SUPPLY",
) -> Proposal:
    """遊休額 (idle capital) テスト用: 実行済み (status='executed') の提案を1件追加する。"""
    proposal = Proposal(
        user_id=user.id,
        operation=operation,
        asset="USDC",
        protocol="aave",
        amount=amount_usd,
        amount_usd=amount_usd,
        reason="test executed proposal",
        status="executed",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    session.add(proposal)
    session.flush()
    return proposal


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
        assert p.estimated_gas_usd is not None
        assert p.estimated_gas_usd > Decimal("0")


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
    assert proposals[0].estimated_gas_usd is not None
    assert proposals[0].estimated_gas_usd > Decimal("0")


# ---------------------------------------------------------------------------
# ai_judgment_loop のテスト
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scheduler_runs_after_startup_delay_then_interval():
    """startup_delay_sec=0 の場合、delay sleep なしで job が実行され、その後 interval sleep が来ること。"""
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
            await ai_judgment_loop(interval_hours=1, startup_delay_sec=0)
        except asyncio.CancelledError:
            pass

    # The job must have been called before the long interval sleep
    assert ("job",) in call_order
    # The first non-zero sleep should come AFTER the job (interval sleep, not startup delay)
    first_job_idx = call_order.index(("job",))
    first_long_sleep_idx = next(
        i for i, item in enumerate(call_order) if item[0] == "sleep" and item[1] > 0
    )
    assert first_job_idx < first_long_sleep_idx


@pytest.mark.asyncio
async def test_scheduler_startup_delay_fires_before_job():
    """startup_delay_sec > 0 の場合、delay sleep が job より先に来ること (P3-5)。"""
    call_order: list[tuple] = []
    startup_delay = 300

    async def fake_sleep(seconds: float) -> None:
        call_order.append(("sleep", seconds))
        if seconds == startup_delay:
            return  # startup delay: continue past it
        if seconds > 0:
            raise asyncio.CancelledError  # stop after interval sleep

    def fake_run_job() -> dict:
        call_order.append(("job",))
        return {"action": "HOLD", "confidence": 70, "proposals_created": 0, "decision_id": 1}

    with (
        patch("app.automation.ai_judgment_scheduler.run_ai_judgment_job", side_effect=fake_run_job),
        patch("asyncio.sleep", side_effect=fake_sleep),
    ):
        try:
            await ai_judgment_loop(interval_hours=1, startup_delay_sec=startup_delay)
        except asyncio.CancelledError:
            pass

    # startup delay sleep must come before the job
    assert ("sleep", startup_delay) in call_order
    assert ("job",) in call_order
    startup_sleep_idx = call_order.index(("sleep", startup_delay))
    first_job_idx = call_order.index(("job",))
    assert startup_sleep_idx < first_job_idx, (
        f"startup delay sleep (idx={startup_sleep_idx}) must precede first job (idx={first_job_idx})"
    )


@pytest.mark.asyncio
async def test_scheduler_startup_delay_zero_skips_delay():
    """startup_delay_sec=0 の場合、300秒 sleep が発生しないこと (P3-5)。"""
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        if seconds > 0:
            raise asyncio.CancelledError

    def fake_run_job() -> dict:
        return {"action": "HOLD", "confidence": 70, "proposals_created": 0, "decision_id": 1}

    with (
        patch("app.automation.ai_judgment_scheduler.run_ai_judgment_job", side_effect=fake_run_job),
        patch("asyncio.sleep", side_effect=fake_sleep),
    ):
        try:
            await ai_judgment_loop(interval_hours=1, startup_delay_sec=0)
        except asyncio.CancelledError:
            pass

    # No 300-second startup delay sleep should have been issued
    assert 300 not in sleep_calls, (
        f"startup_delay_sec=0 should not sleep 300s but got {sleep_calls}"
    )


@pytest.mark.asyncio
async def test_scheduler_repeats_after_interval():
    """初回実行後にinterval_hours間隔で繰り返すこと。"""
    job_call_count = 0
    sleep_call_count = 0

    async def fake_sleep(seconds: float) -> None:
        nonlocal sleep_call_count
        sleep_call_count += 1
        if sleep_call_count >= 3:  # stop after 3rd sleep (interval + interval + interval)
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
            # startup_delay_sec=0 to skip startup delay and focus on interval repetition
            await ai_judgment_loop(interval_hours=1, startup_delay_sec=0)
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
            await ai_judgment_loop(interval_hours=1, on_error=fake_on_error, startup_delay_sec=0)
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
            await ai_judgment_loop(interval_hours=1, startup_delay_sec=0)
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
            await ai_judgment_loop(interval_hours=1, on_error=bad_callback, startup_delay_sec=0)
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


def test_buy_creates_proposal_for_require_approval_and_auto_execute_users(db_session):
    """2026-07-16: BUY 判定時、execution_policy='require_approval'/'auto_execute' の
    両方に Proposal が作成されること（'proposal_only' は対象外のまま）。
    AUTO_EXECUTE ユーザーは委譲(SCW) grant を持たないため、提案は作られるが
    自動実行はされず 'pending' のまま残る（別テストで検証）。

    2026-08-06 PR6: 委譲枠を持たない AUTO_EXECUTE ユーザーは、提案生成前の
    不変条件チェックで require_approval へ**降格される**ようになった。このため
    同 tick 内では既に承認制ユーザーとして扱われ、auto_execute_skipped は
    加算されない（0 になる）。ユーザーから見た結果（提案が pending で残る）は同じ。
    """
    approval_user = _add_active_user(
        db_session, "approval@example.com", execution_policy="require_approval"
    )
    auto_user = _add_active_user(db_session, "auto@example.com", execution_policy="auto_execute")
    _add_active_user(db_session, "proposal@example.com", execution_policy="proposal_only")
    _add_fund_allocation(db_session, approval_user)
    _add_fund_allocation(db_session, auto_user)
    db_session.commit()

    mock_result = _make_cross_validation_result(TradeAction.BUY)

    with (
        patch("app.automation.ai_judgment_scheduler.AIService") as MockAIService,
        patch("app.automation.ai_judgment_scheduler.KnowledgeService") as MockKnowledgeService,
    ):
        MockAIService.return_value.judge_with_rag.return_value = mock_result
        MockKnowledgeService.return_value.search.return_value = []

        result = run_ai_judgment_job(db=db_session)

    assert result["proposals_created"] == 2
    proposals = db_session.scalars(select(Proposal)).all()
    assert len(proposals) == 2
    proposal_user_ids = {p.user_id for p in proposals}
    assert proposal_user_ids == {approval_user.id, auto_user.id}
    # 委譲grantが無いため auto-execution は skip（'pending' のまま・自動実行しない）。
    assert all(p.status == "pending" for p in proposals)
    assert result["auto_executed"] == 0
    # 2026-08-06 PR6: 降格により承認制ユーザー扱いになるため 0。
    assert result["auto_execute_skipped"] == 0


def test_auto_execute_user_without_grant_stays_pending_on_buy(db_session):
    """2026-07-16: auto_execute ユーザーは提案が作られるが、有効な委譲(SCW) grant が
    無い限り自動実行されず 'pending' のまま残る（既存の手動フローに委ねる）。

    2026-08-06 PR6: さらに、権限を持たないまま「完全おまかせ」を表示し続けるのは
    表示と実行能力の乖離なので、承認制へ降格し本人に通知するようになった。
    """
    auto_user = _add_active_user(db_session, "auto@example.com", execution_policy="auto_execute")
    _add_fund_allocation(db_session, auto_user)
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
    assert result["auto_executed"] == 0
    # 2026-08-06 PR6: 降格により、この tick では既に承認制ユーザー扱いになるため
    # auto_execute_skipped は加算されない。
    assert result["auto_execute_skipped"] == 0
    proposals = db_session.scalars(select(Proposal)).all()
    assert len(proposals) == 1
    assert proposals[0].status == "pending"
    # ★降格が実際に行われたこと（表示と実行能力の乖離が解消されたこと）
    db_session.refresh(auto_user)
    assert auto_user.execution_policy == "require_approval"


# ---------------------------------------------------------------------------
# ティア別間隔のテスト（B-4）
# ---------------------------------------------------------------------------


def test_get_tier_interval_hours_upper_default():
    """UPPER ティアのデフォルト間隔は 4 時間であること。"""
    assert _get_tier_interval_hours(InvestmentTier.UPPER.value) == 4


def test_get_tier_interval_hours_lower_default():
    """LOWER ティアのデフォルト間隔は 8 時間であること。"""
    assert _get_tier_interval_hours(InvestmentTier.LOWER.value) == 8


def test_get_tier_interval_hours_env_override(monkeypatch):
    """環境変数で間隔を上書きできること。"""
    monkeypatch.setenv("AI_JUDGMENT_INTERVAL_HOURS_UPPER", "6")
    monkeypatch.setenv("AI_JUDGMENT_INTERVAL_HOURS_LOWER", "12")
    assert _get_tier_interval_hours(InvestmentTier.UPPER.value) == 6
    assert _get_tier_interval_hours(InvestmentTier.LOWER.value) == 12


def test_is_user_due_first_time():
    """last_judgment_at が None のユーザーは常に判定対象。"""
    from datetime import datetime, timezone  # noqa: PLC0415

    user = User(
        email="first@example.com",
        username="first",
        hashed_password="x",
        tier=InvestmentTier.LOWER.value,
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


def test_is_user_due_lower_within_interval():
    """LOWER ユーザーが 8 時間未満の場合はスキップ。"""
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    now = datetime.now(timezone.utc)
    user = User(
        email="lower@example.com",
        username="lower",
        hashed_password="x",
        tier=InvestmentTier.LOWER.value,
        last_judgment_at=now - timedelta(hours=5),
    )
    assert _is_user_due_for_judgment(user, now) is False


def test_is_user_due_lower_past_interval():
    """LOWER ユーザーが 8 時間以上経過した場合は判定対象。"""
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    now = datetime.now(timezone.utc)
    user = User(
        email="lower2@example.com",
        username="lower2",
        hashed_password="x",
        tier=InvestmentTier.LOWER.value,
        last_judgment_at=now - timedelta(hours=8, minutes=1),
    )
    assert _is_user_due_for_judgment(user, now) is True


def test_buy_skips_lower_user_within_interval(db_session):
    """BUY 判定時、LOWER ユーザーが 8 時間未満の場合は Proposal を作成しないこと。"""
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    recent = datetime.now(timezone.utc) - timedelta(hours=5)
    user = User(
        email="lower_recent@example.com",
        username="lower_recent",
        hashed_password="x",
        is_active=True,
        execution_policy="require_approval",
        tier=InvestmentTier.LOWER.value,
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


def test_buy_includes_upper_user_within_lower_interval(db_session):
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


def test_stale_pending_does_not_permanently_block(db_session):
    """期限切れ(expires_at<now)なのに pending のまま残った提案が、新規提案を永久に
    ブロックしないこと (2026-07-08 自己修復)。

    proposal_timeout_loop が停止している環境 (DISABLE_BACKGROUND_MONITORING=1 の
    staging-v4 等) では期限切れ提案が pending のまま残り、重複ガードがそのユーザーへの
    新規提案を永久にブロックしていた (id 8 / user 10)。_create_proposals_for_users が
    重複判定の前に期限切れ pending を能動的に expired 化することで防ぐ。
    """
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    user = User(
        email="stale_pending@example.com",
        username="stale_pending",
        hashed_password="x",
        is_active=True,
        execution_policy="require_approval",
        tier=InvestmentTier.UPPER.value,
        last_judgment_at=None,
    )
    db_session.add(user)
    db_session.flush()
    _add_fund_allocation(db_session, user)

    # 期限切れ (2 日前) なのに pending のまま残っている既存提案
    stale = Proposal(
        user_id=user.id,
        operation="SUPPLY",
        asset="USDC",
        amount=Decimal("1000"),
        amount_usd=Decimal("1000"),
        reason="stale",
        status="pending",
        expires_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    db_session.add(stale)
    db_session.commit()

    mock_result = _make_cross_validation_result(TradeAction.BUY)
    with (
        patch("app.automation.ai_judgment_scheduler.AIService") as MockAIService,
        patch("app.automation.ai_judgment_scheduler.KnowledgeService") as MockKnowledgeService,
    ):
        MockAIService.return_value.judge_with_rag.return_value = mock_result
        MockKnowledgeService.return_value.search.return_value = []
        result = run_ai_judgment_job(db=db_session)

    # 期限切れ提案は expired 化され、新規提案が 1 件生成される
    assert result["proposals_created"] == 1
    db_session.refresh(stale)
    assert stale.status == "expired"


def test_fresh_pending_still_blocks_new_proposal(db_session):
    """期限内(expires_at>now)の pending 提案は従来どおり新規提案をブロックすること。

    自己修復 (期限切れ expire) が正常な重複ガードを壊していないことの退行防止。
    """
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    user = User(
        email="fresh_pending@example.com",
        username="fresh_pending",
        hashed_password="x",
        is_active=True,
        execution_policy="require_approval",
        tier=InvestmentTier.UPPER.value,
        last_judgment_at=None,
    )
    db_session.add(user)
    db_session.flush()
    _add_fund_allocation(db_session, user)

    # 期限内 (2 日後) の既存 pending 提案 → 従来どおりブロックされるべき
    fresh = Proposal(
        user_id=user.id,
        operation="SUPPLY",
        asset="USDC",
        amount=Decimal("1000"),
        amount_usd=Decimal("1000"),
        reason="fresh",
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(days=2),
    )
    db_session.add(fresh)
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
    db_session.refresh(fresh)
    assert fresh.status == "pending"


# ---------------------------------------------------------------------------
# F-6: tier 正規化のテスト
# ---------------------------------------------------------------------------


def test_create_proposals_uses_normalized_tier(db_session):
    """``user.tier`` が calculate_fee_by_market に渡される際 normalize_tier 経由になっていること。

    LOWER ユーザーは LEGACY_TIER_MAP で LOWER に正規化されるため、
    呼び出し時の tier 引数は "LOWER" になる。
    """
    user = User(
        email="legacy_lower@example.com",
        username="legacy_lower",
        hashed_password="x",
        is_active=True,
        execution_policy="require_approval",
        tier=InvestmentTier.LOWER.value,
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
        f"LOWER は LOWER に正規化されるべきだが {call_kwargs['tier']!r} が渡された"
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


# ---------------------------------------------------------------------------
# GHO 借入シグナル Phase 1（観測のみ・fail-open）(2026-07-03)
# ---------------------------------------------------------------------------


def _base_aave_kwargs():
    return {
        "utilization_rate": Decimal("0.5"),
        "supply_apy": Decimal("3.0"),
        "borrow_apy": Decimal("5.0"),
        "health_factor": Decimal("2.0"),
    }


def test_gho_signal_passed_to_build_market_context_when_optimizer_recommends_gho(db_session):
    """optimizer が正常応答なら gho_borrow_signal が build_market_context に渡ること。"""
    from app.aave.schemas import BorrowRateComparison  # noqa: PLC0415

    mock_result = _make_cross_validation_result(TradeAction.HOLD)
    fake_cmp = BorrowRateComparison(
        usdc_apr=Decimal("0.05"),
        gho_variable_apr=Decimal("0.03"),
        gho_effective_apr=Decimal("0.03"),
        recommendation="GHO",
        annual_savings_usd=Decimal("100"),
        error=None,
    )
    mock_optimizer = MagicMock()
    mock_optimizer.compare_borrow_rates.return_value = fake_cmp

    with (
        patch("app.automation.ai_judgment_scheduler.AIService") as MockAIService,
        patch("app.automation.ai_judgment_scheduler.KnowledgeService") as MockKnowledgeService,
        patch(
            "app.automation.ai_judgment_scheduler.fetch_aave_market_data_safe",
            return_value=_base_aave_kwargs(),
        ),
        patch("app.automation.ai_judgment_scheduler.build_market_context") as mock_build,
        patch(
            "app.aave.borrow_optimizer.make_borrow_optimizer_from_env",
            return_value=mock_optimizer,
        ),
    ):
        MockAIService.return_value.judge_with_rag.return_value = mock_result
        MockKnowledgeService.return_value.search.return_value = []

        run_ai_judgment_job(db=db_session)

    call_kwargs = mock_build.call_args.kwargs
    assert call_kwargs["gho_borrow_signal"] == "recommend_gho"


def test_gho_signal_none_when_optimizer_not_configured(db_session):
    """make_borrow_optimizer_from_env が None（env未設定）→ gho_borrow_signal=None、job は継続。"""
    mock_result = _make_cross_validation_result(TradeAction.HOLD)

    with (
        patch("app.automation.ai_judgment_scheduler.AIService") as MockAIService,
        patch("app.automation.ai_judgment_scheduler.KnowledgeService") as MockKnowledgeService,
        patch(
            "app.automation.ai_judgment_scheduler.fetch_aave_market_data_safe",
            return_value=_base_aave_kwargs(),
        ),
        patch("app.automation.ai_judgment_scheduler.build_market_context") as mock_build,
        patch(
            "app.aave.borrow_optimizer.make_borrow_optimizer_from_env",
            return_value=None,
        ),
    ):
        MockAIService.return_value.judge_with_rag.return_value = mock_result
        MockKnowledgeService.return_value.search.return_value = []

        result = run_ai_judgment_job(db=db_session)

    assert result["action"] == "HOLD"
    call_kwargs = mock_build.call_args.kwargs
    assert call_kwargs["gho_borrow_signal"] is None


def test_gho_signal_none_when_compare_borrow_rates_raises(db_session):
    """optimizer.compare_borrow_rates が例外送出 → fail-open で None、
    かつ context_degraded を誤発火させず job が継続すること
    （GHO シグナル取得は独立 try/except で隔離されている）。"""
    mock_result = _make_cross_validation_result(TradeAction.HOLD)
    mock_optimizer = MagicMock()
    mock_optimizer.compare_borrow_rates.side_effect = RuntimeError("RPC down")

    with (
        patch("app.automation.ai_judgment_scheduler.AIService") as MockAIService,
        patch("app.automation.ai_judgment_scheduler.KnowledgeService") as MockKnowledgeService,
        patch(
            "app.automation.ai_judgment_scheduler.fetch_aave_market_data_safe",
            return_value=_base_aave_kwargs(),
        ),
        patch("app.automation.ai_judgment_scheduler.build_market_context") as mock_build,
        patch(
            "app.aave.borrow_optimizer.make_borrow_optimizer_from_env",
            return_value=mock_optimizer,
        ),
    ):
        MockAIService.return_value.judge_with_rag.return_value = mock_result
        MockKnowledgeService.return_value.search.return_value = []

        result = run_ai_judgment_job(db=db_session)

    # GHO シグナル取得失敗が context_degraded を誤発火させていないこと
    # （通常通り BUY/SELL/HOLD 判定が完走している）。
    assert result["action"] == "HOLD"
    assert result["decision_id"] is not None
    call_kwargs = mock_build.call_args.kwargs
    assert call_kwargs["gho_borrow_signal"] is None
    # 他の Aave フィールドは通常通り渡っている（GHO 失敗が波及していない）
    assert call_kwargs["health_factor"] == Decimal("2.0")


def test_gho_signal_none_when_comparison_has_error(db_session):
    """BorrowRateComparison.error が設定されている（optimizer内部fail-open）
    → borrow_currency_signal を呼ばず None のまま渡ること。"""
    from app.aave.schemas import BorrowRateComparison  # noqa: PLC0415

    mock_result = _make_cross_validation_result(TradeAction.HOLD)
    fake_cmp = BorrowRateComparison(
        usdc_apr=Decimal("0"),
        gho_variable_apr=Decimal("0"),
        gho_effective_apr=Decimal("0"),
        recommendation="USDC",
        annual_savings_usd=Decimal("0"),
        error="AAVE_DATA_PROVIDER_ADDRESS 等の環境変数が未設定です。",
    )
    mock_optimizer = MagicMock()
    mock_optimizer.compare_borrow_rates.return_value = fake_cmp

    with (
        patch("app.automation.ai_judgment_scheduler.AIService") as MockAIService,
        patch("app.automation.ai_judgment_scheduler.KnowledgeService") as MockKnowledgeService,
        patch(
            "app.automation.ai_judgment_scheduler.fetch_aave_market_data_safe",
            return_value=_base_aave_kwargs(),
        ),
        patch("app.automation.ai_judgment_scheduler.build_market_context") as mock_build,
        patch(
            "app.aave.borrow_optimizer.make_borrow_optimizer_from_env",
            return_value=mock_optimizer,
        ),
    ):
        MockAIService.return_value.judge_with_rag.return_value = mock_result
        MockKnowledgeService.return_value.search.return_value = []

        run_ai_judgment_job(db=db_session)

    call_kwargs = mock_build.call_args.kwargs
    assert call_kwargs["gho_borrow_signal"] is None


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


# ---------------------------------------------------------------------------
# _resolve_proposal_amount: min/max クランプ境界値テスト (PR #323 follow-up P1)
# ---------------------------------------------------------------------------


def test_resolve_proposal_amount_clamps_to_min(db_session):
    """allocated × 10% < $50 のとき、$50 にクランプされること。

    境界値: $499 × 10% = $49.90 → $50 (min)
    """
    from app.automation.ai_judgment_scheduler import _resolve_proposal_amount  # noqa: PLC0415

    user = _add_active_user(db_session, "clamp_min@example.com")
    _add_fund_allocation(db_session, user, allocated_usd=Decimal("499"))
    db_session.commit()

    result = _resolve_proposal_amount(db_session, user.id)
    assert result == Decimal("50"), f"expected $50 (min clamp) but got {result}"


def test_resolve_proposal_amount_clamps_to_max(db_session):
    """allocated × 10% > $2,000 のとき、$2,000 にクランプされること。

    境界値: $20001 × 10% = $2000.10 → $2000 (max)
    """
    from app.automation.ai_judgment_scheduler import _resolve_proposal_amount  # noqa: PLC0415

    user = _add_active_user(db_session, "clamp_max@example.com")
    _add_fund_allocation(db_session, user, allocated_usd=Decimal("20001"))
    db_session.commit()

    result = _resolve_proposal_amount(db_session, user.id)
    assert result == Decimal("2000"), f"expected $2000 (max clamp) but got {result}"


def test_resolve_proposal_amount_exact_min_boundary(db_session):
    """allocated × 10% = $50 ちょうどのとき、$50 が返ること（境界 = min の場合は min 返却）。

    $500 × 10% = $50.00
    """
    from app.automation.ai_judgment_scheduler import _resolve_proposal_amount  # noqa: PLC0415

    user = _add_active_user(db_session, "boundary_min@example.com")
    _add_fund_allocation(db_session, user, allocated_usd=Decimal("500"))
    db_session.commit()

    result = _resolve_proposal_amount(db_session, user.id)
    assert result == Decimal("50.00")


def test_resolve_proposal_amount_exact_max_boundary(db_session):
    """allocated × 10% = $2,000 ちょうどのとき、$2,000 が返ること（境界 = max の場合は max 返却）。

    $20000 × 10% = $2000.00
    """
    from app.automation.ai_judgment_scheduler import _resolve_proposal_amount  # noqa: PLC0415

    user = _add_active_user(db_session, "boundary_max@example.com")
    _add_fund_allocation(db_session, user, allocated_usd=Decimal("20000"))
    db_session.commit()

    result = _resolve_proposal_amount(db_session, user.id)
    assert result == Decimal("2000.00")


def test_resolve_proposal_amount_yamamoto_san(db_session):
    """山本さん想定値: $4,600 × 10% = $460 (クランプなし、実機確認済み)。"""
    from app.automation.ai_judgment_scheduler import _resolve_proposal_amount  # noqa: PLC0415

    user = _add_active_user(db_session, "yamamoto@example.com")
    _add_fund_allocation(db_session, user, allocated_usd=Decimal("4600"))
    db_session.commit()

    result = _resolve_proposal_amount(db_session, user.id)
    assert result == Decimal("460.00")


def test_resolve_proposal_amount_multiple_allocations_summed(db_session):
    """複数の active fund_allocations がある場合、合計値に比率を乗じること。

    allocation1: $3,000, allocation2: $2,000 → sum=$5,000 × 10% = $500
    """
    from app.automation.ai_judgment_scheduler import _resolve_proposal_amount  # noqa: PLC0415

    user = _add_active_user(db_session, "multi_alloc@example.com")
    _add_fund_allocation(db_session, user, allocated_usd=Decimal("3000"))
    _add_fund_allocation(db_session, user, allocated_usd=Decimal("2000"))
    db_session.commit()

    result = _resolve_proposal_amount(db_session, user.id)
    assert result == Decimal("500.00")


# ---------------------------------------------------------------------------
# _resolve_proposal_amount: wallet 残高 fallback (案C / docs/61)
# ---------------------------------------------------------------------------


def test_resolve_amount_wallet_fallback_uses_balance(db_session, monkeypatch):
    """allocation 不在 + wallet 設定済 → wallet USDC 残高 × 10% を使う。

    $1,000 残高 × 10% = $100。
    """
    import app.automation.ai_judgment_scheduler as sched  # noqa: PLC0415

    user = _add_active_user(db_session, "wallet_consumer@example.com")
    user.smart_wallet_address = "0x" + "a" * 40
    db_session.commit()

    monkeypatch.setattr(sched, "_read_wallet_usdc_balance", lambda _addr: Decimal("1000"))
    result = sched._resolve_proposal_amount(db_session, user.id)
    assert result == Decimal("100.00")


def test_resolve_amount_wallet_below_min_is_skipped(db_session, monkeypatch):
    """wallet 残高 × 10% が min ($50) 未満 → $0 で skip (切り上げない / 安全側)。

    $400 残高 × 10% = $40 < $50 → $0。
    """
    import app.automation.ai_judgment_scheduler as sched  # noqa: PLC0415

    user = _add_active_user(db_session, "wallet_small@example.com")
    user.wallet_address = "0x" + "b" * 40
    db_session.commit()

    monkeypatch.setattr(sched, "_read_wallet_usdc_balance", lambda _addr: Decimal("400"))
    result = sched._resolve_proposal_amount(db_session, user.id)
    assert result == Decimal("0")


def test_resolve_amount_wallet_clamps_to_max(db_session, monkeypatch):
    """wallet 残高 × 10% が max ($2,000) 超 → $2,000 にクランプ。

    $30,000 残高 × 10% = $3,000 → $2,000。
    """
    import app.automation.ai_judgment_scheduler as sched  # noqa: PLC0415

    user = _add_active_user(db_session, "wallet_big@example.com")
    user.smart_wallet_address = "0x" + "c" * 40
    db_session.commit()

    monkeypatch.setattr(sched, "_read_wallet_usdc_balance", lambda _addr: Decimal("30000"))
    result = sched._resolve_proposal_amount(db_session, user.id)
    assert result == Decimal("2000.00")


def test_resolve_amount_wallet_balance_unavailable_is_skipped(db_session, monkeypatch):
    """残高取得失敗 (None) / 残高0 → $0 で skip (誤った金額を捏造しない)。"""
    import app.automation.ai_judgment_scheduler as sched  # noqa: PLC0415

    user = _add_active_user(db_session, "wallet_rpcfail@example.com")
    user.smart_wallet_address = "0x" + "d" * 40
    db_session.commit()

    monkeypatch.setattr(sched, "_read_wallet_usdc_balance", lambda _addr: None)
    assert sched._resolve_proposal_amount(db_session, user.id) == Decimal("0")

    monkeypatch.setattr(sched, "_read_wallet_usdc_balance", lambda _addr: Decimal("0"))
    assert sched._resolve_proposal_amount(db_session, user.id) == Decimal("0")


def test_resolve_amount_allocation_takes_priority_for_custodial_user(db_session, monkeypatch):
    """SCW を持たない custodial ユーザーは allocation を優先 (既存パートナー互換)。

    allocation $10,000 → $1,000。wallet 残高は参照されない。
    """
    import app.automation.ai_judgment_scheduler as sched  # noqa: PLC0415

    user = _add_active_user(db_session, "both@example.com")
    user.wallet_address = "0x" + "e" * 40
    _add_fund_allocation(db_session, user, allocated_usd=Decimal("10000"))
    db_session.commit()

    def _should_not_be_called(_addr):
        raise AssertionError("wallet balance must not be read when allocation exists")

    monkeypatch.setattr(sched, "_read_wallet_usdc_balance", _should_not_be_called)
    assert sched._resolve_proposal_amount(db_session, user.id) == Decimal("1000.00")


def test_resolve_amount_scw_user_ignores_allocation(db_session, monkeypatch):
    """★SCW を持つユーザーは allocation(帳簿) でなく on-chain 実残高で sizing する。

    2026-08-06 に規則変更。`fund_allocations` は custodial プール持分の帳簿行であり
    オンチェーンの裏付けが無い。SCW 執行の分母に使うと実残高の何倍もの提案を作り、
    承認後に on-chain revert する（本番 user 11 が allocation $4,600 / SCW 残高 $0 の形
    だった）。ゲート側 `resolve_user_deposit_usd` と同一規則。
    """
    import app.automation.ai_judgment_scheduler as sched  # noqa: PLC0415

    scw = "0x" + "e" * 40
    user = _add_active_user(db_session, "scw-with-allocation@example.com")
    user.smart_wallet_address = scw
    _add_fund_allocation(db_session, user, allocated_usd=Decimal("10000"))
    db_session.commit()

    read: list[str] = []

    def _read(addr):
        read.append(addr)
        return Decimal("2000")

    monkeypatch.setattr(sched, "_read_wallet_usdc_balance", _read)
    # 帳簿 $10,000 の 10% = $1,000 ではなく、実残高 $2,000 の 10% = $200。
    assert sched._resolve_proposal_amount(db_session, user.id) == Decimal("200.00")
    assert read == [scw]


def test_resolve_amount_no_allocation_no_wallet_notifies_and_zero(db_session, monkeypatch):
    """allocation も wallet も無い → $0 + Slack 通知 (テスター登録漏れ検知を維持)。"""
    import app.automation.ai_judgment_scheduler as sched  # noqa: PLC0415

    user = _add_active_user(db_session, "nowallet@example.com")
    db_session.commit()

    called: dict[str, int] = {}
    monkeypatch.setattr(
        sched, "_notify_missing_allocation", lambda uid: called.__setitem__("uid", uid)
    )
    result = sched._resolve_proposal_amount(db_session, user.id)
    assert result == Decimal("0")
    assert called.get("uid") == user.id


# ---------------------------------------------------------------------------
# _resolve_proposal_amount: 遊休額 (idle capital) — 分母を静的台帳から動的遊休額へ
# (2026-08-06 / Asana 1217210604911292)
# ---------------------------------------------------------------------------


def test_resolve_proposal_amount_idle_after_partial_deployment(db_session):
    """一部運用済みのとき、遊休額 (allocated - deployed) の10%が提案額になること。

    allocated=$5,000, 実行済みSUPPLY=$3,000 → idle=$2,000 → 10%=$200。
    """
    user = _add_active_user(db_session, "partial_deployed@example.com")
    _add_fund_allocation(db_session, user, allocated_usd=Decimal("5000"))
    _add_executed_proposal(db_session, user, Decimal("3000"), operation="SUPPLY")
    db_session.commit()

    from app.automation.ai_judgment_scheduler import _resolve_proposal_amount  # noqa: PLC0415

    result = _resolve_proposal_amount(db_session, user.id)
    assert result == Decimal("200.00"), f"expected $200 (10% of $2,000 idle) but got {result}"


def test_resolve_proposal_amount_idle_accounts_for_withdraw(db_session):
    """実行済み WITHDRAW は運用済み額から差し引かれること。

    allocated=$1,000, 実行済みSUPPLY=$800, 実行済みWITHDRAW=$300
    → deployed=$500 → idle=$500 → 10%=$50。
    """
    user = _add_active_user(db_session, "withdraw_adjusted@example.com")
    _add_fund_allocation(db_session, user, allocated_usd=Decimal("1000"))
    _add_executed_proposal(db_session, user, Decimal("800"), operation="SUPPLY")
    _add_executed_proposal(db_session, user, Decimal("300"), operation="WITHDRAW")
    db_session.commit()

    from app.automation.ai_judgment_scheduler import _resolve_proposal_amount  # noqa: PLC0415

    result = _resolve_proposal_amount(db_session, user.id)
    assert result == Decimal("50.00"), f"expected $50 (10% of $500 idle) but got {result}"


def test_resolve_proposal_amount_idle_zero_when_fully_deployed(db_session):
    """遊休がゼロ (allocated <= deployed) のとき、提案が出ないこと (Decimal(0))。

    allocated=$1,000, 実行済みSUPPLY=$1,000 → idle=$0 → skip。
    """
    user = _add_active_user(db_session, "fully_deployed@example.com")
    _add_fund_allocation(db_session, user, allocated_usd=Decimal("1000"))
    _add_executed_proposal(db_session, user, Decimal("1000"), operation="SUPPLY")
    db_session.commit()

    from app.automation.ai_judgment_scheduler import _resolve_proposal_amount  # noqa: PLC0415

    assert _resolve_proposal_amount(db_session, user.id) == Decimal("0")


def test_resolve_proposal_amount_idle_never_negative_when_over_withdrawn(db_session):
    """WITHDRAW が SUPPLY を超えて記録されていても deployed は 0 未満に倒れない (安全側)。

    allocated=$1,000, SUPPLY=$200, WITHDRAW=$500 (記録不整合) → deployed=max(0, -300)=0
    → idle=$1,000 → 10%=$100 (allocated 全額を分母にした場合と同じ、暴走しない)。
    """
    user = _add_active_user(db_session, "over_withdrawn@example.com")
    _add_fund_allocation(db_session, user, allocated_usd=Decimal("1000"))
    _add_executed_proposal(db_session, user, Decimal("200"), operation="SUPPLY")
    _add_executed_proposal(db_session, user, Decimal("500"), operation="WITHDRAW")
    db_session.commit()

    from app.automation.ai_judgment_scheduler import _resolve_proposal_amount  # noqa: PLC0415

    result = _resolve_proposal_amount(db_session, user.id)
    assert result == Decimal("100.00")


def test_resolve_proposal_amount_pending_proposals_do_not_count_as_deployed(db_session):
    """status='pending' の提案は「運用済み」に数えない (実行されたものだけ数える)。

    allocated=$1,000, pending SUPPLY=$1,000 (未実行) → deployed=$0 → idle=$1,000 → 10%=$100。
    """
    user = _add_active_user(db_session, "pending_not_deployed@example.com")
    _add_fund_allocation(db_session, user, allocated_usd=Decimal("1000"))
    pending = Proposal(
        user_id=user.id,
        operation="SUPPLY",
        asset="USDC",
        protocol="aave",
        amount=Decimal("1000"),
        amount_usd=Decimal("1000"),
        reason="pending, not executed",
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(pending)
    db_session.commit()

    from app.automation.ai_judgment_scheduler import _resolve_proposal_amount  # noqa: PLC0415

    result = _resolve_proposal_amount(db_session, user.id)
    assert result == Decimal("100.00")


# ---------------------------------------------------------------------------
# _resolve_proposal_amount: 実効最低入金の無音デッドゾーン境界値
# ($100/$200/$500/$1,000/$5,000 / Asana 1217210854320785)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "balance,expected",
    [
        (Decimal("100"), Decimal("0")),  # < 最低入金($200) → deposit gate で skip
        (Decimal("200"), Decimal("0")),  # 10%=$20 < min($50) → 無音デッドゾーン→skip (要修正対象)
        (Decimal("500"), Decimal("50.00")),  # 10%=$50 = min → 提案は出る (採算ゲートは別関数)
        (Decimal("1000"), Decimal("100.00")),  # 10%=$100
        (Decimal("5000"), Decimal("500.00")),  # 10%=$500
    ],
)
def test_resolve_proposal_amount_wallet_deadzone_boundaries(
    db_session, monkeypatch, balance, expected
):
    """非カストディアル (wallet) 経路: $100/$200/$500/$1,000/$5,000 境界値。"""
    import app.automation.ai_judgment_scheduler as sched  # noqa: PLC0415

    user = _add_active_user(db_session, f"wallet_boundary_{balance}@example.com")
    user.smart_wallet_address = "0x" + "1" * 40
    db_session.commit()

    monkeypatch.setattr(sched, "_read_wallet_usdc_balance", lambda _addr: balance)
    result = sched._resolve_proposal_amount(db_session, user.id)
    assert result == expected, f"balance=${balance}: expected {expected} but got {result}"


@pytest.mark.parametrize(
    "allocated,expected",
    [
        (Decimal("100"), Decimal("0")),  # < 最低入金($200) → deposit gate で skip
        (
            Decimal("200"),
            Decimal("50.00"),
        ),  # 10%=$20 < min → custodial は $50 に切り上げ (既存非対称)
        (Decimal("500"), Decimal("50.00")),  # 10%=$50
        (Decimal("1000"), Decimal("100.00")),  # 10%=$100
        (Decimal("5000"), Decimal("500.00")),  # 10%=$500
    ],
)
def test_resolve_proposal_amount_custodial_boundaries(db_session, allocated, expected):
    """custodial (fund_allocation) 経路: $100/$200/$500/$1,000/$5,000 境界値 (deployed=0)。"""
    from app.automation.ai_judgment_scheduler import _resolve_proposal_amount  # noqa: PLC0415

    user = _add_active_user(db_session, f"custodial_boundary_{allocated}@example.com")
    _add_fund_allocation(db_session, user, allocated_usd=allocated)
    db_session.commit()

    result = _resolve_proposal_amount(db_session, user.id)
    assert result == expected, f"allocated=${allocated}: expected {expected} but got {result}"


def test_resolve_proposal_amount_wallet_deadzone_notifies_user(db_session, monkeypatch):
    """$200 デッドゾーン (10%<min) skip 時、本人へ理由通知が送られること (無音対策)。"""
    import app.automation.ai_judgment_scheduler as sched  # noqa: PLC0415

    user = _add_active_user(db_session, "deadzone_notify@example.com")
    user.smart_wallet_address = "0x" + "2" * 40
    db_session.commit()

    sent: list = []
    monkeypatch.setattr(sched, "_read_wallet_usdc_balance", lambda _addr: Decimal("200"))
    monkeypatch.setattr(
        "app.notifications.factory.get_notification_service",
        lambda: MagicMock(send=lambda m: sent.append(m)),
    )
    result = sched._resolve_proposal_amount(db_session, user.id)
    assert result == Decimal("0")
    assert len(sent) == 1
    assert sent[0].user_id == user.id


def test_create_proposals_db_error_one_user_does_not_stop_others(db_session):
    """_resolve_proposal_amount が DB 例外を投げたとき、他ユーザーの処理が継続すること。

    1ユーザーの例外が全体ループを止めないことを確認する（PR #323 follow-up P1）。
    """
    from unittest.mock import MagicMock  # noqa: PLC0415

    from app.auth.constants import ExecutionPolicy  # noqa: PLC0415
    from app.automation.ai_judgment_scheduler import _create_proposals_for_users  # noqa: PLC0415

    user_ok = MagicMock()
    user_ok.id = 1
    user_ok.is_active = True
    user_ok.execution_policy = ExecutionPolicy.REQUIRE_APPROVAL.value
    user_ok.last_judgment_at = None
    user_ok.tier = "LOWER"

    user_fail = MagicMock()
    user_fail.id = 2
    user_fail.is_active = True
    user_fail.execution_policy = ExecutionPolicy.REQUIRE_APPROVAL.value
    user_fail.last_judgment_at = None
    user_fail.tier = "LOWER"

    decision = MagicMock()
    decision.id = 99

    cv_result = _make_cross_validation_result(TradeAction.BUY)

    mock_db = MagicMock()
    mock_db.scalars.return_value.all.return_value = [user_fail, user_ok]

    call_count = 0

    def resolve_side_effect(_db, user_id):
        nonlocal call_count
        call_count += 1
        if user_id == user_fail.id:
            raise RuntimeError("simulated DB error for user 2")
        return Decimal("460")

    with (
        patch(
            "app.automation.ai_judgment_scheduler._resolve_proposal_amount",
            side_effect=resolve_side_effect,
        ),
        patch("app.fees.trade_gate.calculate_fee_by_market") as mock_fee,
        patch("app.notifications.factory.get_notification_service"),
    ):
        mock_fee.return_value.should_trade = True
        mock_fee.return_value.fee_rate = Decimal("0.05")
        mock_fee.return_value.fee_amount = Decimal("23.00")

        count = _create_proposals_for_users(mock_db, decision, cv_result)

    # user_fail は例外でスキップ、user_ok は成功 → count=1
    assert count == 1, f"Expected 1 proposal (user_ok only) but got {count}"
    # _resolve_proposal_amount は両ユーザー分呼ばれていること
    assert call_count == 2, f"Expected resolve called twice but got {call_count}"


# ---------------------------------------------------------------------------
# Hermes Phase 0 capture: save_ai_decision_features + save_ai_decision_outcomes
# ---------------------------------------------------------------------------


def test_save_ai_decision_features_inserts_row(db_session):
    """save_ai_decision_features が ai_decision_features テーブルに1行 INSERT すること。"""
    from unittest.mock import patch  # noqa: PLC0415

    from app.ai.models import AiDecisionFeature  # noqa: PLC0415
    from app.automation.ai_judgment_scheduler import save_ai_decision_features  # noqa: PLC0415

    decision = AIDecision(
        query="test",
        action="HOLD",
        confidence=60,
        primary_provider="claude",
        primary_action="HOLD",
        primary_confidence=60,
        agreed=True,
    )
    db_session.add(decision)
    db_session.flush()

    result = _make_cross_validation_result(TradeAction.HOLD)
    aave_data = {
        "utilization_rate": None,
        "supply_apy": None,
        "borrow_apy": None,
        "health_factor": None,
    }
    market_ctx = {"degraded": True, "reason": "test"}

    with patch("app.automation.ai_judgment_scheduler._generate_embedding", return_value=None):
        save_ai_decision_features(db_session, decision, result, aave_data, market_ctx)

    db_session.flush()
    row = db_session.query(AiDecisionFeature).filter_by(ai_decision_id=decision.id).one()
    assert row.judge_action == "HOLD"
    assert row.confidence == 80
    assert row.cross_verify is True


def test_save_ai_decision_features_fail_open(db_session):
    """save_ai_decision_features が失敗しても例外を伝播しないこと (fail-open)。"""
    from unittest.mock import patch  # noqa: PLC0415

    from app.automation.ai_judgment_scheduler import save_ai_decision_features  # noqa: PLC0415

    decision = AIDecision(
        query="test",
        action="HOLD",
        confidence=60,
        primary_provider="claude",
        primary_action="HOLD",
        primary_confidence=60,
        agreed=True,
    )
    db_session.add(decision)
    db_session.flush()

    result = _make_cross_validation_result(TradeAction.HOLD)
    aave_data = {
        "utilization_rate": None,
        "supply_apy": None,
        "borrow_apy": None,
        "health_factor": None,
    }

    # db.add が例外を投げてもエラー伝播しないことを確認
    with patch.object(db_session, "add", side_effect=RuntimeError("db add error")):
        save_ai_decision_features(db_session, decision, result, aave_data, {})
    # ここに到達すれば fail-open 動作が確認できている


def test_run_ai_judgment_job_inserts_features(test_db):
    """run_ai_judgment_job 実行後に ai_decision_features が INSERT されること。"""
    from unittest.mock import patch  # noqa: PLC0415

    from app.ai.models import AiDecisionFeature  # noqa: PLC0415
    from app.automation.ai_judgment_scheduler import run_ai_judgment_job  # noqa: PLC0415

    session = test_db()
    try:
        result = _make_cross_validation_result(TradeAction.HOLD)
        with (
            patch(
                "app.automation.ai_judgment_scheduler.AIService.judge_with_rag",
                return_value=result,
            ),
            patch(
                "app.automation.ai_judgment_scheduler.KnowledgeService.search",
                return_value=[],
            ),
            patch(
                "app.automation.ai_judgment_scheduler.fetch_aave_market_data_safe",
                return_value={
                    "utilization_rate": None,
                    "supply_apy": None,
                    "borrow_apy": None,
                    "health_factor": None,
                },
            ),
            patch("app.automation.ai_judgment_scheduler.get_judgment_logger") as mock_logger,
            patch(
                "app.automation.ai_judgment_scheduler.build_market_context",
                side_effect=RuntimeError("degraded"),
            ),
            patch(
                "app.automation.ai_judgment_scheduler._generate_embedding",
                return_value=None,
            ),
        ):
            from app.ai.judgment_log import CognitiveState  # noqa: PLC0415

            mock_logger.return_value.get_cognitive_state.return_value = CognitiveState()
            run_ai_judgment_job(db=session)

        rows = session.query(AiDecisionFeature).all()
        assert len(rows) == 1
        assert rows[0].judge_action == "HOLD"
    finally:
        session.close()
