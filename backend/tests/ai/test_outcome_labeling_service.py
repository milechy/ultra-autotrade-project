# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/ai/test_outcome_labeling_service.py
"""OutcomeLabelingService のテスト。

純粋計算関数 (_annualized_yield_pct / _compute_regret_score /
_compute_is_positive_example) と DB インテグレーションを分けてテスト。
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Generator

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-outcome-labeling")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin@example.com")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.ai.models import AIDecision, AiDecisionOutcome  # noqa: E402
from app.ai.outcome_labeling_service import (  # noqa: E402
    OutcomeLabelingService,
    _annualized_yield_pct,
    _compute_is_positive_example,
    _compute_regret_score,
)
from app.database import Base  # noqa: E402
from app.portfolio.models import PortfolioSnapshot  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


def _make_decision(
    db: Session,
    *,
    action: str = "HOLD",
    created_at: datetime | None = None,
) -> AIDecision:
    if created_at is None:
        created_at = datetime.now(timezone.utc) - timedelta(hours=50)
    d = AIDecision(
        query="test query",
        action=action,
        confidence=70,
        primary_provider="test",
        primary_action=action,
        primary_confidence=70,
        agreed=True,
        created_at=created_at,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def _make_snapshot(
    db: Session,
    *,
    user_id: int = 1,
    total_supply_usd: Decimal = Decimal("10000"),
    health_factor: Decimal | None = Decimal("2.5"),
    recorded_at: datetime,
) -> PortfolioSnapshot:
    s = PortfolioSnapshot(
        user_id=user_id,
        total_value_usd=total_supply_usd,
        total_supply_usd=total_supply_usd,
        total_borrow_usd=Decimal("0"),
        health_factor=health_factor,
        recorded_at=recorded_at,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


# ---------------------------------------------------------------------------
# Pure computation tests
# ---------------------------------------------------------------------------


class TestAnnualizedYieldPct:
    def test_zero_supply_before_returns_zero(self) -> None:
        assert _annualized_yield_pct(Decimal("0"), Decimal("100"), 24) == 0.0

    def test_negative_supply_before_returns_zero(self) -> None:
        assert _annualized_yield_pct(Decimal("-1"), Decimal("100"), 24) == 0.0

    def test_positive_yield_24h(self) -> None:
        # 10000 -> 10001 in 24h = raw_return 0.0001
        # annualized = 0.0001 * (8760/24) * 100 = 0.0001 * 365 * 100 = 3.65% APY
        result = _annualized_yield_pct(Decimal("10000"), Decimal("10001"), 24)
        assert abs(result - 3.65) < 0.01

    def test_no_change_returns_zero(self) -> None:
        result = _annualized_yield_pct(Decimal("10000"), Decimal("10000"), 24)
        assert result == 0.0

    def test_clamp_positive(self) -> None:
        # 10 -> 10000 in 24h = huge positive, clamped at 500
        result = _annualized_yield_pct(Decimal("10"), Decimal("10000"), 24)
        assert result == 500.0

    def test_clamp_negative(self) -> None:
        # 10000 -> 1 in 24h = huge negative, clamped at -500
        result = _annualized_yield_pct(Decimal("10000"), Decimal("1"), 24)
        assert result == -500.0


class TestComputeRegretScore:
    def test_hold_positive_yield_has_regret(self) -> None:
        score = _compute_regret_score("HOLD", 5.0)
        assert score == pytest.approx(0.5, abs=0.01)

    def test_hold_zero_yield_no_regret(self) -> None:
        assert _compute_regret_score("HOLD", 0.0) == 0.0

    def test_hold_negative_yield_no_regret(self) -> None:
        assert _compute_regret_score("HOLD", -5.0) == 0.0

    def test_supply_negative_yield_has_regret(self) -> None:
        score = _compute_regret_score("SUPPLY", -5.0)
        assert score == pytest.approx(0.5, abs=0.01)

    def test_supply_positive_yield_no_regret(self) -> None:
        assert _compute_regret_score("SUPPLY", 5.0) == 0.0

    def test_sell_positive_yield_has_regret(self) -> None:
        score = _compute_regret_score("SELL", 5.0)
        assert score == pytest.approx(0.5, abs=0.01)

    def test_buy_same_as_supply(self) -> None:
        assert _compute_regret_score("BUY", -5.0) == _compute_regret_score("SUPPLY", -5.0)

    def test_regret_capped_at_one(self) -> None:
        assert _compute_regret_score("HOLD", 100.0) == 1.0


class TestComputeIsPositiveExample:
    def test_supply_positive_yield_is_positive(self) -> None:
        assert _compute_is_positive_example("SUPPLY", 1.0) is True

    def test_supply_negative_yield_is_negative(self) -> None:
        assert _compute_is_positive_example("SUPPLY", -1.0) is False

    def test_supply_tiny_yield_is_none(self) -> None:
        assert _compute_is_positive_example("SUPPLY", 0.1) is None

    def test_hold_negative_yield_is_positive(self) -> None:
        assert _compute_is_positive_example("HOLD", -1.0) is True

    def test_hold_big_positive_yield_is_negative(self) -> None:
        assert _compute_is_positive_example("HOLD", 3.0) is False

    def test_hold_small_positive_yield_is_none(self) -> None:
        assert _compute_is_positive_example("HOLD", 0.3) is None

    def test_sell_negative_yield_is_positive(self) -> None:
        assert _compute_is_positive_example("SELL", -1.0) is True

    def test_sell_positive_yield_is_negative(self) -> None:
        assert _compute_is_positive_example("SELL", 1.0) is False

    def test_buy_same_as_supply(self) -> None:
        assert _compute_is_positive_example("BUY", 1.0) is True


# ---------------------------------------------------------------------------
# Integration tests (SQLite)
# ---------------------------------------------------------------------------


class TestOutcomeLabelingServiceIntegration:
    def test_run_batch_no_decisions(self, db: Session) -> None:
        svc = OutcomeLabelingService(db)
        result = svc.run_batch()
        assert result.total_processed == 0
        assert result.completed_at is not None

    def test_skips_decision_without_snapshots(self, db: Session) -> None:
        _make_decision(db, action="HOLD")
        svc = OutcomeLabelingService(db)
        result = svc.run_batch()
        assert result.total_processed == 0
        for hr in result.horizons:
            assert hr.skipped_no_snapshot > 0

    def test_inserts_outcome_when_snapshots_exist(self, db: Session) -> None:
        now = datetime.now(timezone.utc)
        decision_at = now - timedelta(hours=50)
        decision = _make_decision(db, action="SUPPLY", created_at=decision_at)

        # before スナップショット
        _make_snapshot(
            db,
            total_supply_usd=Decimal("10000"),
            recorded_at=decision_at + timedelta(minutes=5),
        )
        # 24h after スナップショット
        _make_snapshot(
            db,
            total_supply_usd=Decimal("10001"),
            health_factor=Decimal("2.6"),
            recorded_at=decision_at + timedelta(hours=24, minutes=5),
        )
        # 48h after スナップショット
        _make_snapshot(
            db,
            total_supply_usd=Decimal("10002"),
            health_factor=Decimal("2.7"),
            recorded_at=decision_at + timedelta(hours=48, minutes=5),
        )

        svc = OutcomeLabelingService(db)
        result = svc.run_batch()

        assert result.total_processed == 2  # 24h + 48h

        outcomes = db.query(AiDecisionOutcome).filter(
            AiDecisionOutcome.decision_id == decision.id,
            AiDecisionOutcome.horizon_hours.isnot(None),
        ).all()
        assert len(outcomes) == 2

        h24 = next(o for o in outcomes if o.horizon_hours == 24)
        assert h24.realized_yield_delta is not None
        assert float(h24.realized_yield_delta) > 0  # supply increased -> positive yield
        assert h24.hf_min_after is not None
        assert h24.regret_score is not None
        assert float(h24.regret_score) == 0.0  # SUPPLY + positive yield = no regret
        assert h24.is_positive_example is True
        assert h24.asset == "USDC"
        assert h24.protocol == "aave_v3"

    def test_idempotent_skips_existing_horizon(self, db: Session) -> None:
        now = datetime.now(timezone.utc)
        decision_at = now - timedelta(hours=50)
        decision = _make_decision(db, action="HOLD", created_at=decision_at)

        _make_snapshot(
            db,
            total_supply_usd=Decimal("10000"),
            recorded_at=decision_at + timedelta(minutes=5),
        )
        _make_snapshot(
            db,
            total_supply_usd=Decimal("10005"),
            recorded_at=decision_at + timedelta(hours=24, minutes=5),
        )

        svc = OutcomeLabelingService(db)
        result1 = svc.run_batch()
        result2 = svc.run_batch()

        assert result1.total_processed >= 1
        # 2nd run: existing rows should be skipped
        assert result2.total_processed == 0

    def test_decision_too_recent_is_skipped(self, db: Session) -> None:
        # 10h ago → horizon 24h はまだ経過していない
        decision_at = datetime.now(timezone.utc) - timedelta(hours=10)
        _make_decision(db, action="SUPPLY", created_at=decision_at)

        svc = OutcomeLabelingService(db)
        result = svc.run_batch()
        assert result.total_processed == 0

    def test_custom_asset_and_protocol(self, db: Session) -> None:
        now = datetime.now(timezone.utc)
        decision_at = now - timedelta(hours=50)
        decision = _make_decision(db, action="SUPPLY", created_at=decision_at)

        _make_snapshot(
            db,
            total_supply_usd=Decimal("5000"),
            recorded_at=decision_at + timedelta(minutes=5),
        )
        _make_snapshot(
            db,
            total_supply_usd=Decimal("5010"),
            recorded_at=decision_at + timedelta(hours=24, minutes=5),
        )
        _make_snapshot(
            db,
            total_supply_usd=Decimal("5020"),
            recorded_at=decision_at + timedelta(hours=48, minutes=5),
        )

        svc = OutcomeLabelingService(db, asset="ETH", protocol="lido")
        result = svc.run_batch()
        assert result.total_processed == 2

        outcomes = db.query(AiDecisionOutcome).filter(
            AiDecisionOutcome.decision_id == decision.id,
            AiDecisionOutcome.horizon_hours.isnot(None),
        ).all()
        for o in outcomes:
            assert o.asset == "ETH"
            assert o.protocol == "lido"
