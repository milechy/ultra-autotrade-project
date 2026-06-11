# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_partner_wallet_routing.py
"""partner 別 wallet ルーティングの統合テスト。

user_id=11 (山本) と user_id=18 (橋口) が、それぞれ自分の wallet_address
に紐づいて Aave 操作・snapshot 取得されることを保証する。

DoD: 橋口 approve → 山本 wallet で執行 という致命構造が発生しないことを検証。
"""

from __future__ import annotations

import os
import tempfile
from decimal import Decimal
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-partner-wallet")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin@partner-wallet-test.com")

from app.aave.client import AccountData  # noqa: E402
from app.aave.schemas import (  # noqa: E402
    AaveOperationResult,
    AaveOperationStatus,
    AaveOperationType,
)
from app.auth.models import User  # noqa: E402
from app.database import Base  # noqa: E402
from app.portfolio.models import PortfolioSnapshot  # noqa: E402
from app.portfolio.snapshot_service import record_portfolio_snapshot  # noqa: E402
from app.proposals.models import Proposal  # noqa: E402

YAMAMOTO_WALLET = "0xYamamoto1111111111111111111111111111111111"
HASHIGUCHI_WALLET = "0xHashiguchi2222222222222222222222222222222"


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


def _make_partner(db: Session, uid: int, wallet: str) -> User:
    user = User(
        id=uid,
        email=f"partner{uid}@test.com",
        username=f"partner{uid}",
        hashed_password="x",
        role="partner",
        is_active=True,
        wallet_address=wallet,
    )
    db.add(user)
    db.flush()
    return user


def _make_tester(db: Session, uid: int, invited_by: int) -> User:
    user = User(
        id=uid,
        email=f"tester{uid}@test.com",
        username=f"tester{uid}",
        hashed_password="x",
        role="viewer",
        is_active=True,
        invited_by=invited_by,
    )
    db.add(user)
    db.flush()
    return user


def _make_proposal(db: Session, user_id: int) -> Proposal:
    from datetime import datetime, timedelta, timezone

    proposal = Proposal(
        user_id=user_id,
        operation="SUPPLY",
        asset="USDC",
        amount=Decimal("1000"),
        amount_usd=Decimal("1000.00"),
        reason="partner wallet routing test",
        status="approved",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(proposal)
    db.flush()
    return proposal


# ---------------------------------------------------------------------------
# snapshot_service: partner 別 wallet ルーティング
# ---------------------------------------------------------------------------


class TestSnapshotPartnerWalletRouting:
    def test_yamamoto_snapshot_uses_yamamoto_wallet(self, db_session: Session) -> None:
        """user_id=11 (山本) のテスターは山本 wallet のデータで snapshot される。"""
        yamamoto = _make_partner(db_session, uid=11, wallet=YAMAMOTO_WALLET)
        tester_y = _make_tester(db_session, uid=101, invited_by=yamamoto.id)
        db_session.commit()

        def _side_effect(wallet: str) -> AccountData:
            assert wallet == YAMAMOTO_WALLET, f"山本 wallet 以外が呼ばれた: {wallet}"
            return AccountData(
                total_collateral_usd=Decimal("5000"),
                total_debt_usd=Decimal("1000"),
                available_borrows_usd=Decimal("3000"),
                health_factor=Decimal("2.5"),
            )

        mock_client = MagicMock()
        mock_client.get_account_data.side_effect = _side_effect

        with patch(
            "app.portfolio.snapshot_service.get_default_aave_client",
            return_value=mock_client,
        ):
            result = record_portfolio_snapshot(db_session)

        assert result["snapshots_created"] == 1
        snap = db_session.query(PortfolioSnapshot).filter_by(user_id=tester_y.id).first()
        assert snap is not None
        assert Decimal(str(snap.total_supply_usd)) == Decimal("5000.000000")
        assert Decimal(str(snap.total_borrow_usd)) == Decimal("1000.000000")

    def test_hashiguchi_snapshot_uses_hashiguchi_wallet(self, db_session: Session) -> None:
        """user_id=18 (橋口) のテスターは橋口 wallet のデータで snapshot される。"""
        hashiguchi = _make_partner(db_session, uid=18, wallet=HASHIGUCHI_WALLET)
        tester_h = _make_tester(db_session, uid=181, invited_by=hashiguchi.id)
        db_session.commit()

        def _side_effect(wallet: str) -> AccountData:
            assert wallet == HASHIGUCHI_WALLET, f"橋口 wallet 以外が呼ばれた: {wallet}"
            return AccountData(
                total_collateral_usd=Decimal("8000"),
                total_debt_usd=Decimal("2000"),
                available_borrows_usd=Decimal("4000"),
                health_factor=Decimal("3.0"),
            )

        mock_client = MagicMock()
        mock_client.get_account_data.side_effect = _side_effect

        with patch(
            "app.portfolio.snapshot_service.get_default_aave_client",
            return_value=mock_client,
        ):
            result = record_portfolio_snapshot(db_session)

        assert result["snapshots_created"] == 1
        snap = db_session.query(PortfolioSnapshot).filter_by(user_id=tester_h.id).first()
        assert snap is not None
        assert Decimal(str(snap.total_supply_usd)) == Decimal("8000.000000")
        assert Decimal(str(snap.total_borrow_usd)) == Decimal("2000.000000")

    def test_both_partners_use_own_wallets(self, db_session: Session) -> None:
        """山本・橋口 2 partner が並走しても互いの wallet を汚染しない。"""
        yamamoto = _make_partner(db_session, uid=11, wallet=YAMAMOTO_WALLET)
        hashiguchi = _make_partner(db_session, uid=18, wallet=HASHIGUCHI_WALLET)
        tester_y = _make_tester(db_session, uid=101, invited_by=yamamoto.id)
        tester_h = _make_tester(db_session, uid=181, invited_by=hashiguchi.id)
        db_session.commit()

        def _side_effect(wallet: str) -> AccountData:
            if wallet == YAMAMOTO_WALLET:
                return AccountData(
                    total_collateral_usd=Decimal("5000"),
                    total_debt_usd=Decimal("500"),
                    available_borrows_usd=Decimal("3000"),
                    health_factor=Decimal("2.5"),
                )
            if wallet == HASHIGUCHI_WALLET:
                return AccountData(
                    total_collateral_usd=Decimal("9000"),
                    total_debt_usd=Decimal("3000"),
                    available_borrows_usd=Decimal("4000"),
                    health_factor=Decimal("3.5"),
                )
            raise AssertionError(f"予期しない wallet: {wallet}")

        mock_client = MagicMock()
        mock_client.get_account_data.side_effect = _side_effect

        with patch(
            "app.portfolio.snapshot_service.get_default_aave_client",
            return_value=mock_client,
        ):
            result = record_portfolio_snapshot(db_session)

        assert result["snapshots_created"] == 2

        snap_y = db_session.query(PortfolioSnapshot).filter_by(user_id=tester_y.id).first()
        snap_h = db_session.query(PortfolioSnapshot).filter_by(user_id=tester_h.id).first()
        assert snap_y is not None
        assert snap_h is not None

        # 山本テスターは山本 wallet のデータのみ
        assert Decimal(str(snap_y.total_supply_usd)) == Decimal("5000.000000")
        assert Decimal(str(snap_y.total_borrow_usd)) == Decimal("500.000000")

        # 橋口テスターは橋口 wallet のデータのみ — 山本のデータが混入しない
        assert Decimal(str(snap_h.total_supply_usd)) == Decimal("9000.000000")
        assert Decimal(str(snap_h.total_borrow_usd)) == Decimal("3000.000000")


# ---------------------------------------------------------------------------
# _execute_aave_for_proposal: wallet_address ルーティング
# ---------------------------------------------------------------------------


class TestProposalWalletRouting:
    def _fake_result(self) -> AaveOperationResult:
        return AaveOperationResult(
            operation=AaveOperationType.DEPOSIT,
            status=AaveOperationStatus.SUCCESS,
            asset_symbol="USDC",
            amount=Decimal("1000"),
            tx_hash="0xfake",
        )

    def test_yamamoto_proposal_uses_yamamoto_wallet(self, db_session: Session) -> None:
        """山本 (user_id=11) の提案 approve → 山本 wallet_address で execute_rebalance。"""
        from app.proposals.router import _execute_aave_for_proposal

        yamamoto = _make_partner(db_session, uid=11, wallet=YAMAMOTO_WALLET)
        proposal = _make_proposal(db_session, user_id=yamamoto.id)
        db_session.commit()

        captured_wallet: list[str] = []

        def _mock_execute(**kwargs: object) -> AaveOperationResult:
            captured_wallet.append(str(kwargs.get("wallet_address", "")))
            return self._fake_result()

        with patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
            side_effect=_mock_execute,
        ):
            _execute_aave_for_proposal(proposal, db_session)

        assert len(captured_wallet) == 1
        assert captured_wallet[0] == YAMAMOTO_WALLET

    def test_hashiguchi_proposal_uses_hashiguchi_wallet(self, db_session: Session) -> None:
        """橋口 (user_id=18) の提案 approve → 橋口 wallet_address で execute_rebalance。"""
        from app.proposals.router import _execute_aave_for_proposal

        hashiguchi = _make_partner(db_session, uid=18, wallet=HASHIGUCHI_WALLET)
        proposal = _make_proposal(db_session, user_id=hashiguchi.id)
        db_session.commit()

        captured_wallet: list[str] = []

        def _mock_execute(**kwargs: object) -> AaveOperationResult:
            captured_wallet.append(str(kwargs.get("wallet_address", "")))
            return self._fake_result()

        with patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
            side_effect=_mock_execute,
        ):
            _execute_aave_for_proposal(proposal, db_session)

        assert len(captured_wallet) == 1
        assert captured_wallet[0] == HASHIGUCHI_WALLET

    def test_wallets_are_not_swapped(self, db_session: Session) -> None:
        """橋口提案が山本 wallet で実行されないこと（致命構造の防止）。"""
        from app.proposals.router import _execute_aave_for_proposal

        _make_partner(db_session, uid=11, wallet=YAMAMOTO_WALLET)
        hashiguchi = _make_partner(db_session, uid=18, wallet=HASHIGUCHI_WALLET)
        proposal_h = _make_proposal(db_session, user_id=hashiguchi.id)
        db_session.commit()

        captured_wallet: list[str] = []

        def _mock_execute(**kwargs: object) -> AaveOperationResult:
            captured_wallet.append(str(kwargs.get("wallet_address", "")))
            return self._fake_result()

        with patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
            side_effect=_mock_execute,
        ):
            _execute_aave_for_proposal(proposal_h, db_session)

        assert len(captured_wallet) == 1
        # 橋口の提案は橋口 wallet → 山本 wallet ではない
        assert captured_wallet[0] == HASHIGUCHI_WALLET
        assert captured_wallet[0] != YAMAMOTO_WALLET


# ---------------------------------------------------------------------------
# NULL wallet ガード: wallet_address 未設定 partner は執行されない
# ---------------------------------------------------------------------------


class TestNullWalletBlocking:
    """DoD: (a) 執行されない (b) デフォルト wallet にフォールバックしない (c) 明示エラー"""

    def test_null_wallet_blocks_execution(self, db_session: Session) -> None:
        """wallet_address=None の partner 提案は execute_rebalance が呼ばれずに failed になる。"""
        from app.proposals.router import _execute_aave_for_proposal

        # wallet_address を設定しない partner
        partner = _make_partner(db_session, uid=99, wallet="")
        partner.wallet_address = None
        proposal = _make_proposal(db_session, user_id=partner.id)
        db_session.commit()

        execute_called = []

        def _should_not_be_called(**kwargs: object) -> AaveOperationResult:
            execute_called.append(kwargs)
            raise AssertionError("execute_rebalance should NOT be called for null-wallet partner")

        with patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
            side_effect=_should_not_be_called,
        ):
            _execute_aave_for_proposal(proposal, db_session)

        # (a) 執行されない
        assert len(execute_called) == 0
        # (c) 明示エラー: proposal は failed になる
        assert proposal.status == "failed"

    def test_null_wallet_explicit_error_message(self, db_session: Session) -> None:
        """wallet_address=None のとき error_message に wallet_address が含まれる。"""
        from app.proposals.router import _execute_aave_for_proposal

        partner = _make_partner(db_session, uid=99, wallet="")
        partner.wallet_address = None
        proposal = _make_proposal(db_session, user_id=partner.id)
        db_session.commit()

        with patch("app.aave.service.MultiChainAaveService.execute_rebalance"):
            _execute_aave_for_proposal(proposal, db_session)

        assert proposal.status == "failed"
        assert proposal.error_message is not None
        assert "wallet_address" in proposal.error_message

    def test_no_default_wallet_fallback(self, db_session: Session) -> None:
        """wallet_address=None の partner が山本 wallet で実行されないこと。"""
        import os

        from app.proposals.router import _execute_aave_for_proposal

        partner = _make_partner(db_session, uid=99, wallet="")
        partner.wallet_address = None
        proposal = _make_proposal(db_session, user_id=partner.id)
        db_session.commit()

        captured_wallet: list[str] = []

        def _capture(**kwargs: object) -> AaveOperationResult:
            captured_wallet.append(str(kwargs.get("wallet_address", "(none)")))
            raise AssertionError("execute_rebalance should NOT be called")

        # 環境変数に山本 wallet が設定されていても使われない
        with (
            patch.dict(os.environ, {"AAVE_WALLET_ADDRESS": YAMAMOTO_WALLET}),
            patch(
                "app.aave.service.MultiChainAaveService.execute_rebalance",
                side_effect=_capture,
            ),
        ):
            _execute_aave_for_proposal(proposal, db_session)

        # execute_rebalance は一度も呼ばれず、山本 wallet は混入しない
        assert len(captured_wallet) == 0
        assert proposal.status == "failed"

    def test_empty_string_wallet_also_blocked(self, db_session: Session) -> None:
        """wallet_address='' (空文字) も None と同様にブロックされる。"""
        from app.proposals.router import _execute_aave_for_proposal

        partner = _make_partner(db_session, uid=99, wallet="")
        # wallet_address は "" のまま (Noneでなく空文字)
        proposal = _make_proposal(db_session, user_id=partner.id)
        db_session.commit()

        with patch("app.aave.service.MultiChainAaveService.execute_rebalance") as mock_exec:
            _execute_aave_for_proposal(proposal, db_session)

        mock_exec.assert_not_called()
        assert proposal.status == "failed"

    def test_yamamoto_wallet_not_mixed_into_hashiguchi_null(self, db_session: Session) -> None:
        """山本が設定済みで橋口が NULL → 橋口の提案は山本 wallet で実行されない。"""
        from app.proposals.router import _execute_aave_for_proposal

        _make_partner(db_session, uid=11, wallet=YAMAMOTO_WALLET)
        hashiguchi = _make_partner(db_session, uid=18, wallet="")
        hashiguchi.wallet_address = None
        proposal_h = _make_proposal(db_session, user_id=hashiguchi.id)
        db_session.commit()

        captured: list[str] = []

        def _capture(**kwargs: object) -> AaveOperationResult:
            captured.append(str(kwargs.get("wallet_address", "")))
            raise AssertionError("should not execute")

        with patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
            side_effect=_capture,
        ):
            _execute_aave_for_proposal(proposal_h, db_session)

        # 山本 wallet は混入しない
        assert YAMAMOTO_WALLET not in captured
        assert proposal_h.status == "failed"


# ---------------------------------------------------------------------------
# snapshot_service: wallet 未設定 partner は env フォールバックなしで skip
# ---------------------------------------------------------------------------


class TestSnapshotNullWalletSkip:
    def test_partner_without_wallet_is_skipped_not_env_fallback(self, db_session: Session) -> None:
        """wallet_address 未設定 partner → env AAVE_WALLET_ADDRESS でテスターの snapshot を取らない。"""
        import os
        from unittest.mock import patch

        partner = _make_partner(db_session, uid=99, wallet="")
        partner.wallet_address = None
        _make_tester(db_session, uid=991, invited_by=partner.id)
        db_session.commit()

        mock_client = MagicMock()
        mock_client.get_account_data.return_value = AccountData(
            total_collateral_usd=Decimal("1000"),
            total_debt_usd=Decimal("0"),
            available_borrows_usd=Decimal("500"),
            health_factor=Decimal("inf"),
        )

        with (
            patch.dict(os.environ, {"AAVE_WALLET_ADDRESS": YAMAMOTO_WALLET}),
            patch(
                "app.portfolio.snapshot_service.get_default_aave_client",
                return_value=mock_client,
            ),
        ):
            record_portfolio_snapshot(db_session)

        # wallet なし partner のテスター (uid=991) には snapshot が作られない
        # (admin fallback は別ロジック — partner の wallet 汚染防止のみ確認)
        snap = db_session.query(PortfolioSnapshot).filter_by(user_id=991).first()
        assert snap is None

        # partner のテスターに対して YAMAMOTO_WALLET で snapshot が作られていないことが主目的（上で確認済み）
