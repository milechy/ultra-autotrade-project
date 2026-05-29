# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_hermes_phase0_capture.py
"""Hermes Phase 0 capture — ai_decision_outcomes.partner_approved 配線テスト。"""

import os
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-hermes-capture")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin@example.com")

from app.ai.models import AIDecision, AiDecisionFeature, AiDecisionOutcome  # noqa: E402
from app.database import Base  # noqa: E402
from app.proposals.router import _capture_partner_decision  # noqa: E402


@pytest.fixture()
def db_session():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


def _make_decision(session) -> AIDecision:
    d = AIDecision(
        query="test",
        action="HOLD",
        confidence=60,
        primary_provider="claude",
        primary_action="HOLD",
        primary_confidence=60,
        agreed=True,
    )
    session.add(d)
    session.flush()
    return d


class TestCapturePartnerDecision:
    def test_approve_inserts_outcome_row(self, db_session):
        decision = _make_decision(db_session)
        db_session.commit()

        _capture_partner_decision(db_session, decision.id, partner_approved=True)

        row = db_session.query(AiDecisionOutcome).filter_by(decision_id=decision.id).one()
        assert row.partner_approved is True

    def test_reject_inserts_outcome_row(self, db_session):
        decision = _make_decision(db_session)
        db_session.commit()

        _capture_partner_decision(db_session, decision.id, partner_approved=False)

        row = db_session.query(AiDecisionOutcome).filter_by(decision_id=decision.id).one()
        assert row.partner_approved is False

    def test_no_ai_decision_id_is_noop(self, db_session):
        """ai_decision_id が NULL の提案は no-op で例外しないこと。"""
        _capture_partner_decision(db_session, None, partner_approved=True)
        count = db_session.query(AiDecisionOutcome).count()
        assert count == 0

    def test_outcome_other_fields_are_null(self, db_session):
        """Phase 1 までは partner_approved 以外の列は NULL であること。"""
        decision = _make_decision(db_session)
        db_session.commit()

        _capture_partner_decision(db_session, decision.id, partner_approved=True)

        row = db_session.query(AiDecisionOutcome).filter_by(decision_id=decision.id).one()
        assert row.horizon_hours is None
        assert row.realized_yield_delta is None
        assert row.gas_cost_usd is None
        assert row.hf_min_after is None
        assert row.regret_score is None
        assert row.is_positive_example is None


class TestAiDecisionFeatureModel:
    def test_model_creates_and_reads_back(self, db_session):
        """AiDecisionFeature テーブルへの INSERT/SELECT が動作すること。"""
        decision = _make_decision(db_session)

        feature = AiDecisionFeature(
            ai_decision_id=decision.id,
            agent_signals={"indicator": {"bias": "bullish", "confidence": 72}},
            raw_features={"utilization_rate": "45.5", "health_factor": "2.1"},
            judge_action="HOLD",
            confidence=60,
            cross_verify=True,
            embedding=None,
        )
        db_session.add(feature)
        db_session.flush()

        row = (
            db_session.query(AiDecisionFeature)
            .filter_by(ai_decision_id=decision.id)
            .one()
        )
        assert row.judge_action == "HOLD"
        assert row.cross_verify is True
        assert row.agent_signals["indicator"]["bias"] == "bullish"
        assert row.raw_features["health_factor"] == "2.1"
