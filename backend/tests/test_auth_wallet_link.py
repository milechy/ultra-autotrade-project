# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_auth_wallet_link.py
"""
POST /auth/wallet/link テスト (F-17 L1 / Asana 1214658266551885)。

5 ケース:
- 200: 認証済み + 有効署名 → 紐付け成功
- 401: Authorization ヘッダーなし → 未認証
- 422: 署名検証失敗
- 409: 別ユーザーが同 wallet を既にリンク済み
- 404: privy_did 不一致 (JWT ユーザーと wallet ユーザーが別人)
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

# テスト用環境変数 (import 前に設定)
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-wallet-link-tests-1234"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["JWT_ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"
os.environ["INITIAL_ADMIN_EMAIL"] = "admin@example.com"

from app.auth.models import User, UserRole
from app.auth.service import AuthService
from app.database import Base, get_db
from app.main import create_app

# テスト用秘密鍵 (テスト専用、本番環境では使用しない)
TEST_PRIVATE_KEY = "0x4c0883a69102937d6231471b5dbb6e538eba2ef158d8b8b75f21c8f4d9c3f5a2"
TEST_ACCOUNT = Account.from_key(TEST_PRIVATE_KEY)
TEST_WALLET_ADDRESS = TEST_ACCOUNT.address  # checksum 付き

OTHER_PRIVATE_KEY = "0x1111111111111111111111111111111111111111111111111111111111111111"


def _sign(message: str, private_key: str) -> str:
    encoded = encode_defunct(text=message)
    signed = Account.sign_message(encoded, private_key=private_key)
    return signed.signature.hex()


@pytest.fixture()
def test_db():
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

    yield override_get_db, TestSessionLocal

    Base.metadata.drop_all(bind=test_engine)
    os.unlink(path)


@pytest.fixture()
def client(test_db) -> TestClient:
    override_get_db, _ = test_db
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _make_user(
    SessionLocal,
    *,
    email: str = "viewer@example.com",
    username: str = "viewer1",
    wallet_address: str | None = None,
    privy_did: str | None = None,
) -> tuple[int, str]:
    """テストユーザーを作成し、(user_id, jwt_token) を返す。"""
    with SessionLocal() as session:
        user = User(
            email=email,
            username=username,
            hashed_password=AuthService.hash_password("test-password-123"),
            role=UserRole.VIEWER.value,
            wallet_address=wallet_address.lower() if wallet_address else None,
            privy_did=privy_did,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        token, _ = AuthService.create_access_token(
            user_id=user.id, email=user.email, role=user.role
        )
        return user.id, token


def _valid_payload(message: str = "Ultra AutoTrade: link 2026-05-10T00:00:00Z") -> dict:
    return {
        "address": TEST_WALLET_ADDRESS,
        "signature": _sign(message, TEST_PRIVATE_KEY),
        "message": message,
    }


class TestWalletLink:
    """POST /auth/wallet/link の 5 ケース。"""

    # ── 200 ────────────────────────────────────────────────────────────────
    def test_200_authenticated_valid_signature_links_wallet(self, client: TestClient, test_db):
        _, SessionLocal = test_db
        user_id, token = _make_user(SessionLocal)

        payload = _valid_payload()
        response = client.post(
            "/auth/wallet/link",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200, response.json()
        data = response.json()
        assert data["user_id"] == user_id
        assert data["wallet_address"] == TEST_WALLET_ADDRESS.lower()
        assert "linked_at" in data
        # ISO8601 文字列であること (最低限の sanity check)
        assert "T" in data["linked_at"]

        # DB 反映確認
        with SessionLocal() as session:
            updated = session.query(User).filter(User.id == user_id).first()
            assert updated is not None
            assert updated.wallet_address == TEST_WALLET_ADDRESS.lower()

    # ── 401 ────────────────────────────────────────────────────────────────
    def test_401_no_authorization_header_returns_unauthenticated(self, client: TestClient):
        # token なし
        response = client.post("/auth/wallet/link", json=_valid_payload())
        assert response.status_code == 401

    # ── 422 ────────────────────────────────────────────────────────────────
    def test_422_invalid_signature_returns_422(self, client: TestClient, test_db):
        _, SessionLocal = test_db
        _, token = _make_user(SessionLocal)

        message = "Ultra AutoTrade: link 2026-05-10T00:00:00Z"
        # 別の private key で署名 → recover が別アドレスになるので一致しない
        wrong_signature = _sign(message, OTHER_PRIVATE_KEY)

        response = client.post(
            "/auth/wallet/link",
            json={
                "address": TEST_WALLET_ADDRESS,
                "signature": wrong_signature,
                "message": message,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422, response.json()
        assert "signature" in response.json()["detail"].lower()

    # ── 409 ────────────────────────────────────────────────────────────────
    def test_409_wallet_already_linked_to_another_user(self, client: TestClient, test_db):
        _, SessionLocal = test_db
        # 別ユーザー A が既に同じ wallet を保持
        _make_user(
            SessionLocal,
            email="other@example.com",
            username="other1",
            wallet_address=TEST_WALLET_ADDRESS,
        )
        # JWT ユーザー B (ウォレット未紐付け、privy_did も未設定)
        _, token_b = _make_user(
            SessionLocal,
            email="b@example.com",
            username="userb1",
        )

        response = client.post(
            "/auth/wallet/link",
            json=_valid_payload(),
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert response.status_code == 409, response.json()
        assert "already" in response.json()["detail"].lower()

    # ── 404 ────────────────────────────────────────────────────────────────
    def test_404_privy_did_mismatch_jwt_user_vs_wallet_user(self, client: TestClient, test_db):
        _, SessionLocal = test_db
        # 別ユーザー A (wallet + privy_did 設定済み)
        _make_user(
            SessionLocal,
            email="walletowner@example.com",
            username="walletowner",
            wallet_address=TEST_WALLET_ADDRESS,
            privy_did="did:privy:owner-of-wallet",
        )
        # JWT ユーザー B (privy_did 別人)
        _, token_b = _make_user(
            SessionLocal,
            email="impostor@example.com",
            username="impostor",
            privy_did="did:privy:different-person",
        )

        response = client.post(
            "/auth/wallet/link",
            json=_valid_payload(),
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert response.status_code == 404, response.json()
        assert (
            "privy_did" in response.json()["detail"].lower()
            or "match" in response.json()["detail"].lower()
        )
