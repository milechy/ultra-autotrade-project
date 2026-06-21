# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_scw_executor.py
"""scw_executor（委譲(SCW)経路の実行コア / 2-D-C）の単体テスト。

dormant ゲート / caip2 変換 / build_deposit_txs→calls 変換 / send_calls 呼び出し形 /
tx_hash 抽出 / エラー写像を検証する。Privy への live 送信は別途（staging-v4）。
"""

from __future__ import annotations

from typing import Iterator
from unittest.mock import MagicMock

import pytest

from app.aave.chains import get_chain_config
from app.privy.rest_client import PrivyRestError
from app.proposals.scw_executor import (
    ScwExecutionError,
    ScwNotEnabledError,
    build_supply_calls,
    caip2_for_chain,
    execute_calls_via_scw,
)

_WALLET_ID = "sle3q76qzuvzwen06y64hfcj"
_CALLS = [{"to": "0xpool", "value": "0x0", "data": "0xdeadbeef"}]


@pytest.fixture()
def enabled_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("DELEGATION_PRIVY_POLICY_ENABLED", "true")
    monkeypatch.setenv("PRIVY_SERVER_SIGNER_ID", "kq_server_1")
    monkeypatch.setenv("PRIVY_APP_ID", "app123")
    monkeypatch.setenv("PRIVY_APP_SECRET", "secret123")
    yield


def _disable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DELEGATION_PRIVY_POLICY_ENABLED", raising=False)


# ---- caip2 ----


def test_caip2_base() -> None:
    assert caip2_for_chain("base") == f"eip155:{get_chain_config('base').chain_id}"
    assert caip2_for_chain("base") == "eip155:8453"


def test_caip2_base_sepolia() -> None:
    assert caip2_for_chain("base_sepolia") == "eip155:84532"


# ---- build_supply_calls ----


def test_build_supply_calls_order_and_shape() -> None:
    deposit_txs = {
        "approve_tx": {"to": "0xtoken", "data": "0xapprove", "value": "0x0", "from": "0xx"},
        "supply_tx": {"to": "0xpool", "data": "0xsupply", "value": "0x0", "from": "0xx"},
    }
    calls = build_supply_calls(deposit_txs)
    assert [c["to"] for c in calls] == ["0xtoken", "0xpool"]
    assert calls[0] == {"to": "0xtoken", "value": "0x0", "data": "0xapprove"}
    # from/nonce/gas は含めない
    assert "from" not in calls[1]


def test_build_supply_calls_supply_only() -> None:
    calls = build_supply_calls({"supply_tx": {"to": "0xpool", "data": "0xs"}})
    assert len(calls) == 1
    assert calls[0]["value"] == "0x0"  # 既定 value


def test_build_supply_calls_empty_raises() -> None:
    with pytest.raises(ScwExecutionError):
        build_supply_calls({})


# ---- execute_calls_via_scw ----


def test_execute_disabled_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _disable(monkeypatch)
    with pytest.raises(ScwNotEnabledError):
        execute_calls_via_scw(
            privy_wallet_id=_WALLET_ID, chain_name="base", calls=_CALLS, client=MagicMock()
        )


def test_execute_disabled_does_not_call_privy(monkeypatch: pytest.MonkeyPatch) -> None:
    _disable(monkeypatch)
    fake = MagicMock()
    with pytest.raises(ScwNotEnabledError):
        execute_calls_via_scw(
            privy_wallet_id=_WALLET_ID, chain_name="base", calls=_CALLS, client=fake
        )
    fake.send_calls.assert_not_called()


def test_execute_requires_wallet_id(enabled_env: None) -> None:
    with pytest.raises(ScwExecutionError):
        execute_calls_via_scw(
            privy_wallet_id="", chain_name="base", calls=_CALLS, client=MagicMock()
        )


def test_execute_requires_calls(enabled_env: None) -> None:
    with pytest.raises(ScwExecutionError):
        execute_calls_via_scw(
            privy_wallet_id=_WALLET_ID, chain_name="base", calls=[], client=MagicMock()
        )


def test_execute_success_request_shape(enabled_env: None) -> None:
    fake = MagicMock()
    fake.send_calls.return_value = {"transaction_hash": "0xfeed"}
    result = execute_calls_via_scw(
        privy_wallet_id=_WALLET_ID,
        chain_name="base",
        calls=_CALLS,
        client=fake,
    )
    assert result.tx_hash == "0xfeed"
    assert result.status == "submitted"
    # send_calls に渡る引数（caip2 / calls / sponsor）
    kwargs = fake.send_calls.call_args.kwargs
    assert fake.send_calls.call_args.args[0] == _WALLET_ID
    assert kwargs["caip2"] == "eip155:8453"
    assert kwargs["calls"] == _CALLS
    assert kwargs["sponsor"] is True


def test_execute_tx_hash_nested_result(enabled_env: None) -> None:
    fake = MagicMock()
    fake.send_calls.return_value = {"result": {"hash": "0xabc"}}
    result = execute_calls_via_scw(
        privy_wallet_id=_WALLET_ID, chain_name="base", calls=_CALLS, client=fake
    )
    assert result.tx_hash == "0xabc"


def test_execute_unknown_when_no_hash(enabled_env: None) -> None:
    fake = MagicMock()
    fake.send_calls.return_value = {"bundle_id": "xyz"}
    result = execute_calls_via_scw(
        privy_wallet_id=_WALLET_ID, chain_name="base", calls=_CALLS, client=fake
    )
    assert result.tx_hash is None
    assert result.status == "unknown"
    assert result.raw == {"bundle_id": "xyz"}


def test_execute_privy_error_wrapped(enabled_env: None) -> None:
    fake = MagicMock()
    fake.send_calls.side_effect = PrivyRestError(500, "boom")
    with pytest.raises(ScwExecutionError):
        execute_calls_via_scw(
            privy_wallet_id=_WALLET_ID, chain_name="base", calls=_CALLS, client=fake
        )
