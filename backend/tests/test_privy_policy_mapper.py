# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_privy_policy_mapper.py
"""policy_mapper の単体テスト（v4 Phase 2-D-B.2 / L1 写像）。

委譲枠 → Privy policy(v1.0) の写像が Privy 実機受理スキーマどおり（version/chain_type/
rules/conditions）であること、未対応プロトコル・不正入力で fail-closed すること、
50 文字超 policy name・未サポートフィールドが生成されないことを検証する。
実 Privy への投入（live 受理）は L1 で別途実施。
"""

from __future__ import annotations

import pytest

from app.aave.chains import get_chain_config
from app.privy.policy_mapper import (
    PolicyMappingError,
    build_delegation_policy,
    build_operator_fee_policy,
    resolve_protocol_contracts,
)

_WALLET = "0x1234567890123456789012345678901234567890"
_ATOKEN = "0xABCdef0000000000000000000000000000000001"


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
        chain_name="base",
    )
    assert policy["version"] == "1.0"
    assert policy["chain_type"] == "ethereum"
    # Privy schema に default_action は存在しない（Bug 3 修正）
    assert "default_action" not in policy
    # name は wallet 短縮形を含み 50 文字以内（Bug 1 修正）
    assert _WALLET[:6].lower() in policy["name"]
    assert _WALLET[-4:].lower() in policy["name"]
    assert len(policy["name"]) <= 50
    # 委譲 method ごとに 1 ALLOW rule
    methods = {r["method"] for r in policy["rules"]}
    assert methods == {"eth_signUserOperation", "eth_sendTransaction"}
    assert all(r["action"] == "ALLOW" for r in policy["rules"])


def test_build_policy_to_allowlist_condition() -> None:
    pool = get_chain_config("base").pool_address.lower()
    policy = build_delegation_policy(
        wallet_address=_WALLET,
        allowed_protocols=["aave"],
        chain_name="base",
    )
    rule = policy["rules"][0]
    to_cond = next(c for c in rule["conditions"] if c["field"] == "to")
    # 単一コントラクトは eq
    assert to_cond["operator"] == "eq"
    assert to_cond["value"] == pool
    assert to_cond["field_source"] == "ethereum_transaction"


def test_build_policy_no_expiry_condition() -> None:
    """current_unix_timestamp は Privy policy で未サポート → 条件に含まれない（Bug 2 修正）。"""
    policy = build_delegation_policy(
        wallet_address=_WALLET,
        allowed_protocols=["aave"],
        chain_name="base",
    )
    for rule in policy["rules"]:
        assert not any(c.get("field") == "current_unix_timestamp" for c in rule["conditions"]), (
            "current_unix_timestamp は Privy 未サポートフィールド"
        )


def test_build_policy_name_under_50_chars() -> None:
    """最長チェーン名 base_sepolia でも 50 文字以内（Bug 1 修正）。"""
    policy = build_delegation_policy(
        wallet_address=_WALLET,
        allowed_protocols=["aave"],
        chain_name="base_sepolia",
    )
    assert len(policy["name"]) <= 50


def test_build_policy_custom_name() -> None:
    policy = build_delegation_policy(
        wallet_address=_WALLET,
        allowed_protocols=["aave"],
        chain_name="base",
        policy_name="my-policy",
    )
    assert policy["name"] == "my-policy"


def test_build_policy_empty_wallet_raises() -> None:
    with pytest.raises(PolicyMappingError):
        build_delegation_policy(
            wallet_address="  ",
            allowed_protocols=["aave"],
            chain_name="base",
        )


def test_build_policy_unsupported_protocol_raises() -> None:
    with pytest.raises(PolicyMappingError):
        build_delegation_policy(
            wallet_address=_WALLET,
            allowed_protocols=["aave", "pendle"],
            chain_name="base",
        )


# ---------------------------------------------------------------------------
# operator fee policy（手数料徴収 wallet の Privy 化）
# ---------------------------------------------------------------------------


def test_build_operator_fee_policy_structure() -> None:
    """operator fee policy: eth_sendTransaction を aToken 宛のみ ALLOW。"""
    policy = build_operator_fee_policy(atoken_address=_ATOKEN, chain_name="base_sepolia")
    assert policy["version"] == "1.0"
    assert policy["chain_type"] == "ethereum"
    assert len(policy["rules"]) == 1
    rule = policy["rules"][0]
    assert rule["method"] == "eth_sendTransaction"
    assert rule["action"] == "ALLOW"
    cond = rule["conditions"][0]
    assert cond["field"] == "to"
    assert cond["operator"] == "eq"
    # 宛先は小文字化された aToken 1 件
    assert cond["value"] == _ATOKEN.lower()


def test_build_operator_fee_policy_name_under_50_chars() -> None:
    policy = build_operator_fee_policy(atoken_address=_ATOKEN, chain_name="base_sepolia")
    assert len(policy["name"]) <= 50


def test_build_operator_fee_policy_empty_atoken_raises() -> None:
    with pytest.raises(PolicyMappingError):
        build_operator_fee_policy(atoken_address="  ", chain_name="base")


def test_build_operator_fee_policy_custom_name() -> None:
    policy = build_operator_fee_policy(
        atoken_address=_ATOKEN, chain_name="base", policy_name="op-fee"
    )
    assert policy["name"] == "op-fee"
