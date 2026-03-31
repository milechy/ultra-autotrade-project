# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/auth/test_wallet_connect.py
"""
WalletConnect 認証のテスト。

- 有効な署名でユーザーが自動作成されること
- 無効な署名で 401 が返ること
- 既存 wallet ユーザーには既存 JWT が返ること
- 新規ユーザーは needs_terms_acceptance = True
"""

import os
import tempfile
from typing import Generator

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# テスト用環境変数を設定
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-wallet-tests-1234"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["JWT_ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"
os.environ["INITIAL_ADMIN_EMAIL"] = "admin@example.com"

from app.database import Base, get_db
from app.main import create_app

# テスト用秘密鍵（テスト専用、本番環境では使用しない）
TEST_PRIVATE_KEY = "0x4c0883a69102937d6231471b5dbb6e538eba2ef158d8b8b75f21c8f4d9c3f5a2"
TEST_ACCOUNT = Account.from_key(TEST_PRIVATE_KEY)
TEST_WALLET_ADDRESS = TEST_ACCOUNT.address


def _sign_message(message: str, private_key: str) -> str:
    """テスト用署名を生成する。"""
    encoded = encode_defunct(text=message)
    signed = Account.sign_message(encoded, private_key=private_key)
    return signed.signature.hex()


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


class TestWalletConnect:
    """WalletConnect 認証のテスト。"""

    def _make_valid_request(self) -> dict:
        """有効なリクエストペイロードを生成する。"""
        message = "Ultra AutoTrade: test at 2026-03-24T00:00:00Z"
        signature = _sign_message(message, TEST_PRIVATE_KEY)
        return {
            "wallet_address": TEST_WALLET_ADDRESS,
            "message": message,
            "signature": signature,
        }

    def test_wallet_connect_creates_new_user(self, client: TestClient):
        """有効な署名で新規ユーザーが自動作成されること。"""
        payload = self._make_valid_request()
        response = client.post("/auth/wallet/connect", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["is_new_user"] is True

    def test_wallet_connect_new_user_needs_terms(self, client: TestClient):
        """新規ユーザーは needs_terms_acceptance = True になること。"""
        payload = self._make_valid_request()
        response = client.post("/auth/wallet/connect", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["needs_terms_acceptance"] is True

    def test_wallet_connect_existing_user_returns_token(self, client: TestClient):
        """既存 wallet ユーザーには JWT が返り、is_new_user = False になること。"""
        payload = self._make_valid_request()

        # 1回目: ユーザー作成
        first_response = client.post("/auth/wallet/connect", json=payload)
        assert first_response.status_code == 200
        assert first_response.json()["is_new_user"] is True

        # 2回目: 既存ユーザー
        second_response = client.post("/auth/wallet/connect", json=payload)
        assert second_response.status_code == 200
        second_data = second_response.json()
        assert "access_token" in second_data
        assert second_data["is_new_user"] is False

    def test_wallet_connect_invalid_signature_returns_401(self, client: TestClient):
        """無効な署名で 401 が返ること。"""
        message = "Ultra AutoTrade: test at 2026-03-24T00:00:00Z"
        # 別の秘密鍵で署名（アドレスが一致しない）
        other_key = "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        wrong_signature = _sign_message(message, other_key)

        response = client.post(
            "/auth/wallet/connect",
            json={
                "wallet_address": TEST_WALLET_ADDRESS,
                "message": message,
                "signature": wrong_signature,
            },
        )
        assert response.status_code == 401

    def test_wallet_connect_malformed_signature_returns_401(self, client: TestClient):
        """壊れた署名で 401 が返ること。"""
        message = "Ultra AutoTrade: test at 2026-03-24T00:00:00Z"
        response = client.post(
            "/auth/wallet/connect",
            json={
                "wallet_address": TEST_WALLET_ADDRESS,
                "message": message,
                "signature": "0xinvalidsignature",
            },
        )
        assert response.status_code == 401

    def test_wallet_connect_address_normalized_to_lowercase(self, client: TestClient):
        """ウォレットアドレスが小文字で保存されること。"""
        message = "Ultra AutoTrade: test at 2026-03-24T00:00:00Z"
        signature = _sign_message(message, TEST_PRIVATE_KEY)

        # チェックサム付きアドレス（大文字混在）で送信
        response = client.post(
            "/auth/wallet/connect",
            json={
                "wallet_address": TEST_WALLET_ADDRESS,  # チェックサム付き
                "message": message,
                "signature": signature,
            },
        )
        assert response.status_code == 200

        # 小文字アドレスでも同一ユーザーとして認識される
        lower_address = TEST_WALLET_ADDRESS.lower()
        signature2 = _sign_message(message, TEST_PRIVATE_KEY)
        response2 = client.post(
            "/auth/wallet/connect",
            json={
                "wallet_address": lower_address,
                "message": message,
                "signature": signature2,
            },
        )
        assert response2.status_code == 200
        assert response2.json()["is_new_user"] is False

    def test_wallet_connect_returns_expires_in(self, client: TestClient):
        """レスポンスに expires_in が含まれること。"""
        payload = self._make_valid_request()
        response = client.post("/auth/wallet/connect", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "expires_in" in data
        assert data["expires_in"] > 0
