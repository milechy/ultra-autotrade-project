# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_invitations.py
"""
招待コード API のテスト。

- コード生成（16文字ランダム）
- コード検証（有効・期限切れ・使用回数超過）
- 招待コード付き登録 → viewer ロール + invited_user_id 自動設定
- 招待コードなし登録 → 従来通り動作（初回管理者のみ）
"""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# テスト用環境変数
os.environ["JWT_SECRET_KEY"] = "test-secret-key-invitation-tests"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["JWT_ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"
os.environ["INITIAL_ADMIN_EMAIL"] = "admin@example.com"
os.environ["DISABLE_AI_JUDGMENT_SCHEDULER"] = "1"
os.environ["DISABLE_BACKGROUND_MONITORING"] = "1"

from app.auth.models import User
from app.auth.service import AuthService
from app.database import Base, get_db
from app.invitations import service as invitation_service
from app.invitations.models import Invitation
from app.main import create_app


@pytest.fixture()
def test_db() -> Generator:
    """テスト用 SQLite DB を作成し、セッション override factory を返す。"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    yield override_get_db, engine

    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


@pytest.fixture()
def client(test_db) -> TestClient:
    """TestClient を返す（DB override 済み）。"""
    override_get_db, _ = test_db
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


@pytest.fixture()
def partner_user(test_db) -> User:
    """role='partner' のテストユーザーを作成して返す。"""
    override_get_db, _ = test_db
    gen = override_get_db()
    db: Session = next(gen)
    try:
        user = User(
            email="partner@example.com",
            username="partneruser",
            hashed_password=AuthService.hash_password("Password123"),
            role="partner",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


@pytest.fixture()
def partner_token(client: TestClient, partner_user: User) -> str:
    """partner ユーザーの JWT トークンを返す。"""
    token, _ = AuthService.create_access_token(
        user_id=partner_user.id,
        email=partner_user.email,
        role=partner_user.role,
    )
    return token


def _future(hours: int = 24) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


def _past(hours: int = 1) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=hours)


# ────────────────────────────────────────────────────────────────
# Service レベルのユニットテスト
# ────────────────────────────────────────────────────────────────


class TestInvitationService:
    """InvitationService のユニットテスト。"""

    def test_create_generates_16char_code(self, test_db) -> None:
        """コードが16文字のランダム文字列であること。"""
        override_get_db, _ = test_db
        db: Session = next(override_get_db())
        try:
            inv = invitation_service.create_invitation(db, partner_id=1, expires_at=_future())
            assert len(inv.code) == 16
            assert inv.code.isalnum()
        finally:
            db.close()

    def test_validate_valid_code(self, test_db) -> None:
        """有効なコードは Invitation を返す。"""
        override_get_db, _ = test_db
        db: Session = next(override_get_db())
        try:
            inv = invitation_service.create_invitation(db, partner_id=1, expires_at=_future())
            result = invitation_service.validate_code(db, inv.code)
            assert result is not None
            assert result.id == inv.id
        finally:
            db.close()

    def test_validate_expired_code(self, test_db) -> None:
        """期限切れコードは None を返す。"""
        override_get_db, _ = test_db
        db: Session = next(override_get_db())
        try:
            inv = invitation_service.create_invitation(db, partner_id=1, expires_at=_past())
            result = invitation_service.validate_code(db, inv.code)
            assert result is None
        finally:
            db.close()

    def test_validate_used_up_code(self, test_db) -> None:
        """使用回数超過コードは None を返す。"""
        override_get_db, _ = test_db
        db: Session = next(override_get_db())
        try:
            inv = invitation_service.create_invitation(
                db, partner_id=1, expires_at=_future(), max_uses=1
            )
            invitation_service.increment_usage(db, inv)
            result = invitation_service.validate_code(db, inv.code)
            assert result is None
        finally:
            db.close()

    def test_validate_nonexistent_code(self, test_db) -> None:
        """存在しないコードは None を返す。"""
        override_get_db, _ = test_db
        db: Session = next(override_get_db())
        try:
            result = invitation_service.validate_code(db, "DOESNOTEXIST1234")
            assert result is None
        finally:
            db.close()

    def test_increment_usage_sets_invited_user_id(self, test_db) -> None:
        """max_uses=1 の場合、increment_usage で invited_user_id が設定される。"""
        override_get_db, _ = test_db
        db: Session = next(override_get_db())
        try:
            inv = invitation_service.create_invitation(db, partner_id=1, expires_at=_future())
            invitation_service.increment_usage(db, inv, user_id=42)
            db.refresh(inv)
            assert inv.used_count == 1
            assert inv.invited_user_id == 42
        finally:
            db.close()


# ────────────────────────────────────────────────────────────────
# API エンドポイントのテスト
# ────────────────────────────────────────────────────────────────


class TestInvitationAPI:
    """招待コード API のテスト。"""

    def test_create_invitation_as_partner(self, client: TestClient, partner_token: str) -> None:
        """partner ユーザーは招待コードを発行できる。"""
        resp = client.post(
            "/api/invitations",
            json={"expires_at": _future().isoformat(), "max_uses": 1},
            headers={"Authorization": f"Bearer {partner_token}"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["code"]) == 16
        assert data["used_count"] == 0
        assert data["max_uses"] == 1

    def test_create_invitation_requires_auth(self, client: TestClient) -> None:
        """認証なしは 403 を返す。"""
        resp = client.post(
            "/api/invitations",
            json={"expires_at": _future().isoformat()},
        )
        assert resp.status_code in (401, 403)

    def test_list_invitations_as_partner(self, client: TestClient, partner_token: str) -> None:
        """partner は自分の招待コード一覧を取得できる。"""
        # 2つ作成
        for _ in range(2):
            client.post(
                "/api/invitations",
                json={"expires_at": _future().isoformat()},
                headers={"Authorization": f"Bearer {partner_token}"},
            )
        resp = client.get(
            "/api/invitations",
            headers={"Authorization": f"Bearer {partner_token}"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) >= 2

    def test_validate_invitation_valid(self, client: TestClient, partner_token: str) -> None:
        """有効なコードは valid=True を返す。"""
        create_resp = client.post(
            "/api/invitations",
            json={"expires_at": _future().isoformat()},
            headers={"Authorization": f"Bearer {partner_token}"},
        )
        code = create_resp.json()["code"]

        resp = client.get(f"/api/invitations/{code}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["uses_remaining"] == 1

    def test_validate_invitation_invalid(self, client: TestClient) -> None:
        """存在しないコードは valid=False を返す。"""
        resp = client.get("/api/invitations/INVALIDCODE1234")
        assert resp.status_code == 200
        assert resp.json()["valid"] is False

    def test_validate_no_auth_required(self, client: TestClient) -> None:
        """検証エンドポイントは認証不要。"""
        resp = client.get("/api/invitations/SOMERANDMCODE1")
        # 200 (valid=False) であること（401/403 ではない）
        assert resp.status_code == 200


# ────────────────────────────────────────────────────────────────
# 登録フローのテスト
# ────────────────────────────────────────────────────────────────


class TestRegistrationWithInvitation:
    """招待コード付き登録フローのテスト。"""

    def test_register_with_valid_invitation(
        self, client: TestClient, partner_token: str, test_db
    ) -> None:
        """有効な招待コードで登録すると viewer ロールになる。"""
        # 招待コード発行
        create_resp = client.post(
            "/api/invitations",
            json={"expires_at": _future().isoformat()},
            headers={"Authorization": f"Bearer {partner_token}"},
        )
        code = create_resp.json()["code"]

        # 招待コードで登録
        resp = client.post(
            "/auth/register",
            json={
                "email": "invited@example.com",
                "username": "inviteduser",
                "password": "Password123",
                "invitation_code": code,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "invited@example.com"
        assert data["role"] == "viewer"

    def test_register_with_invitation_sets_invited_user_id(
        self, client: TestClient, partner_token: str, test_db
    ) -> None:
        """招待コード経由で登録するとinvitation.invited_user_idが設定される。"""
        # 招待コード発行
        create_resp = client.post(
            "/api/invitations",
            json={"expires_at": _future().isoformat()},
            headers={"Authorization": f"Bearer {partner_token}"},
        )
        inv_data = create_resp.json()
        code = inv_data["code"]
        inv_id = inv_data["id"]

        # 登録
        resp = client.post(
            "/auth/register",
            json={
                "email": "linked@example.com",
                "username": "linkeduser",
                "password": "Password123",
                "invitation_code": code,
            },
        )
        assert resp.status_code == 201
        user_id = resp.json()["id"]

        # invitation.invited_user_id が設定されているか確認
        override_get_db, _ = test_db
        db: Session = next(override_get_db())
        try:
            inv = db.query(Invitation).filter(Invitation.id == inv_id).first()
            assert inv is not None
            assert inv.invited_user_id == user_id
            assert inv.used_count == 1
        finally:
            db.close()

    def test_register_with_expired_invitation(self, client: TestClient, test_db) -> None:
        """期限切れの招待コードで登録すると 400 エラー。"""
        override_get_db, _ = test_db
        db: Session = next(override_get_db())
        try:
            # 期限切れ招待を直接作成
            inv = Invitation(
                code="EXPIREDCODE1234",
                partner_id=1,
                expires_at=_past(),
                max_uses=1,
                used_count=0,
            )
            db.add(inv)
            db.commit()
        finally:
            db.close()

        resp = client.post(
            "/auth/register",
            json={
                "email": "expired@example.com",
                "username": "expireduser",
                "password": "Password123",
                "invitation_code": "EXPIREDCODE1234",
            },
        )
        assert resp.status_code == 400
        assert (
            "expired" in resp.json()["detail"].lower() or "invalid" in resp.json()["detail"].lower()
        )

    def test_register_with_used_up_invitation(self, client: TestClient, test_db) -> None:
        """使用回数超過の招待コードで登録すると 400 エラー。"""
        override_get_db, _ = test_db
        db: Session = next(override_get_db())
        try:
            inv = Invitation(
                code="USEDUPCODE12345",
                partner_id=1,
                expires_at=_future(),
                max_uses=1,
                used_count=1,
            )
            db.add(inv)
            db.commit()
        finally:
            db.close()

        resp = client.post(
            "/auth/register",
            json={
                "email": "usedcode@example.com",
                "username": "usedcodeuser",
                "password": "Password123",
                "invitation_code": "USEDUPCODE12345",
            },
        )
        assert resp.status_code == 400

    def test_register_without_invitation_initial_admin(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """invitation_code なしの登録は初回管理者登録として動作する。"""
        monkeypatch.setenv("INITIAL_ADMIN_EMAIL", "admin@example.com")
        resp = client.post(
            "/auth/register",
            json={
                "email": "admin@example.com",
                "username": "adminuser",
                "password": "Password123",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["role"] == "admin"

    def test_register_without_invitation_second_user_fails(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """初回管理者登録後、invitation_code なしで別ユーザー登録は 403。"""
        monkeypatch.setenv("INITIAL_ADMIN_EMAIL", "admin@example.com")
        # 初回管理者登録
        client.post(
            "/auth/register",
            json={
                "email": "admin@example.com",
                "username": "adminuser",
                "password": "Password123",
            },
        )
        # 2回目は拒否
        resp = client.post(
            "/auth/register",
            json={
                "email": "other@example.com",
                "username": "otheruser",
                "password": "Password123",
            },
        )
        assert resp.status_code == 403
