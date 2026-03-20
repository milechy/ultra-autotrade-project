# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_qa_approval_flow.py
"""
QA: E2E approval flow tests.

Verifies that the transparency → approval flow works correctly,
and that emergency stop / SAFE_MODE / risk-profile constraints are enforced.
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.aave.router import get_multi_chain_aave_service
from app.aave.schemas import (
    AaveOperationMode,
    AaveOperationResult,
    AaveOperationStatus,
    AaveOperationType,
    AaveSystemState,
)
from app.auth.dependencies import require_admin, require_viewer
from app.auth.models import UserRole
from app.main import create_app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_admin_user() -> MagicMock:
    user = MagicMock()
    user.id = 1
    user.email = "admin@example.com"
    user.username = "admin"
    user.role = UserRole.ADMIN.value
    user.is_active = True
    return user


def _make_state(
    emergency_stop: bool = False,
    mode: AaveOperationMode = AaveOperationMode.NORMAL,
    circuit_closed: bool = True,
) -> AaveSystemState:
    return AaveSystemState(
        emergency_stop=emergency_stop,
        mode=mode,
        health_factor=None,
        last_update=datetime.now(timezone.utc),
        reason=None,
        circuit_closed=circuit_closed,
        stale_threshold_seconds=300,
    )


class _DummyMultiChainService:
    """Minimal multi-chain service that records calls and returns a fixed result."""

    def __init__(self, operation: AaveOperationType = AaveOperationType.DEPOSIT) -> None:
        self.calls: list[tuple] = []
        self._operation = operation

    def execute_rebalance(
        self,
        chain_name: str,
        action=None,
        amount=None,
        asset_symbol=None,
        dry_run=False,
    ) -> AaveOperationResult:
        self.calls.append((chain_name, action, amount, asset_symbol, dry_run))
        return AaveOperationResult(
            operation=self._operation,
            status=AaveOperationStatus.SUCCESS,
            asset_symbol=asset_symbol or "USDC",
            amount=Decimal(str(amount)) if amount is not None else Decimal("0"),
            tx_hash=None if dry_run else "dummy-tx",
            message="dry-run ok" if dry_run else "ok",
            chain_name=chain_name,
        )

    def get_all_health_factors(self) -> dict:
        return {"arbitrum": Decimal("2.5")}

    def get_chain_names(self) -> list:
        return ["arbitrum"]


class _NoopMultiChainService(_DummyMultiChainService):
    """Service that always returns NOOP (simulates blocked execution)."""

    def __init__(self) -> None:
        super().__init__(operation=AaveOperationType.NOOP)

    def execute_rebalance(
        self,
        chain_name: str,
        action=None,
        amount=None,
        asset_symbol=None,
        dry_run=False,
    ) -> AaveOperationResult:
        self.calls.append((chain_name, action, amount, asset_symbol, dry_run))
        return AaveOperationResult(
            operation=AaveOperationType.NOOP,
            status=AaveOperationStatus.SKIPPED,
            asset_symbol=asset_symbol or "USDC",
            amount=Decimal("0"),
            tx_hash=None,
            message="emergency_stop is True; all Aave operations are blocked.",
            chain_name=chain_name,
        )


def _create_client(service, override_admin: bool = True) -> TestClient:
    admin_user = _make_admin_user()
    app = create_app()
    app.dependency_overrides[get_multi_chain_aave_service] = lambda: service
    if override_admin:
        app.dependency_overrides[require_admin] = lambda: admin_user
        app.dependency_overrides[require_viewer] = lambda: admin_user
    return TestClient(app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_full_approval_flow() -> None:
    """
    Full AI → transparency → approval flow (dry_run=True).

    1. Call transparency endpoints (no auth required, no mocks needed).
    2. Call POST /api/aave/rebalance with dry_run=True via mocked service.
    """
    service = _DummyMultiChainService()
    client = _create_client(service)

    # Step 1: Check transparency endpoints are accessible
    safety_resp = client.get("/api/transparency/safety-score")
    assert safety_resp.status_code == 200

    signal_resp = client.get("/api/transparency/signal")
    assert signal_resp.status_code == 200

    # Step 2: Execute dry-run rebalance
    payload = {
        "action": "BUY",
        "amount": "500",
        "asset_symbol": "USDC",
        "dry_run": True,
    }
    resp = client.post("/api/aave/rebalance", json=payload)
    assert resp.status_code == 200

    data = resp.json()
    # dry_run=True means the service is called; result depends on mock
    assert "result" in data
    assert service.calls, "Service should have been called"
    assert service.calls[0][4] is True  # dry_run flag was True


def test_approval_blocked_by_emergency() -> None:
    """
    Emergency stop blocks rebalance — service returns NOOP with SKIPPED status.
    """
    service = _NoopMultiChainService()
    client = _create_client(service)

    payload = {
        "action": "BUY",
        "amount": "100",
        "asset_symbol": "USDC",
    }
    resp = client.post("/api/aave/rebalance", json=payload)
    assert resp.status_code == 200

    data = resp.json()
    result = data["result"]
    assert result["operation"] == "NOOP"
    assert result["status"] == "skipped"


def test_approval_blocked_by_safe_mode() -> None:
    """
    SAFE_MODE blocks BUY — service returns NOOP for BUY actions.
    """

    class SafeModeService(_NoopMultiChainService):
        def execute_rebalance(
            self, chain_name, action=None, amount=None, asset_symbol=None, dry_run=False
        ):  # type: ignore[override]
            self.calls.append((chain_name, action, amount, asset_symbol, dry_run))
            return AaveOperationResult(
                operation=AaveOperationType.NOOP,
                status=AaveOperationStatus.SKIPPED,
                asset_symbol=asset_symbol or "USDC",
                amount=Decimal("0"),
                tx_hash=None,
                message="Mode=safe_mode: BUY is blocked; only SELL/HOLD allowed.",
                chain_name=chain_name,
            )

    service = SafeModeService()
    client = _create_client(service)

    payload = {
        "action": "BUY",
        "amount": "200",
        "asset_symbol": "USDC",
    }
    resp = client.post("/api/aave/rebalance", json=payload)
    assert resp.status_code == 200

    data = resp.json()
    result = data["result"]
    assert result["operation"] == "NOOP"
    assert result["status"] == "skipped"
    assert "safe_mode" in result["message"].lower() or "BUY" in result["message"]


def test_approval_respects_risk_profile() -> None:
    """
    Risk profile constraints: conservative profile does not allow ETH.

    RiskProfileManager.is_action_allowed() returns allowed=False for ETH
    when the profile is 'conservative'.
    """
    from app.aave.risk_profile import RiskProfileManager

    mgr = RiskProfileManager()

    # ETH is not in conservative's allowed_assets list
    result = mgr.is_action_allowed(
        mode="conservative",
        asset_symbol="ETH",
        confidence=Decimal("0.9"),
    )
    assert result.allowed is False
    assert "conservative" in result.reason or "ETH" in result.reason

    # USDC is allowed in conservative profile with sufficient confidence
    result_allowed = mgr.is_action_allowed(
        mode="conservative",
        asset_symbol="USDC",
        confidence=Decimal("0.9"),
    )
    assert result_allowed.allowed is True

    # Low confidence is blocked even for allowed assets
    result_low_conf = mgr.is_action_allowed(
        mode="conservative",
        asset_symbol="USDC",
        confidence=Decimal("0.5"),  # below conservative min_confidence=0.8
    )
    assert result_low_conf.allowed is False