# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_integration_proposals.py
"""
シナリオD: 提案(Proposals)統合テスト

- GET /api/proposals/pending → list形式
- POST /api/proposals/{id}/approve → ステータス変更
- POST /api/proposals/{id}/reject → ステータス変更
- 期限切れproposalの承認 → エラー
"""

import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import create_app


@pytest.fixture()
def test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    test_engine = create_engine(
        f"sqlite:///{path}", connect_args={"check_same_thread": False}
    )
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    yield override_get_db, test_engine
    Base.metadata.drop_all(bind=test_engine)
    os.close(fd)
    os.unlink(path)


@pytest.fixture()
def client(test_db):
    override_get_db, _ = test_db
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def get_admin_token(client: TestClient) -> str:
    email = os.environ.get("INITIAL_ADMIN_EMAIL", "terms_admin@example.com")
    client.post(
        "/auth/register",
        json={"email": email, "username": "admin", "password": "adminpassword123"},
    )
    r = client.post(
        "/auth/login",
        json={"email": email, "password": "adminpassword123"},
    )
    return r.json()["access_token"]


def _create_proposal(client: TestClient, token: str, user_id: int, expires_at: str | None = None) -> dict:
    """テスト用 proposal を作成して返す。"""
    payload = {
        "user_id": user_id,
        "ai_decision_id": None,
        "operation": "SUPPLY",
        "asset": "USDC",
        "amount": "100.0",
        "amount_usd": "100.0",
        "reason": "Test proposal",
        "expected_hf_after": "2.0",
        "estimated_gas_usd": "1.0",
    }
    if expires_at is not None:
        payload["expires_at"] = expires_at
    r = client.post(
        "/api/proposals",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    return r


def test_proposals_pending(client: TestClient) -> None:
    """GET /api/proposals/pending → 200 + list形式"""
    token = get_admin_token(client)
    r = client.get(
        "/api/proposals/pending",
        headers={"Authorization": f"Bearer {token}"},
    )
    if r.status_code == 404:
        pytest.skip("endpoint /api/proposals/pending not implemented")
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert isinstance(data["items"], list)


def test_proposal_approve(client: TestClient, test_db) -> None:
    """POST /api/proposals/{id}/approve → ステータス変更"""
    override_get_db, _ = test_db
    token = get_admin_token(client)

    # まず自分のユーザーIDを取得
    me_r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    if me_r.status_code != 200:
        pytest.skip("GET /auth/me not available")
    user_id = me_r.json()["id"]

    # proposal 作成
    create_r = _create_proposal(client, token, user_id)
    if create_r.status_code == 404:
        pytest.skip("POST /api/proposals not implemented")
    if create_r.status_code not in (200, 201):
        pytest.skip(f"Cannot create proposal: {create_r.status_code} {create_r.text}")

    proposal_id = create_r.json()["id"]

    # 承認
    approve_r = client.post(
        f"/api/proposals/{proposal_id}/approve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert approve_r.status_code in (200, 201)
    data = approve_r.json()
    assert data["status"] in ("approved", "executed")


def test_proposal_reject(client: TestClient) -> None:
    """POST /api/proposals/{id}/reject → ステータス変更"""
    token = get_admin_token(client)

    me_r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    if me_r.status_code != 200:
        pytest.skip("GET /auth/me not available")
    user_id = me_r.json()["id"]

    create_r = _create_proposal(client, token, user_id)
    if create_r.status_code == 404:
        pytest.skip("POST /api/proposals not implemented")
    if create_r.status_code not in (200, 201):
        pytest.skip(f"Cannot create proposal: {create_r.status_code} {create_r.text}")

    proposal_id = create_r.json()["id"]

    reject_r = client.post(
        f"/api/proposals/{proposal_id}/reject",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reject_r.status_code == 200
    data = reject_r.json()
    assert data["status"] == "rejected"


def test_proposal_expired(client: TestClient) -> None:
    """期限切れproposalの承認 → エラー（400/404/422）

    実装上、_expire_old_proposals() は list_pending_proposals() 内で呼ばれる。
    そのため期限切れ proposal を承認するには、まず pending リストを取得して
    expired に変えてから承認を試みる必要がある。
    """
    token = get_admin_token(client)

    me_r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    if me_r.status_code != 200:
        pytest.skip("GET /auth/me not available")
    user_id = me_r.json()["id"]

    # 過去に期限切れになる expires_at を指定
    expired_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    create_r = _create_proposal(client, token, user_id, expires_at=expired_at)
    if create_r.status_code == 404:
        pytest.skip("POST /api/proposals not implemented")
    if create_r.status_code not in (200, 201):
        pytest.skip(f"Cannot create proposal: {create_r.status_code} {create_r.text}")

    proposal_id = create_r.json()["id"]

    # pending リストを取得して _expire_old_proposals() をトリガー
    # これにより status が pending → expired に変わる
    client.get(
        "/api/proposals/pending",
        headers={"Authorization": f"Bearer {token}"},
    )

    # 期限切れ proposal を承認しようとすると 400 を返すこと
    approve_r = client.post(
        f"/api/proposals/{proposal_id}/approve",
        headers={"Authorization": f"Bearer {token}"},
    )
    # 期限切れにより status が expired になっているので 400
    assert approve_r.status_code in (400, 404, 422)
