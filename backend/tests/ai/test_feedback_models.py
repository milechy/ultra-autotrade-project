# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/ai/test_feedback_models.py
"""AIFeedback モデル・スキーマのテスト。"""

import os
import tempfile
from decimal import Decimal

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-feedback-models")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "terms_admin@example.com")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.ai.feedback_models import (  # noqa: E402
    AIFeedback,
    AIFeedbackCreate,
    AIFeedbackResponse,
    AIFeedbackStats,
)
from app.database import Base  # noqa: E402


@pytest.fixture()
def db_session():
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


class TestAIFeedbackModel:
    def test_create_minimal(self, db_session) -> None:
        """最小フィールドで AIFeedback を作成できる。"""
        fb = AIFeedback(
            ai_decision_id=1,
            actual_outcome="profit",
        )
        db_session.add(fb)
        db_session.commit()
        db_session.refresh(fb)

        assert fb.id is not None
        assert fb.ai_decision_id == 1
        assert fb.actual_outcome == "profit"
        assert fb.feedback_source == "manual"  # デフォルト値
        assert fb.is_correct is None

    def test_create_full(self, db_session) -> None:
        """全フィールドで AIFeedback を作成できる。"""
        fb = AIFeedback(
            ai_decision_id=42,
            is_correct=True,
            actual_outcome="profit",
            pnl_usd=Decimal("123.456789"),
            expected_apy=Decimal("5.1234"),
            actual_apy=Decimal("6.5432"),
            improvement_suggestion="Increase confidence threshold",
            feedback_source="auto_howl",
            recorded_by="admin@example.com",
        )
        db_session.add(fb)
        db_session.commit()
        db_session.refresh(fb)

        assert fb.is_correct is True
        assert fb.feedback_source == "auto_howl"
        assert fb.recorded_by == "admin@example.com"
        assert fb.improvement_suggestion == "Increase confidence threshold"

    def test_created_at_auto(self, db_session) -> None:
        """created_at と recorded_at が自動設定される。"""
        fb = AIFeedback(ai_decision_id=1, actual_outcome="neutral")
        db_session.add(fb)
        db_session.commit()
        db_session.refresh(fb)

        assert fb.created_at is not None
        assert fb.recorded_at is not None

    def test_multiple_feedbacks_same_decision(self, db_session) -> None:
        """同一 ai_decision_id に複数フィードバックを登録できる。"""
        for outcome in ("profit", "loss"):
            db_session.add(AIFeedback(ai_decision_id=99, actual_outcome=outcome))
        db_session.commit()

        from sqlalchemy import select

        rows = list(
            db_session.scalars(
                select(AIFeedback).where(AIFeedback.ai_decision_id == 99)
            ).all()
        )
        assert len(rows) == 2


class TestAIFeedbackCreateSchema:
    def test_valid_minimal(self) -> None:
        """最小フィールドで AIFeedbackCreate を作成できる。"""
        data = AIFeedbackCreate(ai_decision_id=1, actual_outcome="profit")
        assert data.ai_decision_id == 1
        assert data.actual_outcome == "profit"
        assert data.is_correct is None
        assert data.pnl_usd is None

    def test_valid_all_outcomes(self) -> None:
        """全 actual_outcome 値を受け付ける。"""
        for outcome in ("profit", "loss", "neutral", "unknown"):
            data = AIFeedbackCreate(ai_decision_id=1, actual_outcome=outcome)  # type: ignore[arg-type]
            assert data.actual_outcome == outcome

    def test_invalid_outcome_raises(self) -> None:
        """不正な actual_outcome はバリデーションエラー。"""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AIFeedbackCreate(ai_decision_id=1, actual_outcome="invalid_value")  # type: ignore[arg-type]

    def test_suggestion_truncated_at_2000(self) -> None:
        """improvement_suggestion が 2000 文字を超えると切り詰められる。"""
        long_text = "A" * 3000
        data = AIFeedbackCreate(
            ai_decision_id=1, actual_outcome="profit", improvement_suggestion=long_text
        )
        assert len(data.improvement_suggestion) == 2000  # type: ignore[arg-type]

    def test_suggestion_within_limit(self) -> None:
        """2000 文字以内は切り詰めなし。"""
        text = "B" * 500
        data = AIFeedbackCreate(
            ai_decision_id=1, actual_outcome="neutral", improvement_suggestion=text
        )
        assert data.improvement_suggestion == text

    def test_decimal_fields(self) -> None:
        """Decimal フィールドを設定できる。"""
        data = AIFeedbackCreate(
            ai_decision_id=1,
            actual_outcome="loss",
            pnl_usd=Decimal("-50.12"),
            expected_apy=Decimal("4.5"),
            actual_apy=Decimal("2.1"),
        )
        assert data.pnl_usd == Decimal("-50.12")


class TestAIFeedbackResponseSchema:
    def test_decimal_as_string(self, db_session) -> None:
        """AIFeedbackResponse で Decimal フィールドが文字列で返る。"""
        fb = AIFeedback(
            ai_decision_id=1,
            actual_outcome="profit",
            pnl_usd=Decimal("10.5"),
            expected_apy=Decimal("5.0"),
            actual_apy=Decimal("5.5"),
        )
        db_session.add(fb)
        db_session.commit()
        db_session.refresh(fb)

        response = AIFeedbackResponse.model_validate(fb)
        assert isinstance(response.pnl_usd, str)
        assert isinstance(response.expected_apy, str)
        assert isinstance(response.actual_apy, str)

    def test_none_decimals(self, db_session) -> None:
        """Decimal フィールドが None の場合は None で返る。"""
        fb = AIFeedback(ai_decision_id=1, actual_outcome="unknown")
        db_session.add(fb)
        db_session.commit()
        db_session.refresh(fb)

        response = AIFeedbackResponse.model_validate(fb)
        assert response.pnl_usd is None
        assert response.expected_apy is None
        assert response.actual_apy is None


class TestAIFeedbackStatsSchema:
    def test_schema_creation(self) -> None:
        """AIFeedbackStats を生成できる。"""
        stats = AIFeedbackStats(
            total_feedbacks=10,
            correct_count=7,
            incorrect_count=2,
            accuracy_rate=0.778,
            avg_pnl_usd="15.500000",
            feedback_by_source={"manual": 8, "auto_howl": 2},
        )
        assert stats.total_feedbacks == 10
        assert stats.accuracy_rate == pytest.approx(0.778, rel=1e-3)

    def test_schema_none_accuracy(self) -> None:
        """accuracy_rate が None でも生成できる（フィードバック未決定時）。"""
        stats = AIFeedbackStats(
            total_feedbacks=0,
            correct_count=0,
            incorrect_count=0,
            accuracy_rate=None,
            avg_pnl_usd=None,
            feedback_by_source={},
        )
        assert stats.accuracy_rate is None
        assert stats.avg_pnl_usd is None
