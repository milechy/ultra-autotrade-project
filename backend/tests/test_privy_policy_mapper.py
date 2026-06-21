# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_privy_policy_mapper.py
"""policy_mapper の単体テスト（v4 Phase 2-D-B.2 / L1 写像）。

委譲枠 → Privy policy(v1.0) の写像が schema どおり（version/chain_type/rules/conditions/
default_action）であること、未対応プロトコル・不正入力で fail-closed すること、期限が
unix 秒条件に正しく落ちることを検証する。実 Privy への投入（live 受理）は L1 で別途実施。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.aave.chains import get_chain_config
from app.privy.policy_mapper import (
    PolicyMappingError,
    build_delegation_policy,
    resolve_protocol_contracts,
)

_EXPIRES = datetime(2026, 7, 1, 0, 0, 0, tzinfo=timezone.utc)
_WALLET = "0x1234567890123456789012345678901234567890"


def test_resolve_aave_contract_base() -> None:
    contracts = resolve_protocol_contracts(["aave"], "base")
    assert contracts == [get_chain_config("base").pool_address.lower()]


def test_resolve_dedupes_and_lowercases() -> None:
    contracts = resolve_protocol_contracts(["aave", "AAVE", " Aave "], "base_sepolia")
    assert contracts == [get_chain_config("base_sepolia").pool_address.lower()]


def test_resolve_empty_protocols_raises() -> None:
    with pytest.raises(PolicyMappingError):
        resolve_protocol_contracts([], "base")


def test_resolve_unsupported_protocol_fails_closed() -> None:
    with pytest.raises(PolicyMappingError) as ei:
        resolve_protocol_contracts(["lido"], "base")
    assert "lido" in str(ei.value)


def test_resolve_bad_chain_raises() -> None:
    with pytest.raises(PolicyMappingError):
        resolve_protocol_contracts(["aave"], "no_such_chain")


def test_build_policy_top_level_schema() -> None:
    policy = build_delegation_policy(
        wallet_address=_WALLET,
        allowed_protocols=["aave"],
        expires_at=_EXPIRES,
        chain_name="base",
    )
    assert policy["version"] == "1.0"
    assert policy["chain_type"] == "ethereum"
    assert policy["default_action"] == "DENY"
    assert _WALLET.lower() in policy["name"]
    # 委譲 method ごとに 1 ALLOW rule
    methods = {r["method"] for r in policy["rules"]}
    assert methods == {"eth_signUserOperation", "eth_sendTransaction"}
    assert all(r["action"] == "ALLOW" for r in policy["rules"])


def test_build_policy_to_allowlist_condition() -> None:
    pool = get_chain_config("base").pool_address.lower()
    policy = build_delegation_policy(
        wallet_address=_WALLET,
        allowed_protocols=["aave"],
        expires_at=_EXPIRES,
        chain_name="base",
    )
    rule = policy["rules"][0]
    to_cond = next(c for c in rule["conditions"] if c["field"] == "to")
    # 単一コントラクトは eq
    assert to_cond["operator"] == "eq"
    assert to_cond["value"] == pool
    assert to_cond["field_source"] == "ethereum_transaction"


def test_build_policy_expiry_condition_unix() -> None:
    policy = build_delegation_policy(
        wallet_address=_WALLET,
        allowed_protocols=["aave"],
        expires_at=_EXPIRES,
        chain_name="base",
    )
    rule = policy["rules"][0]
    exp_cond = next(c for c in rule["conditions"] if c["field"] == "current_unix_timestamp")
    assert exp_cond["operator"] == "lte"
    assert exp_cond["value"] == str(int(_EXPIRES.timestamp()))


def test_build_policy_naive_expiry_treated_as_utc() -> None:
    naive = datetime(2026, 7, 1, 0, 0, 0)
    policy = build_delegation_policy(
        wallet_address=_WALLET,
        allowed_protocols=["aave"],
        expires_at=naive,
        chain_name="base",
    )
    exp_cond = next(
        c for c in policy["rules"][0]["conditions"] if c["field"] == "current_unix_timestamp"
    )
    assert exp_cond["value"] == str(int(_EXPIRES.timestamp()))


def test_build_policy_custom_name() -> None:
    policy = build_delegation_policy(
        wallet_address=_WALLET,
        allowed_protocols=["aave"],
        expires_at=_EXPIRES,
        chain_name="base",
        policy_name="my-policy",
    )
    assert policy["name"] == "my-policy"


def test_build_policy_empty_wallet_raises() -> None:
    with pytest.raises(PolicyMappingError):
        build_delegation_policy(
            wallet_address="  ",
            allowed_protocols=["aave"],
            expires_at=_EXPIRES,
            chain_name="base",
        )


def test_build_policy_unsupported_protocol_raises() -> None:
    with pytest.raises(PolicyMappingError):
        build_delegation_policy(
            wallet_address=_WALLET,
            allowed_protocols=["aave", "pendle"],
            expires_at=_EXPIRES,
            chain_name="base",
        )
