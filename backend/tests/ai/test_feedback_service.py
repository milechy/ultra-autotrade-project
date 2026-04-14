# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/ai/test_feedback_service.py
"""FeedbackService のテスト。"""

import os
import tempfile
from decimal import Decimal
from typing import Generator

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-feedback-service")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "terms_admin@example.com")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.ai.feedback_models import AIFeedback, AIFeedbackCreate  # noqa: E402
from app.ai.feedback_service import FeedbackService  # noqa: E402
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


def _create_decision(db: Session, decision_id: int | None = None) -> AIDecision:
    """テスト用 AIDecision を作成して返す。"""
    decision = AIDecision(
        query="test query",
        action="HOLD",
        confidence=60,
        primary_provider="claude",
        primary_action="HOLD",
        primary_confidence=60,
        agreed=True,
    )
    db.add(decision)
    db.commit()
    db.refresh(decision)
    return decision


class TestRecordFeedback:
    def test_record_manual_feedback(self, db: Session) -> None:
        """manual フィードバックを正常に記録できる。"""
        decision = _create_decision(db)
        svc = FeedbackService(db)

        data = AIFeedbackCreate(
            ai_decision_id=decision.id,
            is_correct=True,
            actual_outcome="profit",
        )
        result = svc.record_feedback(data, recorded_by="admin@example.com")

        assert result.id is not None
        assert result.ai_decision_id == decision.id
        assert result.is_correct is True
        assert result.actual_outcome == "profit"
        assert result.feedback_source == "manual"
        assert result.recorded_by == "admin@example.com"

    def test_record_with_all_fields(self, db: Session) -> None:
        """全フィールドを指定してフィードバックを記録できる。"""
        decision = _create_decision(db)
        svc = FeedbackService(db)

        data = AIFeedbackCreate(
            ai_decision_id=decision.id,
            is_correct=False,
            actual_outcome="loss",
            pnl_usd=Decimal("-25.50"),
            expected_apy=Decimal("5.0"),
            actual_apy=Decimal("2.5"),
            improvement_suggestion="Lower risk threshold",
        )
        result = svc.record_feedback(data, recorded_by="admin@example.com")

        assert result.is_correct is False
        assert result.actual_outcome == "loss"
        assert result.pnl_usd is not None
        assert result.improvement_suggestion == "Lower risk threshold"

    def test_record_persists_to_db(self, db: Session) -> None:
        """記録したフィードバックが DB に永続化される。"""
        from sqlalchemy import select

        decision = _create_decision(db)
        svc = FeedbackService(db)
        data = AIFeedbackCreate(ai_decision_id=decision.id, actual_outcome="neutral")
        svc.record_feedback(data, recorded_by="admin@example.com")

        feedbacks = list(
            db.scalars(
                select(AIFeedback).where(AIFeedback.ai_decision_id == decision.id)
            ).all()
        )
        assert len(feedbacks) == 1
        assert feedbacks[0].actual_outcome == "neutral"

    def test_judgment_log_failure_is_fail_open(self, db: Session, monkeypatch) -> None:
        """JudgmentLogger 更新が失敗しても DB 記録は成功する（fail-open）。"""
        decision = _create_decision(db)
        svc = FeedbackService(db)

        # _try_update_judgment_log を例外を投げるようにモック
        def _raise(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003
            raise RuntimeError("simulated JudgmentLogger failure")

        monkeypatch.setattr(svc, "_try_update_judgment_log", _raise)

        data = AIFeedbackCreate(
            ai_decision_id=decision.id,
            is_correct=True,
            actual_outcome="profit",
        )
        # 例外が伝播しないこと
        result = svc.record_feedback(data, recorded_by="admin@example.com")
        assert result.id is not None

    def test_source_override(self, db: Session) -> None:
        """feedback_source を指定して記録できる。"""
        decision = _create_decision(db)
        svc = FeedbackService(db)
        data = AIFeedbackCreate(ai_decision_id=decision.id, actual_outcome="unknown")
        result = svc.record_feedback(
            data, recorded_by="system", feedback_source="auto_outcome"
        )
        assert result.feedback_source == "auto_outcome"


class TestGetFeedbackByDecision:
    def test_existing_decision(self, db: Session) -> None:
        """存在する判定 ID のフィードバックを取得できる。"""
        decision = _create_decision(db)
        svc = FeedbackService(db)

        for outcome in ("profit", "loss"):
            svc.record_feedback(
                AIFeedbackCreate(ai_decision_id=decision.id, actual_outcome=outcome),
                recorded_by="admin@example.com",
            )

        results = svc.get_feedback_by_decision(decision.id)
        assert len(results) == 2

    def test_nonexistent_decision_returns_empty(self, db: Session) -> None:
        """存在しない判定 ID は空リストを返す。"""
        svc = FeedbackService(db)
        results = svc.get_feedback_by_decision(99999)
        assert results == []

    def test_ordered_by_recorded_at_desc(self, db: Session) -> None:
        """結果は recorded_at 降順で返る。"""
        import time

        decision = _create_decision(db)
        svc = FeedbackService(db)
        for outcome in ("profit", "loss", "neutral"):
            svc.record_feedback(
                AIFeedbackCreate(ai_decision_id=decision.id, actual_outcome=outcome),
                recorded_by="admin@example.com",
            )
            time.sleep(0.01)  # recorded_at が異なるよう微小スリープ

        results = svc.get_feedback_by_decision(decision.id)
        # recorded_at 降順 → 最後に追加した "neutral" が先頭
        assert results[0].actual_outcome == "neutral"


class TestGetStats:
    def test_empty_stats(self, db: Session) -> None:
        """フィードバックが 0 件のとき空の統計を返す。"""
        svc = FeedbackService(db)
        stats = svc.get_stats(days=30)

        assert stats.total_feedbacks == 0
        assert stats.correct_count == 0
        assert stats.incorrect_count == 0
        assert stats.accuracy_rate is None
        assert stats.avg_pnl_usd is None
        assert stats.feedback_by_source == {}

    def test_accuracy_rate_calculated(self, db: Session) -> None:
        """correct/incorrect から accuracy_rate が計算される。"""
        decision = _create_decision(db)
        svc = FeedbackService(db)

        for is_correct in (True, True, False):
            svc.record_feedback(
                AIFeedbackCreate(
                    ai_decision_id=decision.id,
                    actual_outcome="profit" if is_correct else "loss",
                    is_correct=is_correct,
                ),
                recorded_by="admin@example.com",
            )

        stats = svc.get_stats(days=0)
        assert stats.total_feedbacks == 3
        assert stats.correct_count == 2
        assert stats.incorrect_count == 1
        assert stats.accuracy_rate == pytest.approx(2 / 3, rel=1e-3)

    def test_accuracy_rate_none_when_all_undecided(self, db: Session) -> None:
        """is_correct が None のフィードバックのみのとき accuracy_rate は None。"""
        decision = _create_decision(db)
        svc = FeedbackService(db)
        svc.record_feedback(
            AIFeedbackCreate(
                ai_decision_id=decision.id, actual_outcome="unknown", is_correct=None
            ),
            recorded_by="admin@example.com",
        )

        stats = svc.get_stats(days=0)
        assert stats.accuracy_rate is None

    def test_avg_pnl_usd(self, db: Session) -> None:
        """複数件の pnl_usd が正しく平均される。"""
        decision = _create_decision(db)
        svc = FeedbackService(db)

        for pnl in (Decimal("100"), Decimal("200"), Decimal("300")):
            svc.record_feedback(
                AIFeedbackCreate(
                    ai_decision_id=decision.id, actual_outcome="profit", pnl_usd=pnl
                ),
                recorded_by="admin@example.com",
            )

        stats = svc.get_stats(days=0)
        assert stats.avg_pnl_usd is not None
        avg = Decimal(stats.avg_pnl_usd)
        assert avg == pytest.approx(Decimal("200"), rel=Decimal("1e-3"))

    def test_feedback_by_source(self, db: Session) -> None:
        """feedback_by_source が正しくカウントされる。"""
        decision = _create_decision(db)
        svc = FeedbackService(db)

        svc.record_feedback(
            AIFeedbackCreate(ai_decision_id=decision.id, actual_outcome="profit"),
            recorded_by="admin@example.com",
            feedback_source="manual",
        )
        svc.record_feedback(
            AIFeedbackCreate(ai_decision_id=decision.id, actual_outcome="neutral"),
            recorded_by="system",
            feedback_source="auto_howl",
        )

        stats = svc.get_stats(days=0)
        assert stats.feedback_by_source["manual"] == 1
        assert stats.feedback_by_source["auto_howl"] == 1

    def test_days_filter(self, db: Session) -> None:
        """days フィルタが機能する（days=0 は全期間）。"""
        svc = FeedbackService(db)
        decision = _create_decision(db)
        svc.record_feedback(
            AIFeedbackCreate(ai_decision_id=decision.id, actual_outcome="profit"),
            recorded_by="admin@example.com",
        )

        stats_all = svc.get_stats(days=0)
        stats_7d = svc.get_stats(days=7)
        # 作成直後なので 7 日以内のデータとして集計される
        assert stats_all.total_feedbacks == stats_7d.total_feedbacks


class TestBulkAutoFeedback:
    def test_empty_list_returns_empty(self, db: Session) -> None:
        """空リストを渡すと空リストが返る。"""
        svc = FeedbackService(db)
        results = svc.bulk_auto_feedback([])
        assert results == []

    def test_bulk_records_all(self, db: Session) -> None:
        """複数フィードバックを一括登録できる。"""
        decision = _create_decision(db)
        svc = FeedbackService(db)

        feedbacks = [
            AIFeedbackCreate(
                ai_decision_id=decision.id, actual_outcome="profit", is_correct=True
            ),
            AIFeedbackCreate(
                ai_decision_id=decision.id, actual_outcome="loss", is_correct=False
            ),
        ]
        results = svc.bulk_auto_feedback(feedbacks)

        assert len(results) == 2
        assert all(r.feedback_source == "auto_howl" for r in results)

    def test_bulk_source_override(self, db: Session) -> None:
        """source パラメータを指定できる。"""
        decision = _create_decision(db)
        svc = FeedbackService(db)
        data = [AIFeedbackCreate(ai_decision_id=decision.id, actual_outcome="neutral")]
        results = svc.bulk_auto_feedback(data, source="auto_outcome")
        assert results[0].feedback_source == "auto_outcome"

    def test_bulk_partial_failure_continues(self, db: Session, monkeypatch) -> None:
        """一部の登録が失敗しても残りは継続する。"""
        decision = _create_decision(db)
        svc = FeedbackService(db)

        call_count = 0
        original_record = svc.record_feedback

        def patched_record(data, recorded_by, feedback_source="manual"):  # noqa: ANN001
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("simulated failure on first item")
            return original_record(data, recorded_by, feedback_source)

        monkeypatch.setattr(svc, "record_feedback", patched_record)

        feedbacks = [
            AIFeedbackCreate(ai_decision_id=decision.id, actual_outcome="profit"),
            AIFeedbackCreate(ai_decision_id=decision.id, actual_outcome="loss"),
        ]
        results = svc.bulk_auto_feedback(feedbacks)
        # 1件失敗しても 2件目は成功
        assert len(results) == 1
        assert results[0].actual_outcome == "loss"
