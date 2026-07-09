# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_pendle_scw_execution.py
"""[Phase D / D3] _execute_pendle_for_proposal の broadcast 分岐（SCW 委譲署名）。

二段ガード全 true のときのみ SCW broadcast し executed/tx_hash をセットすること、いずれか
欠ければ D2 dry-run に留まること、HARD_STOP 発火時は broadcast せず approved 据え置きになること、
Aave 経路を絶対に呼ばないことを検証する（実 broadcast はしない・全て monkeypatch）。
"""

import os
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-pendle-scw-exec")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin@example.com")

import app.privy.delegation_service as delegation_mod  # noqa: E402
import app.proposals.router as router_mod  # noqa: E402
import app.protocols.pendle.client as pendle_client_mod  # noqa: E402
import app.protocols.pendle.config as pendle_config_mod  # noqa: E402
from app.proposals.router import (  # noqa: E402
    PendleDryRunNotBroadcast,
    _execute_pendle_for_proposal,
)
from app.protocols.pendle.config import PendleConfig  # noqa: E402
from app.protocols.pendle.schemas import RouterV4SwapResult  # noqa: E402

_MARKET = "0x1111111111111111111111111111111111111111"
_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
_WALLET = "0x7f9300000000000000000000000000000000a0Ff"


def _mk_proposal() -> MagicMock:
    p = MagicMock()
    p.id = 77
    p.protocol = "pendle"
    p.operation = "BUY_PT"
    p.amount_usd = Decimal("50.00")
    p.amount = Decimal("50.00")
    p.asset = "PT-yoUSD"
    p.user_id = 11
    p.ai_decision_id = None
    p.execution_attempts = 0
    return p


def _mk_db() -> MagicMock:
    db = MagicMock()
    user = MagicMock()
    user.wallet_address = _WALLET
    user.smart_wallet_address = None
    db.get.return_value = user
    return db


class _FakeDryRunClient:
    async def build_buy_pt_swap_result(self, **kwargs: object) -> "RouterV4SwapResult":
        return RouterV4SwapResult(
            success=True,
            to="0x888888888889758F76e7103c6CbF23ABbF58F946",
            calldata="0x" + "ab" * 10,
            approvals=[],
        )


def _patch_common(
    monkeypatch: pytest.MonkeyPatch,
    *,
    enable_onchain_write: bool,
    delegation_enabled: bool,
    allowed_protocols: list[str] | None = None,
) -> None:
    config = PendleConfig(
        market_address=_MARKET,
        underlying_token_address=_USDC,
        underlying_token_decimals=6,
        stable_underlying=True,
        chain="base_sepolia",
    )
    config.enable_onchain_write = enable_onchain_write
    monkeypatch.setattr(pendle_config_mod, "get_pendle_config", lambda: config)
    monkeypatch.setattr(delegation_mod, "is_delegation_policy_enabled", lambda: delegation_enabled)
    # dry-run フォールバック用のフェイク client（実 SDK を叩かない）。
    monkeypatch.setattr(
        pendle_client_mod, "get_pendle_router_v4_client", lambda cfg: _FakeDryRunClient()
    )
    grant = MagicMock()
    grant.privy_signer_id = "signer-1"
    grant.privy_policy_id = "policy-1"
    grant.wallet_address = _WALLET
    grant.allowed_protocols = allowed_protocols if allowed_protocols is not None else ["pendle"]
    monkeypatch.setattr(router_mod, "get_active_grant", lambda uid, db: grant)


def test_broadcast_when_all_gates_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """二段ガード全 true → SCW 実行し executed/tx_hash をセット。"""
    _patch_common(monkeypatch, enable_onchain_write=True, delegation_enabled=True)
    monkeypatch.setattr(router_mod, "_pendle_execution_blocked", lambda p, db: None)
    called: dict[str, object] = {}

    def _fake_scw(
        proposal: object, chain: object, grant: object, user: object, db: object
    ) -> object:
        called["chain"] = chain
        return SimpleNamespace(tx_hash="0xdeadbeef", status="submitted")

    monkeypatch.setattr(router_mod, "_execute_pendle_via_scw", _fake_scw)

    p, db = _mk_proposal(), _mk_db()
    _execute_pendle_for_proposal(p, db)  # broadcast 分岐は raise しない

    assert p.status == "executed"
    assert p.tx_hash == "0xdeadbeef"
    assert p.execution_attempts == 1
    assert called["chain"] == "base_sepolia"
    db.add.assert_called_once()


def test_dry_run_when_onchain_write_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """PENDLE_ENABLE_ONCHAIN_WRITE=false → broadcast せず D2 dry-run。"""
    _patch_common(monkeypatch, enable_onchain_write=False, delegation_enabled=True)

    def _must_not_scw(*a: object, **k: object) -> object:
        raise AssertionError("onchain_write=false で SCW を呼んではならない")

    monkeypatch.setattr(router_mod, "_execute_pendle_via_scw", _must_not_scw)
    with pytest.raises(PendleDryRunNotBroadcast):
        _execute_pendle_for_proposal(_mk_proposal(), _mk_db())


def test_dry_run_when_delegation_dormant(monkeypatch: pytest.MonkeyPatch) -> None:
    """delegation policy 無効（dormant）→ broadcast せず D2 dry-run。"""
    _patch_common(monkeypatch, enable_onchain_write=True, delegation_enabled=False)

    def _must_not_scw(*a: object, **k: object) -> object:
        raise AssertionError("delegation dormant で SCW を呼んではならない")

    monkeypatch.setattr(router_mod, "_execute_pendle_via_scw", _must_not_scw)
    with pytest.raises(PendleDryRunNotBroadcast):
        _execute_pendle_for_proposal(_mk_proposal(), _mk_db())


def test_dry_run_when_grant_missing_pendle(monkeypatch: pytest.MonkeyPatch) -> None:
    """grant.allowed_protocols に pendle が無い → broadcast せず D2 dry-run。"""
    _patch_common(
        monkeypatch, enable_onchain_write=True, delegation_enabled=True, allowed_protocols=["aave"]
    )

    def _must_not_scw(*a: object, **k: object) -> object:
        raise AssertionError("pendle 未委譲で SCW を呼んではならない")

    monkeypatch.setattr(router_mod, "_execute_pendle_via_scw", _must_not_scw)
    with pytest.raises(PendleDryRunNotBroadcast):
        _execute_pendle_for_proposal(_mk_proposal(), _mk_db())


def test_hard_stop_blocks_broadcast(monkeypatch: pytest.MonkeyPatch) -> None:
    """HARD_STOP 発火 → broadcast せず approved 据え置き（raise しない・executed にしない）。"""
    _patch_common(monkeypatch, enable_onchain_write=True, delegation_enabled=True)
    monkeypatch.setattr(
        router_mod, "_pendle_execution_blocked", lambda p, db: "HARD_STOP (source=x, reason=y)"
    )

    def _must_not_scw(*a: object, **k: object) -> object:
        raise AssertionError("HARD_STOP 時に SCW を呼んではならない")

    monkeypatch.setattr(router_mod, "_execute_pendle_via_scw", _must_not_scw)

    p, db = _mk_proposal(), _mk_db()
    _execute_pendle_for_proposal(p, db)  # 据え置き = raise しない
    assert p.status != "executed"


def test_scw_failure_marks_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    """SCW 送信失敗 → failed + 失敗トランザクション記録（raise しない）。"""
    from app.proposals.scw_executor import ScwExecutionError

    _patch_common(monkeypatch, enable_onchain_write=True, delegation_enabled=True)
    monkeypatch.setattr(router_mod, "_pendle_execution_blocked", lambda p, db: None)
    monkeypatch.setattr(router_mod, "_record_failed_transaction", lambda *a, **k: None)

    def _fail_scw(*a: object, **k: object) -> object:
        raise ScwExecutionError("Privy send_calls failed")

    monkeypatch.setattr(router_mod, "_execute_pendle_via_scw", _fail_scw)

    p, db = _mk_proposal(), _mk_db()
    _execute_pendle_for_proposal(p, db)
    assert p.status == "failed"
    assert "ScwExecutionError" in (p.error_message or "")


def test_broadcast_never_calls_aave(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_common(monkeypatch, enable_onchain_write=True, delegation_enabled=True)
    monkeypatch.setattr(router_mod, "_pendle_execution_blocked", lambda p, db: None)
    monkeypatch.setattr(
        router_mod,
        "_execute_pendle_via_scw",
        lambda *a, **k: SimpleNamespace(tx_hash="0x1", status="submitted"),
    )

    def _must_not_run(p: object, db: object) -> None:
        raise AssertionError("Pendle broadcast で Aave 経路を実行してはならない")

    monkeypatch.setattr(router_mod, "_execute_aave_for_proposal", _must_not_run)
    _execute_pendle_for_proposal(_mk_proposal(), _mk_db())
