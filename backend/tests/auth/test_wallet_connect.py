# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/auth/test_wallet_connect.py
"""
WalletConnect 認証のテスト。

- 有効な署名でユーザーが自動作成されること
- 無効な署名で 401 が返ること
- 既存 wallet ユーザーには既存 JWT が返ること
- 新規ユーザーは needs_terms_acceptance = True
- Privy ID Token (JWT) 検証 (Codex Review P1 対応, Asana 1214284566521324)
- 重複 privy_did 登録時の 409 Conflict (Codex Review P2 対応)
"""

import os
import tempfile
import time
from typing import Generator, Tuple

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
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

from app.auth.models import User
from app.auth.privy_verifier import reset_privy_verifier
from app.database import Base, get_db
from app.main import create_app

# テスト用秘密鍵（テスト専用、本番環境では使用しない）
TEST_PRIVATE_KEY = "0x4c0883a69102937d6231471b5dbb6e538eba2ef158d8b8b75f21c8f4d9c3f5a2"
TEST_ACCOUNT = Account.from_key(TEST_PRIVATE_KEY)
TEST_WALLET_ADDRESS = TEST_ACCOUNT.address

# 第二のウォレット (重複 privy_did テスト用)
TEST_PRIVATE_KEY_2 = "0x1111111111111111111111111111111111111111111111111111111111111111"
TEST_ACCOUNT_2 = Account.from_key(TEST_PRIVATE_KEY_2)
TEST_WALLET_ADDRESS_2 = TEST_ACCOUNT_2.address

PRIVY_TEST_APP_ID = "test-app-id-for-pytest"


def _sign_message(message: str, private_key: str) -> str:
    """テスト用署名を生成する。"""
    encoded = encode_defunct(text=message)
    signed = Account.sign_message(encoded, private_key=private_key)
    return signed.signature.hex()


def _generate_es256_keypair() -> Tuple[bytes, bytes]:
    """ES256 (P-256) keypair を PEM 形式で生成する。"""
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def _make_id_token(
    private_pem: bytes,
    *,
    sub: str,
    app_id: str = PRIVY_TEST_APP_ID,
    iss: str = "privy.io",
    exp_offset: int = 3600,
    iat_offset: int = 0,
) -> str:
    """Privy ID Token を生成する。"""
    now = int(time.time())
    payload = {
        "iss": iss,
        "aud": app_id,
        "sub": sub,
        "iat": now + iat_offset,
        "exp": now + exp_offset,
    }
    return pyjwt.encode(payload, private_pem, algorithm="ES256")


@pytest.fixture()
def privy_keypair() -> Tuple[bytes, bytes]:
    """ES256 keypair を生成する fixture。"""
    return _generate_es256_keypair()


@pytest.fixture()
def privy_env(privy_keypair: Tuple[bytes, bytes]) -> Generator[None, None, None]:
    """PRIVY_APP_ID / PRIVY_VERIFICATION_KEY を設定し、PrivyVerifier シングルトンをリセット。"""
    _, public_pem = privy_keypair
    prev_app_id = os.environ.get("PRIVY_APP_ID")
    prev_key = os.environ.get("PRIVY_VERIFICATION_KEY")
    os.environ["PRIVY_APP_ID"] = PRIVY_TEST_APP_ID
    os.environ["PRIVY_VERIFICATION_KEY"] = public_pem.decode("ascii")
    reset_privy_verifier()
    try:
        yield
    finally:
        if prev_app_id is None:
            os.environ.pop("PRIVY_APP_ID", None)
        else:
            os.environ["PRIVY_APP_ID"] = prev_app_id
        if prev_key is None:
            os.environ.pop("PRIVY_VERIFICATION_KEY", None)
        else:
            os.environ["PRIVY_VERIFICATION_KEY"] = prev_key
        reset_privy_verifier()


@pytest.fixture()
def privy_unset_env() -> Generator[None, None, None]:
    """PRIVY_APP_ID 未設定環境を保証する fixture (後方互換テスト用)。"""
    prev_app_id = os.environ.pop("PRIVY_APP_ID", None)
    prev_key = os.environ.pop("PRIVY_VERIFICATION_KEY", None)
    reset_privy_verifier()
    try:
        yield
    finally:
        if prev_app_id is not None:
            os.environ["PRIVY_APP_ID"] = prev_app_id
        if prev_key is not None:
            os.environ["PRIVY_VERIFICATION_KEY"] = prev_key
        reset_privy_verifier()


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

    def _make_valid_request_2(self) -> dict:
        """第二ウォレットの有効リクエスト (重複 DID テスト用)。"""
        message = "Ultra AutoTrade: test at 2026-03-24T00:00:00Z (#2)"
        signature = _sign_message(message, TEST_PRIVATE_KEY_2)
        return {
            "wallet_address": TEST_WALLET_ADDRESS_2,
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

    # ── Privy ID Token 検証 (Codex Review P1) ─────────────────────────

    def test_wallet_connect_valid_id_token_with_matching_did_saves_did(
        self,
        client: TestClient,
        test_db,
        privy_keypair: Tuple[bytes, bytes],
        privy_env: None,  # noqa: ARG002
    ):
        """有効 privy_id_token + 一致 privy_did → 200 で DB 保存 (新仕様)。"""
        _, engine = test_db
        private_pem, _ = privy_keypair
        did = "did:privy:test123abc"
        token = _make_id_token(private_pem, sub=did)

        payload = self._make_valid_request()
        payload["privy_did"] = did
        payload["privy_id_token"] = token

        response = client.post("/auth/wallet/connect", json=payload)
        assert response.status_code == 200, response.json()
        assert response.json()["is_new_user"] is True

        Session = sessionmaker(bind=engine)
        with Session() as session:
            user = (
                session.query(User)
                .filter(User.wallet_address == TEST_WALLET_ADDRESS.lower())
                .first()
            )
            assert user is not None
            assert user.privy_did == did

    def test_wallet_connect_valid_id_token_did_mismatch_returns_401(
        self,
        client: TestClient,
        privy_keypair: Tuple[bytes, bytes],
        privy_env: None,  # noqa: ARG002
    ):
        """有効 privy_id_token + 不一致 privy_did → 401 (DID 偽装試行を拒否)。"""
        private_pem, _ = privy_keypair
        token = _make_id_token(private_pem, sub="did:privy:authentic-user")

        payload = self._make_valid_request()
        payload["privy_did"] = "did:privy:attacker-impersonation"
        payload["privy_id_token"] = token

        response = client.post("/auth/wallet/connect", json=payload)
        assert response.status_code == 401
        assert "match" in response.json()["detail"].lower()

    def test_wallet_connect_unverified_did_returns_400_when_privy_enabled(
        self,
        client: TestClient,
        privy_env: None,  # noqa: ARG002
    ):
        """privy_id_token なし + privy_did あり (PRIVY 設定済み) → 400 (未検証 DID 拒否)。"""
        payload = self._make_valid_request()
        payload["privy_did"] = "did:privy:unverified123"

        response = client.post("/auth/wallet/connect", json=payload)
        assert response.status_code == 400
        assert "id_token" in response.json()["detail"].lower()

    def test_wallet_connect_expired_id_token_returns_401(
        self,
        client: TestClient,
        privy_keypair: Tuple[bytes, bytes],
        privy_env: None,  # noqa: ARG002
    ):
        """期限切れ privy_id_token → 401。"""
        private_pem, _ = privy_keypair
        # iat=2h前, exp=1h前 → 既に期限切れ
        expired_token = _make_id_token(
            private_pem, sub="did:privy:expired", iat_offset=-7200, exp_offset=-3600
        )

        payload = self._make_valid_request()
        payload["privy_id_token"] = expired_token

        response = client.post("/auth/wallet/connect", json=payload)
        assert response.status_code == 401

    def test_wallet_connect_invalid_signature_id_token_returns_401(
        self,
        client: TestClient,
        privy_env: None,  # noqa: ARG002
    ):
        """別の鍵で署名された privy_id_token → 401。"""
        # 設定に登録されていない別 keypair で署名
        attacker_private_pem, _ = _generate_es256_keypair()
        forged_token = _make_id_token(attacker_private_pem, sub="did:privy:forged")

        payload = self._make_valid_request()
        payload["privy_id_token"] = forged_token

        response = client.post("/auth/wallet/connect", json=payload)
        assert response.status_code == 401

    def test_wallet_connect_duplicate_privy_did_returns_409(
        self,
        client: TestClient,
        privy_keypair: Tuple[bytes, bytes],
        privy_env: None,  # noqa: ARG002
    ):
        """同じ privy_did で別ウォレットの新規ユーザー作成 → 409 Conflict (Codex Review P2)。"""
        private_pem, _ = privy_keypair
        did = "did:privy:duplicate"
        token = _make_id_token(private_pem, sub=did)

        # 1回目: ウォレット A で登録 (DID 保存)
        first = self._make_valid_request()
        first["privy_did"] = did
        first["privy_id_token"] = token
        resp1 = client.post("/auth/wallet/connect", json=first)
        assert resp1.status_code == 200

        # 2回目: 別ウォレット B で同じ DID を使って登録 → 409
        second = self._make_valid_request_2()
        second["privy_did"] = did
        second["privy_id_token"] = token  # 同じ DID なので token も同じで OK
        resp2 = client.post("/auth/wallet/connect", json=second)
        assert resp2.status_code == 409
        assert "did" in resp2.json()["detail"].lower()

    def test_wallet_connect_id_token_only_uses_sub_as_did(
        self,
        client: TestClient,
        test_db,
        privy_keypair: Tuple[bytes, bytes],
        privy_env: None,  # noqa: ARG002
    ):
        """privy_id_token のみ (privy_did なし) → 200 で sub を DID として使用。"""
        _, engine = test_db
        private_pem, _ = privy_keypair
        did = "did:privy:from-sub-only"
        token = _make_id_token(private_pem, sub=did)

        payload = self._make_valid_request()
        # privy_did は送らない
        payload["privy_id_token"] = token

        response = client.post("/auth/wallet/connect", json=payload)
        assert response.status_code == 200, response.json()

        Session = sessionmaker(bind=engine)
        with Session() as session:
            user = (
                session.query(User)
                .filter(User.wallet_address == TEST_WALLET_ADDRESS.lower())
                .first()
            )
            assert user is not None
            assert user.privy_did == did

    def test_wallet_connect_existing_user_id_token_backfill(
        self,
        client: TestClient,
        test_db,
        privy_keypair: Tuple[bytes, bytes],
        privy_env: None,  # noqa: ARG002
    ):
        """既存ユーザーに privy_did 未設定なら、有効な ID Token で後追い保存。"""
        _, engine = test_db

        # 1回目: privy 関連なしで作成
        first = self._make_valid_request()
        resp1 = client.post("/auth/wallet/connect", json=first)
        assert resp1.status_code == 200

        # 2回目: 有効 ID Token + 一致 DID で再接続
        private_pem, _ = privy_keypair
        did = "did:privy:backfill456"
        token = _make_id_token(private_pem, sub=did)
        second = self._make_valid_request()
        second["privy_did"] = did
        second["privy_id_token"] = token
        resp2 = client.post("/auth/wallet/connect", json=second)
        assert resp2.status_code == 200
        assert resp2.json()["is_new_user"] is False

        Session = sessionmaker(bind=engine)
        with Session() as session:
            user = (
                session.query(User)
                .filter(User.wallet_address == TEST_WALLET_ADDRESS.lower())
                .first()
            )
            assert user is not None
            assert user.privy_did == did

    def test_wallet_connect_without_privy_did_still_works(
        self,
        client: TestClient,
        privy_unset_env: None,  # noqa: ARG002
    ):
        """privy_did/privy_id_token なしのリクエストは従来通り動作する (後方互換)。"""
        payload = self._make_valid_request()
        # privy_did / privy_id_token を明示的に含めない
        assert "privy_did" not in payload
        assert "privy_id_token" not in payload

        response = client.post("/auth/wallet/connect", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["is_new_user"] is True

    # ── 後方互換リグレッション修正 (Codex Review P1, GID 1214284845161706) ────

    def test_unconfigured_privy_with_id_token_returns_200(
        self,
        client: TestClient,
        privy_unset_env: None,  # noqa: ARG002
    ):
        """PRIVY_APP_ID 未設定 + privy_id_token あり → 200 (silent drop, 後方互換)。"""
        payload = self._make_valid_request()
        payload["privy_id_token"] = "ey.fake.token"

        response = client.post("/auth/wallet/connect", json=payload)
        assert response.status_code == 200
        assert "access_token" in response.json()

    def test_unconfigured_privy_with_did_only_returns_200(
        self,
        client: TestClient,
        privy_unset_env: None,  # noqa: ARG002
    ):
        """PRIVY_APP_ID 未設定 + privy_did あり (id_token なし) → 200 (silent drop, 後方互換)。"""
        payload = self._make_valid_request()
        payload["privy_did"] = "did:privy:test-compat"

        response = client.post("/auth/wallet/connect", json=payload)
        assert response.status_code == 200
        assert "access_token" in response.json()

    def test_unconfigured_privy_with_both_fields_returns_200(
        self,
        client: TestClient,
        privy_unset_env: None,  # noqa: ARG002
    ):
        """PRIVY_APP_ID 未設定 + privy_id_token + privy_did 両方あり → 200 (両方 drop)。"""
        payload = self._make_valid_request()
        payload["privy_id_token"] = "ey.fake.token"
        payload["privy_did"] = "did:privy:test-compat-both"

        response = client.post("/auth/wallet/connect", json=payload)
        assert response.status_code == 200
        assert "access_token" in response.json()

    def test_unconfigured_privy_emits_warning_log(
        self,
        client: TestClient,
        privy_unset_env: None,  # noqa: ARG002
        caplog: pytest.LogCaptureFixture,
    ):
        """PRIVY_APP_ID 未設定 + privy_id_token あり → WARN ログ出力 (機密情報を含まない)。"""
        import logging

        payload = self._make_valid_request()
        payload["privy_id_token"] = "ey.fake.token"

        with caplog.at_level(logging.WARNING):
            response = client.post("/auth/wallet/connect", json=payload)

        assert response.status_code == 200
        assert any("Privy verification disabled" in r.message for r in caplog.records)
        # 機密情報 (id_token の中身) がログに含まれないことを確認
        assert not any("ey.fake.token" in r.message for r in caplog.records)
