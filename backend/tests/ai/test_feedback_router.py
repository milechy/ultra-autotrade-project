# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/ai/test_feedback_router.py
"""AI判定フィードバック API ルーターのテスト。"""

import os
import tempfile
from typing import Generator

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-feedback-router")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "terms_admin@example.com")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.ai.models import AIDecision  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402


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
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


@pytest.fixture()
def db_session(test_db):
    _, _, SessionLocal = test_db
    session = SessionLocal()
    yield session
    session.close()


def get_admin_token(client: TestClient) -> str:
    email = os.environ.get("INITIAL_ADMIN_EMAIL", "terms_admin@example.com")
    client.post(
        "/auth/register",
        json={"email": email, "username": "admin", "password": "adminpassword123"},
    )
    r = client.post("/auth/login", json={"email": email, "password": "adminpassword123"})
    return r.json()["access_token"]


def get_viewer_token(client: TestClient) -> str:
    """admin 以外の viewer ユーザートークンを取得する。

    admin が /users エンドポイントで viewer を作成する（recruitment フロー）。
    """
    admin_token = get_admin_token(client)
    email = "viewer@example.com"
    client.post(
        "/users",
        json={
            "email": email,
            "username": "viewer",
            "password": "viewerpassword123",
            "role": "viewer",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    r = client.post("/auth/login", json={"email": email, "password": "viewerpassword123"})
    return r.json()["access_token"]


def create_decision(db_session) -> int:
    """テスト用 AIDecision を作成して id を返す。"""
    decision = AIDecision(
        query="test query",
        action="HOLD",
        confidence=60,
        primary_provider="claude",
        primary_action="HOLD",
        primary_confidence=60,
        agreed=True,
    )
    db_session.add(decision)
    db_session.commit()
    db_session.refresh(decision)
    return decision.id


VALID_FEEDBACK_PAYLOAD = {
    "ai_decision_id": 1,  # 実際のIDは各テストで上書き
    "is_correct": True,
    "actual_outcome": "profit",
    "pnl_usd": "100.50",
}


class TestPostRecord:
    def test_admin_can_record_feedback(self, client: TestClient, db_session) -> None:
        """admin がフィードバックを記録できる。"""
        token = get_admin_token(client)
        decision_id = create_decision(db_session)

        payload = {**VALID_FEEDBACK_PAYLOAD, "ai_decision_id": decision_id}
        r = client.post(
            "/api/ai/feedback/record",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["ai_decision_id"] == decision_id
        assert data["actual_outcome"] == "profit"
        assert data["is_correct"] is True
        assert data["feedback_source"] == "manual"
        assert "id" in data
        assert "recorded_at" in data

    def test_non_admin_is_forbidden(self, client: TestClient, db_session) -> None:
        """admin 以外はフィードバックを記録できない（403）。"""
        token = get_viewer_token(client)
        decision_id = create_decision(db_session)

        payload = {**VALID_FEEDBACK_PAYLOAD, "ai_decision_id": decision_id}
        r = client.post(
            "/api/ai/feedback/record",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403

    def test_unauthenticated_is_rejected(self, client: TestClient) -> None:
        """認証なしは 401 または 403。"""
        r = client.post("/api/ai/feedback/record", json=VALID_FEEDBACK_PAYLOAD)
        assert r.status_code in (401, 403)

    def test_nonexistent_decision_returns_404(self, client: TestClient) -> None:
        """存在しない decision_id は 404。"""
        token = get_admin_token(client)
        payload = {**VALID_FEEDBACK_PAYLOAD, "ai_decision_id": 99999}
        r = client.post(
            "/api/ai/feedback/record",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404

    def test_invalid_actual_outcome_is_rejected(self, client: TestClient, db_session) -> None:
        """不正な actual_outcome は 422。"""
        token = get_admin_token(client)
        decision_id = create_decision(db_session)
        payload = {"ai_decision_id": decision_id, "actual_outcome": "invalid_value"}
        r = client.post(
            "/api/ai/feedback/record",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 422

    def test_minimal_payload(self, client: TestClient, db_session) -> None:
        """必須フィールドのみのペイロードで記録できる。"""
        token = get_admin_token(client)
        decision_id = create_decision(db_session)
        r = client.post(
            "/api/ai/feedback/record",
            json={"ai_decision_id": decision_id, "actual_outcome": "unknown"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        assert r.json()["is_correct"] is None

    def test_decimal_fields_returned_as_strings(self, client: TestClient, db_session) -> None:
        """Decimal フィールドが文字列で返される。"""
        token = get_admin_token(client)
        decision_id = create_decision(db_session)
        r = client.post(
            "/api/ai/feedback/record",
            json={
                "ai_decision_id": decision_id,
                "actual_outcome": "profit",
                "pnl_usd": "123.456789",
                "expected_apy": "5.1",
                "actual_apy": "6.2",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        data = r.json()
        assert isinstance(data["pnl_usd"], str)
        assert isinstance(data["expected_apy"], str)
        assert isinstance(data["actual_apy"], str)


class TestGetStats:
    def test_admin_can_get_stats(self, client: TestClient) -> None:
        """admin が統計を取得できる。"""
        token = get_admin_token(client)
        r = client.get(
            "/api/ai/feedback/stats",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "total_feedbacks" in data
        assert "correct_count" in data
        assert "accuracy_rate" in data
        assert "feedback_by_source" in data

    def test_empty_stats(self, client: TestClient) -> None:
        """フィードバックなしのとき 0 件統計が返る。"""
        token = get_admin_token(client)
        r = client.get(
            "/api/ai/feedback/stats",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = r.json()
        assert data["total_feedbacks"] == 0
        assert data["accuracy_rate"] is None

    def test_non_admin_is_forbidden(self, client: TestClient) -> None:
        """admin 以外は統計取得不可（403）。"""
        token = get_viewer_token(client)
        r = client.get(
            "/api/ai/feedback/stats",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403

    def test_days_parameter_validation(self, client: TestClient) -> None:
        """days に負の値を渡すと 422。"""
        token = get_admin_token(client)
        r = client.get(
            "/api/ai/feedback/stats?days=-1",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 422

    def test_days_zero_means_all(self, client: TestClient, db_session) -> None:
        """days=0 は全期間を返す。"""
        decision_id = create_decision(db_session)
        token = get_admin_token(client)
        # フィードバックを 1 件追加
        client.post(
            "/api/ai/feedback/record",
            json={"ai_decision_id": decision_id, "actual_outcome": "profit"},
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.get(
            "/api/ai/feedback/stats?days=0",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = r.json()
        assert data["total_feedbacks"] >= 1


class TestGetFeedbackByDecision:
    def test_existing_decision_with_feedback(
        self, client: TestClient, db_session
    ) -> None:
        """フィードバックのある判定の一覧が取得できる。"""
        token = get_admin_token(client)
        decision_id = create_decision(db_session)

        # 先にフィードバックを登録
        client.post(
            "/api/ai/feedback/record",
            json={"ai_decision_id": decision_id, "actual_outcome": "profit", "is_correct": True},
            headers={"Authorization": f"Bearer {token}"},
        )

        r = client.get(
            f"/api/ai/feedback/{decision_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["ai_decision_id"] == decision_id

    def test_nonexistent_decision_returns_empty_list(self, client: TestClient) -> None:
        """フィードバックのない判定 ID は空リストを返す。"""
        token = get_admin_token(client)
        r = client.get(
            "/api/ai/feedback/99999",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json() == []

    def test_non_admin_is_forbidden(self, client: TestClient) -> None:
        """admin 以外はフィードバック一覧取得不可（403）。"""
        token = get_viewer_token(client)
        r = client.get(
            "/api/ai/feedback/1",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403

    def test_multiple_feedbacks_for_same_decision(
        self, client: TestClient, db_session
    ) -> None:
        """同一判定 ID に複数フィードバックが返る。"""
        token = get_admin_token(client)
        decision_id = create_decision(db_session)

        for outcome in ("profit", "loss"):
            client.post(
                "/api/ai/feedback/record",
                json={"ai_decision_id": decision_id, "actual_outcome": outcome},
                headers={"Authorization": f"Bearer {token}"},
            )

        r = client.get(
            f"/api/ai/feedback/{decision_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = r.json()
        assert len(data) == 2
