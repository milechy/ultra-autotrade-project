# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_exchange_copy_trading.py
"""Tests for copy trading endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(autouse=True)
def clear_storage() -> None:
    """Reset in-memory storage before each test."""
    from app.exchange.copy_trading import _performance, _strategies, _subscriptions

    _strategies.clear()
    _subscriptions.clear()
    _performance.clear()


@pytest.fixture()
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


class TestListStrategies:
    def test_empty_list(self, client: TestClient) -> None:
        resp = client.get("/exchange/strategies")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_public_strategies(self, client: TestClient) -> None:
        # Create a strategy first
        payload = {
            "name": "BTC Momentum",
            "description": "Follows BTC momentum",
            "risk_level": "medium",
            "strategist_id": "user-001",
        }
        create_resp = client.post("/exchange/strategies", json=payload)
        assert create_resp.status_code == 201

        resp = client.get("/exchange/strategies")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "BTC Momentum"
        assert data[0]["risk_level"] == "medium"
        assert data[0]["performance"] is None


class TestCreateStrategy:
    def test_creates_strategy(self, client: TestClient) -> None:
        payload = {
            "name": "Test Strategy",
            "description": "A test strategy",
            "risk_level": "low",
            "strategist_id": "strat-001",
        }
        resp = client.post("/exchange/strategies", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Strategy"
        assert data["risk_level"] == "low"
        assert data["is_public"] is True
        assert "id" in data

    def test_invalid_risk_level(self, client: TestClient) -> None:
        payload = {
            "name": "Bad Strategy",
            "description": "desc",
            "risk_level": "extreme",
            "strategist_id": "strat-001",
        }
        resp = client.post("/exchange/strategies", json=payload)
        assert resp.status_code == 422


class TestGetStrategy:
    def test_get_existing_strategy(self, client: TestClient) -> None:
        create_resp = client.post(
            "/exchange/strategies",
            json={"name": "X", "description": "Y", "risk_level": "high", "strategist_id": "s1"},
        )
        strategy_id = create_resp.json()["id"]

        resp = client.get(f"/exchange/strategies/{strategy_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == strategy_id

    def test_get_nonexistent_strategy(self, client: TestClient) -> None:
        resp = client.get("/exchange/strategies/does-not-exist")
        assert resp.status_code == 404


class TestSubscribe:
    def test_subscribe_to_strategy(self, client: TestClient) -> None:
        create_resp = client.post(
            "/exchange/strategies",
            json={"name": "S", "description": "D", "risk_level": "low", "strategist_id": "s1"},
        )
        strategy_id = create_resp.json()["id"]

        resp = client.post(
            f"/exchange/strategies/{strategy_id}/subscribe",
            json={"follower_id": "follower-001", "copy_ratio": 0.5},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["strategy_id"] == strategy_id
        assert data["copy_ratio"] == 0.5
        assert data["is_active"] is True

    def test_duplicate_subscription_returns_conflict(self, client: TestClient) -> None:
        create_resp = client.post(
            "/exchange/strategies",
            json={"name": "S", "description": "D", "risk_level": "low", "strategist_id": "s1"},
        )
        strategy_id = create_resp.json()["id"]
        sub_payload = {"follower_id": "follower-001", "copy_ratio": 0.5}

        client.post(f"/exchange/strategies/{strategy_id}/subscribe", json=sub_payload)
        resp = client.post(f"/exchange/strategies/{strategy_id}/subscribe", json=sub_payload)
        assert resp.status_code == 409

    def test_subscribe_nonexistent_strategy(self, client: TestClient) -> None:
        resp = client.post(
            "/exchange/strategies/nonexistent/subscribe",
            json={"follower_id": "f1", "copy_ratio": 0.5},
        )
        assert resp.status_code == 404


class TestUnsubscribe:
    def test_unsubscribe(self, client: TestClient) -> None:
        create_resp = client.post(
            "/exchange/strategies",
            json={"name": "S", "description": "D", "risk_level": "low", "strategist_id": "s1"},
        )
        strategy_id = create_resp.json()["id"]
        client.post(
            f"/exchange/strategies/{strategy_id}/subscribe",
            json={"follower_id": "f1", "copy_ratio": 0.5},
        )

        resp = client.delete(
            f"/exchange/strategies/{strategy_id}/subscribe",
            params={"follower_id": "f1"},
        )
        assert resp.status_code == 204

    def test_unsubscribe_not_found(self, client: TestClient) -> None:
        resp = client.delete(
            "/exchange/strategies/nonexistent/subscribe",
            params={"follower_id": "f1"},
        )
        assert resp.status_code == 404


class TestUpdateRatio:
    def test_update_copy_ratio(self, client: TestClient) -> None:
        create_resp = client.post(
            "/exchange/strategies",
            json={"name": "S", "description": "D", "risk_level": "low", "strategist_id": "s1"},
        )
        strategy_id = create_resp.json()["id"]
        sub_resp = client.post(
            f"/exchange/strategies/{strategy_id}/subscribe",
            json={"follower_id": "f1", "copy_ratio": 0.5},
        )
        sub_id = sub_resp.json()["id"]

        resp = client.put(f"/exchange/subscriptions/{sub_id}/ratio", json={"copy_ratio": 0.8})
        assert resp.status_code == 200
        assert resp.json()["copy_ratio"] == 0.8


class TestListSubscriptions:
    def test_list_subscriptions(self, client: TestClient) -> None:
        create_resp = client.post(
            "/exchange/strategies",
            json={"name": "S", "description": "D", "risk_level": "low", "strategist_id": "s1"},
        )
        strategy_id = create_resp.json()["id"]
        client.post(
            f"/exchange/strategies/{strategy_id}/subscribe",
            json={"follower_id": "f1", "copy_ratio": 0.5},
        )

        resp = client.get("/exchange/subscriptions", params={"follower_id": "f1"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["follower_id"] == "f1"
