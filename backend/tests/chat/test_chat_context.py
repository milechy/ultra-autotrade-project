# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/chat/test_chat_context.py
"""
build_context_block() のテスト。

チャット画面はサジェストボタンのみ（自由入力なし）のため、AI には
ユーザー本人の実データ（ポートフォリオ・AI判定・リスク設定）を渡す必要がある。

テストケース:
① データなしユーザー → 各項目が「データなし」で明示される
② ポートフォリオ・AI判定データありユーザー → 実データが文字列に含まれる
③ 本人宛のAI判定が無い場合 → システム判定（user_id IS NULL）にフォールバック
④ POST /api/chat が call_claude にコンテキストを渡している
"""

import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Generator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-chat-context-1234")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin@example.com")

from app.ai.models import AIDecision
from app.auth.models import User, UserRole
from app.auth.service import AuthService
from app.chat.service import build_context_block
from app.database import Base
from app.main import create_app
from app.portfolio.models import PortfolioHistory, PortfolioSnapshot

TEST_DB_URL = "sqlite:///./test_chat_context.db"


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()
    import os as _os

    try:
        _os.remove("./test_chat_context.db")
    except FileNotFoundError:
        pass


@pytest.fixture()
def db(engine) -> Generator[Session, None, None]:
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def test_client(db: Session):
    app = create_app()

    def override_get_db():
        try:
            yield db
        finally:
            pass

    from app.database import get_db  # noqa: F811

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app, raise_server_exceptions=True)


def _create_user(db: Session, email: str, wallet: str, risk_mode: str = "balanced") -> User:
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(
            email=email,
            username=email.split("@")[0],
            hashed_password="hashed_dummy",
            wallet_address=wallet,
            role=UserRole.VIEWER,
            is_active=True,
            risk_mode=risk_mode,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# ① データなしユーザー
# ---------------------------------------------------------------------------


def test_build_context_block_no_data(db: Session) -> None:
    """データなしユーザーは各項目で「データなし」が明示される（推測データを含まない）。"""
    user = _create_user(db, email="ctx_nodata@example.com", wallet="0xCTX1")

    context = build_context_block(db, user)

    assert "リスクモード: balanced" in context
    assert "データなし" in context
    assert "まだ資産スナップショットが記録されていません" in context
    assert "まだAI判定が実行されていません" in context


# ---------------------------------------------------------------------------
# ② 実データあり
# ---------------------------------------------------------------------------


def test_build_context_block_with_real_data(db: Session) -> None:
    """ポートフォリオ・AI判定の実データが文字列に反映される。"""
    user = _create_user(
        db, email="ctx_withdata@example.com", wallet="0xCTX2", risk_mode="aggressive"
    )

    db.add(
        PortfolioSnapshot(
            user_id=user.id,
            total_value_usd=Decimal("12345.67"),
            total_supply_usd=Decimal("12345.67"),
            total_borrow_usd=Decimal("0"),
            health_factor=Decimal("2.5000"),
            recorded_at=datetime.now(timezone.utc),
        )
    )
    db.add(
        PortfolioHistory(
            user_id=user.id,
            period_type="monthly",
            period_start=datetime(2026, 6, 1, tzinfo=timezone.utc),
            period_end=datetime(2026, 6, 30, tzinfo=timezone.utc),
            open_value_usd=Decimal("10000.00"),
            close_value_usd=Decimal("10500.00"),
            high_value_usd=Decimal("10600.00"),
            low_value_usd=Decimal("9900.00"),
            pnl_usd=Decimal("500.00"),
            pnl_pct=Decimal("5.00"),
        )
    )
    db.add(
        AIDecision(
            user_id=user.id,
            query="今の運用状況は？",
            action="BUY",
            confidence=78,
            reason="Aaveプールの利用率が低下し供給APYが上昇したため。",
            primary_provider="claude",
            primary_action="BUY",
            primary_confidence=78,
            agreed=True,
        )
    )
    db.commit()

    context = build_context_block(db, user)

    assert "リスクモード: aggressive" in context
    assert "$12,345.67" in context
    assert "2.50" in context  # Health Factor
    assert "5.00%" in context  # 月次損益率
    assert "BUY" in context
    assert "Aaveプールの利用率が低下し供給APYが上昇したため" in context


# ---------------------------------------------------------------------------
# ③ システム判定へのフォールバック
# ---------------------------------------------------------------------------


def test_build_context_block_falls_back_to_system_decision(db: Session) -> None:
    """本人宛のAI判定が無い場合、システム判定（user_id IS NULL）が使われる。"""
    user = _create_user(db, email="ctx_fallback@example.com", wallet="0xCTX3")

    db.add(
        AIDecision(
            user_id=None,
            query="system tick",
            action="HOLD",
            confidence=55,
            reason="市場のボラティリティが高いため様子見。",
            primary_provider="claude",
            primary_action="HOLD",
            primary_confidence=55,
            agreed=True,
        )
    )
    db.commit()

    context = build_context_block(db, user)

    assert "HOLD" in context
    assert "市場のボラティリティが高いため様子見" in context


# ---------------------------------------------------------------------------
# ④ POST /api/chat が call_claude にコンテキストを渡している
# ---------------------------------------------------------------------------


def test_post_chat_passes_context_to_call_claude(test_client: TestClient, db: Session) -> None:
    """POST /api/chat が call_claude(message, context_block) の第2引数にユーザー実データを渡す。"""
    user = _create_user(
        db, email="ctx_apicheck@example.com", wallet="0xCTX4", risk_mode="conservative"
    )

    captured: dict[str, str] = {}

    def _fake_call_claude(message: str, context_block: str) -> str:
        captured["message"] = message
        captured["context_block"] = context_block
        return "テスト応答"

    token, _ = AuthService.create_access_token(user.id, user.email, user.role)

    with patch("app.chat.service.call_claude", side_effect=_fake_call_claude):
        resp = test_client.post(
            "/api/chat",
            json={"message": "今の運用状況は？"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    assert captured["message"] == "今の運用状況は？"
    assert "リスクモード: conservative" in captured["context_block"]
