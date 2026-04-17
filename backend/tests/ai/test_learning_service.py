# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/ai/test_learning_service.py
"""AILearningService のテスト。"""

import os
import tempfile
from typing import Generator
from unittest.mock import patch

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-learning-service")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "terms_admin@example.com")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.ai.feedback_models import AIFeedback, AIFeedbackCreate  # noqa: E402
from app.ai.feedback_service import FeedbackService  # noqa: E402
from app.ai.learning_service import (  # noqa: E402
    AILearningService,
    LearningCycleResult,
)
from app.ai.models import AIDecision  # noqa: E402
from app.database import Base  # noqa: E402


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


def _create_decision(db: Session, action: str = "HOLD") -> AIDecision:
    """テスト用 AIDecision を作成して返す。"""
    decision = AIDecision(
        query="test query",
        action=action,
        confidence=60,
        primary_provider="claude",
        primary_action=action,
        primary_confidence=60,
        agreed=True,
    )
    db.add(decision)
    db.commit()
    db.refresh(decision)
    return decision


def _create_feedback(db: Session, decision_id: int, is_correct: bool = True) -> AIFeedback:
    """テスト用 AIFeedback を作成して返す。"""
    svc = FeedbackService(db)
    data = AIFeedbackCreate(
        ai_decision_id=decision_id,
        actual_outcome="profit" if is_correct else "loss",
        is_correct=is_correct,
    )
    return svc.record_feedback(data, recorded_by="test")


class TestRunLearningCycle:
    @pytest.mark.asyncio
    async def test_returns_learning_cycle_result(self, db: Session) -> None:
        """学習サイクルが LearningCycleResult を返す。"""
        svc = AILearningService(db)
        result = await svc.run_learning_cycle()
        assert isinstance(result, LearningCycleResult)
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_all_steps_run_with_no_data(self, db: Session) -> None:
        """データ 0 件でも全ステップが完走する（fail-open）。"""
        svc = AILearningService(db)
        result = await svc.run_learning_cycle()
        # Step 1: auto_feedback が返る（エラーなし）
        assert result.auto_feedback is not None
        assert result.auto_feedback.evaluated_count == 0
        # Step 2: stats が返る
        assert result.stats is not None
        assert result.stats.total_feedbacks == 0
        # auto_feedback_error がないこと
        assert result.auto_feedback_error is None

    @pytest.mark.asyncio
    async def test_step1_error_does_not_propagate(self, db: Session) -> None:
        """Step 1 が例外を投げても他ステップは実行される（fail-open）。"""
        svc = AILearningService(db)

        async def _raise(*_args, **_kwargs):  # noqa: ANN001, ANN002, ANN003
            raise RuntimeError("simulated step 1 failure")

        svc._generate_auto_feedback = _raise  # type: ignore[method-assign]
        result = await svc.run_learning_cycle()

        assert result.auto_feedback is None
        assert result.auto_feedback_error is not None
        # Step 2 は実行されている
        assert result.stats is not None
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_completed_at_is_set(self, db: Session) -> None:
        """completed_at が UTC で設定される。"""
        from datetime import timezone

        svc = AILearningService(db)
        result = await svc.run_learning_cycle()
        assert result.completed_at is not None
        assert result.completed_at.tzinfo == timezone.utc


class TestGenerateAutoFeedback:
    @pytest.mark.asyncio
    async def test_no_unevaluated_decisions(self, db: Session) -> None:
        """未評価判定がなければ 0 件を返す。"""
        svc = AILearningService(db)
        result = await svc._generate_auto_feedback()
        assert result.evaluated_count == 0
        assert result.feedback_created == 0

    @pytest.mark.asyncio
    async def test_already_evaluated_decision_is_skipped(self, db: Session) -> None:
        """既にフィードバック済みの判定はスキップされる。"""
        decision = _create_decision(db)
        _create_feedback(db, decision.id, is_correct=True)

        svc = AILearningService(db)
        result = await svc._generate_auto_feedback()
        # 既に評価済みなので evaluated_count == 0
        assert result.evaluated_count == 0

    @pytest.mark.asyncio
    async def test_evaluate_judgment_exception_is_collected(self, db: Session) -> None:
        """evaluate_judgment が例外を投げてもループが継続し errors に記録される。"""
        _create_decision(db)

        svc = AILearningService(db)
        with patch(
            "app.ai.learning_service.evaluate_judgment",
            side_effect=RuntimeError("evaluation error"),
        ):
            result = await svc._generate_auto_feedback()

        assert result.evaluated_count >= 1
        assert len(result.errors) >= 1


class TestUpdateCognitiveState:
    @pytest.mark.asyncio
    async def test_no_stats_returns_not_updated(self, db: Session) -> None:
        """stats が None のとき updated=False を返す。"""
        svc = AILearningService(db)
        result = await svc._update_cognitive_state(None)
        assert result.updated is False

    @pytest.mark.asyncio
    async def test_stats_without_accuracy_returns_not_updated(self, db: Session) -> None:
        """accuracy_rate が None のとき updated=False を返す。"""
        from app.ai.feedback_models import AIFeedbackStats

        svc = AILearningService(db)
        stats = AIFeedbackStats(
            total_feedbacks=0,
            correct_count=0,
            incorrect_count=0,
            accuracy_rate=None,
            avg_pnl_usd=None,
            feedback_by_source={},
        )
        result = await svc._update_cognitive_state(stats)
        assert result.updated is False

    @pytest.mark.asyncio
    async def test_win_rate_updated_from_stats(self, db: Session) -> None:
        """accuracy_rate が CognitiveState.win_rate に反映される。"""
        from app.ai.feedback_models import AIFeedbackStats

        svc = AILearningService(db)
        stats = AIFeedbackStats(
            total_feedbacks=10,
            correct_count=7,
            incorrect_count=3,
            accuracy_rate=0.7,
            avg_pnl_usd=None,
            feedback_by_source={"manual": 10},
        )
        result = await svc._update_cognitive_state(stats)
        assert result.updated is True
        assert result.new_win_rate == pytest.approx(0.7, rel=1e-6)


class TestComputeActionAccuracy:
    def test_empty_db_returns_empty_dict(self, db: Session) -> None:
        """フィードバックなしのとき空の dict を返す。"""
        svc = AILearningService(db)
        result = svc._compute_action_accuracy()
        assert result == {}

    def test_accuracy_computed_per_action(self, db: Session) -> None:
        """アクション別正答率が正しく計算される。"""
        # HOLD: 2 correct, 1 incorrect → 2/3
        hold1 = _create_decision(db, action="HOLD")
        hold2 = _create_decision(db, action="HOLD")
        hold3 = _create_decision(db, action="HOLD")
        _create_feedback(db, hold1.id, is_correct=True)
        _create_feedback(db, hold2.id, is_correct=True)
        _create_feedback(db, hold3.id, is_correct=False)

        # BUY: 1 correct → 1.0
        buy = _create_decision(db, action="BUY")
        _create_feedback(db, buy.id, is_correct=True)

        svc = AILearningService(db)
        result = svc._compute_action_accuracy()

        assert "HOLD" in result
        assert result["HOLD"] == pytest.approx(2 / 3, rel=1e-3)
        assert "BUY" in result
        assert result["BUY"] == pytest.approx(1.0, rel=1e-6)
