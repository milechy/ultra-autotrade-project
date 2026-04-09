# backend/tests/test_notification_log_router.py
"""
NotificationLog API および DatabaseNotificationSender のテスト。

テスト構成:
- GET /api/partner/notifications — 認証・RBAC・フィルタ・ページネーション
- DatabaseNotificationSender.send() — DB保存・fail-open
"""

import os
import tempfile
from collections.abc import Generator
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-notif-log")

from app.auth.router import router as auth_router  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.notifications.models import NotificationLog  # noqa: E402
from app.notifications.service import DatabaseNotificationSender  # noqa: E402
from app.notifications.schemas import NotificationChannel, NotificationMessage, NotificationSeverity  # noqa: E402
from app.partner.router import router as partner_router  # noqa: E402
from app.users.router import router as users_router  # noqa: E402

_ADMIN_EMAIL = "notif-log-admin@example.com"
_ADMIN_PASS = "adminpass123!"
_PARTNER_EMAIL = "notif-log-partner@example.com"
_PARTNER_PASS = "partnerpass123!"
_PARTNER2_EMAIL = "notif-log-partner2@example.com"
_PARTNER2_PASS = "partnerpass456!"
_VIEWER_EMAIL = "notif-log-viewer@example.com"
_VIEWER_PASS = "viewerpass123!"

SessionFactory = sessionmaker[Session]


# ---------------------------------------------------------------------------
# App / DB fixtures
# ---------------------------------------------------------------------------


def _create_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(partner_router)
    return app


@pytest.fixture()
def test_db() -> Generator[tuple[SessionFactory, object], None, None]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory: SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    yield factory, engine
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


@pytest.fixture()
def client(
    test_db: tuple[SessionFactory, object],
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    monkeypatch.setenv("INITIAL_ADMIN_EMAIL", _ADMIN_EMAIL)
    session_factory, _ = test_db
    app = _create_test_app()

    def override_get_db() -> Generator[Session, None, None]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


@pytest.fixture()
def tokens(
    client: TestClient,
    test_db: tuple[SessionFactory, object],
) -> dict[str, str]:
    """admin / partner / partner2 / viewer を登録し、各トークンを返す。"""
    session_factory, _ = test_db

    client.post("/auth/register", json={"email": _ADMIN_EMAIL, "username": "notif-admin", "password": _ADMIN_PASS})
    r = client.post("/auth/login", json={"email": _ADMIN_EMAIL, "password": _ADMIN_PASS})
    admin_token = r.json()["access_token"]

    for email, username, password, role in [
        (_PARTNER_EMAIL, "notif-partner", _PARTNER_PASS, "partner"),
        (_PARTNER2_EMAIL, "notif-partner2", _PARTNER2_PASS, "partner"),
        (_VIEWER_EMAIL, "notif-viewer", _VIEWER_PASS, "viewer"),
    ]:
        client.post(
            "/users",
            json={"email": email, "username": username, "password": password, "role": role},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

    r = client.post("/auth/login", json={"email": _PARTNER_EMAIL, "password": _PARTNER_PASS})
    partner_token = r.json()["access_token"]

    r = client.post("/auth/login", json={"email": _PARTNER2_EMAIL, "password": _PARTNER2_PASS})
    partner2_token = r.json()["access_token"]

    r = client.post("/auth/login", json={"email": _VIEWER_EMAIL, "password": _VIEWER_PASS})
    viewer_token = r.json()["access_token"]

    return {
        "admin": admin_token,
        "partner": partner_token,
        "partner2": partner2_token,
        "viewer": viewer_token,
    }


def _get_partner_id(client: TestClient, token: str) -> int:
    """/auth/me からパートナー自身の user id を取得する。"""
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    return r.json()["id"]


def _seed_logs(session_factory: SessionFactory, partner_id: int, other_partner_id: int) -> None:
    """テスト用通知ログをDBに直接挿入する。"""
    db = session_factory()
    try:
        logs = [
            NotificationLog(channel="slack", severity="info", title="Info notice", body="body1",
                            partner_id=partner_id, created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
            NotificationLog(channel="line", severity="warning", title="Warning notice", body="body2",
                            partner_id=partner_id, created_at=datetime(2026, 1, 2, tzinfo=timezone.utc)),
            NotificationLog(channel="slack", severity="emergency", title="Emergency!", body="body3",
                            partner_id=partner_id, created_at=datetime(2026, 1, 3, tzinfo=timezone.utc)),
            # 別パートナーのログ（partner 1 には見えてはいけない）
            NotificationLog(channel="slack", severity="alert", title="Other partner log", body="hidden",
                            partner_id=other_partner_id, created_at=datetime(2026, 1, 4, tzinfo=timezone.utc)),
            # partner_id=None のシステム全体向け（誰にも表示しない）
            NotificationLog(channel="internal_log", severity="info", title="System notice", body="sys",
                            partner_id=None, created_at=datetime(2026, 1, 5, tzinfo=timezone.utc)),
        ]
        db.add_all(logs)
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Tests: GET /api/partner/notifications
# ---------------------------------------------------------------------------


class TestGetPartnerNotifications:
    def test_returns_only_own_logs(
        self,
        client: TestClient,
        tokens: dict[str, str],
        test_db: tuple[SessionFactory, object],
    ) -> None:
        session_factory, _ = test_db
        partner_id = _get_partner_id(client, tokens["partner"])
        partner2_id = _get_partner_id(client, tokens["partner2"])
        _seed_logs(session_factory, partner_id, partner2_id)

        r = client.get(
            "/api/partner/notifications",
            headers={"Authorization": f"Bearer {tokens['partner']}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 3
        titles = [item["title"] for item in body["items"]]
        assert "Other partner log" not in titles
        assert "System notice" not in titles

    def test_returns_empty_for_new_partner(
        self,
        client: TestClient,
        tokens: dict[str, str],
    ) -> None:
        r = client.get(
            "/api/partner/notifications",
            headers={"Authorization": f"Bearer {tokens['partner']}"},
        )
        assert r.status_code == 200
        assert r.json()["total"] == 0
        assert r.json()["items"] == []

    def test_severity_filter(
        self,
        client: TestClient,
        tokens: dict[str, str],
        test_db: tuple[SessionFactory, object],
    ) -> None:
        session_factory, _ = test_db
        partner_id = _get_partner_id(client, tokens["partner"])
        partner2_id = _get_partner_id(client, tokens["partner2"])
        _seed_logs(session_factory, partner_id, partner2_id)

        r = client.get(
            "/api/partner/notifications?severity=warning",
            headers={"Authorization": f"Bearer {tokens['partner']}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["severity"] == "warning"

    def test_pagination(
        self,
        client: TestClient,
        tokens: dict[str, str],
        test_db: tuple[SessionFactory, object],
    ) -> None:
        session_factory, _ = test_db
        partner_id = _get_partner_id(client, tokens["partner"])
        partner2_id = _get_partner_id(client, tokens["partner2"])
        _seed_logs(session_factory, partner_id, partner2_id)

        r = client.get(
            "/api/partner/notifications?page=1&per_page=2",
            headers={"Authorization": f"Bearer {tokens['partner']}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 3
        assert len(body["items"]) == 2
        assert body["page"] == 1
        assert body["per_page"] == 2

        r2 = client.get(
            "/api/partner/notifications?page=2&per_page=2",
            headers={"Authorization": f"Bearer {tokens['partner']}"},
        )
        assert r2.status_code == 200
        assert len(r2.json()["items"]) == 1

    def test_viewer_forbidden(
        self,
        client: TestClient,
        tokens: dict[str, str],
    ) -> None:
        r = client.get(
            "/api/partner/notifications",
            headers={"Authorization": f"Bearer {tokens['viewer']}"},
        )
        assert r.status_code == 403

    def test_unauthenticated_rejected(self, client: TestClient) -> None:
        r = client.get("/api/partner/notifications")
        assert r.status_code == 401

    def test_ordered_newest_first(
        self,
        client: TestClient,
        tokens: dict[str, str],
        test_db: tuple[SessionFactory, object],
    ) -> None:
        session_factory, _ = test_db
        partner_id = _get_partner_id(client, tokens["partner"])
        partner2_id = _get_partner_id(client, tokens["partner2"])
        _seed_logs(session_factory, partner_id, partner2_id)

        r = client.get(
            "/api/partner/notifications",
            headers={"Authorization": f"Bearer {tokens['partner']}"},
        )
        items = r.json()["items"]
        dates = [item["created_at"] for item in items]
        assert dates == sorted(dates, reverse=True)


# ---------------------------------------------------------------------------
# Tests: DatabaseNotificationSender
# ---------------------------------------------------------------------------


class TestDatabaseNotificationSender:
    def test_saves_notification_to_db(
        self,
        test_db: tuple[SessionFactory, object],
    ) -> None:
        session_factory, _ = test_db
        sender = DatabaseNotificationSender(session_factory)
        msg = NotificationMessage(
            channel=NotificationChannel.SLACK,
            severity=NotificationSeverity.WARNING,
            title="Test title",
            body="Test body",
            partner_id=42,
            user_id=7,
        )
        sender.send(msg)

        db = session_factory()
        try:
            log = db.query(NotificationLog).first()
            assert log is not None
            assert log.channel == "slack"
            assert log.severity == "warning"
            assert log.title == "Test title"
            assert log.body == "Test body"
            assert log.partner_id == 42
            assert log.user_id == 7
        finally:
            db.close()

    def test_saves_without_partner_id(
        self,
        test_db: tuple[SessionFactory, object],
    ) -> None:
        session_factory, _ = test_db
        sender = DatabaseNotificationSender(session_factory)
        msg = NotificationMessage(
            channel=NotificationChannel.INTERNAL_LOG,
            severity=NotificationSeverity.INFO,
            title="System notice",
            body="No partner",
        )
        sender.send(msg)

        db = session_factory()
        try:
            log = db.query(NotificationLog).first()
            assert log is not None
            assert log.partner_id is None
            assert log.user_id is None
        finally:
            db.close()

    def test_fails_open_on_broken_factory(self) -> None:
        """DBが壊れていても例外を上に伝播しない（fail-open）。"""
        def broken_factory():
            raise RuntimeError("DB unavailable")

        sender = DatabaseNotificationSender(broken_factory)
        msg = NotificationMessage(
            channel=NotificationChannel.INTERNAL_LOG,
            severity=NotificationSeverity.INFO,
            title="Title",
            body="Body",
        )
        # 例外が発生しないことを確認
        sender.send(msg)
