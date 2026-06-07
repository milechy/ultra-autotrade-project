# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_api_v1_fees.py
"""F-8a: ``/api/v1/fees/*`` 8 endpoints のテスト。

カバー範囲:
- 認可: 401 (未認証) / 403 (権限不足) / 200 (正常)
- 正常系: レスポンス構造、Decimal が文字列で返る
- 空データ: my-summary は 0 / months_count=0、my-history は []
- simulate: F-5 FeeCalculator と完全一致
- admin endpoints: all-users, uata-income, finalize-month (501)

DB は SQLite テスト DB (Base + V10Base 両方を create_all)。
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

os.environ["JWT_SECRET_KEY"] = "test-secret-key-api-v1-fees"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["JWT_ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"
os.environ["INITIAL_ADMIN_EMAIL"] = "fees_admin@example.com"

from app.auth.models import InvestmentTier, RiskMode, UserRole  # noqa: E402
from app.auth.schemas import UserCreateRequest  # noqa: E402
from app.auth.service import AuthService  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.fees import FeeCalculationInput, FeeCalculator  # noqa: E402
from app.fees.models import FeeConfigV10, FeeTransaction  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.helpers.fee_config_factory import make_v10_default_config  # noqa: E402

_JST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_db() -> Generator[tuple, None, None]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    # FeeConfigV10 / FeeTransaction は app.database.Base に統合済み (F-13 billing cleanup)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    yield override_get_db, SessionLocal
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


@pytest.fixture()
def client(test_db) -> TestClient:
    override_get_db, _ = test_db
    os.environ["INITIAL_ADMIN_EMAIL"] = "fees_admin@example.com"
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _seed_active_config(db: Session) -> FeeConfigV10:
    """make_v10_default_config を DB に投入する。"""
    cfg = make_v10_default_config()
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg


def _register_admin(client: TestClient) -> str:
    """初回 register で admin になる → access_token を返す。"""
    client.post(
        "/auth/register",
        json={
            "email": "fees_admin@example.com",
            "username": "feesadmin",
            "password": "adminpassword123",
        },
    )
    r = client.post(
        "/auth/login",
        json={"email": "fees_admin@example.com", "password": "adminpassword123"},
    )
    return r.json()["access_token"]


def _create_user(
    SessionFactory,
    *,
    email: str,
    username: str,
    role: UserRole = UserRole.VIEWER,
    password: str = "password123",
) -> int:
    """admin 経由で登録できないため、AuthService 直叩きでテスト用ユーザー作成。"""
    with SessionFactory() as db:
        req = UserCreateRequest(email=email, username=username, password=password, role=role)
        user = AuthService.create_user(db, req)
        return user.id


def _login(client: TestClient, email: str, password: str = "password123") -> str:
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _add_fee_tx(
    SessionFactory,
    *,
    user_id: int,
    month: date,
    fee_amount: Decimal = Decimal("1000"),
    sub_amount: Decimal = Decimal("3000"),
    takehome: Decimal = Decimal("23000"),
    excess: Decimal = Decimal("0"),
    affiliate_id: int | None = None,
    affiliate_amount: Decimal = Decimal("0"),
    finalized: bool = False,
) -> None:
    with SessionFactory() as db:
        tx = FeeTransaction(
            user_id=user_id,
            calculation_month=month,
            tier="MIDDLE",
            risk_mode="balanced",
            deposit_amount_jpy=Decimal("1000000"),
            gross_profit_jpy=Decimal("100000"),
            expense_jpy=Decimal("0"),
            net_profit_jpy=Decimal("100000"),
            fee_rate_applied=Decimal("0.25"),
            fee_amount_jpy=fee_amount,
            subscription_rate_applied=Decimal("0.003"),
            subscription_amount_jpy=sub_amount,
            subscription_protected=False,
            monthly_yield_cap_applied=Decimal("0.023"),
            yield_excess_to_uata_jpy=excess,
            user_takehome_jpy=takehome,
            affiliate_id=affiliate_id,
            affiliate_amount_jpy=affiliate_amount,
            finalized_at=datetime.now(timezone.utc) if finalized else None,
        )
        db.add(tx)
        db.commit()


# ===========================================================================
# Authorization (401 / 403)
# ===========================================================================


class TestAuthorization:
    """各 endpoint の認可境界テスト。"""

    def test_config_unauthenticated_returns_401(self, client: TestClient) -> None:
        r = client.get("/api/v1/fees/config")
        assert r.status_code == 401

    def test_my_summary_unauthenticated_returns_401(self, client: TestClient) -> None:
        r = client.get("/api/v1/fees/my-summary")
        assert r.status_code == 401

    def test_my_history_unauthenticated_returns_401(self, client: TestClient) -> None:
        r = client.get("/api/v1/fees/my-history")
        assert r.status_code == 401

    def test_simulate_unauthenticated_returns_401(self, client: TestClient) -> None:
        r = client.post(
            "/api/v1/fees/simulate",
            json={
                "deposit_jpy": "1000000",
                "gross_profit_jpy": "10000",
                "user_tier": "LOWER",
                "user_risk_mode": "conservative",
            },
        )
        assert r.status_code == 401

    def test_affiliate_earnings_unauthenticated_returns_401(self, client: TestClient) -> None:
        r = client.get("/api/v1/fees/affiliate-earnings")
        assert r.status_code == 401

    def test_all_users_requires_admin(self, client: TestClient, test_db) -> None:
        _, SessionFactory = test_db
        # 初回 register で admin が出来るが、もう 1 人 viewer を作る
        _register_admin(client)
        _create_user(SessionFactory, email="viewer@example.com", username="viewer1")
        token = _login(client, "viewer@example.com")
        r = client.get(
            "/api/v1/fees/all-users",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403

    def test_uata_income_requires_admin(self, client: TestClient, test_db) -> None:
        _, SessionFactory = test_db
        _register_admin(client)
        _create_user(SessionFactory, email="viewer@example.com", username="viewer1")
        token = _login(client, "viewer@example.com")
        r = client.get(
            "/api/v1/fees/uata-income?month_from=2026-05-01&month_to=2026-05-01",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403

    def test_finalize_month_requires_admin(self, client: TestClient, test_db) -> None:
        _, SessionFactory = test_db
        _register_admin(client)
        _create_user(SessionFactory, email="viewer@example.com", username="viewer1")
        token = _login(client, "viewer@example.com")
        r = client.post(
            "/api/v1/fees/finalize-month?month=2026-05-01",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403


# ===========================================================================
# /config endpoint
# ===========================================================================


class TestFeeConfigEndpoint:
    def test_503_when_no_active_config(self, client: TestClient) -> None:
        token = _register_admin(client)
        r = client.get(
            "/api/v1/fees/config",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 503

    def test_200_returns_v10_default(self, client: TestClient, test_db) -> None:
        _, SessionFactory = test_db
        with SessionFactory() as db:
            _seed_active_config(db)
        token = _register_admin(client)
        r = client.get(
            "/api/v1/fees/config",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["config_name"] == "v10_default"
        assert body["tier_thresholds_jpy"] == [1000000, 10000000]
        assert body["tier_fee_rates"] == [0.30, 0.25, 0.20]
        assert body["subscription_rates"]["conservative"] == 0.0
        assert body["subscription_rates"]["balanced"] == 0.003
        # Numeric(6,4) のため "0.1000" として返る (紹介報酬 = 紹介友達の実受取利益 × 10%)
        assert Decimal(body["affiliate_rate"]) == Decimal("0.10")
        assert body["is_active"] is True


# ===========================================================================
# /my-summary endpoint
# ===========================================================================


class TestMySummaryEndpoint:
    def test_returns_zeros_when_no_transactions(self, client: TestClient, test_db) -> None:
        _, SessionFactory = test_db
        with SessionFactory() as db:
            _seed_active_config(db)
        token = _register_admin(client)
        r = client.get(
            "/api/v1/fees/my-summary",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["months_count"] == 0
        # SQLAlchemy SUM の coalesce 結果は SQLite で 0 を返すが、Numeric(18,2) 列の合計は
        # PG では "0.00" になる。Decimal 比較で 0 一致を確認。
        assert Decimal(body["total_fee_paid_jpy"]) == Decimal("0")
        assert Decimal(body["total_subscription_paid_jpy"]) == Decimal("0")

    def test_aggregates_only_own_transactions(self, client: TestClient, test_db) -> None:
        _, SessionFactory = test_db
        with SessionFactory() as db:
            _seed_active_config(db)
        # admin (user1) 登録 + viewer (user2) 作成
        token = _register_admin(client)
        with SessionFactory() as db:
            admin_id = AuthService.get_user_by_email(db, "fees_admin@example.com").id
        viewer_id = _create_user(SessionFactory, email="other@example.com", username="other1")

        # admin に 2 ヶ月、other に 1 ヶ月
        _add_fee_tx(
            SessionFactory,
            user_id=admin_id,
            month=date(2026, 4, 1),
            fee_amount=Decimal("1000"),
            sub_amount=Decimal("3000"),
        )
        _add_fee_tx(
            SessionFactory,
            user_id=admin_id,
            month=date(2026, 5, 1),
            fee_amount=Decimal("2000"),
            sub_amount=Decimal("3000"),
        )
        _add_fee_tx(
            SessionFactory,
            user_id=viewer_id,
            month=date(2026, 4, 1),
            fee_amount=Decimal("9999"),
            sub_amount=Decimal("9999"),
        )

        r = client.get(
            "/api/v1/fees/my-summary",
            headers={"Authorization": f"Bearer {token}"},
        )
        body = r.json()
        # admin の 2 ヶ月分のみ
        assert body["months_count"] == 2
        assert Decimal(body["total_fee_paid_jpy"]) == Decimal("3000")  # 1000 + 2000
        assert Decimal(body["total_subscription_paid_jpy"]) == Decimal("6000")  # 3000 + 3000


# ===========================================================================
# /my-history endpoint
# ===========================================================================


class TestMyHistoryEndpoint:
    def test_empty_returns_empty_list(self, client: TestClient, test_db) -> None:
        _, SessionFactory = test_db
        with SessionFactory() as db:
            _seed_active_config(db)
        token = _register_admin(client)
        r = client.get(
            "/api/v1/fees/my-history",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_only_own_history_desc(self, client: TestClient, test_db) -> None:
        _, SessionFactory = test_db
        with SessionFactory() as db:
            _seed_active_config(db)
        token = _register_admin(client)
        with SessionFactory() as db:
            admin_id = AuthService.get_user_by_email(db, "fees_admin@example.com").id
        other_id = _create_user(SessionFactory, email="other@example.com", username="other1")

        _add_fee_tx(SessionFactory, user_id=admin_id, month=date(2026, 4, 1))
        _add_fee_tx(SessionFactory, user_id=admin_id, month=date(2026, 5, 1))
        _add_fee_tx(SessionFactory, user_id=other_id, month=date(2026, 5, 1))

        r = client.get(
            "/api/v1/fees/my-history",
            headers={"Authorization": f"Bearer {token}"},
        )
        rows = r.json()
        assert len(rows) == 2
        # 降順
        assert rows[0]["calculation_month"] == "2026-05-01"
        assert rows[1]["calculation_month"] == "2026-04-01"

    def test_limit_param_caps_results(self, client: TestClient, test_db) -> None:
        _, SessionFactory = test_db
        with SessionFactory() as db:
            _seed_active_config(db)
        token = _register_admin(client)
        with SessionFactory() as db:
            admin_id = AuthService.get_user_by_email(db, "fees_admin@example.com").id
        for m in (1, 2, 3, 4, 5):
            _add_fee_tx(SessionFactory, user_id=admin_id, month=date(2026, m, 1))

        r = client.get(
            "/api/v1/fees/my-history?limit=2",
            headers={"Authorization": f"Bearer {token}"},
        )
        rows = r.json()
        assert len(rows) == 2
        assert rows[0]["calculation_month"] == "2026-05-01"


# ===========================================================================
# /simulate endpoint — must match FeeCalculator
# ===========================================================================


class TestSimulateMatchesCalculator:
    def test_simulate_matches_calculator_lower_conservative(
        self, client: TestClient, test_db
    ) -> None:
        _, SessionFactory = test_db
        with SessionFactory() as db:
            _seed_active_config(db)
        token = _register_admin(client)
        with SessionFactory() as db:
            admin_id = AuthService.get_user_by_email(db, "fees_admin@example.com").id

        payload = {
            "deposit_jpy": "100000",
            "gross_profit_jpy": "1000",
            "expense_jpy": "100",
            "user_tier": "LOWER",
            "user_risk_mode": "conservative",
            "is_first_month": False,
        }
        r = client.post(
            "/api/v1/fees/simulate",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()

        # F-5 を直接呼んで一致確認
        config = make_v10_default_config()
        calc = FeeCalculator(config)
        expected = calc.calculate_monthly(
            FeeCalculationInput(
                user_id=admin_id,
                calculation_month=date.today().replace(day=1),
                deposit_jpy=Decimal("100000"),
                gross_profit_jpy=Decimal("1000"),
                expense_jpy=Decimal("100"),
                user_tier=InvestmentTier.LOWER,
                user_risk_mode=RiskMode.CONSERVATIVE,
                is_first_month=False,
            )
        )
        assert body["net_profit_jpy"] == str(expected.net_profit_jpy)
        assert body["fee_amount_jpy"] == str(expected.fee_amount_jpy)
        assert body["user_takehome_jpy"] == str(expected.user_takehome_jpy)
        assert body["subscription_protected"] == expected.subscription_protected

    def test_simulate_subscription_protection_branch(self, client: TestClient, test_db) -> None:
        _, SessionFactory = test_db
        with SessionFactory() as db:
            _seed_active_config(db)
        token = _register_admin(client)
        # balanced + 1000 利益 (sub=3000 > 1000) → 保護発動
        r = client.post(
            "/api/v1/fees/simulate",
            json={
                "deposit_jpy": "1000000",
                "gross_profit_jpy": "1000",
                "user_tier": "MIDDLE",
                "user_risk_mode": "balanced",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        body = r.json()
        assert body["subscription_protected"] is True
        assert body["subscription_amount_jpy"] == "0"
        assert body["yield_excess_to_uata_jpy"] == "1000"
        assert body["user_takehome_jpy"] == "0"

    def test_simulate_first_month_zero_subscription(self, client: TestClient, test_db) -> None:
        _, SessionFactory = test_db
        with SessionFactory() as db:
            _seed_active_config(db)
        token = _register_admin(client)
        r = client.post(
            "/api/v1/fees/simulate",
            json={
                "deposit_jpy": "1000000",
                "gross_profit_jpy": "10000",
                "user_tier": "MIDDLE",
                "user_risk_mode": "balanced",
                "is_first_month": True,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        body = r.json()
        assert body["subscription_rate_applied"] == "0"
        assert body["subscription_amount_jpy"] == "0"

    def test_simulate_503_when_no_active_config(self, client: TestClient) -> None:
        token = _register_admin(client)
        r = client.post(
            "/api/v1/fees/simulate",
            json={
                "deposit_jpy": "100000",
                "gross_profit_jpy": "1000",
                "user_tier": "LOWER",
                "user_risk_mode": "conservative",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 503


# ===========================================================================
# /affiliate-earnings endpoint
# ===========================================================================


class TestAffiliateEarningsEndpoint:
    def test_empty_returns_empty_list(self, client: TestClient, test_db) -> None:
        _, SessionFactory = test_db
        with SessionFactory() as db:
            _seed_active_config(db)
        token = _register_admin(client)
        r = client.get(
            "/api/v1/fees/affiliate-earnings",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_rows_where_self_is_affiliate(self, client: TestClient, test_db) -> None:
        _, SessionFactory = test_db
        with SessionFactory() as db:
            _seed_active_config(db)
        token = _register_admin(client)
        with SessionFactory() as db:
            admin_id = AuthService.get_user_by_email(db, "fees_admin@example.com").id
        invitee_id = _create_user(SessionFactory, email="invitee@example.com", username="inv1")

        # invitee の月次に admin が affiliate として記録されている
        _add_fee_tx(
            SessionFactory,
            user_id=invitee_id,
            month=date(2026, 5, 1),
            sub_amount=Decimal("3000"),
            affiliate_id=admin_id,
            affiliate_amount=Decimal("900"),
        )

        r = client.get(
            "/api/v1/fees/affiliate-earnings",
            headers={"Authorization": f"Bearer {token}"},
        )
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["invitee_user_id"] == invitee_id
        assert Decimal(rows[0]["affiliate_amount_jpy"]) == Decimal("900")
        assert Decimal(rows[0]["invitee_subscription_amount_jpy"]) == Decimal("3000")


# ===========================================================================
# Admin: /all-users
# ===========================================================================


class TestAllUsersEndpoint:
    def test_admin_gets_all_users_for_month(self, client: TestClient, test_db) -> None:
        _, SessionFactory = test_db
        with SessionFactory() as db:
            _seed_active_config(db)
        token = _register_admin(client)
        with SessionFactory() as db:
            admin_id = AuthService.get_user_by_email(db, "fees_admin@example.com").id
        other_id = _create_user(SessionFactory, email="other@example.com", username="other1")

        _add_fee_tx(SessionFactory, user_id=admin_id, month=date(2026, 5, 1))
        _add_fee_tx(SessionFactory, user_id=other_id, month=date(2026, 5, 1))
        _add_fee_tx(SessionFactory, user_id=admin_id, month=date(2026, 4, 1))

        r = client.get(
            "/api/v1/fees/all-users?month=2026-05-01",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        rows = r.json()
        # 2026-05-01 の 2 件のみ (4 月分は含まれない)
        assert len(rows) == 2
        user_ids = {row["user_id"] for row in rows}
        assert {admin_id, other_id} == user_ids

    def test_admin_default_month_is_current(self, client: TestClient, test_db) -> None:
        _, SessionFactory = test_db
        with SessionFactory() as db:
            _seed_active_config(db)
        token = _register_admin(client)
        with SessionFactory() as db:
            admin_id = AuthService.get_user_by_email(db, "fees_admin@example.com").id
        current_month = date.today().replace(day=1)
        _add_fee_tx(SessionFactory, user_id=admin_id, month=current_month)

        # month 引数省略
        r = client.get(
            "/api/v1/fees/all-users",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 1


# ===========================================================================
# Admin: /finalize-month (F-7 実装済み)
# ===========================================================================


def _add_portfolio_snapshot(
    SessionFactory,
    *,
    user_id: int,
    recorded_at: datetime,
    total_supply_usd: Decimal,
    total_value_usd: Decimal | None = None,
) -> None:
    from app.portfolio.models import PortfolioSnapshot  # noqa: PLC0415

    with SessionFactory() as db:
        snap = PortfolioSnapshot(
            user_id=user_id,
            total_value_usd=total_value_usd or total_supply_usd,
            total_supply_usd=total_supply_usd,
            total_borrow_usd=Decimal("0"),
            health_factor=None,
            recorded_at=recorded_at,
        )
        db.add(snap)
        db.commit()


def _add_transaction(
    SessionFactory,
    *,
    user_id: int,
    created_at: datetime,
    status: str = "completed",
    is_dry_run: bool = False,
    operation: str = "deposit",
    amount_usd: Decimal = Decimal("100"),
) -> None:
    from app.transactions.models import Transaction  # noqa: PLC0415

    with SessionFactory() as db:
        txn = Transaction(
            user_id=user_id,
            operation=operation,
            asset="USDC",
            amount=amount_usd,
            amount_usd=amount_usd,
            chain="polygon",
            status=status,
            is_dry_run=is_dry_run,
            created_at=created_at,
        )
        db.add(txn)
        db.commit()


class TestFinalizeMonth:
    """F-7: POST /api/v1/fees/finalize-month の正常系・境界テスト。"""

    def test_requires_admin(self, client: TestClient) -> None:
        r = client.post("/api/v1/fees/finalize-month?month=2026-05-01")
        assert r.status_code == 401

    def test_user_without_snapshot_is_skipped(self, client: TestClient, test_db) -> None:
        override_get_db, SessionFactory = test_db
        with SessionFactory() as db:
            _seed_active_config(db)
        token = _register_admin(client)

        r = client.post(
            "/api/v1/fees/finalize-month?month=2026-05-01",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["users_processed"] == 0
        assert body["users_skipped_no_snapshot"] >= 1

    def test_creates_fee_transaction_for_user_with_snapshots(
        self, client: TestClient, test_db
    ) -> None:
        override_get_db, SessionFactory = test_db
        with SessionFactory() as db:
            _seed_active_config(db)
        token = _register_admin(client)
        user_id = _create_user(SessionFactory, email="fee_u@example.com", username="fee_u")

        month_start = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)
        month_end = datetime(2026, 5, 31, 23, 0, tzinfo=timezone.utc)
        _add_portfolio_snapshot(
            SessionFactory,
            user_id=user_id,
            recorded_at=month_start,
            total_supply_usd=Decimal("10000"),
        )
        _add_portfolio_snapshot(
            SessionFactory,
            user_id=user_id,
            recorded_at=month_end,
            total_supply_usd=Decimal("10200"),  # $200 利益
        )

        r = client.post(
            "/api/v1/fees/finalize-month?month=2026-05-01&usd_jpy_rate=150",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["users_processed"] == 1
        assert body["calculation_month"] == "2026-05-01"
        assert Decimal(body["total_fee_jpy"]) > Decimal("0")

        with SessionFactory() as db:
            tx = db.scalar(select(FeeTransaction).where(FeeTransaction.user_id == user_id))
            assert tx is not None
            assert tx.deposit_amount_jpy == Decimal("1530000")  # 10200 * 150
            assert tx.gross_profit_jpy == Decimal("30000")  # 200 * 150

    def test_dry_run_does_not_write_db(self, client: TestClient, test_db) -> None:
        override_get_db, SessionFactory = test_db
        with SessionFactory() as db:
            _seed_active_config(db)
        token = _register_admin(client)
        user_id = _create_user(SessionFactory, email="dryrun@example.com", username="dryrun_u")
        _add_portfolio_snapshot(
            SessionFactory,
            user_id=user_id,
            recorded_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            total_supply_usd=Decimal("5000"),
        )
        _add_portfolio_snapshot(
            SessionFactory,
            user_id=user_id,
            recorded_at=datetime(2026, 5, 31, tzinfo=timezone.utc),
            total_supply_usd=Decimal("5100"),
        )

        r = client.post(
            "/api/v1/fees/finalize-month?month=2026-05-01&dry_run=true",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["dry_run"] is True
        assert r.json()["users_processed"] == 1

        with SessionFactory() as db:
            count = db.scalar(
                select(func.count(FeeTransaction.id)).where(FeeTransaction.user_id == user_id)
            )
            assert count == 0  # dry_run なので DB 未書込

    def test_expense_jpy_calculated_from_completed_trades(
        self, client: TestClient, test_db
    ) -> None:
        """F-9: 完了トレード件数 × TRADE_FIXED_COST_USD × usd_jpy_rate が expense_jpy に反映される。"""
        override_get_db, SessionFactory = test_db
        with SessionFactory() as db:
            _seed_active_config(db)
        token = _register_admin(client)
        user_id = _create_user(SessionFactory, email="exp@example.com", username="exp_u")

        month_dt = datetime(2026, 5, 15, tzinfo=timezone.utc)
        _add_portfolio_snapshot(
            SessionFactory,
            user_id=user_id,
            recorded_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            total_supply_usd=Decimal("10000"),
        )
        _add_portfolio_snapshot(
            SessionFactory,
            user_id=user_id,
            recorded_at=datetime(2026, 5, 31, tzinfo=timezone.utc),
            total_supply_usd=Decimal("10200"),
        )
        # 完了トレード 2 件
        _add_transaction(SessionFactory, user_id=user_id, created_at=month_dt)
        _add_transaction(SessionFactory, user_id=user_id, created_at=month_dt)
        # 除外: dry_run / pending / 別月
        _add_transaction(SessionFactory, user_id=user_id, created_at=month_dt, is_dry_run=True)
        _add_transaction(SessionFactory, user_id=user_id, created_at=month_dt, status="pending")
        _add_transaction(
            SessionFactory,
            user_id=user_id,
            created_at=datetime(2026, 4, 30, tzinfo=timezone.utc),
        )

        os.environ["TRADE_FIXED_COST_USD"] = "0.27"
        r = client.post(
            "/api/v1/fees/finalize-month?month=2026-05-01&usd_jpy_rate=150",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["users_processed"] == 1

        with SessionFactory() as db:
            tx = db.scalar(select(FeeTransaction).where(FeeTransaction.user_id == user_id))
            assert tx is not None
            # 2 trades × $0.27 × 150 = 81 JPY (ROUND_DOWN)
            assert tx.expense_jpy == Decimal("81")

    def test_already_finalized_is_skipped(self, client: TestClient, test_db) -> None:
        override_get_db, SessionFactory = test_db
        with SessionFactory() as db:
            _seed_active_config(db)
        token = _register_admin(client)
        user_id = _create_user(SessionFactory, email="finalized@example.com", username="fin_u")
        _add_fee_tx(
            SessionFactory,
            user_id=user_id,
            month=date(2026, 5, 1),
            finalized=True,
        )
        _add_portfolio_snapshot(
            SessionFactory,
            user_id=user_id,
            recorded_at=datetime(2026, 5, 15, tzinfo=timezone.utc),
            total_supply_usd=Decimal("8000"),
        )

        r = client.post(
            "/api/v1/fees/finalize-month?month=2026-05-01",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["users_skipped_already_finalized"] >= 1
        assert body["users_processed"] == 0


# ===========================================================================
# Admin: /uata-income
# ===========================================================================


class TestUataIncomeEndpoint:
    def test_empty_range_returns_zeros(self, client: TestClient) -> None:
        token = _register_admin(client)
        r = client.get(
            "/api/v1/fees/uata-income?month_from=2026-05-01&month_to=2026-05-01",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert Decimal(body["subscription_total"]) == Decimal("0")
        assert Decimal(body["fee_total"]) == Decimal("0")
        assert Decimal(body["yield_excess_total"]) == Decimal("0")
        assert Decimal(body["affiliate_payout_total"]) == Decimal("0")
        assert Decimal(body["uata_income_total"]) == Decimal("0")

    def test_aggregates_within_range(self, client: TestClient, test_db) -> None:
        _, SessionFactory = test_db
        token = _register_admin(client)
        with SessionFactory() as db:
            admin_id = AuthService.get_user_by_email(db, "fees_admin@example.com").id

        # 4 月: sub 3000, fee 1000, excess 500, affiliate 900
        _add_fee_tx(
            SessionFactory,
            user_id=admin_id,
            month=date(2026, 4, 1),
            fee_amount=Decimal("1000"),
            sub_amount=Decimal("3000"),
            excess=Decimal("500"),
            affiliate_amount=Decimal("900"),
        )
        # 5 月: 範囲外 (month_to=4月)
        _add_fee_tx(SessionFactory, user_id=admin_id, month=date(2026, 5, 1))

        r = client.get(
            "/api/v1/fees/uata-income?month_from=2026-04-01&month_to=2026-04-30",
            headers={"Authorization": f"Bearer {token}"},
        )
        body = r.json()
        assert Decimal(body["subscription_total"]) == Decimal("3000")
        assert Decimal(body["fee_total"]) == Decimal("1000")
        assert Decimal(body["yield_excess_total"]) == Decimal("500")
        assert Decimal(body["affiliate_payout_total"]) == Decimal("900")
        # uata_income = 3000 + 1000 + 500 - 900 = 3600
        assert Decimal(body["uata_income_total"]) == Decimal("3600")

    def test_invalid_range_returns_400(self, client: TestClient) -> None:
        token = _register_admin(client)
        r = client.get(
            "/api/v1/fees/uata-income?month_from=2026-06-01&month_to=2026-05-01",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 400


# ===========================================================================
# Coexistence: 既存 /api/billing/* / /api/fees/* が無回帰
# ===========================================================================


class TestLegacyEndpointsRemoved:
    """F-13 で旧 billing エンドポイントが削除されたことを確認 (404 になること)。"""

    def test_legacy_billing_config_route_removed(self, client: TestClient) -> None:
        r = client.get("/api/billing/config")
        assert r.status_code == 404, "/api/billing/config route should be removed by F-13!"

    def test_aave_fees_calculate_still_registered(self, client: TestClient) -> None:
        # aave/fee_router.py は F-8b 廃止予定だが F-13 スコープ外 → 404 でないこと
        r = client.get("/api/fees/calculate?aum_usd=1000")
        assert r.status_code != 404, "/api/fees/calculate (aave) should still be registered!"


# ===========================================================================
# F-S6: allowance-info エンドポイント
# ===========================================================================


class TestAllowanceInfo:
    """GET /api/v1/fees/allowance-info のテスト。"""

    def test_unauthenticated_returns_401(self, client: TestClient) -> None:
        r = client.get("/api/v1/fees/allowance-info")
        assert r.status_code == 401

    def test_authenticated_returns_info_without_operator(self, client: TestClient) -> None:
        token = _register_admin(client)
        # OPERATOR_FEE_WALLET_ADDRESS 未設定時は configured=false で返る
        os.environ.pop("OPERATOR_FEE_WALLET_ADDRESS", None)
        r = client.get(
            "/api/v1/fees/allowance-info",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["configured"] is False
        assert body["operator_address"] == ""
        assert "chain_id" in body
        assert "usdc_address" in body
        assert "data_provider_address" in body
        assert "recommended_allowance_usdc" in body
        # recommended は 6 decimal の Decimal str
        assert Decimal(body["recommended_allowance_usdc"]) > 0

    def test_authenticated_returns_info_with_operator(self, client: TestClient) -> None:
        token = _register_admin(client)
        test_address = "0xTestOperatorAddress1234567890123456789012"
        os.environ["OPERATOR_FEE_WALLET_ADDRESS"] = test_address
        try:
            r = client.get(
                "/api/v1/fees/allowance-info",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["configured"] is True
            assert body["operator_address"] == test_address
        finally:
            os.environ.pop("OPERATOR_FEE_WALLET_ADDRESS", None)
