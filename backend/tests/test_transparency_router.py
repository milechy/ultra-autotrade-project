# backend/tests/test_transparency_router.py
"""Transparency router tests using FastAPI TestClient."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.aave.transparency_router import router as transparency_router


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(transparency_router)
    return TestClient(app)


# ── 1. Safety Score ──────────────────────────────────────────────────────────


def test_safety_score_200(client: TestClient) -> None:
    resp = client.get("/api/transparency/safety-score")
    assert resp.status_code == 200
    data = resp.json()
    score = float(data["score"])
    assert 0 <= score <= 100


# ── 2. Signal ────────────────────────────────────────────────────────────────


def test_signal_200(client: TestClient) -> None:
    resp = client.get("/api/transparency/signal")
    assert resp.status_code == 200
    data = resp.json()
    assert data["weather"] in ("sunny", "cloudy", "stormy")


# ── 3. Impact (valid) ────────────────────────────────────────────────────────


def test_impact_200(client: TestClient) -> None:
    resp = client.get(
        "/api/transparency/impact",
        params={"current_amount": 1000, "action_amount": 500},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "impact" in data
    assert "formatted" in data


# ── 4. Impact (negative action_amount → 422) ─────────────────────────────────


def test_impact_negative(client: TestClient) -> None:
    resp = client.get(
        "/api/transparency/impact",
        params={"current_amount": 1000, "action_amount": -1},
    )
    assert resp.status_code == 422


# ── 5. Simulation ────────────────────────────────────────────────────────────


def test_simulation_200(client: TestClient) -> None:
    resp = client.get("/api/transparency/simulation")
    assert resp.status_code == 200
    data = resp.json()
    assert "scenarios" in data
    assert len(data["scenarios"]) == 3


# ── 6. Performance ───────────────────────────────────────────────────────────


def test_performance_200(client: TestClient) -> None:
    resp = client.get("/api/transparency/performance")
    assert resp.status_code == 200
    data = resp.json()
    assert "period_days" in data


# ── 7. Risk Profiles (list) ──────────────────────────────────────────────────


def test_risk_profiles_200(client: TestClient) -> None:
    resp = client.get("/api/transparency/risk-profile")
    assert resp.status_code == 200
    data = resp.json()
    assert "profiles" in data
    assert len(data["profiles"]) == 3


# ── 8. Risk Profile invalid mode → conservative fallback ─────────────────────


def test_risk_profile_invalid(client: TestClient) -> None:
    resp = client.get("/api/transparency/risk-profile/invalid_mode")
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "conservative"
