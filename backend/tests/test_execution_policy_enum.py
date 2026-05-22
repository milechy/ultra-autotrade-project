# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_execution_policy_enum.py
"""ExecutionPolicy enum / CHECK 制約 / server_default の挙動検証テスト。

GID 1214176344039867 (P1) で導入。
P0 GID 1214993061793196 (P3-1): default を require_approval に変更 (2026-05-21)。

検証観点:
1. ExecutionPolicy.values() が全 valid 値を返す
2. CHECK 制約が無効値の直 INSERT を拒否する
3. PUT /api/user/settings が enum と整合した値検証を行う
4. User 作成時に execution_policy 未指定で safe default ('require_approval') が適用される
"""

import os
import tempfile
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-execution-policy-enum")

from app.auth.constants import ExecutionPolicy  # noqa: E402
from app.auth.models import User  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402

# 他テスト (test_invitations 等) が import 時に INITIAL_ADMIN_EMAIL を別値で上書きするため、
# 本テスト固有の email を client fixture 内で都度セットする。test_user_settings_role_auth 準拠。
_ADMIN_EMAIL = "exec_policy_admin@example.com"
_ADMIN_PASSWORD = "execpolicy12345"


@pytest.fixture()
def test_db():
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

    yield override_get_db, engine, SessionLocal
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


@pytest.fixture()
def client(test_db) -> TestClient:
    override_get_db, _, _ = test_db
    # 他テストの import-time 副作用で INITIAL_ADMIN_EMAIL が書き換わっているため、
    # 本テスト固有値で必ず上書きしてから create_app() を呼ぶ。
    os.environ["INITIAL_ADMIN_EMAIL"] = _ADMIN_EMAIL
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _register_and_login(client: TestClient) -> str:
    """admin として register → login し、access_token を返す。"""
    rr = client.post(
        "/auth/register",
        json={
            "email": _ADMIN_EMAIL,
            "username": "exec_policy_admin",
            "password": _ADMIN_PASSWORD,
        },
    )
    if rr.status_code in (200, 201):
        payload = rr.json()
        if "access_token" in payload:
            return payload["access_token"]
    r = client.post(
        "/auth/login",
        json={"email": _ADMIN_EMAIL, "password": _ADMIN_PASSWORD},
    )
    payload = r.json()
    assert "access_token" in payload, (
        f"register={rr.status_code} body={rr.json()}, login status={r.status_code}, body={payload}"
    )
    return payload["access_token"]


# ---------------------------------------------------------------------------
# 1. enum.values()
# ---------------------------------------------------------------------------


def test_execution_policy_values_returns_all_valid_strings() -> None:
    """``ExecutionPolicy.values()`` が CHECK 制約と一致する全 valid 値を返す。"""
    values = ExecutionPolicy.values()
    assert set(values) == {"auto_execute", "require_approval", "proposal_only"}
    assert len(values) == 3


def test_valid_values_accepted_by_user_creation(test_db) -> None:
    """有効値 3 種それぞれで User を作成・保存できる。"""
    _, _, SessionLocal = test_db
    session = SessionLocal()
    try:
        for idx, policy in enumerate(ExecutionPolicy.values()):
            user = User(
                email=f"valid{idx}@example.com",
                username=f"valid{idx}",
                hashed_password="hashed",
                is_active=True,
                execution_policy=policy,
            )
            session.add(user)
        session.commit()
        # 全件 commit 成功 (= CHECK 制約をパス)
        rows = session.execute(text("SELECT execution_policy FROM users")).all()
        assert {row[0] for row in rows} == set(ExecutionPolicy.values())
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 2. CHECK 制約による無効値拒否
# ---------------------------------------------------------------------------


def test_invalid_value_rejected_by_db_constraint(test_db) -> None:
    """生 SQL で 'shadow' 等の無効値を INSERT すると IntegrityError になる。"""
    _, engine, _ = test_db
    with engine.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO users "
                    "(email, username, hashed_password, role, is_active, "
                    "notification_frequency, user_mode, execution_policy, tier) "
                    "VALUES (:email, :username, :pw, 'viewer', 1, "
                    "'important', 'managed', :policy, 'LOWER')"
                ),
                {
                    "email": "invalid@example.com",
                    "username": "invaliduser",
                    "pw": "hashed",
                    "policy": "shadow",  # 無効値
                },
            )


# ---------------------------------------------------------------------------
# 3. PUT /api/user/settings の enum 整合性
# ---------------------------------------------------------------------------


def test_settings_api_accepts_all_enum_values(client: TestClient) -> None:
    """PUT /api/user/settings で全 ExecutionPolicy 値が受け入れられる。"""
    token = _register_and_login(client)
    for policy in ExecutionPolicy.values():
        r = client.put(
            "/api/user/settings",
            json={"execution_policy": policy},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, f"policy={policy}: {r.text}"
        assert r.json()["execution_policy"] == policy


def test_settings_api_rejects_invalid_value(client: TestClient) -> None:
    """PUT /api/user/settings で enum 外の値は 422 で拒否される。"""
    token = _register_and_login(client)
    r = client.put(
        "/api/user/settings",
        json={"execution_policy": "shadow"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422
    # detail に enum 値リストが含まれること (運用者が valid 値を把握できる)
    detail = r.json().get("detail", "")
    for policy in ExecutionPolicy.values():
        assert policy in detail, f"detail missing {policy}: {detail}"


# ---------------------------------------------------------------------------
# 4. server_default の適用
# ---------------------------------------------------------------------------


def test_default_value_on_user_creation(test_db) -> None:
    """User() で execution_policy 未指定時に safe default 'require_approval' が適用される。

    P0 GID 1214993061793196 (P3-1): 金融システムの安全既定として require_approval を
    デフォルト値にした。role default=VIEWER + auto_execute の組み合わせは設計違反。
    """
    _, _, SessionLocal = test_db
    session = SessionLocal()
    try:
        user = User(
            email="default@example.com",
            username="defaultuser",
            hashed_password="hashed",
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        assert user.execution_policy == ExecutionPolicy.REQUIRE_APPROVAL.value, (
            f"新規 User の execution_policy は '{ExecutionPolicy.REQUIRE_APPROVAL.value}' であるべき。"
            f" 実際の値: '{user.execution_policy}'"
        )
    finally:
        session.close()


def test_explicit_auto_execute_still_works(test_db) -> None:
    """execution_policy を明示的に auto_execute で指定した場合は正常に保存される。

    safe default 変更後も、明示的な値指定は機能し続けることを確認。
    """
    _, _, SessionLocal = test_db
    session = SessionLocal()
    try:
        user = User(
            email="explicit_auto@example.com",
            username="explicit_auto_user",
            hashed_password="hashed",
            is_active=True,
            execution_policy=ExecutionPolicy.AUTO_EXECUTE.value,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        assert user.execution_policy == ExecutionPolicy.AUTO_EXECUTE.value
    finally:
        session.close()
