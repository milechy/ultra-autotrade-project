# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_phase2d_a_wiring.py
"""スライス2-D-A: 既存安全装置の AUTO 執行経路への結線。

検証:
- 手動承認 (approve_proposal) は AUTO_EXECUTION_ENABLED の値に関わらず委譲枠なしで通る
  （2026-07-16 修正: is_auto_execution=False 固定。Rule8 は本エンドポイント対象外）。
- risk_limiter %クランプ結線: check_trade_within_limits が違反を返すと execute_rebalance を
  呼ばず status を 'approved' 据え置き（transient）。
- _daily_traded_usd_for_user: 当日 approved/executed 合計（自分以外）。

PolicyEngine Rule8（AUTO 執行は有効委譲枠必須）自体は健在。適用対象は将来の
スケジューラ発・無承認自動実行（is_auto_execution=True で呼ばれる経路）のみで、
そちらのテストは backend/tests/test_auto_execute_trigger.py（PR3以降）に分離する。
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Generator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-phase2d-a")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "phase2da_admin@example.com")

from app.aave.schemas import (  # noqa: E402
    AaveOperationResult,
    AaveOperationStatus,
    AaveOperationType,
)
from app.auth.models import User  # noqa: E402
from app.automation.safety_gate import HardStopResult  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.proposals.models import Proposal  # noqa: E402

_WALLET = "0xPhase2dA00000000000000000000000000000001"


# --------------------------------------------------------------------------- #
# 単体（in-memory db_session）
# --------------------------------------------------------------------------- #
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


def _make_user(db: Session, uid: int = 11) -> User:
    user = User(
        id=uid,
        email=f"phase2da{uid}@test.com",
        username=f"phase2da{uid}",
        hashed_password="x",
        role="partner",
        is_active=True,
        wallet_address=_WALLET,
    )
    db.add(user)
    db.flush()
    return user


def _make_proposal(db: Session, user_id: int, status: str = "approved") -> Proposal:
    proposal = Proposal(
        user_id=user_id,
        operation="SUPPLY",
        asset="USDC",
        amount=Decimal("1000"),
        amount_usd=Decimal("1000.00"),
        reason="phase2d-a test",
        status=status,
        approved_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(proposal)
    db.flush()
    return proposal


def _fake_result() -> AaveOperationResult:
    return AaveOperationResult(
        operation=AaveOperationType.DEPOSIT,
        status=AaveOperationStatus.SUCCESS,
        asset_symbol="USDC",
        amount=Decimal("1000"),
        tx_hash="0xphase2da",
    )


def test_risk_limiter_holds_execution(db_session: Session) -> None:
    """check_trade_within_limits が違反を返すと execute せず 'approved' 据え置き。"""
    from app.proposals.router import _execute_aave_for_proposal

    user = _make_user(db_session)
    proposal = _make_proposal(db_session, user_id=user.id)
    db_session.commit()

    called: list[bool] = []

    def _mock_execute(**kwargs: object) -> AaveOperationResult:
        called.append(True)
        return _fake_result()

    with (
        patch.dict(os.environ, {"CUSTODIAL_EXECUTION_ENABLED": "true"}),
        patch(
            "app.automation.safety_gate.evaluate_hard_stop",
            return_value=HardStopResult(blocked=False),
        ),
        patch(
            "app.aave.risk_limiter.check_trade_within_limits",
            return_value="single trade exceeds 10% of total assets",
        ),
        patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
            side_effect=_mock_execute,
        ),
    ):
        _execute_aave_for_proposal(proposal, db_session)

    assert called == []  # execute_rebalance は呼ばれない
    assert proposal.status == "approved"  # transient: failed にしない
    assert proposal.tx_hash is None


def test_risk_limiter_pass_allows_execution(db_session: Session) -> None:
    """違反なし（None）なら従来通り execute まで進む。"""
    from app.proposals.router import _execute_aave_for_proposal

    user = _make_user(db_session)
    proposal = _make_proposal(db_session, user_id=user.id)
    db_session.commit()

    called: list[bool] = []

    def _mock_execute(**kwargs: object) -> AaveOperationResult:
        called.append(True)
        return _fake_result()

    with (
        patch.dict(os.environ, {"CUSTODIAL_EXECUTION_ENABLED": "true"}),
        patch(
            "app.automation.safety_gate.evaluate_hard_stop",
            return_value=HardStopResult(blocked=False),
        ),
        patch(
            "app.aave.risk_limiter.check_trade_within_limits",
            return_value=None,
        ),
        patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
            side_effect=_mock_execute,
        ),
    ):
        _execute_aave_for_proposal(proposal, db_session)

    assert called == [True]
    assert proposal.status == "executed"


def test_daily_traded_usd_for_user(db_session: Session) -> None:
    """当日 approved/executed の合計（自分以外を除外）。"""
    from app.proposals.router import _daily_traded_usd_for_user

    user = _make_user(db_session)
    p1 = _make_proposal(db_session, user_id=user.id, status="approved")
    p2 = _make_proposal(db_session, user_id=user.id, status="executed")
    _self = _make_proposal(db_session, user_id=user.id, status="approved")
    # pending は集計対象外
    _make_proposal(db_session, user_id=user.id, status="pending")
    db_session.commit()

    total = _daily_traded_usd_for_user(user.id, db_session, exclude_proposal_id=_self.id)
    # p1 + p2 = 2000（_self 除外, pending 除外）
    assert total == Decimal("2000.00")
    assert p1.id != p2.id


# --------------------------------------------------------------------------- #
# 統合（approve エンドポイント / Rule8）
# --------------------------------------------------------------------------- #
@pytest.fixture()
def test_db() -> Generator:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    yield override_get_db, SessionLocal
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


@pytest.fixture()
def client(test_db: tuple) -> TestClient:
    override_get_db, _ = test_db
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _admin_token(client: TestClient, session_local: object) -> str:
    email = os.environ["INITIAL_ADMIN_EMAIL"]
    client.post(
        "/auth/register",
        json={"email": email, "username": "admin", "password": "adminpassword123"},
    )
    r = client.post("/auth/login", json={"email": email, "password": "adminpassword123"})
    token = r.json()["access_token"]
    db = session_local()
    try:
        admin = db.query(User).filter(User.email == email).first()
        if admin and not admin.wallet_address:
            admin.wallet_address = "0xTestAdminWallet0000000000000000000000000"
            db.commit()
    finally:
        db.close()
    return token


def _create_proposal(client: TestClient, token: str) -> int:
    r = client.post(
        "/api/proposals",
        json={
            "user_id": 1,
            "operation": "SUPPLY",
            "asset": "USDC",
            "amount": "1000.000000000000000000",
            "amount_usd": "1000.00",
            "reason": "phase2d-a rule8",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


def test_auto_execution_flag_no_longer_requires_grant_for_human_approval(
    client: TestClient, test_db: tuple
) -> None:
    """2026-07-16 修正の回帰テスト: approve_proposal は is_auto_execution=False 固定
    （build_partner_tx と同型、本人がクリックする承認フローのため）。
    AUTO_EXECUTION_ENABLED=true でも、委譲枠を持たない custodial ユーザーの承認は
    Rule8（有効委譲枠必須）でブロックされず、custodial 単一鍵実行まで進む。
    Rule8 は将来のスケジューラ発の無承認自動実行（is_auto_execution=True）専用に予約する。
    """
    _override, SessionLocal = test_db
    token = _admin_token(client, SessionLocal)
    proposal_id = _create_proposal(client, token)

    fake_result = AaveOperationResult(
        operation=AaveOperationType.DEPOSIT,
        status=AaveOperationStatus.SUCCESS,
        asset_symbol="USDC",
        amount=Decimal("1000.00"),
        tx_hash="0xauto",
    )

    with (
        patch.dict(
            os.environ,
            {"AUTO_EXECUTION_ENABLED": "true", "CUSTODIAL_EXECUTION_ENABLED": "true"},
        ),
        patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
            return_value=fake_result,
        ),
    ):
        r = client.post(
            f"/api/proposals/{proposal_id}/approve",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 200, r.text
    assert r.json()["status"] == "executed"


def test_manual_approve_without_grant_ok(client: TestClient, test_db: tuple) -> None:
    """AUTO 無効（既定）は委譲枠なしでも承認できる（Rule8 は AUTO 経路のみ）。"""
    _override, SessionLocal = test_db
    token = _admin_token(client, SessionLocal)
    proposal_id = _create_proposal(client, token)

    # AUTO_EXECUTION_ENABLED 未設定 = false。手動署名待ちで approved になる。
    r = client.post(
        f"/api/proposals/{proposal_id}/approve",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"


# ---------------------------------------------------------------------------
# [shadow mode] per-user 総資産の観測（2026-07-17）
#
# CLAUDE.md Rule 3/4 は total_assets=None のため実際には効いていない。分母の resolver は
# 用意したが、いきなり有効化すると本番ユーザーを止める（sizing の $50 下限 × 10% ルールは
# 総資産 $500 未満で両立しない / 最低入金は $1,000）。まず観測だけ行う。
# ---------------------------------------------------------------------------


def test_shadow_does_not_change_execution_behavior(db_session: Session) -> None:
    """★shadow の総資産が「ブロックすべき」と言っても、**実際にはブロックしない**こと。

    shadow の目的は観測であって enforcement ではない。ここが壊れると、意図せず本番ユーザーの
    取引を止める（= 本タスクで最も避けたい事故）。
    """
    from app.proposals.router import _execute_aave_for_proposal

    user = _make_user(db_session)
    proposal = _make_proposal(db_session, user_id=user.id)
    db_session.commit()

    called: list[bool] = []

    def _mock_execute(**kwargs: object) -> AaveOperationResult:
        called.append(True)
        return _fake_result()

    with (
        patch.dict(os.environ, {"CUSTODIAL_EXECUTION_ENABLED": "true"}),
        patch(
            "app.automation.safety_gate.evaluate_hard_stop",
            return_value=HardStopResult(blocked=False),
        ),
        # 総資産が $1（= 提案額は確実に 10% 超）と観測されても…
        patch(
            "app.users.total_assets_resolver.resolve_user_total_assets_usd",
            return_value=Decimal("1"),
        ),
        patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
            side_effect=_mock_execute,
        ),
    ):
        _execute_aave_for_proposal(proposal, db_session)

    # …執行は止まらない（limiter には None が渡り続けるため）
    assert called, "shadow 観測が執行をブロックしてはならない"


def test_shadow_passes_none_to_limiter(db_session: Session) -> None:
    """limiter に渡る total_assets_usd が **None のままである**こと（挙動変化ゼロの担保）。"""
    from app.proposals.router import _execute_aave_for_proposal

    user = _make_user(db_session)
    proposal = _make_proposal(db_session, user_id=user.id)
    db_session.commit()

    seen: list[object] = []

    def _spy(**kwargs: object) -> None:
        seen.append(kwargs.get("total_assets_usd"))
        return None

    with (
        patch.dict(os.environ, {"CUSTODIAL_EXECUTION_ENABLED": "true"}),
        patch(
            "app.automation.safety_gate.evaluate_hard_stop",
            return_value=HardStopResult(blocked=False),
        ),
        patch(
            "app.users.total_assets_resolver.resolve_user_total_assets_usd",
            return_value=Decimal("12345"),
        ),
        patch("app.aave.risk_limiter.check_trade_within_limits", side_effect=_spy),
        patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
            return_value=_fake_result(),
        ),
    ):
        _execute_aave_for_proposal(proposal, db_session)

    # shadow 側の試算呼び出しと、実ゲートの呼び出しの両方が来る。
    # **実ゲートに渡るのは None**（shadow の 12345 が漏れていない）こと。
    assert None in seen, f"実ゲートに None 以外が渡っている: {seen}"


def test_shadow_failure_does_not_break_execution(db_session: Session) -> None:
    """観測が例外を投げても執行を壊さないこと（観測は執行より弱い）。"""
    from app.proposals.router import _execute_aave_for_proposal

    user = _make_user(db_session)
    proposal = _make_proposal(db_session, user_id=user.id)
    db_session.commit()

    called: list[bool] = []

    with (
        patch.dict(os.environ, {"CUSTODIAL_EXECUTION_ENABLED": "true"}),
        patch(
            "app.automation.safety_gate.evaluate_hard_stop",
            return_value=HardStopResult(blocked=False),
        ),
        patch(
            "app.users.total_assets_resolver.resolve_user_total_assets_usd",
            side_effect=RuntimeError("rpc down"),
        ),
        patch(
            "app.aave.service.MultiChainAaveService.execute_rebalance",
            side_effect=lambda **_: (called.append(True), _fake_result())[1],
        ),
    ):
        _execute_aave_for_proposal(proposal, db_session)

    assert called, "観測の失敗が執行を止めてはならない"
