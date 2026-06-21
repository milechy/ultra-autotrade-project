# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_privy_delegation_service.py
"""delegation_service（L1: 委譲枠→Privy policy 作成）の単体テスト。

dormant ゲート（フラグ / L0 signer id / Privy creds の有無）と、有効時の policy 作成
（PrivyRestClient.create_policy を mock）・エラー写像を検証する。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterator
from unittest.mock import MagicMock, patch

import pytest

from app.privy import delegation_service as ds
from app.privy.delegation_service import (
    DelegationPolicyError,
    DelegationPolicyNotEnabledError,
    is_delegation_policy_enabled,
    prepare_delegation_policy,
)
from app.privy.rest_client import PrivyRestError

_EXPIRES = datetime(2026, 7, 1, tzinfo=timezone.utc)
_WALLET = "0x1234567890123456789012345678901234567890"


@pytest.fixture()
def enabled_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("DELEGATION_PRIVY_POLICY_ENABLED", "true")
    monkeypatch.setenv("PRIVY_SERVER_SIGNER_ID", "kq_server_1")
    monkeypatch.setenv("PRIVY_APP_ID", "app123")
    monkeypatch.setenv("PRIVY_APP_SECRET", "secret123")
    yield


def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in (
        "DELEGATION_PRIVY_POLICY_ENABLED",
        "PRIVY_SERVER_SIGNER_ID",
        "PRIVY_APP_ID",
        "PRIVY_APP_SECRET",
    ):
        monkeypatch.delenv(k, raising=False)


def test_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    assert is_delegation_policy_enabled() is False


def test_flag_alone_not_enough(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("DELEGATION_PRIVY_POLICY_ENABLED", "true")
    # signer id / creds が無いので無効
    assert is_delegation_policy_enabled() is False


def test_enabled_requires_all(enabled_env: None) -> None:
    assert is_delegation_policy_enabled() is True


def test_prepare_raises_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    with pytest.raises(DelegationPolicyNotEnabledError):
        prepare_delegation_policy(
            wallet_address=_WALLET,
            allowed_protocols=["aave"],
            expires_at=_EXPIRES,
            chain_name="base",
        )


def test_prepare_success_returns_ids(enabled_env: None) -> None:
    fake = MagicMock()
    fake.create_policy.return_value = {"id": "policy_abc"}
    with patch.object(ds, "PrivyRestClient", return_value=fake):
        policy_id, signer_id = prepare_delegation_policy(
            wallet_address=_WALLET,
            allowed_protocols=["aave"],
            expires_at=_EXPIRES,
            chain_name="base",
        )
    assert policy_id == "policy_abc"
    assert signer_id == "kq_server_1"
    # create_policy に渡る body が Privy policy schema
    sent = fake.create_policy.call_args.args[0]
    assert sent["version"] == "1.0"
    assert sent["default_action"] == "DENY"


def test_prepare_mapping_error_wrapped(enabled_env: None) -> None:
    """未対応プロトコルは DelegationPolicyError（Privy を叩かない）。"""
    fake = MagicMock()
    with patch.object(ds, "PrivyRestClient", return_value=fake):
        with pytest.raises(DelegationPolicyError):
            prepare_delegation_policy(
                wallet_address=_WALLET,
                allowed_protocols=["lido"],
                expires_at=_EXPIRES,
                chain_name="base",
            )
    fake.create_policy.assert_not_called()


def test_prepare_privy_error_wrapped(enabled_env: None) -> None:
    fake = MagicMock()
    fake.create_policy.side_effect = PrivyRestError(400, "bad")
    with patch.object(ds, "PrivyRestClient", return_value=fake):
        with pytest.raises(DelegationPolicyError):
            prepare_delegation_policy(
                wallet_address=_WALLET,
                allowed_protocols=["aave"],
                expires_at=_EXPIRES,
                chain_name="base",
            )


def test_prepare_missing_id_wrapped(enabled_env: None) -> None:
    fake = MagicMock()
    fake.create_policy.return_value = {"no_id": True}
    with patch.object(ds, "PrivyRestClient", return_value=fake):
        with pytest.raises(DelegationPolicyError):
            prepare_delegation_policy(
                wallet_address=_WALLET,
                allowed_protocols=["aave"],
                expires_at=_EXPIRES,
                chain_name="base",
            )


def test_resolve_chain_name_defaults_to_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AAVE_ACTIVE_CHAINS", raising=False)
    assert ds.resolve_delegation_chain_name() == "base"
