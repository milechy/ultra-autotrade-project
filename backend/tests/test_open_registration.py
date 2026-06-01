# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_open_registration.py
"""
Open Registration (一般登録) API のテスト。

POST /auth/register-open:
- 利用規約同意あり → 201 (viewer ロール)
- 利用規約同意なし → 422
- Email 重複 → 409
- open 招待レコード (type='open', partner_id=None) が監査用に生成される
- KYC ゲート接続点の存在確認（コメント）
- 既存 invite フロー (POST /auth/register + invitation_code) は無変更

InvitationService:
- create_open_invitation で type='open', partner_id=None のレコードが作成される
"""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ["JWT_SECRET_KEY"] = "test-secret-key-open-registration"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["JWT_ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"
os.environ["INITIAL_ADMIN_EMAIL"] = "admin@example.com"
os.environ["DISABLE_AI_JUDGMENT_SCHEDULER"] = "1"
os.environ["DISABLE_BACKGROUND_MONITORING"] = "1"

from app.auth.models import User
from app.auth.service import AuthService
from app.database import Base, get_db
from app.invitations import service as invitation_service
from app.invitations.models import INVITATION_TYPE_INVITE, INVITATION_TYPE_OPEN, Invitation
from app.main import create_app


@pytest.fixture()
def test_db() -> Generator:
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
    override_get_db, _ = test_db
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _future(hours: int = 24) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


# ────────────────────────────────────────────────────────────────
# InvitationService: create_open_invitation のユニットテスト
# ────────────────────────────────────────────────────────────────


class TestOpenInvitationService:
    def test_create_open_invitation_type_and_no_partner(self, test_db) -> None:
        """create_open_invitation は type='open', partner_id=None を生成する。"""
        override_get_db, _ = test_db
        db: Session = next(override_get_db())
        try:
            inv = invitation_service.create_open_invitation(db, expires_at=_future())
            assert inv.type == INVITATION_TYPE_OPEN
            assert inv.partner_id is None
            assert len(inv.code) == 16
        finally:
            db.close()

    def test_create_invitation_keeps_invite_type(self, test_db) -> None:
        """既存 create_invitation は type='invite' のまま（後方互換）。"""
        override_get_db, _ = test_db
        db: Session = next(override_get_db())
        try:
            inv = invitation_service.create_invitation(db, partner_id=1, expires_at=_future())
            assert inv.type == INVITATION_TYPE_INVITE
            assert inv.partner_id == 1
        finally:
            db.close()

    def test_open_invitation_validates_normally(self, test_db) -> None:
        """open 招待コードも validate_code で有効判定される。"""
        override_get_db, _ = test_db
        db: Session = next(override_get_db())
        try:
            inv = invitation_service.create_open_invitation(db, expires_at=_future())
            result = invitation_service.validate_code(db, inv.code)
            assert result is not None
            assert result.type == INVITATION_TYPE_OPEN
        finally:
            db.close()


# ────────────────────────────────────────────────────────────────
# POST /auth/register-open API テスト
# ────────────────────────────────────────────────────────────────


class TestOpenRegistrationAPI:
    def test_register_open_success(self, client: TestClient, test_db) -> None:
        """利用規約同意ありで 201 / role=viewer が返る。"""
        resp = client.post(
            "/auth/register-open",
            json={
                "email": "openuser@example.com",
                "username": "openuser",
                "password": "Password123",
                "terms_consent": True,
            },
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["email"] == "openuser@example.com"
        assert data["role"] == "viewer"
        assert "access_token" in data

    def test_register_open_creates_audit_invitation(self, client: TestClient, test_db) -> None:
        """open 登録後に type='open' の監査レコードが invitations テーブルに作られる。"""
        _, engine = test_db
        resp = client.post(
            "/auth/register-open",
            json={
                "email": "audit@example.com",
                "username": "audituser",
                "password": "Password123",
                "terms_consent": True,
            },
        )
        assert resp.status_code == 201

        SessionLocal = sessionmaker(bind=engine)
        db = SessionLocal()
        try:
            inv = (
                db.query(Invitation)
                .filter(Invitation.type == INVITATION_TYPE_OPEN)
                .order_by(Invitation.id.desc())
                .first()
            )
            assert inv is not None
            assert inv.partner_id is None
            assert inv.used_count == 1
        finally:
            db.close()

    def test_register_open_terms_consent_false_returns_422(self, client: TestClient) -> None:
        """terms_consent=False は 422 を返す。"""
        resp = client.post(
            "/auth/register-open",
            json={
                "email": "noconsent@example.com",
                "username": "noconsent",
                "password": "Password123",
                "terms_consent": False,
            },
        )
        assert resp.status_code == 422

    def test_register_open_duplicate_email_returns_409(self, client: TestClient) -> None:
        """同一 email で 2 回登録すると 409。"""
        payload = {
            "email": "dup@example.com",
            "username": "dupuser",
            "password": "Password123",
            "terms_consent": True,
        }
        resp1 = client.post("/auth/register-open", json=payload)
        assert resp1.status_code == 201

        payload2 = dict(payload)
        payload2["username"] = "dupuser2"
        resp2 = client.post("/auth/register-open", json=payload2)
        assert resp2.status_code == 409

    def test_register_open_does_not_affect_invite_flow(self, client: TestClient, test_db) -> None:
        """open 登録後も既存 invite フロー (POST /auth/register + invitation_code) が動作する。"""
        override_get_db, _ = test_db
        db: Session = next(override_get_db())
        try:
            # partner ユーザーを直接作成
            partner = User(
                email="partner@example.com",
                username="partner",
                hashed_password=AuthService.hash_password("Password123"),
                role="partner",
            )
            db.add(partner)
            db.commit()
            db.refresh(partner)
            partner_id = partner.id

            # partner が invite 招待を発行
            inv = invitation_service.create_invitation(
                db, partner_id=partner_id, expires_at=_future()
            )
            code = inv.code
        finally:
            db.close()

        # open 登録（別ユーザー）
        client.post(
            "/auth/register-open",
            json={
                "email": "openonly@example.com",
                "username": "openonly",
                "password": "Password123",
                "terms_consent": True,
            },
        )

        # invite フローで別ユーザー登録 → 動作確認
        resp = client.post(
            "/auth/register",
            json={
                "email": "invited@example.com",
                "username": "inviteduser",
                "password": "Password123",
                "invitation_code": code,
            },
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["role"] == "viewer"
