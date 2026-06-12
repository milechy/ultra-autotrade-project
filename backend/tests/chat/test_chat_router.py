# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/chat/test_chat_router.py
"""
チャット API エンドポイントのテスト。

テストケース:
① 未認証リクエスト → 401
② POST /api/chat で user + ai 2行 INSERT + response 返却
③ anthropic_api_key=None でも fail-open（500 にならない）
④ GET /api/chat/history の before_id カーソル + has_more
⑤ 他ユーザーのメッセージは見えない（user_id 絞り込み）
"""

import os
from typing import Generator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# テスト用 JWT 設定（必須環境変数）
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-chat-tests-1234")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin@example.com")

from app.auth.models import User, UserRole
from app.auth.service import AuthService
from app.chat.models import ChatMessage
from app.database import Base
from app.main import create_app

# ---------------------------------------------------------------------------
# テスト用 SQLite DB（:memory: でセッション内完結）
# ---------------------------------------------------------------------------
TEST_DB_URL = "sqlite:///./test_chat.db"


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()
    # テスト後にファイル削除
    import os as _os

    try:
        _os.remove("./test_chat.db")
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
    """TestClient with DB override."""
    app = create_app()

    def override_get_db():
        try:
            yield db
        finally:
            pass

    from app.database import get_db  # noqa: F811

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app, raise_server_exceptions=True)


def _create_user_and_token(db: Session, email: str, wallet: str) -> tuple[User, str]:
    """テスト用ユーザーを作成し JWT を返す。"""

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(
            email=email,
            username=email.split("@")[0],
            hashed_password="hashed_dummy",
            wallet_address=wallet,
            role=UserRole.VIEWER,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token, _ = AuthService.create_access_token(user.id, user.email, user.role)
    return user, token


# ---------------------------------------------------------------------------
# ① 未認証リクエスト → 401
# ---------------------------------------------------------------------------


def test_post_chat_unauthenticated(test_client: TestClient) -> None:
    """Authorization ヘッダーなしで POST /api/chat → 401。"""
    resp = test_client.post("/api/chat", json={"message": "Hello"})
    assert resp.status_code == 401


def test_get_history_unauthenticated(test_client: TestClient) -> None:
    """Authorization ヘッダーなしで GET /api/chat/history → 401。"""
    resp = test_client.get("/api/chat/history")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# ② POST /api/chat で user + ai 2行 INSERT + response 返却
# ---------------------------------------------------------------------------


def test_post_chat_inserts_two_rows_and_returns_response(
    test_client: TestClient, db: Session
) -> None:
    """POST /api/chat で chat_messages に user + ai 2行が保存され、response キーが返る。"""
    user, token = _create_user_and_token(db, email="chatuser1@example.com", wallet="0xAAA1")

    # call_claude をモック（実 Claude API 呼び出し回避）
    with patch("app.chat.service.call_claude", return_value="テスト AI 返答"):
        resp = test_client.post(
            "/api/chat",
            json={"message": "こんにちは"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "response" in data
    assert data["response"] == "テスト AI 返答"

    # DB に user + ai 2行が保存されていること
    rows = db.query(ChatMessage).filter(ChatMessage.user_id == user.id).all()
    assert len(rows) >= 2
    roles = {r.role for r in rows}
    assert "user" in roles
    assert "ai" in roles


def test_post_chat_rejects_empty_message(test_client: TestClient, db: Session) -> None:
    """空メッセージ / 長すぎるメッセージは 422（Field バリデーション）。"""
    _user, token = _create_user_and_token(db, email="chatuser_empty@example.com", wallet="0xAAAE")
    headers = {"Authorization": f"Bearer {token}"}

    empty = test_client.post("/api/chat", json={"message": ""}, headers=headers)
    assert empty.status_code == 422

    too_long = test_client.post("/api/chat", json={"message": "あ" * 4001}, headers=headers)
    assert too_long.status_code == 422


# ---------------------------------------------------------------------------
# ③ anthropic_api_key=None でも fail-open（500 にならない）
# ---------------------------------------------------------------------------


def test_post_chat_failopen_when_no_api_key(test_client: TestClient, db: Session) -> None:
    """anthropic_api_key が None でも 200 を返し、フォールバック文言を返す。"""
    user, token = _create_user_and_token(db, email="chatuser2@example.com", wallet="0xAAA2")

    # get_ai_settings で api_key=None を返すようにモック
    from app.ai.config import AISettings

    mock_settings = AISettings(
        anthropic_api_key=None,
        openai_api_key=None,
        claude_model="claude-sonnet-4-6",
        openai_model="gpt-4o",
        min_confidence_threshold=60,
        cross_validation_enabled=False,
        prompt_version="v1",
        shadow_mode=False,
        ai_fallback_model="claude-haiku-4-5-20251001",
    )

    with patch("app.chat.service.get_ai_settings", return_value=mock_settings):
        resp = test_client.post(
            "/api/chat",
            json={"message": "APIキーなしテスト"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "response" in data
    # フォールバック文言が返ること（500 ではない）
    assert len(data["response"]) > 0


# ---------------------------------------------------------------------------
# ④ GET /api/chat/history の before_id カーソル + has_more
# ---------------------------------------------------------------------------


def test_get_history_cursor_and_has_more(test_client: TestClient, db: Session) -> None:
    """before_id カーソルと has_more フラグが正しく動作する。"""
    user, token = _create_user_and_token(db, email="chatuser3@example.com", wallet="0xAAA3")

    # 6件のメッセージを直接 INSERT
    for i in range(6):
        msg = ChatMessage(user_id=user.id, role="user" if i % 2 == 0 else "ai", content=f"msg{i}")
        db.add(msg)
    db.commit()

    # limit=3 で最初のページを取得
    resp = test_client.get(
        "/api/chat/history?limit=3",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["messages"]) == 3
    assert data["has_more"] is True

    # 取得した末尾の id を before_id として次ページを取得
    last_id = data["messages"][-1]["id"]
    resp2 = test_client.get(
        f"/api/chat/history?limit=3&before_id={last_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert len(data2["messages"]) >= 1
    # before_id より小さい id しか返らないこと
    for msg in data2["messages"]:
        assert msg["id"] < last_id


# ---------------------------------------------------------------------------
# ⑤ 他ユーザーのメッセージは見えない（user_id 絞り込み）
# ---------------------------------------------------------------------------


def test_history_user_isolation(test_client: TestClient, db: Session) -> None:
    """別ユーザーのメッセージが GET /api/chat/history に現れない。"""
    user_a, token_a = _create_user_and_token(db, email="chatuser_a@example.com", wallet="0xCCC1")
    user_b, _ = _create_user_and_token(db, email="chatuser_b@example.com", wallet="0xCCC2")

    # ユーザーBのメッセージを INSERT
    msg_b = ChatMessage(user_id=user_b.id, role="user", content="ユーザーBの秘密メッセージ")
    db.add(msg_b)
    db.commit()

    # ユーザーAとして履歴取得 → ユーザーBのメッセージが含まれないこと
    resp = test_client.get(
        "/api/chat/history?limit=100",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    contents = [m["content"] for m in data["messages"]]
    assert "ユーザーBの秘密メッセージ" not in contents
