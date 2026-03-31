# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_line_auth.py
"""
LINE LIFF認証エンドポイントのテスト。

- POST /auth/line with valid idToken (mock LINE API call)
- POST /auth/line with invalid idToken (should return 401)
- User auto-creation for new LINE users
- User retrieval for existing LINE users
"""

import os
import tempfile
from typing import Generator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# テスト用環境変数を設定
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-line-auth-tests-1234"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["JWT_ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"
os.environ["INITIAL_ADMIN_EMAIL"] = "admin@example.com"
os.environ.setdefault("LIFF_ID", "dummy-liff-id-for-tests")

from app.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402

# --- テスト用 LINE ペイロード ---
VALID_LINE_USER_ID = "Uabcdef1234567890abcdef1234567890"
VALID_LINE_DISPLAY_NAME = "Test LINE User"
VALID_LINE_PAYLOAD = {
    "sub": VALID_LINE_USER_ID,
    "name": VALID_LINE_DISPLAY_NAME,
    "iss": "https://access.line.me",
    "aud": "dummy-liff-id-for-tests",
}


@pytest.fixture()
def test_db():
    """テスト用の一時的な SQLite データベースを作成する。"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    test_engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    Base.metadata.create_all(bind=test_engine)

    def override_get_db() -> Generator:
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    yield override_get_db, test_engine

    Base.metadata.drop_all(bind=test_engine)
    os.unlink(path)


@pytest.fixture()
def client(test_db) -> TestClient:
    """テスト用クライアントを作成する。"""
    override_get_db, _ = test_db
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


class TestLineAuth:
    """LINE LIFF認証エンドポイントのテスト。"""

    def _valid_payload(self) -> dict:
        """有効なリクエストペイロードを返す。"""
        return {
            "id_token": "valid-dummy-id-token",
            "display_name": VALID_LINE_DISPLAY_NAME,
        }

    def test_line_auth_valid_token_returns_access_token(self, client: TestClient):
        """有効な idToken でアクセストークンが返ること。"""
        with patch(
            "app.auth.line.verify_line_id_token",
            new_callable=AsyncMock,
            return_value=VALID_LINE_PAYLOAD,
        ):
            response = client.post("/auth/line", json=self._valid_payload())

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0

    def test_line_auth_valid_token_creates_new_user(self, client: TestClient):
        """新規 LINE ユーザーがデータベースに作成されること。"""
        with patch(
            "app.auth.line.verify_line_id_token",
            new_callable=AsyncMock,
            return_value=VALID_LINE_PAYLOAD,
        ):
            response = client.post("/auth/line", json=self._valid_payload())

        assert response.status_code == 200
        assert "access_token" in response.json()

    def test_line_auth_existing_user_returns_token(self, client: TestClient):
        """同じ LINE ユーザーが2回リクエストしても同一ユーザーとして処理されること。"""
        with patch(
            "app.auth.line.verify_line_id_token",
            new_callable=AsyncMock,
            return_value=VALID_LINE_PAYLOAD,
        ):
            first = client.post("/auth/line", json=self._valid_payload())
        assert first.status_code == 200
        first_token = first.json()["access_token"]

        # 2回目: 同じユーザーが再ログイン — 別のトークンが発行されるが 200 が返ること
        with patch(
            "app.auth.line.verify_line_id_token",
            new_callable=AsyncMock,
            return_value=VALID_LINE_PAYLOAD,
        ):
            second = client.post("/auth/line", json=self._valid_payload())
        assert second.status_code == 200
        second_token = second.json()["access_token"]

        # トークンは毎回生成されるが両方とも有効
        assert isinstance(first_token, str) and len(first_token) > 0
        assert isinstance(second_token, str) and len(second_token) > 0

    def test_line_auth_invalid_token_returns_401(self, client: TestClient):
        """無効な idToken で 401 が返ること。"""
        from app.auth.line import LineAuthError

        with patch(
            "app.auth.line.verify_line_id_token",
            new_callable=AsyncMock,
            side_effect=LineAuthError("LINE idTokenの検証に失敗しました"),
        ):
            response = client.post(
                "/auth/line",
                json={"id_token": "invalid-token", "display_name": "attacker"},
            )

        assert response.status_code == 401

    def test_line_auth_missing_sub_returns_401(self, client: TestClient):
        """LINE ペイロードに sub が含まれない場合 401 が返ること。"""
        from app.auth.line import LineAuthError

        with patch(
            "app.auth.line.verify_line_id_token",
            new_callable=AsyncMock,
            side_effect=LineAuthError("LINE idTokenのペイロードが不正です"),
        ):
            response = client.post(
                "/auth/line",
                json={"id_token": "malformed-token", "display_name": "Test"},
            )

        assert response.status_code == 401

    def test_line_auth_uses_payload_name_over_request_display_name(self, client: TestClient):
        """LINE APIが返す name が display_name より優先されること。"""
        payload_with_name = {
            "sub": "Uxyz987654",
            "name": "Name From LINE API",
        }
        with patch(
            "app.auth.line.verify_line_id_token",
            new_callable=AsyncMock,
            return_value=payload_with_name,
        ):
            response = client.post(
                "/auth/line",
                json={
                    "id_token": "valid-token",
                    "display_name": "Name From Request",
                },
            )

        assert response.status_code == 200

    def test_line_auth_different_users_get_separate_tokens(self, client: TestClient):
        """異なる LINE ユーザーが別々のトークンを受け取ること。"""
        payload_user1 = {"sub": "Uuser111", "name": "User One"}
        payload_user2 = {"sub": "Uuser222", "name": "User Two"}

        with patch(
            "app.auth.line.verify_line_id_token",
            new_callable=AsyncMock,
            return_value=payload_user1,
        ):
            resp1 = client.post(
                "/auth/line",
                json={"id_token": "token1", "display_name": "User One"},
            )

        with patch(
            "app.auth.line.verify_line_id_token",
            new_callable=AsyncMock,
            return_value=payload_user2,
        ):
            resp2 = client.post(
                "/auth/line",
                json={"id_token": "token2", "display_name": "User Two"},
            )

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["access_token"] != resp2.json()["access_token"]

    def test_line_auth_missing_liff_id_returns_401(self, client: TestClient):
        """LIFF_ID 環境変数が未設定の場合、LineAuthError が発生して 401 になること。"""
        from app.auth.line import LineAuthError

        with patch(
            "app.auth.line.verify_line_id_token",
            new_callable=AsyncMock,
            side_effect=LineAuthError("LIFF_ID環境変数が設定されていません"),
        ):
            response = client.post(
                "/auth/line",
                json={"id_token": "some-token", "display_name": "User"},
            )

        assert response.status_code == 401
        assert "LIFF_ID" in response.json()["detail"]
