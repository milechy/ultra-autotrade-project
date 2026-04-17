# backend/tests/test_allocation_service.py
"""
資金割り振りサービス層のユニットテスト。

按分計算の正確性・エッジケースを中心にテストする。
"""

import os
import tempfile
from decimal import Decimal
from itertools import count
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-allocation-svc")

_counter = count(1)

from app.aave.client import AccountData  # noqa: E402
from app.auth.models import User, UserRole  # noqa: E402
from app.database import Base  # noqa: E402
from app.partner.allocation_models import FundAllocation  # noqa: E402
from app.partner.allocation_schemas import (  # noqa: E402
    AllocationCreateRequest,
    AllocationUpdateRequest,
)
from app.partner.allocation_service import (  # noqa: E402
    _HF_INFINITY_DISPLAY,
    _calc_pnl,
    _get_wallet_address,
    create_allocation,
    delete_allocation,
    get_allocations,
    get_my_allocation,
    get_performance,
    update_allocation,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SessionFactory = sessionmaker[Session]


@pytest.fixture()
def db() -> Session:
    """インメモリ SQLite セッションを返す。"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory: SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = factory()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


def _make_partner(db: Session, wallet_address: str | None = None) -> User:
    """テスト用パートナーユーザーを作成して返す。"""
    uid = next(_counter)
    partner = User(
        email=f"partner-{uid}@example.com",
        username=f"partner-{uid}",
        hashed_password="hashed",
        role=UserRole.PARTNER.value,
        is_active=True,
        wallet_address=wallet_address,
    )
    db.add(partner)
    db.commit()
    db.refresh(partner)
    return partner


def _make_allocation(
    db: Session,
    partner_id: int,
    tester_name: str,
    amount: Decimal,
    status: str = "active",
) -> FundAllocation:
    """テスト用割り振りレコードを直接作成する。"""
    req = AllocationCreateRequest(tester_name=tester_name, allocated_amount_usd=amount)
    result = create_allocation(db, partner_id, req)
    if status != "active":
        alloc = db.query(FundAllocation).filter(FundAllocation.id == result.id).first()
        assert alloc is not None
        alloc.status = status
        db.commit()
        db.refresh(alloc)
        return alloc
    alloc = db.query(FundAllocation).filter(FundAllocation.id == result.id).first()
    assert alloc is not None
    return alloc


# ---------------------------------------------------------------------------
# CRUD テスト
# ---------------------------------------------------------------------------


class TestCreateAllocation:
    def test_create_basic(self, db: Session) -> None:
        partner = _make_partner(db)
        req = AllocationCreateRequest(tester_name="Alice", allocated_amount_usd=Decimal("1000.5"))
        resp = create_allocation(db, partner.id, req)

        assert resp.id > 0
        assert resp.partner_id == partner.id
        assert resp.tester_name == "Alice"
        assert resp.allocated_amount_usd == Decimal("1000.5")
        assert resp.status == "active"
        assert resp.withdrawn_at is None

    def test_create_with_notes(self, db: Session) -> None:
        partner = _make_partner(db)
        req = AllocationCreateRequest(
            tester_name="Bob",
            allocated_amount_usd=Decimal("500"),
            notes="First batch",
        )
        resp = create_allocation(db, partner.id, req)
        assert resp.notes == "First batch"


class TestGetAllocations:
    def test_returns_active_by_default(self, db: Session) -> None:
        partner = _make_partner(db)
        _make_allocation(db, partner.id, "Alice", Decimal("100"))
        _make_allocation(db, partner.id, "Bob", Decimal("200"), status="withdrawn")

        result = get_allocations(db, partner.id, status="active")
        assert len(result) == 1
        assert result[0].tester_name == "Alice"

    def test_returns_all_when_status_none(self, db: Session) -> None:
        partner = _make_partner(db)
        _make_allocation(db, partner.id, "Alice", Decimal("100"))
        _make_allocation(db, partner.id, "Bob", Decimal("200"), status="withdrawn")

        result = get_allocations(db, partner.id, status=None)
        assert len(result) == 2

    def test_no_cross_partner_leak(self, db: Session) -> None:
        p1 = _make_partner(db)
        p2 = _make_partner(db)
        _make_allocation(db, p1.id, "Alice", Decimal("100"))
        _make_allocation(db, p2.id, "Intruder", Decimal("999"))

        result = get_allocations(db, p1.id)
        assert all(r.partner_id == p1.id for r in result)
        assert len(result) == 1


class TestUpdateAllocation:
    def test_update_tester_name(self, db: Session) -> None:
        partner = _make_partner(db)
        alloc = _make_allocation(db, partner.id, "OldName", Decimal("100"))
        req = AllocationUpdateRequest(tester_name="NewName")
        resp = update_allocation(db, alloc.id, partner.id, req)
        assert resp is not None
        assert resp.tester_name == "NewName"
        assert resp.allocated_amount_usd == Decimal("100")

    def test_update_status_to_withdrawn_sets_withdrawn_at(self, db: Session) -> None:
        partner = _make_partner(db)
        alloc = _make_allocation(db, partner.id, "Alice", Decimal("100"))
        req = AllocationUpdateRequest(status="withdrawn")
        resp = update_allocation(db, alloc.id, partner.id, req)
        assert resp is not None
        assert resp.status == "withdrawn"
        assert resp.withdrawn_at is not None

    def test_update_not_found_returns_none(self, db: Session) -> None:
        partner = _make_partner(db)
        req = AllocationUpdateRequest(tester_name="Ghost")
        result = update_allocation(db, 99999, partner.id, req)
        assert result is None

    def test_update_another_partners_record_returns_none(self, db: Session) -> None:
        p1 = _make_partner(db)
        p2 = _make_partner(db)
        alloc = _make_allocation(db, p1.id, "Alice", Decimal("100"))
        req = AllocationUpdateRequest(tester_name="Hacked")
        result = update_allocation(db, alloc.id, p2.id, req)
        assert result is None


class TestDeleteAllocation:
    def test_delete_success(self, db: Session) -> None:
        partner = _make_partner(db)
        alloc = _make_allocation(db, partner.id, "Alice", Decimal("100"))
        assert delete_allocation(db, alloc.id, partner.id) is True
        assert get_allocations(db, partner.id) == []

    def test_delete_not_found(self, db: Session) -> None:
        partner = _make_partner(db)
        assert delete_allocation(db, 99999, partner.id) is False

    def test_delete_another_partners_record(self, db: Session) -> None:
        p1 = _make_partner(db)
        p2 = _make_partner(db)
        alloc = _make_allocation(db, p1.id, "Alice", Decimal("100"))
        assert delete_allocation(db, alloc.id, p2.id) is False
        # p1 の alloc は残っているはず
        assert len(get_allocations(db, p1.id)) == 1


# ---------------------------------------------------------------------------
# パフォーマンス按分テスト
# ---------------------------------------------------------------------------

_DUMMY_ACCOUNT_DATA = AccountData(
    total_collateral_usd=Decimal("10000"),
    total_debt_usd=Decimal("3000"),
    available_borrows_usd=Decimal("5000"),
    health_factor=Decimal("2.5"),
)


class TestGetPerformance:
    def test_basic_pro_rata(self, db: Session) -> None:
        """2テスター均等割り振り → current_value は total_supply の半分ずつ。"""
        partner = _make_partner(db)
        _make_allocation(db, partner.id, "Alice", Decimal("500"))
        _make_allocation(db, partner.id, "Bob", Decimal("500"))

        with patch("app.partner.allocation_service.get_default_aave_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.get_account_data.return_value = _DUMMY_ACCOUNT_DATA
            mock_factory.return_value = mock_client

            summary = get_performance(db, partner)

        assert summary.total_allocated_usd == Decimal("1000")
        assert summary.total_supply_usd == Decimal("10000")
        assert len(summary.testers) == 2
        for t in summary.testers:
            assert t.allocation_ratio == Decimal("0.5")
            assert t.current_value_usd == Decimal("5000")
            assert t.pnl_usd == Decimal("4500")  # 5000 - 500
            # pnl_percentage は % 換算済み: 4500/500*100 = 900
            assert t.pnl_percentage == Decimal("900.0000")

    def test_unequal_allocation(self, db: Session) -> None:
        """3:1 割り振り → ratio が 0.75 / 0.25。"""
        partner = _make_partner(db)
        _make_allocation(db, partner.id, "Alice", Decimal("750"))
        _make_allocation(db, partner.id, "Bob", Decimal("250"))

        with patch("app.partner.allocation_service.get_default_aave_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.get_account_data.return_value = _DUMMY_ACCOUNT_DATA
            mock_factory.return_value = mock_client

            summary = get_performance(db, partner)

        alice = next(t for t in summary.testers if t.tester_name == "Alice")
        bob = next(t for t in summary.testers if t.tester_name == "Bob")
        assert alice.allocation_ratio == Decimal("0.75")
        assert bob.allocation_ratio == Decimal("0.25")
        assert alice.current_value_usd == Decimal("7500")
        assert bob.current_value_usd == Decimal("2500")

    def test_total_allocation_exceeds_aave_balance(self, db: Session) -> None:
        """割り当て合計 > Aave 残高 → current_value は縮小、pnl は負。"""
        partner = _make_partner(db)
        _make_allocation(db, partner.id, "Alice", Decimal("8000"))
        _make_allocation(db, partner.id, "Bob", Decimal("8000"))

        # Aave 残高は 10000 （total_collateral_usd）
        with patch("app.partner.allocation_service.get_default_aave_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.get_account_data.return_value = _DUMMY_ACCOUNT_DATA
            mock_factory.return_value = mock_client

            summary = get_performance(db, partner)

        assert summary.total_allocated_usd == Decimal("16000")
        assert summary.total_supply_usd == Decimal("10000")
        for t in summary.testers:
            assert t.current_value_usd == Decimal("5000")  # 0.5 * 10000
            assert t.pnl_usd < Decimal("0")  # 5000 - 8000 = -3000

    def test_zero_allocations(self, db: Session) -> None:
        """割り当て 0 件 → testers は空リスト。"""
        partner = _make_partner(db)

        with patch("app.partner.allocation_service.get_default_aave_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.get_account_data.return_value = _DUMMY_ACCOUNT_DATA
            mock_factory.return_value = mock_client

            summary = get_performance(db, partner)

        assert summary.testers == []
        assert summary.total_allocated_usd == Decimal("0")

    def test_hf_infinity_clamped(self, db: Session) -> None:
        """HF が Infinity → Decimal('999.0') に丸められる。"""
        partner = _make_partner(db)
        _make_allocation(db, partner.id, "Alice", Decimal("100"))

        infinite_data = AccountData(
            total_collateral_usd=Decimal("0"),
            total_debt_usd=Decimal("0"),
            available_borrows_usd=Decimal("0"),
            health_factor=Decimal("Infinity"),
        )

        with patch("app.partner.allocation_service.get_default_aave_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.get_account_data.return_value = infinite_data
            mock_factory.return_value = mock_client

            summary = get_performance(db, partner)

        assert summary.health_factor == _HF_INFINITY_DISPLAY

    def test_withdrawn_allocations_excluded_from_performance(self, db: Session) -> None:
        """withdrawn 割り振りはパフォーマンス計算対象外。"""
        partner = _make_partner(db)
        _make_allocation(db, partner.id, "Active", Decimal("1000"))
        _make_allocation(db, partner.id, "Gone", Decimal("5000"), status="withdrawn")

        with patch("app.partner.allocation_service.get_default_aave_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.get_account_data.return_value = _DUMMY_ACCOUNT_DATA
            mock_factory.return_value = mock_client

            summary = get_performance(db, partner)

        assert len(summary.testers) == 1
        assert summary.testers[0].tester_name == "Active"
        assert summary.total_allocated_usd == Decimal("1000")

    def test_aave_error_uses_zero_supply(self, db: Session) -> None:
        """Aave 呼び出し失敗時は total_supply=0 にフォールバック。"""
        partner = _make_partner(db)
        _make_allocation(db, partner.id, "Alice", Decimal("1000"))

        with patch("app.partner.allocation_service.get_default_aave_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.get_account_data.side_effect = RuntimeError("RPC error")
            mock_factory.return_value = mock_client

            summary = get_performance(db, partner)

        assert summary.total_supply_usd == Decimal("0")
        assert summary.testers[0].current_value_usd == Decimal("0")


# ---------------------------------------------------------------------------
# エッジケース: 未カバー行を対象とした追加テスト
# ---------------------------------------------------------------------------


class TestAllocationServiceEdgeCases:
    def test_update_notes(self, db: Session) -> None:
        """update_allocation: notes フィールドが更新される（L132）。"""
        partner = _make_partner(db)
        alloc = _make_allocation(db, partner.id, "Alice", Decimal("100"))
        req = AllocationUpdateRequest(notes="updated notes")
        resp = update_allocation(db, alloc.id, partner.id, req)
        assert resp is not None
        assert resp.notes == "updated notes"

    def test_calc_pnl_zero_allocated(self) -> None:
        """_calc_pnl: allocated=0 のときはゼロタプルを返す（L190 前半ガード）。"""
        result = _calc_pnl(Decimal("0"), Decimal("1000"), Decimal("5000"))
        assert result == (Decimal("0"), Decimal("0"), Decimal("0"))

    def test_calc_pnl_zero_total_allocated(self) -> None:
        """_calc_pnl: total_allocated=0 のときはゼロタプルを返す（L190 後半ガード）。"""
        result = _calc_pnl(Decimal("500"), Decimal("0"), Decimal("5000"))
        assert result == (Decimal("0"), Decimal("0"), Decimal("0"))

    def test_get_my_allocation_partner_not_found(self, db: Session) -> None:
        """get_my_allocation: partner が DB に存在しない場合 None を返す（L275）。"""
        from datetime import datetime, timezone  # noqa: PLC0415

        tester = _make_partner(db)
        tester.role = "viewer"
        db.commit()
        db.refresh(tester)

        # orphaned partner_id（存在しない）で FundAllocation を直接挿入
        alloc = FundAllocation(
            partner_id=999999,  # 存在しないパートナー
            tester_name=tester.username,
            tester_user_id=tester.id,
            allocated_amount_usd=Decimal("500"),
            status="active",
            allocated_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(alloc)
        db.commit()

        result = get_my_allocation(db, tester)
        assert result is None

    def test_get_performance_zero_amount_allocation(self, db: Session) -> None:
        """get_performance: allocated_amount_usd=0 の割り振りで ratio=0 と pnl_pct=0 が設定される（L391, L399）。"""
        from datetime import datetime, timezone  # noqa: PLC0415

        partner = _make_partner(db)
        # amount=0 の割り振りを直接挿入（create_allocation は 0 を許容しない場合があるため直接挿入）
        alloc = FundAllocation(
            partner_id=partner.id,
            tester_name="zero-tester",
            allocated_amount_usd=Decimal("0"),
            status="active",
            allocated_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(alloc)
        db.commit()

        with patch("app.partner.allocation_service.get_default_aave_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.get_account_data.return_value = _DUMMY_ACCOUNT_DATA
            mock_factory.return_value = mock_client

            summary = get_performance(db, partner)

        assert len(summary.testers) == 1
        tester = summary.testers[0]
        assert tester.allocation_ratio == Decimal("0")
        assert tester.pnl_percentage == Decimal("0")


class TestGetWalletAddress:
    def test_uses_user_wallet_address(self, db: Session) -> None:
        partner = _make_partner(db, wallet_address="0xABC123")
        assert _get_wallet_address(partner) == "0xABC123"

    def test_fallback_to_env_when_no_wallet(
        self, db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        partner = _make_partner(db, wallet_address=None)
        monkeypatch.setenv("AAVE_WALLET_ADDRESS", "0xENV456")
        assert _get_wallet_address(partner) == "0xENV456"

    def test_empty_string_when_neither_set(
        self, db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        partner = _make_partner(db, wallet_address=None)
        monkeypatch.delenv("AAVE_WALLET_ADDRESS", raising=False)
        assert _get_wallet_address(partner) == ""
