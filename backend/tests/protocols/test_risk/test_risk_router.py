# Copyright (c) Ultra AutoTrade. All rights reserved.
"""Risk Engine FastAPI ルーターのテスト。"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.protocols.risk.router import router
from app.protocols.risk.schemas import ProtocolHealth, RiskLevel

_app = FastAPI()
_app.include_router(router)
_client = TestClient(_app)


def _make_protocol_health(protocol: str = "aave") -> ProtocolHealth:
    return ProtocolHealth(
        protocol=protocol,
        risk_level=RiskLevel.LOW,
        tvl_usd=Decimal("1000000000"),
        tvl_change_24h_pct=Decimal("0"),
        is_operational=True,
        last_checked=datetime.now(timezone.utc),
        alerts=[],
    )


class TestGetAllHealth:
    """GET /api/protocols/health のテスト。"""

    def test_all_health_returns_200(self) -> None:
        """正常時に 200 を返すこと。"""
        with patch("app.protocols.risk.router._get_monitor") as mock_get_monitor:
            mock_monitor = AsyncMock()
            mock_monitor.check_all.return_value = [
                _make_protocol_health("aave"),
                _make_protocol_health("lido"),
                _make_protocol_health("pendle"),
            ]
            mock_get_monitor.return_value = mock_monitor

            response = _client.get("/api/protocols/health")

        assert response.status_code == 200

    def test_all_health_returns_three_protocols(self) -> None:
        """3 プロトコルのヘルス情報が返ること。"""
        with patch("app.protocols.risk.router._get_monitor") as mock_get_monitor:
            mock_monitor = AsyncMock()
            mock_monitor.check_all.return_value = [
                _make_protocol_health("aave"),
                _make_protocol_health("lido"),
                _make_protocol_health("pendle"),
            ]
            mock_get_monitor.return_value = mock_monitor

            response = _client.get("/api/protocols/health")

        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 3

    def test_all_health_exception_returns_503(self) -> None:
        """例外発生時に 503 を返すこと。"""
        with patch("app.protocols.risk.router._get_monitor") as mock_get_monitor:
            mock_monitor = AsyncMock()
            mock_monitor.check_all.side_effect = Exception("モニタリング失敗")
            mock_get_monitor.return_value = mock_monitor

            response = _client.get("/api/protocols/health")

        assert response.status_code == 503

    def test_all_health_response_has_risk_level(self) -> None:
        """レスポンスに risk_level が含まれること。"""
        with patch("app.protocols.risk.router._get_monitor") as mock_get_monitor:
            mock_monitor = AsyncMock()
            mock_monitor.check_all.return_value = [
                _make_protocol_health("aave"),
            ]
            mock_get_monitor.return_value = mock_monitor

            response = _client.get("/api/protocols/health")

        data = response.json()
        assert "risk_level" in data[0]
        assert "is_operational" in data[0]


class TestGetAaveHealth:
    """GET /api/protocols/health/aave のテスト。"""

    def test_aave_health_returns_200(self) -> None:
        """正常時に 200 を返すこと。"""
        with patch("app.protocols.risk.router._get_monitor") as mock_get_monitor:
            mock_monitor = AsyncMock()
            mock_monitor.check_aave_health.return_value = _make_protocol_health("aave")
            mock_get_monitor.return_value = mock_monitor

            response = _client.get("/api/protocols/health/aave")

        assert response.status_code == 200

    def test_aave_health_protocol_name(self) -> None:
        """レスポンスの protocol フィールドが 'aave' であること。"""
        with patch("app.protocols.risk.router._get_monitor") as mock_get_monitor:
            mock_monitor = AsyncMock()
            mock_monitor.check_aave_health.return_value = _make_protocol_health("aave")
            mock_get_monitor.return_value = mock_monitor

            response = _client.get("/api/protocols/health/aave")

        data = response.json()
        assert data["protocol"] == "aave"

    def test_aave_health_exception_returns_503(self) -> None:
        """例外発生時に 503 を返すこと。"""
        with patch("app.protocols.risk.router._get_monitor") as mock_get_monitor:
            mock_monitor = AsyncMock()
            mock_monitor.check_aave_health.side_effect = Exception("Aave ヘルスチェック失敗")
            mock_get_monitor.return_value = mock_monitor

            response = _client.get("/api/protocols/health/aave")

        assert response.status_code == 503


class TestGetLidoHealth:
    """GET /api/protocols/health/lido のテスト。"""

    def test_lido_health_returns_200(self) -> None:
        """正常時に 200 を返すこと。"""
        with patch("app.protocols.risk.router._get_monitor") as mock_get_monitor:
            mock_monitor = AsyncMock()
            mock_monitor.check_lido_health.return_value = _make_protocol_health("lido")
            mock_get_monitor.return_value = mock_monitor

            response = _client.get("/api/protocols/health/lido")

        assert response.status_code == 200

    def test_lido_health_protocol_name(self) -> None:
        """レスポンスの protocol フィールドが 'lido' であること。"""
        with patch("app.protocols.risk.router._get_monitor") as mock_get_monitor:
            mock_monitor = AsyncMock()
            mock_monitor.check_lido_health.return_value = _make_protocol_health("lido")
            mock_get_monitor.return_value = mock_monitor

            response = _client.get("/api/protocols/health/lido")

        data = response.json()
        assert data["protocol"] == "lido"

    def test_lido_health_exception_returns_503(self) -> None:
        """例外発生時に 503 を返すこと。"""
        with patch("app.protocols.risk.router._get_monitor") as mock_get_monitor:
            mock_monitor = AsyncMock()
            mock_monitor.check_lido_health.side_effect = Exception("Lido ヘルスチェック失敗")
            mock_get_monitor.return_value = mock_monitor

            response = _client.get("/api/protocols/health/lido")

        assert response.status_code == 503


class TestGetPendleHealth:
    """GET /api/protocols/health/pendle のテスト。"""

    def test_pendle_health_returns_200(self) -> None:
        """正常時に 200 を返すこと。"""
        with patch("app.protocols.risk.router._get_monitor") as mock_get_monitor:
            mock_monitor = AsyncMock()
            mock_monitor.check_pendle_health.return_value = _make_protocol_health("pendle")
            mock_get_monitor.return_value = mock_monitor

            response = _client.get("/api/protocols/health/pendle")

        assert response.status_code == 200

    def test_pendle_health_protocol_name(self) -> None:
        """レスポンスの protocol フィールドが 'pendle' であること。"""
        with patch("app.protocols.risk.router._get_monitor") as mock_get_monitor:
            mock_monitor = AsyncMock()
            mock_monitor.check_pendle_health.return_value = _make_protocol_health("pendle")
            mock_get_monitor.return_value = mock_monitor

            response = _client.get("/api/protocols/health/pendle")

        data = response.json()
        assert data["protocol"] == "pendle"

    def test_pendle_health_exception_returns_503(self) -> None:
        """例外発生時に 503 を返すこと。"""
        with patch("app.protocols.risk.router._get_monitor") as mock_get_monitor:
            mock_monitor = AsyncMock()
            mock_monitor.check_pendle_health.side_effect = Exception("Pendle ヘルスチェック失敗")
            mock_get_monitor.return_value = mock_monitor

            response = _client.get("/api/protocols/health/pendle")

        assert response.status_code == 503


class TestStagingGuardRegression:
    """P0-1 DummyClient staging guard 回帰テスト。

    staging 環境で LIDO_SANDBOX=true / PENDLE_SANDBOX=true を設定しても
    /api/protocols/health/* が 200 を返すことを HTTP レベルで検証する。
    (旧 guard: 'staging' in ('staging', 'production') → RuntimeError → 500
     新 guard: 'staging' == 'production' → False → DummyClient 利用可能 → 200)
    """

    def test_lido_health_staging_with_sandbox_returns_200(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """APP_ENV=staging + LIDO_SANDBOX=true で /health/lido が 200 を返すこと。"""
        monkeypatch.setenv("APP_ENV", "staging")
        monkeypatch.setenv("LIDO_SANDBOX", "true")
        monkeypatch.setenv("PENDLE_SANDBOX", "true")
        staging_client = TestClient(_app, raise_server_exceptions=False)
        resp = staging_client.get("/api/protocols/health/lido")
        assert resp.status_code == 200

    def test_pendle_health_staging_with_sandbox_returns_200(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """APP_ENV=staging + PENDLE_SANDBOX=true で /health/pendle が 200 を返すこと。"""
        monkeypatch.setenv("APP_ENV", "staging")
        monkeypatch.setenv("LIDO_SANDBOX", "true")
        monkeypatch.setenv("PENDLE_SANDBOX", "true")
        staging_client = TestClient(_app, raise_server_exceptions=False)
        resp = staging_client.get("/api/protocols/health/pendle")
        assert resp.status_code == 200

    def test_lido_health_production_with_sandbox_returns_5xx(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """APP_ENV=production + LIDO_SANDBOX=true で /health/lido が 5xx を返すこと。"""
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("LIDO_SANDBOX", "true")
        monkeypatch.setenv("PENDLE_SANDBOX", "true")
        prod_client = TestClient(_app, raise_server_exceptions=False)
        resp = prod_client.get("/api/protocols/health/lido")
        assert resp.status_code in (500, 503)
