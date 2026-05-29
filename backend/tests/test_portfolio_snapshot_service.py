# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_portfolio_snapshot_service.py
"""ポートフォリオスナップショットサービスのテスト。"""

import os
import tempfile
from decimal import Decimal
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-snapshot")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin@snapshot-test.com")

from app.aave.client import AccountData  # noqa: E402
from app.auth.models import User  # noqa: E402
from app.database import Base  # noqa: E402
from app.portfolio.models import PortfolioHistory, PortfolioSnapshot  # noqa: E402
from app.portfolio.snapshot_service import (  # noqa: E402
    _normalize_hf,
    _upsert_daily_history,
    record_portfolio_snapshot,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


def _make_admin(db: Session, uid: int = 1) -> User:
    user = User(
        id=uid,
        email=f"admin{uid}@test.com",
        username=f"admin{uid}",
        hashed_password="x",
        role="admin",
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _make_user(
    db: Session,
    uid: int,
    invited_by: int | None = None,
    role: str = "viewer",
    wallet_address: str | None = None,
) -> User:
    user = User(
        id=uid,
        email=f"user{uid}@test.com",
        username=f"user{uid}",
        hashed_password="x",
        role=role,
        is_active=True,
        invited_by=invited_by,
        wallet_address=wallet_address,
    )
    db.add(user)
    db.flush()
    return user


def _make_account_data(
    supply: str = "10000",
    debt: str = "3000",
    hf: str = "2.5",
) -> AccountData:
    return AccountData(
        total_collateral_usd=Decimal(supply),
        total_debt_usd=Decimal(debt),
        available_borrows_usd=Decimal("5000"),
        health_factor=Decimal(hf),
    )


# ---------------------------------------------------------------------------
# _normalize_hf
# ---------------------------------------------------------------------------


class TestNormalizeHf:
    def test_finite_value(self) -> None:
        assert _normalize_hf(Decimal("2.5")) == Decimal("2.5")

    def test_infinity_returns_none(self) -> None:
        assert _normalize_hf(Decimal("Infinity")) is None

    def test_negative_infinity_returns_none(self) -> None:
        assert _normalize_hf(Decimal("-Infinity")) is None

    def test_nan_returns_none(self) -> None:
        assert _normalize_hf(Decimal("NaN")) is None


# ---------------------------------------------------------------------------
# _upsert_daily_history
# ---------------------------------------------------------------------------


class TestUpsertDailyHistory:
    def test_creates_new_record(self, db_session: Session) -> None:
        from datetime import datetime, timezone

        _make_admin(db_session)
        now = datetime.now(timezone.utc)
        _upsert_daily_history(db_session, 1, Decimal("7000"), Decimal("2.5"), now)
        db_session.flush()

        row = db_session.query(PortfolioHistory).filter_by(user_id=1).first()
        assert row is not None
        assert row.period_type == "daily"
        assert Decimal(str(row.open_value_usd)) == Decimal("7000")
        assert Decimal(str(row.close_value_usd)) == Decimal("7000")
        assert Decimal(str(row.pnl_usd)) == Decimal("0")
        assert row.snapshot_count == 1

    def test_updates_existing_record(self, db_session: Session) -> None:
        from datetime import datetime, timezone

        _make_admin(db_session)
        now = datetime.now(timezone.utc)
        # 1回目 (open = 7000)
        _upsert_daily_history(db_session, 1, Decimal("7000"), Decimal("2.5"), now)
        db_session.flush()
        # 2回目 (close = 7500)
        _upsert_daily_history(db_session, 1, Decimal("7500"), Decimal("2.6"), now)
        db_session.flush()

        row = db_session.query(PortfolioHistory).filter_by(user_id=1).first()
        assert Decimal(str(row.open_value_usd)) == Decimal("7000")
        assert Decimal(str(row.close_value_usd)) == Decimal("7500")
        assert Decimal(str(row.high_value_usd)) == Decimal("7500")
        assert Decimal(str(row.low_value_usd)) == Decimal("7000")
        assert row.snapshot_count == 2
        # pnl_pct: (7500-7000)/7000*100 ≈ 7.1429%
        assert Decimal(str(row.pnl_pct)) > Decimal("7")

    def test_low_updated_on_decrease(self, db_session: Session) -> None:
        from datetime import datetime, timezone

        _make_admin(db_session)
        now = datetime.now(timezone.utc)
        _upsert_daily_history(db_session, 1, Decimal("7000"), None, now)
        db_session.flush()
        _upsert_daily_history(db_session, 1, Decimal("6000"), None, now)
        db_session.flush()

        row = db_session.query(PortfolioHistory).filter_by(user_id=1).first()
        assert Decimal(str(row.low_value_usd)) == Decimal("6000")


# ---------------------------------------------------------------------------
# record_portfolio_snapshot
# ---------------------------------------------------------------------------


class TestRecordPortfolioSnapshot:
    def _mock_aave_client(self, account_data: AccountData) -> MagicMock:
        mock_client = MagicMock()
        mock_client.get_account_data.return_value = account_data
        return mock_client

    def test_no_testers_saves_admin_snapshot(self, db_session: Session) -> None:
        """テスターがいない場合、管理者ユーザーのスナップショットを保存する。"""
        _make_admin(db_session, uid=1)
        db_session.commit()

        account_data = _make_account_data("10000", "3000", "2.5")
        with patch(
            "app.portfolio.snapshot_service.get_default_aave_client",
            return_value=self._mock_aave_client(account_data),
        ):
            result = record_portfolio_snapshot(db_session)

        assert result["snapshots_created"] == 1
        snap = db_session.query(PortfolioSnapshot).first()
        assert snap is not None
        assert snap.user_id == 1
        assert Decimal(str(snap.total_supply_usd)) == Decimal("10000")
        assert Decimal(str(snap.total_borrow_usd)) == Decimal("3000")
        assert Decimal(str(snap.total_value_usd)) == Decimal("7000")  # net_worth

    def test_with_testers_saves_per_tester(self, db_session: Session) -> None:
        """テスターが2人いる場合、partner wallet_address で取得したデータを均等按分して保存。"""
        partner = _make_user(db_session, uid=10, role="partner", wallet_address="0xPartner10")
        _make_user(db_session, uid=11, invited_by=partner.id)
        _make_user(db_session, uid=12, invited_by=partner.id)
        db_session.commit()

        account_data = _make_account_data("10000", "2000", "3.0")
        with patch(
            "app.portfolio.snapshot_service.get_default_aave_client",
            return_value=self._mock_aave_client(account_data),
        ):
            result = record_portfolio_snapshot(db_session)

        assert result["snapshots_created"] == 2
        snaps = db_session.query(PortfolioSnapshot).all()
        user_ids = {s.user_id for s in snaps}
        assert user_ids == {11, 12}
        # テスター2人で均等按分: supply = 5000, debt = 1000 each
        for snap in snaps:
            assert Decimal(str(snap.total_supply_usd)) == Decimal("5000.000000")
            assert Decimal(str(snap.total_borrow_usd)) == Decimal("1000.000000")

    def test_aave_error_returns_skipped(self, db_session: Session) -> None:
        """Aave接続エラー時はスキップして snapshots_created=0 を返す。"""
        _make_admin(db_session, uid=1)
        db_session.commit()

        mock_client = MagicMock()
        mock_client.get_account_data.side_effect = Exception("RPC connection failed")

        with patch(
            "app.portfolio.snapshot_service.get_default_aave_client",
            return_value=mock_client,
        ):
            result = record_portfolio_snapshot(db_session)

        assert result["snapshots_created"] == 0
        assert result.get("skipped") is True
        assert db_session.query(PortfolioSnapshot).count() == 0

    def test_creates_daily_history(self, db_session: Session) -> None:
        """スナップショット保存時に日次PortfolioHistoryも作成される。"""
        _make_admin(db_session, uid=1)
        db_session.commit()

        account_data = _make_account_data("8000", "0", "999")
        with patch(
            "app.portfolio.snapshot_service.get_default_aave_client",
            return_value=self._mock_aave_client(account_data),
        ):
            record_portfolio_snapshot(db_session)

        history = (
            db_session.query(PortfolioHistory).filter_by(user_id=1, period_type="daily").first()
        )
        assert history is not None
        assert Decimal(str(history.open_value_usd)) == Decimal("8000")
        assert history.snapshot_count == 1

    def test_two_partners_separate_wallets(self, db_session: Session) -> None:
        """partner 別 wallet_address で各自の Aave データを取得してテスターに保存する。"""
        partner1 = _make_user(db_session, uid=10, role="partner", wallet_address="0xWallet10")
        partner2 = _make_user(db_session, uid=20, role="partner", wallet_address="0xWallet20")
        tester1 = _make_user(db_session, uid=11, invited_by=partner1.id)
        tester2 = _make_user(db_session, uid=21, invited_by=partner2.id)
        db_session.commit()

        # partner1 wallet → 6000 supply, partner2 wallet → 4000 supply
        def _side_effect(wallet: str) -> AccountData:
            if wallet == "0xWallet10":
                return _make_account_data("6000", "0", "999")
            if wallet == "0xWallet20":
                return _make_account_data("4000", "0", "999")
            return _make_account_data("0", "0", "1")

        mock_client = MagicMock()
        mock_client.get_account_data.side_effect = _side_effect

        with patch(
            "app.portfolio.snapshot_service.get_default_aave_client",
            return_value=mock_client,
        ):
            result = record_portfolio_snapshot(db_session)

        assert result["snapshots_created"] == 2
        snap1 = db_session.query(PortfolioSnapshot).filter_by(user_id=tester1.id).first()
        snap2 = db_session.query(PortfolioSnapshot).filter_by(user_id=tester2.id).first()
        assert snap1 is not None
        assert snap2 is not None
        # partner1 の wallet → supply=6000, partner2 の wallet → supply=4000
        assert Decimal(str(snap1.total_supply_usd)) == Decimal("6000.000000")
        assert Decimal(str(snap2.total_supply_usd)) == Decimal("4000.000000")

    def test_inactive_tester_excluded(self, db_session: Session) -> None:
        """is_active=False のテスターはスナップショット対象外。"""
        partner = _make_user(
            db_session, uid=10, role="partner", wallet_address="0xPartner10Inactive"
        )
        _make_user(db_session, uid=11, invited_by=partner.id)
        inactive = _make_user(db_session, uid=12, invited_by=partner.id)
        inactive.is_active = False
        db_session.commit()

        account_data = _make_account_data("10000", "0", "999")
        with patch(
            "app.portfolio.snapshot_service.get_default_aave_client",
            return_value=self._mock_aave_client(account_data),
        ):
            result = record_portfolio_snapshot(db_session)

        assert result["snapshots_created"] == 1
        snap = db_session.query(PortfolioSnapshot).first()
        assert snap.user_id == 11

    def test_infinity_hf_stored_as_none(self, db_session: Session) -> None:
        """HF が Infinity のとき health_factor=None で保存される。"""
        _make_admin(db_session, uid=1)
        db_session.commit()

        account_data = AccountData(
            total_collateral_usd=Decimal("5000"),
            total_debt_usd=Decimal("0"),
            available_borrows_usd=Decimal("5000"),
            health_factor=Decimal("Infinity"),
        )
        with patch(
            "app.portfolio.snapshot_service.get_default_aave_client",
            return_value=self._mock_aave_client(account_data),
        ):
            record_portfolio_snapshot(db_session)

        snap = db_session.query(PortfolioSnapshot).first()
        assert snap.health_factor is None
