# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_portfolio_snapshot_service.py
"""ポートフォリオスナップショットサービスのテスト。

wallet_address 伝播版 (Lane 14): パートナーごとに wallet_address を解決して
Aave get_account_data() を個別に呼ぶ。テスター 1 件以上を抱える各パートナーが
独立した Aave データを記録する。
"""

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
from app.partner.allocation_models import FundAllocation  # noqa: E402,F401
from app.portfolio.models import PortfolioHistory, PortfolioSnapshot  # noqa: E402
from app.portfolio.snapshot_service import (  # noqa: E402
    _get_wallet_address,
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


def _make_admin(db: Session, uid: int = 1, wallet: str | None = None) -> User:
    user = User(
        id=uid,
        email=f"admin{uid}@test.com",
        username=f"admin{uid}",
        hashed_password="x",
        role="admin",
        is_active=True,
        wallet_address=wallet,
    )
    db.add(user)
    db.flush()
    return user


def _make_user(
    db: Session,
    uid: int,
    invited_by: int | None = None,
    role: str = "viewer",
    wallet: str | None = None,
) -> User:
    user = User(
        id=uid,
        email=f"user{uid}@test.com",
        username=f"user{uid}",
        hashed_password="x",
        role=role,
        is_active=True,
        invited_by=invited_by,
        wallet_address=wallet,
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
# _get_wallet_address
# ---------------------------------------------------------------------------


class TestGetWalletAddress:
    def test_user_wallet_preferred(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """users.wallet_address が設定されていれば env より優先される。"""
        monkeypatch.setenv("AAVE_WALLET_ADDRESS", "0xENV_FALLBACK")
        u = _make_user(db_session, uid=100, wallet="0xUSER_WALLET")
        assert _get_wallet_address(u) == "0xUSER_WALLET"

    def test_env_fallback(self, db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
        """users.wallet_address が None なら env にフォールバックする。"""
        monkeypatch.setenv("AAVE_WALLET_ADDRESS", "0xENV_FALLBACK")
        u = _make_user(db_session, uid=100, wallet=None)
        assert _get_wallet_address(u) == "0xENV_FALLBACK"

    def test_both_unset_returns_empty(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """users.wallet_address も env も未設定なら空文字を返す。"""
        monkeypatch.delenv("AAVE_WALLET_ADDRESS", raising=False)
        u = _make_user(db_session, uid=100, wallet=None)
        assert _get_wallet_address(u) == ""


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
        _upsert_daily_history(db_session, 1, Decimal("7000"), Decimal("2.5"), now)
        db_session.flush()
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

    def test_no_testers_saves_admin_snapshot(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """テスターがいない場合、管理者ユーザーの wallet_address でスナップショットを保存する。"""
        _make_admin(db_session, uid=1, wallet="0xADMIN")
        monkeypatch.delenv("AAVE_WALLET_ADDRESS", raising=False)
        db_session.commit()

        account_data = _make_account_data("10000", "3000", "2.5")
        mock_client = self._mock_aave_client(account_data)
        with patch(
            "app.portfolio.snapshot_service.get_default_aave_client",
            return_value=mock_client,
        ):
            result = record_portfolio_snapshot(db_session)

        assert result["snapshots_created"] == 1
        # admin の wallet で Aave が呼ばれたことを確認
        mock_client.get_account_data.assert_called_once_with("0xADMIN")

        snap = db_session.query(PortfolioSnapshot).first()
        assert snap is not None
        assert snap.user_id == 1
        assert Decimal(str(snap.total_supply_usd)) == Decimal("10000")
        assert Decimal(str(snap.total_borrow_usd)) == Decimal("3000")
        assert Decimal(str(snap.total_value_usd)) == Decimal("7000")  # net_worth

    def test_no_testers_admin_uses_env_fallback(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """admin.wallet_address が None でも AAVE_WALLET_ADDRESS env で fallback して保存される。"""
        _make_admin(db_session, uid=1, wallet=None)
        monkeypatch.setenv("AAVE_WALLET_ADDRESS", "0xENV_ADMIN")
        db_session.commit()

        account_data = _make_account_data("5000", "1000", "3.0")
        mock_client = self._mock_aave_client(account_data)
        with patch(
            "app.portfolio.snapshot_service.get_default_aave_client",
            return_value=mock_client,
        ):
            result = record_portfolio_snapshot(db_session)

        assert result["snapshots_created"] == 1
        mock_client.get_account_data.assert_called_once_with("0xENV_ADMIN")

    def test_with_testers_saves_per_tester(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """テスター 2 人が同じパートナー配下のとき、partner.wallet_address で 1 回 Aave を呼んで均等按分する。"""
        monkeypatch.delenv("AAVE_WALLET_ADDRESS", raising=False)
        partner = _make_user(db_session, uid=10, role="partner", wallet="0xPARTNER_10")
        _make_user(db_session, uid=11, invited_by=partner.id)
        _make_user(db_session, uid=12, invited_by=partner.id)
        db_session.commit()

        account_data = _make_account_data("10000", "2000", "3.0")
        mock_client = self._mock_aave_client(account_data)
        with patch(
            "app.portfolio.snapshot_service.get_default_aave_client",
            return_value=mock_client,
        ):
            result = record_portfolio_snapshot(db_session)

        assert result["snapshots_created"] == 2
        assert result["partners_processed"] == 1
        # partner の wallet で 1 回だけ呼ばれている
        mock_client.get_account_data.assert_called_once_with("0xPARTNER_10")

        snaps = db_session.query(PortfolioSnapshot).all()
        user_ids = {s.user_id for s in snaps}
        assert user_ids == {11, 12}
        # テスター 2 人で均等按分: supply = 5000, debt = 1000 each
        for snap in snaps:
            assert Decimal(str(snap.total_supply_usd)) == Decimal("5000.000000")
            assert Decimal(str(snap.total_borrow_usd)) == Decimal("1000.000000")

    def test_partner_wallet_propagation_each_partner_isolated(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lane 14 主旨: 各 partner.wallet_address で別個に Aave を fetch する。"""
        monkeypatch.delenv("AAVE_WALLET_ADDRESS", raising=False)
        partner1 = _make_user(db_session, uid=10, role="partner", wallet="0xWALLET_P1")
        partner2 = _make_user(db_session, uid=20, role="partner", wallet="0xWALLET_P2")
        tester1 = _make_user(db_session, uid=11, invited_by=partner1.id)
        tester2 = _make_user(db_session, uid=21, invited_by=partner2.id)
        db_session.commit()

        mock_client = MagicMock()
        # partner1 は 8000/1000、partner2 は 4000/500 の独立した Aave データを持つ
        partner1_data = _make_account_data("8000", "1000", "2.5")
        partner2_data = _make_account_data("4000", "500", "3.0")

        def get_data(wallet: str) -> AccountData:
            if wallet == "0xWALLET_P1":
                return partner1_data
            if wallet == "0xWALLET_P2":
                return partner2_data
            raise AssertionError(f"unexpected wallet: {wallet!r}")

        mock_client.get_account_data.side_effect = get_data

        with patch(
            "app.portfolio.snapshot_service.get_default_aave_client",
            return_value=mock_client,
        ):
            result = record_portfolio_snapshot(db_session)

        assert result["snapshots_created"] == 2
        assert result["partners_processed"] == 2

        # 各 partner の wallet で 1 回ずつ呼ばれている
        called_wallets = {c.args[0] for c in mock_client.get_account_data.call_args_list}
        assert called_wallets == {"0xWALLET_P1", "0xWALLET_P2"}

        snap1 = db_session.query(PortfolioSnapshot).filter_by(user_id=tester1.id).first()
        snap2 = db_session.query(PortfolioSnapshot).filter_by(user_id=tester2.id).first()
        assert snap1 is not None
        assert snap2 is not None
        # tester1 は partner1 の全データ (testers=1)
        assert Decimal(str(snap1.total_supply_usd)) == Decimal("8000.000000")
        assert Decimal(str(snap1.total_borrow_usd)) == Decimal("1000.000000")
        # tester2 は partner2 の全データ (testers=1)
        assert Decimal(str(snap2.total_supply_usd)) == Decimal("4000.000000")
        assert Decimal(str(snap2.total_borrow_usd)) == Decimal("500.000000")

    def test_partner_no_wallet_is_skipped_not_env_fallback(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """partner.wallet_address が None のとき env AAVE_WALLET_ADDRESS にフォールバックせずスキップする。

        NULL wallet ガード: partner ループでは env fallback を使わない (ウォレット汚染防止)。
        """
        monkeypatch.setenv("AAVE_WALLET_ADDRESS", "0xENV_FALLBACK")
        partner = _make_user(db_session, uid=10, role="partner", wallet=None)
        _make_user(db_session, uid=11, invited_by=partner.id)
        db_session.commit()

        account_data = _make_account_data("6000", "0", "999")
        mock_client = self._mock_aave_client(account_data)
        with patch(
            "app.portfolio.snapshot_service.get_default_aave_client",
            return_value=mock_client,
        ):
            result = record_portfolio_snapshot(db_session)

        # partner は wallet 未設定のためスキップ (env fallback 禁止)
        assert result["snapshots_created"] == 0
        assert result["partners_skipped"] == 1
        mock_client.get_account_data.assert_not_called()

    def test_partner_skipped_when_no_wallet_and_no_env(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """partner.wallet_address も env も未設定なら当該 partner はスキップ（fail-open）。"""
        monkeypatch.delenv("AAVE_WALLET_ADDRESS", raising=False)
        partner_ok = _make_user(db_session, uid=10, role="partner", wallet="0xPARTNER_10")
        partner_no_wallet = _make_user(db_session, uid=20, role="partner", wallet=None)
        _make_user(db_session, uid=11, invited_by=partner_ok.id)
        _make_user(db_session, uid=21, invited_by=partner_no_wallet.id)
        db_session.commit()

        account_data = _make_account_data("8000", "0", "999")
        mock_client = self._mock_aave_client(account_data)
        with patch(
            "app.portfolio.snapshot_service.get_default_aave_client",
            return_value=mock_client,
        ):
            result = record_portfolio_snapshot(db_session)

        # partner_ok のみ処理されて partner_no_wallet はスキップ
        assert result["snapshots_created"] == 1
        assert result["partners_processed"] == 1
        assert result["partners_skipped"] == 1
        mock_client.get_account_data.assert_called_once_with("0xPARTNER_10")

        # tester2 (partner_no_wallet の招待) には snapshot が無い
        assert db_session.query(PortfolioSnapshot).filter_by(user_id=21).count() == 0
        # tester1 (partner_ok の招待) には snapshot がある
        assert db_session.query(PortfolioSnapshot).filter_by(user_id=11).count() == 1

    def test_partner_aave_error_skips_only_that_partner(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """1 partner の Aave fetch 失敗時、他 partner は継続して snapshot を作る（fail-open per partner）。"""
        monkeypatch.delenv("AAVE_WALLET_ADDRESS", raising=False)
        partner1 = _make_user(db_session, uid=10, role="partner", wallet="0xOK")
        partner2 = _make_user(db_session, uid=20, role="partner", wallet="0xFAIL")
        _make_user(db_session, uid=11, invited_by=partner1.id)
        _make_user(db_session, uid=21, invited_by=partner2.id)
        db_session.commit()

        def side_effect(wallet: str) -> AccountData:
            if wallet == "0xOK":
                return _make_account_data("7000", "0", "999")
            raise Exception("RPC connection failed")

        mock_client = MagicMock()
        mock_client.get_account_data.side_effect = side_effect
        with patch(
            "app.portfolio.snapshot_service.get_default_aave_client",
            return_value=mock_client,
        ):
            result = record_portfolio_snapshot(db_session)

        assert result["snapshots_created"] == 1
        assert result["partners_processed"] == 1
        assert result["partners_skipped"] == 1
        # tester2 には snapshot 無し
        assert db_session.query(PortfolioSnapshot).filter_by(user_id=21).count() == 0

    def test_aave_client_init_error_returns_skipped(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Aave クライアント初期化失敗時はスキップして snapshots_created=0 を返す。"""
        _make_admin(db_session, uid=1, wallet="0xADMIN")
        monkeypatch.delenv("AAVE_WALLET_ADDRESS", raising=False)
        db_session.commit()

        def raise_init() -> None:
            raise Exception("RPC connection failed")

        with patch(
            "app.portfolio.snapshot_service.get_default_aave_client",
            side_effect=raise_init,
        ):
            result = record_portfolio_snapshot(db_session)

        assert result["snapshots_created"] == 0
        assert result.get("skipped") is True
        assert db_session.query(PortfolioSnapshot).count() == 0

    def test_creates_daily_history(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """スナップショット保存時に日次PortfolioHistoryも作成される。"""
        _make_admin(db_session, uid=1, wallet="0xADMIN")
        monkeypatch.delenv("AAVE_WALLET_ADDRESS", raising=False)
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

    def test_fund_allocation_amount_does_not_affect_snapshot(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """新ロジック: FundAllocation の金額に関係なく、各 partner は自分の Aave 全額を記録する。

        旧ロジック (グローバル fetch + ratio 按分) では FundAllocation の比率で
        partner1=60%, partner2=40% に分割されていたが、wallet_address 伝播版では
        各 partner が独立した Aave データを取得するため ratio は適用されない。
        """
        monkeypatch.delenv("AAVE_WALLET_ADDRESS", raising=False)
        partner1 = _make_user(db_session, uid=10, role="partner", wallet="0xP1")
        partner2 = _make_user(db_session, uid=20, role="partner", wallet="0xP2")
        tester1 = _make_user(db_session, uid=11, invited_by=partner1.id)
        tester2 = _make_user(db_session, uid=21, invited_by=partner2.id)

        # 旧テストと同じ allocations: partner1=6000, partner2=4000
        db_session.add(
            FundAllocation(
                partner_id=partner1.id,
                tester_name="tester1",
                allocated_amount_usd=Decimal("6000"),
                status="active",
            )
        )
        db_session.add(
            FundAllocation(
                partner_id=partner2.id,
                tester_name="tester2",
                allocated_amount_usd=Decimal("4000"),
                status="active",
            )
        )
        db_session.commit()

        # 両 partner で異なる Aave データを返す
        def get_data(wallet: str) -> AccountData:
            if wallet == "0xP1":
                return _make_account_data("10000", "0", "999")
            if wallet == "0xP2":
                return _make_account_data("3000", "0", "999")
            raise AssertionError(f"unexpected wallet: {wallet!r}")

        mock_client = MagicMock()
        mock_client.get_account_data.side_effect = get_data
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
        # FundAllocation の比率は無視: 各 partner の wallet が返した実値を使う
        assert Decimal(str(snap1.total_supply_usd)) == Decimal("10000.000000")
        assert Decimal(str(snap2.total_supply_usd)) == Decimal("3000.000000")

    def test_inactive_tester_excluded(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """is_active=False のテスターはスナップショット対象外。"""
        monkeypatch.delenv("AAVE_WALLET_ADDRESS", raising=False)
        partner = _make_user(db_session, uid=10, role="partner", wallet="0xP10")
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
        # アクティブテスター 1 人なので全額が tester11 へ
        assert Decimal(str(snap.total_supply_usd)) == Decimal("10000.000000")

    def test_infinity_hf_stored_as_none(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """HF が Infinity のとき health_factor=None で保存される。"""
        _make_admin(db_session, uid=1, wallet="0xADMIN")
        monkeypatch.delenv("AAVE_WALLET_ADDRESS", raising=False)
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
