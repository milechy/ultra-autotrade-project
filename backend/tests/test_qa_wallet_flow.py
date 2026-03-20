# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_qa_wallet_flow.py
"""
QA: Auth boundary tests for wallet connection flow.

Verifies which endpoints require authentication and which are public.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.auth.models import UserRole
from app.main import create_app


def _make_viewer_user() -> MagicMock:
    user = MagicMock()
    user.id = 1
    user.email = "viewer@example.com"
    user.username = "viewer"
    user.role = UserRole.VIEWER.value
    user.is_active = True
    return user


@pytest.fixture()
def anon_client() -> TestClient:
    """Unauthenticated TestClient (no dependency overrides)."""
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


def test_health_endpoint(anon_client: TestClient) -> None:
    """GET /health returns 200 without authentication."""
    resp = anon_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


def test_aave_status_unauthenticated(anon_client: TestClient) -> None:
    """GET /api/aave/status returns 401 or 403 without a Bearer token."""
    resp = anon_client.get("/api/aave/status")
    assert resp.status_code in (401, 403)


def test_aave_rebalance_unauthenticated(anon_client: TestClient) -> None:
    """POST /api/aave/rebalance returns 401 or 403 without a token."""
    payload = {"action": "BUY", "amount": "100", "asset_symbol": "USDC"}
    resp = anon_client.post("/api/aave/rebalance", json=payload)
    assert resp.status_code in (401, 403)


def test_transparency_public() -> None:
    """GET /api/transparency/safety-score returns 200 without auth."""
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/transparency/safety-score")
    assert resp.status_code == 200
    data = resp.json()
    # Should contain a score field
    assert "score" in data


def test_transparency_signal_public() -> None:
    """GET /api/transparency/signal returns 200 without auth."""
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/transparency/signal")
    assert resp.status_code == 200
    # Response should be a JSON object
    assert isinstance(resp.json(), dict)


def test_fee_schedule_public() -> None:
    """GET /api/transparency/risk-profile returns 200 without auth."""
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/transparency/risk-profile")
    assert resp.status_code == 200
    data = resp.json()
    assert "profiles" in data
    assert len(data["profiles"]) == 3