# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_user_auth_method_check.py
"""users_auth_method_check CHECK 制約の挙動検証テスト。

GID 1214176336328111 で導入。

検証観点:
1. hashed_password / privy_did 両方 NULL → IntegrityError
2. hashed_password のみ設定 → 正常 INSERT
3. privy_did のみ設定 → 正常 INSERT
"""

import os
import tempfile

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-auth-method-check")

from app.auth.models import User  # noqa: E402
from app.database import Base  # noqa: E402

_INSERT_SQL = (
    "INSERT INTO users "
    "(email, username, role, is_active, notification_frequency, user_mode, "
    "execution_policy, tier, created_at, updated_at, hashed_password, privy_did) "
    "VALUES "
    "(:email, :username, 'viewer', 1, 'important', 'managed', "
    "'auto_execute', 'LOWER', datetime('now'), datetime('now'), :hashed_pw, :privy_did)"
)


@pytest.fixture()
def test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    yield engine, SessionLocal
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


def test_both_null_raises_integrity_error(test_db) -> None:
    """hashed_password と privy_did が両方 NULL なら CHECK 制約で IntegrityError。"""
    engine, _ = test_db
    with engine.begin() as conn:
        with pytest.raises(IntegrityError, match="users_auth_method_check"):
            conn.execute(
                text(_INSERT_SQL),
                {
                    "email": "both_null@example.com",
                    "username": "both_null",
                    "hashed_pw": None,
                    "privy_did": None,
                },
            )


def test_hashed_password_only_succeeds(test_db) -> None:
    """hashed_password のみ設定（privy_did=NULL）で INSERT 成功。"""
    _, SessionLocal = test_db
    session = SessionLocal()
    try:
        user = User(
            email="pw_only@example.com",
            username="pw_only",
            hashed_password="$2b$12$hashed_password_value",
            privy_did=None,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        assert user.hashed_password is not None
        assert user.privy_did is None
    finally:
        session.close()


def test_privy_did_only_succeeds(test_db) -> None:
    """privy_did のみ設定（hashed_password=NULL）で INSERT 成功。"""
    engine, _ = test_db
    with engine.begin() as conn:
        conn.execute(
            text(_INSERT_SQL),
            {
                "email": "privy_only@example.com",
                "username": "privy_only",
                "hashed_pw": None,
                "privy_did": "did:privy:test_abc123",
            },
        )
        row = conn.execute(
            text(
                "SELECT hashed_password, privy_did FROM users "
                "WHERE email = 'privy_only@example.com'"
            )
        ).fetchone()
        assert row is not None
        assert row[0] is None
        assert row[1] == "did:privy:test_abc123"
