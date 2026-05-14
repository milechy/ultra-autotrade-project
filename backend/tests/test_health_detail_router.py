# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Tests for /health/detail (admin) — 4-axis multi-layer health (5/14 DoD #6)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Iterator
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from app.auth.dependencies import require_admin
from app.database import get_db
from app.health.cache import reset_health_detail_cache
from app.health.detail_router import router as health_detail_router
from app.health.probes import reset_probe_state
from app.health.schemas import ApiQuotaStatus, HealthDetailResponse


def _admin_user() -> MagicMock:
    u = MagicMock()
    u.id = 1
    u.role = "admin"
    u.is_active = True
    return u


@pytest.fixture(autouse=True)
def _reset_singletons() -> Iterator[None]:
    reset_health_detail_cache()
    reset_probe_state()
    yield
    reset_health_detail_cache()
    reset_probe_state()


@pytest.fixture
def db_session() -> MagicMock:
    """A MagicMock that mimics enough of SQLAlchemy Session for counts."""
    db = MagicMock()
    # By default return 0 for all scalar(count) calls
    db.scalar.return_value = 0
    return db


@pytest.fixture
def app_with_admin(db_session: MagicMock) -> FastAPI:
    app = FastAPI()
    app.include_router(health_detail_router)
    app.dependency_overrides[require_admin] = lambda: _admin_user()
    app.dependency_overrides[get_db] = lambda: db_session
    return app


@pytest.fixture
def app_with_viewer(db_session: MagicMock) -> FastAPI:
    app = FastAPI()
    app.include_router(health_detail_router)

    def _deny() -> None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    app.dependency_overrides[require_admin] = _deny
    app.dependency_overrides[get_db] = lambda: db_session
    return app


# ---------- helpers ----------


def _patch_scheduler(monkeypatch: pytest.MonkeyPatch, last_run_minutes_ago: int = 30) -> None:
    last_run = datetime.now(timezone.utc) - timedelta(minutes=last_run_minutes_ago)
    next_run = datetime.now(timezone.utc) + timedelta(hours=4)
    monkeypatch.setenv("AI_JUDGMENT_INTERVAL_HOURS", "4")
    monkeypatch.setattr(
        "app.automation.ai_judgment_scheduler.get_scheduler_status",
        lambda: {
            "running": True,
            "last_run": last_run.isoformat(),
            "next_run": next_run.isoformat(),
            "last_error": None,
        },
    )


def _patch_probes_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(
        "app.health.detail_router.get_openai_status",
        lambda: ApiQuotaStatus(reachable=True, last_check=now, last_error=None),
    )
    monkeypatch.setattr(
        "app.health.detail_router.get_perplexity_status",
        lambda: ApiQuotaStatus(reachable=True, last_check=now, last_error=None),
    )
    monkeypatch.setattr("app.health.detail_router.get_oracle_fresh", lambda: True)
    monkeypatch.setattr("app.health.detail_router.get_reserve_healthy", lambda: True)


def _patch_safety_state(
    monkeypatch: pytest.MonkeyPatch,
    *,
    is_custom: bool = False,
    expires_on: date | None = None,
    trading_allowed: bool = True,
) -> None:
    from decimal import Decimal

    from app.aave.risk_limiter import EffectiveLimits

    limits = EffectiveLimits(
        hf_min=Decimal("1.3") if is_custom else Decimal("1.6"),
        single_trade_pct_max=Decimal("20") if is_custom else Decimal("10"),
        daily_trade_pct_max=Decimal("60") if is_custom else Decimal("30"),
        cooldown_seconds=120 if is_custom else 600,
        is_custom=is_custom,
        expires_on=expires_on,
    )
    monkeypatch.setattr("app.aave.risk_limiter.get_effective_limits", lambda: limits)

    mock_monitoring = MagicMock()
    mock_monitoring.is_trading_allowed.return_value = trading_allowed
    monkeypatch.setattr("app.automation.state.get_monitoring_service", lambda: mock_monitoring)


def _setup_default_healthy(monkeypatch: pytest.MonkeyPatch, db: MagicMock) -> None:
    _patch_scheduler(monkeypatch, last_run_minutes_ago=30)
    _patch_probes_healthy(monkeypatch)
    _patch_safety_state(monkeypatch)
    # cross_judgment defaults: 10 total, 10 has_secondary, 8 agreed_true, 2 agreed_false
    db.scalar.side_effect = [10, 10, 8, 2]


# ========== Tests ==========


def test_health_detail_requires_admin(
    app_with_viewer: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    db_session: MagicMock,
) -> None:
    """Viewer/partner gets 403."""
    _setup_default_healthy(monkeypatch, db_session)
    client = TestClient(app_with_viewer)
    resp = client.get("/health/detail")
    assert resp.status_code == 403


def test_health_detail_all_ok(
    app_with_admin: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    db_session: MagicMock,
) -> None:
    """All components healthy → status=ok, warnings=[]."""
    _setup_default_healthy(monkeypatch, db_session)
    client = TestClient(app_with_admin)
    resp = client.get("/health/detail")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["warnings"] == []
    assert body["components"]["scheduler"]["ok"] is True
    assert body["components"]["quota"]["ok"] is True
    assert body["components"]["cross_judgment"]["ok"] is True
    assert body["components"]["safety"]["ok"] is True
    assert body["components"]["safety"]["limiter_mode"] == "strict"


def test_health_detail_scheduler_down(
    app_with_admin: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    db_session: MagicMock,
) -> None:
    """Last judgment >>> 2x interval → scheduler.ok=False → status=down."""
    # 4h interval × 2 = 8h threshold. Set last_run 12h ago.
    _patch_scheduler(monkeypatch, last_run_minutes_ago=12 * 60)
    _patch_probes_healthy(monkeypatch)
    _patch_safety_state(monkeypatch)
    db_session.scalar.side_effect = [10, 10, 8, 2]

    client = TestClient(app_with_admin)
    resp = client.get("/health/detail")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "down"
    assert body["components"]["scheduler"]["ok"] is False
    assert "scheduler_stalled" in body["warnings"]


def test_health_detail_degraded_quota_failed(
    app_with_admin: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    db_session: MagicMock,
) -> None:
    """OpenAI quota_exceeded → quota.ok=False → status=degraded."""
    _patch_scheduler(monkeypatch, last_run_minutes_ago=30)
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(
        "app.health.detail_router.get_openai_status",
        lambda: ApiQuotaStatus(reachable=False, last_check=now, last_error="quota_exceeded"),
    )
    monkeypatch.setattr(
        "app.health.detail_router.get_perplexity_status",
        lambda: ApiQuotaStatus(reachable=True, last_check=now, last_error=None),
    )
    monkeypatch.setattr("app.health.detail_router.get_oracle_fresh", lambda: True)
    monkeypatch.setattr("app.health.detail_router.get_reserve_healthy", lambda: True)
    _patch_safety_state(monkeypatch)
    db_session.scalar.side_effect = [10, 10, 8, 2]

    client = TestClient(app_with_admin)
    resp = client.get("/health/detail")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["components"]["quota"]["ok"] is False
    assert "openai_quota_exceeded" in body["warnings"]


def test_health_detail_limiter_expired(
    app_with_admin: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    db_session: MagicMock,
) -> None:
    """is_custom=False (strict, already reverted) → warnings should NOT include expired marker.

    Then test the path where is_custom=True but expires_on is in the past:
    even though risk_limiter would normally have reverted, we surface the warning.
    """
    _patch_scheduler(monkeypatch, last_run_minutes_ago=30)
    _patch_probes_healthy(monkeypatch)
    past = date.today() - timedelta(days=1)
    _patch_safety_state(monkeypatch, is_custom=True, expires_on=past)
    db_session.scalar.side_effect = [10, 10, 8, 2]

    client = TestClient(app_with_admin)
    resp = client.get("/health/detail")
    body = resp.json()
    assert body["components"]["safety"]["limiter_mode"] == "custom"
    assert body["components"]["safety"]["limiter_expires_in_days"] == -1
    assert "limiter_expired_using_strict" in body["warnings"]


def test_health_detail_limiter_expires_soon(
    app_with_admin: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    db_session: MagicMock,
) -> None:
    """expires_in_days=2 → warnings includes 'limiter_expires_soon_2_days'."""
    _patch_scheduler(monkeypatch, last_run_minutes_ago=30)
    _patch_probes_healthy(monkeypatch)
    soon = date.today() + timedelta(days=2)
    _patch_safety_state(monkeypatch, is_custom=True, expires_on=soon)
    db_session.scalar.side_effect = [10, 10, 8, 2]

    client = TestClient(app_with_admin)
    resp = client.get("/health/detail")
    body = resp.json()
    assert body["components"]["safety"]["limiter_expires_in_days"] == 2
    assert "limiter_expires_soon_2_days" in body["warnings"]


def test_health_detail_cross_judgment_no_secondary(
    app_with_admin: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    db_session: MagicMock,
) -> None:
    """6h has_secondary=0 → cross_judgment.ok=False → warnings."""
    _patch_scheduler(monkeypatch, last_run_minutes_ago=30)
    _patch_probes_healthy(monkeypatch)
    _patch_safety_state(monkeypatch)
    # total=5 but has_secondary=0 → ok should be False
    db_session.scalar.side_effect = [5, 0, 0, 0]

    client = TestClient(app_with_admin)
    resp = client.get("/health/detail")
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["components"]["cross_judgment"]["ok"] is False
    assert body["components"]["cross_judgment"]["last_6h_total"] == 5
    assert body["components"]["cross_judgment"]["has_secondary_count"] == 0
    assert "cross_judgment_inactive" in body["warnings"]


def test_health_detail_cache_hit(
    app_with_admin: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    db_session: MagicMock,
) -> None:
    """Second request within TTL must not re-query DB."""
    _patch_scheduler(monkeypatch, last_run_minutes_ago=30)
    _patch_probes_healthy(monkeypatch)
    _patch_safety_state(monkeypatch)
    db_session.scalar.side_effect = [10, 10, 8, 2]

    client = TestClient(app_with_admin)
    r1 = client.get("/health/detail")
    assert r1.status_code == 200
    initial_scalar_calls = db_session.scalar.call_count
    assert initial_scalar_calls == 4

    r2 = client.get("/health/detail")
    assert r2.status_code == 200
    # Cache hit → no additional scalar calls
    assert db_session.scalar.call_count == initial_scalar_calls
    # Response bodies should be identical (same cached_at)
    assert r1.json()["cached_at"] == r2.json()["cached_at"]


def test_health_detail_response_schema(
    app_with_admin: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    db_session: MagicMock,
) -> None:
    """Response validates against HealthDetailResponse Pydantic model."""
    _setup_default_healthy(monkeypatch, db_session)
    client = TestClient(app_with_admin)
    resp = client.get("/health/detail")
    assert resp.status_code == 200
    parsed = HealthDetailResponse.model_validate(resp.json())
    assert parsed.status in ("ok", "degraded", "down")
    assert parsed.components.scheduler.minutes_since_last is not None
    assert parsed.components.safety.limiter_mode in ("strict", "custom")


def test_health_detail_existing_health_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """The existing /health endpoint schema must be unchanged (backward compat)."""
    from app.main import create_app

    monkeypatch.setattr(
        "app.automation.ai_judgment_scheduler.get_scheduler_status",
        lambda: {
            "running": True,
            "last_run": datetime.now(timezone.utc).isoformat(),
            "next_run": (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat(),
            "last_error": None,
        },
    )

    app = create_app()
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    # Schema keys (snapshot of pre-change /health response)
    expected_keys = {
        "status",
        "env",
        "scheduler",
        "scheduler_healthy",
        "last_judgment",
        "next_judgment",
        "scheduler_last_error",
        "warnings",
        "claude_model",
        "claude_fallback_model",
    }
    assert set(body.keys()) == expected_keys
