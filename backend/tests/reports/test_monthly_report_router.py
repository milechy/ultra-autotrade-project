# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""月次レポート EP の RBAC 統合テスト。

GET /api/reports/monthly の権限ルール:
- 未認証 → 401
- Viewer → 自分のデータのみ (200)
- Viewer が他 user_id 指定 → 403
- Admin → 全ユーザー集計 (200)
- Admin が user_id 指定 → 指定ユーザー集計 (200)
"""

from __future__ import annotations

import os
import tempfile
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-report-router")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30")

_ADMIN_EMAIL = "admin_report@example.com"
_ADMIN_PASSWORD = "adminpassword123"
_VIEWER_EMAIL = "viewer_report@example.com"
_VIEWER_PASSWORD = "viewerpassword123"

os.environ["INITIAL_ADMIN_EMAIL"] = _ADMIN_EMAIL

from app.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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

    yield override_get_db, engine
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


@pytest.fixture()
def client(test_db) -> TestClient:
    override_get_db, _ = test_db
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _register_admin(client: TestClient) -> str:
    client.post(
        "/auth/register",
        json={"email": _ADMIN_EMAIL, "username": "admin_report", "password": _ADMIN_PASSWORD},
    )
    r = client.post("/auth/login", json={"email": _ADMIN_EMAIL, "password": _ADMIN_PASSWORD})
    assert r.status_code == 200, f"admin login failed: {r.text}"
    return r.json()["access_token"]


def _create_viewer_and_login(client: TestClient, admin_token: str) -> tuple[str, int]:
    r = client.post(
        "/users",
        json={
            "email": _VIEWER_EMAIL,
            "username": "viewer_report",
            "password": _VIEWER_PASSWORD,
            "role": "viewer",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code in (200, 201), f"create viewer failed: {r.text}"
    viewer_id: int = r.json()["id"]
    r2 = client.post("/auth/login", json={"email": _VIEWER_EMAIL, "password": _VIEWER_PASSWORD})
    assert r2.status_code == 200, f"viewer login failed: {r2.text}"
    return r2.json()["access_token"], viewer_id


# ---------------------------------------------------------------------------
# テスト
# ---------------------------------------------------------------------------


class TestMonthlyReportAuth:
    """認証・認可の基本テスト。"""

    def test_unauthenticated_returns_401(self, client: TestClient) -> None:
        """未認証リクエストは 401 を返す。"""
        r = client.get("/api/reports/monthly")
        assert r.status_code == 401

    def test_viewer_can_access_own_report(self, client: TestClient) -> None:
        """Viewer は自分のレポートにアクセスできる (200)。"""
        admin_token = _register_admin(client)
        viewer_token, viewer_id = _create_viewer_and_login(client, admin_token)

        r = client.get(
            "/api/reports/monthly?year=2026&month=1",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert r.status_code == 200

    def test_viewer_can_specify_own_user_id(self, client: TestClient) -> None:
        """Viewer が自分の user_id を明示指定した場合も 200。"""
        admin_token = _register_admin(client)
        viewer_token, viewer_id = _create_viewer_and_login(client, admin_token)

        r = client.get(
            f"/api/reports/monthly?year=2026&month=1&user_id={viewer_id}",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert r.status_code == 200

    def test_viewer_cannot_access_other_user(self, client: TestClient) -> None:
        """Viewer が他ユーザーの user_id を指定すると 403。"""
        admin_token = _register_admin(client)
        viewer_token, viewer_id = _create_viewer_and_login(client, admin_token)

        other_user_id = viewer_id + 999
        r = client.get(
            f"/api/reports/monthly?year=2026&month=1&user_id={other_user_id}",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert r.status_code == 403

    def test_admin_can_access_without_user_id(self, client: TestClient) -> None:
        """Admin は user_id なしで全ユーザー集計を取得できる (200)。"""
        admin_token = _register_admin(client)

        r = client.get(
            "/api/reports/monthly?year=2026&month=1",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200

    def test_admin_can_specify_any_user_id(self, client: TestClient) -> None:
        """Admin は任意の user_id を指定してレポートを取得できる (200)。"""
        admin_token = _register_admin(client)
        _, viewer_id = _create_viewer_and_login(client, admin_token)

        r = client.get(
            f"/api/reports/monthly?year=2026&month=1&user_id={viewer_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200


class TestMonthlyReportContent:
    """レスポンスコンテンツのテスト。"""

    def test_response_has_content_disposition(self, client: TestClient) -> None:
        """レスポンスに Content-Disposition ヘッダーが含まれる。"""
        admin_token = _register_admin(client)

        r = client.get(
            "/api/reports/monthly?year=2026&month=3",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        assert "content-disposition" in r.headers
        assert "monthly_report_2026_03" in r.headers["content-disposition"]

    def test_response_content_type_is_csv_or_pdf(self, client: TestClient) -> None:
        """レスポンスの Content-Type が CSV または PDF である。"""
        admin_token = _register_admin(client)

        r = client.get(
            "/api/reports/monthly?year=2026&month=3",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        assert r.headers["content-type"] in (
            "text/csv; charset=utf-8",
            "application/pdf",
        )

    def test_default_year_month_uses_current(self, client: TestClient) -> None:
        """year/month 未指定時は今月のファイル名が返る。"""
        from datetime import datetime, timezone

        admin_token = _register_admin(client)

        r = client.get(
            "/api/reports/monthly",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        now = datetime.now(timezone.utc)
        expected_filename = f"monthly_report_{now.year}_{now.month:02d}"
        assert expected_filename in r.headers["content-disposition"]
