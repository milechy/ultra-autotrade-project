# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_proposal_execution_route.py
"""P0-2: CEX(本線) / on-chain Aave(opt-in) 経路分岐の統合テスト。

Asana 1215364069502631 DoD を担保する:
- proposal 単位で execution_route を作成時に確定し変更不可 (immutable)
- CEX 経路: 執行後に CEX API レスポンス + order_id(tx_id) を DB 記録、tx_hash は持たない
  (basescan に一切現れない = 正常)
- on-chain 経路: tx_hash 記録 + proposal_id ↔ tx_hash 紐付け + 他 partner 非混在
- 誤執行: on-chain 選択 proposal を CEX 経路で執行 (逆も) した場合に即時アラート +
  例外で自動進行停止 (手動介入必須)。統合テスト + 模擬執行で担保。
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-exec-route")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "exec_route_admin@example.com")

from app.auth.models import User as UserModel  # noqa: E402
from app.database import Base  # noqa: E402
from app.proposals.execution_route import (  # noqa: E402
    DEFAULT_EXECUTION_ROUTE,
    ExecutionRoute,
    RouteMismatchError,
    assert_route,
    detect_route_mismatch,
    record_cex_execution,
)
from app.proposals.models import Proposal  # noqa: E402


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


def _make_user_with_wallet(db: Session, *, user_id: int, wallet_address: str = "") -> UserModel:
    """テスト用 User を wallet_address 付きで作成する。Layer 1 NULL wallet guard を通過させるために使用。"""
    wallet = wallet_address or ("0x" + f"{user_id:02x}" * 20)
    u = UserModel(
        id=user_id,
        email=f"user{user_id}@test.example",
        username=f"testuser{user_id}",
        hashed_password="hashed_for_test",
        wallet_address=wallet[:42],
    )
    db.add(u)
    db.commit()
    return u


def _make_proposal(
    db: Session,
    *,
    execution_route: str = ExecutionRoute.ONCHAIN_AAVE.value,
    status: str = "approved",
    user_id: int = 1,
) -> Proposal:
    p = Proposal(
        user_id=user_id,
        operation="SUPPLY",
        asset="USDC",
        amount=Decimal("100.000000000000000000"),
        amount_usd=Decimal("100.00"),
        reason="test",
        status=status,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        execution_route=execution_route,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


# ---------------------------------------------------------------------------
# ExecutionRoute enum / detect_route_mismatch
# ---------------------------------------------------------------------------


def test_execution_route_values() -> None:
    assert ExecutionRoute.values() == ["onchain_aave", "cex"]
    assert DEFAULT_EXECUTION_ROUTE == ExecutionRoute.ONCHAIN_AAVE.value


@pytest.mark.parametrize(
    ("route", "has_onchain_tx", "has_cex_order", "expect_mismatch"),
    [
        # 正常: 経路と証跡が一致
        (ExecutionRoute.ONCHAIN_AAVE.value, True, False, False),
        (ExecutionRoute.CEX.value, False, True, False),
        # 証跡なし (執行前): 不整合なし
        (ExecutionRoute.ONCHAIN_AAVE.value, False, False, False),
        (ExecutionRoute.CEX.value, False, False, False),
        # 誤執行: CEX 経路に on-chain tx
        (ExecutionRoute.CEX.value, True, False, True),
        # 誤執行: on-chain 経路に CEX order
        (ExecutionRoute.ONCHAIN_AAVE.value, False, True, True),
    ],
)
def test_detect_route_mismatch_matrix(
    route: str, has_onchain_tx: bool, has_cex_order: bool, expect_mismatch: bool
) -> None:
    result = detect_route_mismatch(
        route, has_onchain_tx=has_onchain_tx, has_cex_order=has_cex_order
    )
    assert (result is not None) == expect_mismatch


# ---------------------------------------------------------------------------
# DoD: immutability
# ---------------------------------------------------------------------------


def test_execution_route_immutable_after_creation(db_session: Session) -> None:
    """作成後に execution_route を別値へ変更すると ValueError (immutable)。"""
    p = _make_proposal(db_session, execution_route=ExecutionRoute.ONCHAIN_AAVE.value)
    with pytest.raises(ValueError, match="immutable"):
        p.execution_route = ExecutionRoute.CEX.value


def test_execution_route_same_value_reassign_allowed(db_session: Session) -> None:
    """同値の再代入 (db.refresh 相当) は許可される。"""
    p = _make_proposal(db_session, execution_route=ExecutionRoute.CEX.value)
    p.execution_route = ExecutionRoute.CEX.value  # no-op、例外にならない
    db_session.refresh(p)
    assert p.execution_route == ExecutionRoute.CEX.value


def test_execution_route_default_is_onchain(db_session: Session) -> None:
    """経路未指定で作成すると後方互換で on-chain Aave になる。"""
    p = Proposal(
        user_id=1,
        operation="SUPPLY",
        asset="USDC",
        amount=Decimal("1"),
        amount_usd=Decimal("1"),
        reason="default-route",
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    assert p.execution_route == ExecutionRoute.ONCHAIN_AAVE.value


# ---------------------------------------------------------------------------
# DoD: CEX 経路の完了記録
# ---------------------------------------------------------------------------


def test_record_cex_execution_sets_evidence_without_tx_hash(db_session: Session) -> None:
    """CEX 経路: order_id + レスポンスを記録し、tx_hash は付けない (basescan clean)。"""
    p = _make_proposal(db_session, execution_route=ExecutionRoute.CEX.value)
    record_cex_execution(
        p,
        cex_order_id="bybit-order-12345",
        cex_response='{"orderId": "bybit-order-12345", "status": "Filled"}',
    )
    db_session.commit()
    db_session.refresh(p)
    assert p.status == "executed"
    assert p.cex_order_id == "bybit-order-12345"
    assert p.cex_response is not None
    assert p.executed_at is not None
    # basescan に現れないのが正常: on-chain tx_hash は記録されない
    assert p.tx_hash is None


def test_record_cex_execution_on_onchain_proposal_raises_and_alerts(db_session: Session) -> None:
    """誤執行: on-chain 選択 proposal を CEX 経路で執行 → 即時アラート + 例外。"""
    p = _make_proposal(db_session, execution_route=ExecutionRoute.ONCHAIN_AAVE.value)
    with patch("app.proposals.execution_route.notify_route_mismatch") as mock_notify:
        with pytest.raises(RouteMismatchError):
            record_cex_execution(p, cex_order_id="x", cex_response="{}")
    mock_notify.assert_called_once()
    # 自動進行は止まる: executed にならない
    assert p.status != "executed"
    assert p.cex_order_id is None


def test_assert_route_consistent_noop(db_session: Session) -> None:
    p = _make_proposal(db_session, execution_route=ExecutionRoute.ONCHAIN_AAVE.value)
    # 一致時は例外を出さない
    assert_route(p, ExecutionRoute.ONCHAIN_AAVE)


# ---------------------------------------------------------------------------
# DoD: 誤執行ガード (submit-tx = on-chain 経路) を _execute / assert_route で担保
# ---------------------------------------------------------------------------


def test_assert_route_cex_proposal_onchain_execution_raises(db_session: Session) -> None:
    """誤執行: CEX 選択 proposal が on-chain 経路で執行 → 即時アラート + 例外。"""
    p = _make_proposal(db_session, execution_route=ExecutionRoute.CEX.value)
    with patch("app.proposals.execution_route.notify_route_mismatch") as mock_notify:
        with pytest.raises(RouteMismatchError):
            assert_route(p, ExecutionRoute.ONCHAIN_AAVE)
    mock_notify.assert_called_once()


def test_execute_aave_blocks_cex_proposal(db_session: Session) -> None:
    """模擬執行: CEX proposal が Aave 自動実行経路に入ると failed + 例外 (実 Aave 呼ばず)。"""
    from app.proposals.router import _execute_aave_for_proposal

    p = _make_proposal(db_session, execution_route=ExecutionRoute.CEX.value)
    with patch("app.proposals.execution_route.notify_route_mismatch") as mock_notify:
        with pytest.raises(RouteMismatchError):
            _execute_aave_for_proposal(p, db_session)
    mock_notify.assert_called_once()
    assert p.status == "failed"
    assert "route mismatch" in (p.error_message or "")
    # on-chain tx は立たない
    assert p.tx_hash is None


# ---------------------------------------------------------------------------
# DoD: on-chain 経路 — proposal_id ↔ tx_hash 紐付け + 他 partner 非混在
# ---------------------------------------------------------------------------


def test_onchain_execution_links_proposal_id_to_tx_hash(db_session: Session) -> None:
    """on-chain 経路の正常執行: proposal_id ↔ tx_hash が DB に紐付く。"""
    from app.proposals.router import _execute_aave_for_proposal

    # Layer 1 NULL wallet guard を通過させるために wallet_address 付きユーザーを作成
    _make_user_with_wallet(db_session, user_id=1, wallet_address="0x" + "ab" * 20)
    p = _make_proposal(db_session, execution_route=ExecutionRoute.ONCHAIN_AAVE.value)
    fake_result = MagicMock()
    fake_result.tx_hash = "0x" + "ab" * 32
    fake_result.status = "success"

    with patch.dict(os.environ, {"AAVE_ACTIVE_CHAINS": "base"}):
        with patch("app.aave.service.MultiChainAaveService") as mock_svc:
            mock_svc.return_value.execute_rebalance.return_value = fake_result
            _execute_aave_for_proposal(p, db_session)

    db_session.commit()
    db_session.refresh(p)
    assert p.status == "executed"
    assert p.tx_hash == "0x" + "ab" * 32
    # DB 上で proposal_id から tx_hash が引ける (紐付け存在)
    fetched = db_session.scalars(select(Proposal).where(Proposal.id == p.id)).first()
    assert fetched is not None
    assert fetched.tx_hash == "0x" + "ab" * 32
    assert fetched.cex_order_id is None  # on-chain 経路は CEX 証跡を持たない


def test_onchain_partners_not_mixed(db_session: Session) -> None:
    """他 partner の tx と非混在: 各 proposal の tx_hash は own proposal_id に紐付く。"""
    from app.proposals.router import _execute_aave_for_proposal

    # Layer 1 NULL wallet guard を通過させるために wallet_address 付きユーザーを作成
    _make_user_with_wallet(db_session, user_id=11, wallet_address="0x" + "11" * 20)
    _make_user_with_wallet(db_session, user_id=22, wallet_address="0x" + "22" * 20)
    p1 = _make_proposal(db_session, user_id=11, execution_route=ExecutionRoute.ONCHAIN_AAVE.value)
    p2 = _make_proposal(db_session, user_id=22, execution_route=ExecutionRoute.ONCHAIN_AAVE.value)

    def _fake_exec(proposal_user_tx: str):
        r = MagicMock()
        r.tx_hash = proposal_user_tx
        r.status = "success"
        return r

    with patch.dict(os.environ, {"AAVE_ACTIVE_CHAINS": "base"}):
        with patch("app.aave.service.MultiChainAaveService") as mock_svc:
            mock_svc.return_value.execute_rebalance.return_value = _fake_exec("0x" + "11" * 32)
            _execute_aave_for_proposal(p1, db_session)
            mock_svc.return_value.execute_rebalance.return_value = _fake_exec("0x" + "22" * 32)
            _execute_aave_for_proposal(p2, db_session)
    db_session.commit()

    assert p1.tx_hash == "0x" + "11" * 32
    assert p2.tx_hash == "0x" + "22" * 32
    assert p1.user_id != p2.user_id
    assert p1.tx_hash != p2.tx_hash
