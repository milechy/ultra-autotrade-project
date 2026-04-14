# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Phase 1.5: fund_allocations.tester_user_id FK化のテスト。

カバレッジ対象:
- FundAllocation モデル: tester_user_id カラム追加
- _find_allocation_for_user(): FK優先 + tester_nameフォールバック + 自動バックフィル
- AllocationCreateRequest / AllocationResponse: tester_user_id フィールド
- create_allocation(): tester_user_id 保存
"""

import os
import tempfile
from decimal import Decimal
from itertools import count

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-alloc-fk")

from app.auth.models import User, UserRole  # noqa: E402
from app.database import Base  # noqa: E402
from app.partner.allocation_models import FundAllocation  # noqa: E402
from app.partner.allocation_schemas import (  # noqa: E402
    AllocationCreateRequest,
    AllocationResponse,
)
from app.partner.allocation_service import (  # noqa: E402
    _find_allocation_for_user,
    create_allocation,
)

_counter = count(1)

SessionFactory = sessionmaker[Session]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db() -> Session:  # type: ignore[misc]
    """インメモリ SQLite セッション（ファイルベース、FK対応）。"""
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


def _make_user(
    db: Session,
    role: str = UserRole.VIEWER.value,
    invited_by: int | None = None,
) -> User:
    uid = next(_counter)
    user = User(
        email=f"user-{uid}@example.com",
        username=f"user-{uid}",
        hashed_password="hashed",
        role=role,
        is_active=True,
        invited_by=invited_by,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_partner(db: Session) -> User:
    return _make_user(db, role=UserRole.PARTNER.value)


def _make_allocation_direct(
    db: Session,
    partner_id: int,
    tester_name: str,
    amount: Decimal = Decimal("1000"),
    status: str = "active",
    tester_user_id: int | None = None,
) -> FundAllocation:
    """DB に直接 FundAllocation レコードを挿入する（サービス層をバイパス）。"""
    from datetime import datetime, timezone

    alloc = FundAllocation(
        partner_id=partner_id,
        tester_name=tester_name,
        tester_user_id=tester_user_id,
        allocated_amount_usd=amount,
        status=status,
        allocated_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(alloc)
    db.commit()
    db.refresh(alloc)
    return alloc


# ---------------------------------------------------------------------------
# モデルテスト
# ---------------------------------------------------------------------------


class TestFundAllocationModel:
    def test_tester_user_id_column_exists(self, db: Session) -> None:
        """tester_user_id カラムが FundAllocation に追加されている。"""
        partner = _make_partner(db)
        tester = _make_user(db)
        alloc = _make_allocation_direct(db, partner.id, tester.username, tester_user_id=tester.id)
        db.refresh(alloc)
        assert alloc.tester_user_id == tester.id

    def test_tester_user_id_nullable(self, db: Session) -> None:
        """tester_user_id は nullable — 既存レコードの後方互換を維持。"""
        partner = _make_partner(db)
        alloc = _make_allocation_direct(db, partner.id, "legacy-tester")
        db.refresh(alloc)
        assert alloc.tester_user_id is None

    def test_tester_name_still_present(self, db: Session) -> None:
        """tester_name カラムは削除されていない（後方互換）。"""
        partner = _make_partner(db)
        alloc = _make_allocation_direct(db, partner.id, "alice")
        assert alloc.tester_name == "alice"


# ---------------------------------------------------------------------------
# スキーマテスト
# ---------------------------------------------------------------------------


class TestAllocationSchemas:
    def test_create_request_accepts_tester_user_id(self) -> None:
        """AllocationCreateRequest: tester_user_id フィールドが追加されている。"""
        req = AllocationCreateRequest(
            tester_name="alice",
            allocated_amount_usd=Decimal("500"),
            tester_user_id=42,
        )
        assert req.tester_user_id == 42

    def test_create_request_tester_user_id_optional(self) -> None:
        """AllocationCreateRequest: tester_user_id は省略可能（デフォルト None）。"""
        req = AllocationCreateRequest(
            tester_name="bob",
            allocated_amount_usd=Decimal("100"),
        )
        assert req.tester_user_id is None

    def test_response_includes_tester_user_id(self, db: Session) -> None:
        """AllocationResponse: tester_user_id フィールドが含まれる。"""
        partner = _make_partner(db)
        tester = _make_user(db)
        req = AllocationCreateRequest(
            tester_name=tester.username,
            allocated_amount_usd=Decimal("300"),
            tester_user_id=tester.id,
        )
        resp = create_allocation(db, partner.id, req)
        assert isinstance(resp, AllocationResponse)
        assert resp.tester_user_id == tester.id

    def test_response_tester_user_id_none_when_not_set(self, db: Session) -> None:
        """AllocationResponse: tester_user_id が未設定の場合は None。"""
        partner = _make_partner(db)
        req = AllocationCreateRequest(
            tester_name="charlie",
            allocated_amount_usd=Decimal("200"),
        )
        resp = create_allocation(db, partner.id, req)
        assert resp.tester_user_id is None


# ---------------------------------------------------------------------------
# create_allocation テスト
# ---------------------------------------------------------------------------


class TestCreateAllocationWithFK:
    def test_create_saves_tester_user_id(self, db: Session) -> None:
        """create_allocation: tester_user_id が正しく保存される。"""
        partner = _make_partner(db)
        tester = _make_user(db)
        req = AllocationCreateRequest(
            tester_name=tester.username,
            allocated_amount_usd=Decimal("1000"),
            tester_user_id=tester.id,
        )
        resp = create_allocation(db, partner.id, req)
        assert resp.tester_user_id == tester.id

    def test_create_without_tester_user_id_keeps_null(self, db: Session) -> None:
        """create_allocation: tester_user_id 省略時は None のまま。"""
        partner = _make_partner(db)
        req = AllocationCreateRequest(
            tester_name="legacy",
            allocated_amount_usd=Decimal("500"),
        )
        resp = create_allocation(db, partner.id, req)
        assert resp.tester_user_id is None


# ---------------------------------------------------------------------------
# _find_allocation_for_user テスト
# ---------------------------------------------------------------------------


class TestFindAllocationForUser:
    def test_match_by_tester_user_id(self, db: Session) -> None:
        """FK マッチ: tester_user_id が設定されていれば直接 FK で取得する。"""
        partner = _make_partner(db)
        tester = _make_user(db)
        alloc = _make_allocation_direct(db, partner.id, tester.username, tester_user_id=tester.id)

        result = _find_allocation_for_user(db, tester)
        assert result is not None
        assert result.id == alloc.id

    def test_fallback_to_tester_name_when_no_fk(self, db: Session) -> None:
        """フォールバック: tester_user_id が未設定でも tester_name でマッチする。"""
        partner = _make_partner(db)
        tester = _make_user(db)
        alloc = _make_allocation_direct(
            db,
            partner.id,
            tester.username,  # tester_user_id=None
        )

        result = _find_allocation_for_user(db, tester)
        assert result is not None
        assert result.id == alloc.id

    def test_auto_backfill_on_name_match(self, db: Session) -> None:
        """自動バックフィル: tester_name フォールバック時に tester_user_id が設定される。"""
        partner = _make_partner(db)
        tester = _make_user(db)
        alloc = _make_allocation_direct(
            db,
            partner.id,
            tester.username,  # tester_user_id=None
        )
        assert alloc.tester_user_id is None

        _find_allocation_for_user(db, tester)

        db.refresh(alloc)
        assert alloc.tester_user_id == tester.id  # バックフィル済み

    def test_returns_none_when_no_match(self, db: Session) -> None:
        """マッチなし: tester_user_id も tester_name も一致しなければ None。"""
        partner = _make_partner(db)
        _make_allocation_direct(db, partner.id, "someone-else")
        tester = _make_user(db)

        result = _find_allocation_for_user(db, tester)
        assert result is None

    def test_fk_match_takes_priority_over_name(self, db: Session) -> None:
        """FK優先: tester_user_id が設定されていれば tester_name と違うユーザーでも FK を使う。"""
        partner = _make_partner(db)
        real_tester = _make_user(db)
        other_tester = _make_user(db)

        # real_tester の user_id が紐付いているが tester_name は other_tester のもの
        alloc = _make_allocation_direct(
            db,
            partner.id,
            other_tester.username,  # tester_name は他人
            tester_user_id=real_tester.id,  # FK は real_tester
        )

        result = _find_allocation_for_user(db, real_tester)
        assert result is not None
        assert result.id == alloc.id

        # other_tester は FK でも名前でも（tester_user_id設定済みのため）一致しない
        result_other = _find_allocation_for_user(db, other_tester)
        assert result_other is None

    def test_invited_by_filters_partner(self, db: Session) -> None:
        """invited_by フィルタ: 異なるパートナーの割り振りを除外する。"""
        partner_a = _make_partner(db)
        partner_b = _make_partner(db)
        tester = _make_user(db, invited_by=partner_a.id)

        # partner_a の割り振り（正しい）
        alloc_a = _make_allocation_direct(
            db, partner_a.id, tester.username, tester_user_id=tester.id
        )
        # partner_b の割り振り（除外対象）
        _make_allocation_direct(db, partner_b.id, tester.username, tester_user_id=tester.id)

        result = _find_allocation_for_user(db, tester)
        assert result is not None
        assert result.id == alloc_a.id

    def test_no_match_when_fk_points_to_different_user(self, db: Session) -> None:
        """tester_user_id IS NULLのフォールバックでは、他ユーザーのFK設定済みレコードを除外。"""
        partner = _make_partner(db)
        tester_a = _make_user(db)
        tester_b = _make_user(db)

        # tester_a に割り振り済み（FK設定済み）
        _make_allocation_direct(db, partner.id, tester_b.username, tester_user_id=tester_a.id)

        # tester_b で検索 → FK=tester_a なのでStep1でヒットせず
        # Step2のフォールバック: tester_user_id IS NULL かつ tester_name=tester_b.username
        # → このレコードは tester_user_id=tester_a.id（IS NOT NULL）なのでヒットしない
        result = _find_allocation_for_user(db, tester_b)
        assert result is None


# ---------------------------------------------------------------------------
# バックフィルスクリプトテスト
# ---------------------------------------------------------------------------


class TestBackfillScript:
    def test_dry_run_does_not_commit(self, db: Session) -> None:
        """dry-run モードでは DB が変更されない。"""
        from scripts.backfill_tester_user_id import run_backfill

        partner = _make_partner(db)
        tester = _make_user(db)
        alloc = _make_allocation_direct(db, partner.id, tester.username)
        assert alloc.tester_user_id is None

        run_backfill(db, dry_run=True)

        db.refresh(alloc)
        assert alloc.tester_user_id is None  # dry-run なので変更なし

    def test_execute_backfills_matching_records(self, db: Session) -> None:
        """execute モードでは tester_name マッチのレコードに tester_user_id が設定される。"""
        from scripts.backfill_tester_user_id import run_backfill

        partner = _make_partner(db)
        tester = _make_user(db)
        alloc = _make_allocation_direct(db, partner.id, tester.username)
        assert alloc.tester_user_id is None

        run_backfill(db, dry_run=False)

        db.refresh(alloc)
        assert alloc.tester_user_id == tester.id

    def test_skips_unmatched_tester_names(self, db: Session) -> None:
        """ユーザーが存在しない tester_name のレコードはスキップされ、None のまま。"""
        from scripts.backfill_tester_user_id import run_backfill

        partner = _make_partner(db)
        alloc = _make_allocation_direct(db, partner.id, "no-such-user-xyz")

        run_backfill(db, dry_run=False)

        db.refresh(alloc)
        assert alloc.tester_user_id is None  # マッチなし、変更なし

    def test_already_backfilled_records_not_updated(self, db: Session) -> None:
        """既に tester_user_id が設定済みのレコードはバックフィル対象外。"""
        from scripts.backfill_tester_user_id import run_backfill

        partner = _make_partner(db)
        tester = _make_user(db)
        alloc = _make_allocation_direct(db, partner.id, tester.username, tester_user_id=tester.id)

        other_tester = _make_user(db)
        # 別ユーザーが同名だったとしても上書きされない
        run_backfill(db, dry_run=False)

        db.refresh(alloc)
        assert alloc.tester_user_id == tester.id  # 変わらない
        assert alloc.tester_user_id != other_tester.id
