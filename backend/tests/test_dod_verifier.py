# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_dod_verifier.py
"""
dod_verifier (非カストディ Aave supply DoD 1-4 機械判定) のユニットテスト。

ネットワーク非依存。P0-1 参照 tx
0xc819b1407a9e9ecedc36b823543b423cf281c73e5573b8b2bca1d8bccf1aa2eb
(Base Sepolia) の実 calldata / receipt logs を固定フィクスチャとして使い、
実 tx と同じ入力でロジックが PASS することを担保する。さらに各 DoD の
反例 (改竄ケース) が FAIL することを確認する。
"""

from __future__ import annotations

import pytest

from app.aave.dod_verifier import (
    DEFAULT_SERVER_KEYS,
    collect_addresses,
    decode_supply_asset,
    decode_supply_onbehalfof,
    evaluate_dod,
    find_mint_recipients,
)

# ── 参照 tx (0xc819...) の実データ ────────────────────────────────
PARTNER = "0x7f93e7D52428A33cA36acD5D7B1C576d5182a0Ff"
USDC = "0xba50cd2a20f6da35d788639e581bca8d0b5d4d5f"
POOL = "0x8bAB6d1b75f19e9eD9fCe8b9BD338844fF79aE27"
ATOKEN = "0x10F1A9D11CDf50041f3f8cB7191CBE2f31750ACC"  # aUSDC (Base Sepolia)
SERVER_KEY = "0x04666D72D4eB21C2336FE360FB20C093Da291016"

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
ZERO_TOPIC = "0x" + "00" * 32

# 実 supply() calldata (selector 617ba037 + asset + amount(1.0 USDC) + onBehalfOf=partner + ref)
REAL_SUPPLY_INPUT = (
    "0x617ba037"
    "000000000000000000000000ba50cd2a20f6da35d788639e581bca8d0b5d4d5f"
    "00000000000000000000000000000000000000000000000000000000000f4240"
    "0000000000000000000000007f93e7d52428a33ca36acd5d7b1c576d5182a0ff"
    "0000000000000000000000000000000000000000000000000000000000000000"
)


def _addr_topic(addr: str) -> str:
    return "0x" + "0" * 24 + addr.lower().replace("0x", "")


def _real_logs() -> list[dict[str, object]]:
    """参照 tx の mint 関連ログ (aToken Transfer from=0x0 → partner) を再現。"""
    return [
        # USDC Transfer partner → aToken (供給原資)
        {
            "address": USDC,
            "topics": [TRANSFER_TOPIC, _addr_topic(PARTNER), _addr_topic(ATOKEN)],
            "data": "0x" + "00" * 28 + "000f4240",
        },
        # aToken mint: Transfer from=0x0 → partner
        {
            "address": ATOKEN,
            "topics": [TRANSFER_TOPIC, ZERO_TOPIC, _addr_topic(PARTNER)],
            "data": "0x" + "00" * 28 + "000f423f",
        },
    ]


# ── decode_supply_onbehalfof ─────────────────────────────────────
def test_decode_onbehalfof_real_tx() -> None:
    assert decode_supply_onbehalfof(REAL_SUPPLY_INPUT) == PARTNER.lower()


def test_decode_asset_real_tx() -> None:
    assert decode_supply_asset(REAL_SUPPLY_INPUT) == USDC.lower()


def test_decode_onbehalfof_rejects_non_supply() -> None:
    # ERC20 approve(0x095ea7b3) は supply ではない
    bad = "0x095ea7b3" + "00" * 64 + "00" * 64
    assert decode_supply_onbehalfof(bad) is None


def test_decode_onbehalfof_rejects_truncated() -> None:
    assert decode_supply_onbehalfof("0x617ba037dead") is None


# ── find_mint_recipients ─────────────────────────────────────────
def test_find_mint_recipients_real() -> None:
    recs = find_mint_recipients(_real_logs(), token_address=ATOKEN)
    assert recs == [PARTNER.lower()]


def test_find_mint_recipients_ignores_non_zero_sender() -> None:
    logs = [
        {
            "address": ATOKEN,
            "topics": [TRANSFER_TOPIC, _addr_topic(PARTNER), _addr_topic(POOL)],
            "data": "0x0",
        }
    ]
    assert find_mint_recipients(logs, token_address=ATOKEN) == []


def test_find_mint_recipients_token_filter() -> None:
    # 別 contract の mint は aToken 指定で除外される
    recs = find_mint_recipients(_real_logs(), token_address=USDC)
    assert recs == []


# ── collect_addresses ────────────────────────────────────────────
def test_collect_addresses_includes_from_and_log_addrs() -> None:
    addrs = collect_addresses(PARTNER, _real_logs())
    assert PARTNER.lower() in addrs
    assert ATOKEN.lower() in addrs
    assert USDC.lower() in addrs


# ── evaluate_dod: 参照 tx は ALL PASS ────────────────────────────
def test_evaluate_dod_reference_tx_all_pass() -> None:
    result = evaluate_dod(
        tx_from=PARTNER,
        tx_input=REAL_SUPPLY_INPUT,
        logs=_real_logs(),
        partner_wallet=PARTNER,
        atoken_address=ATOKEN,
    )
    assert result.passed, [(c.name, c.detail) for c in result.checks if not c.passed]
    names = {c.name for c in result.checks}
    assert names == {
        "DoD1_from",
        "DoD2_onBehalfOf",
        "DoD3_aUSDC_mint",
        "DoD4_server_key_absent",
    }


def test_evaluate_dod_from_session_key_passes() -> None:
    session = "0xAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAa"
    result = evaluate_dod(
        tx_from=session,
        tx_input=REAL_SUPPLY_INPUT,
        logs=_real_logs(),
        partner_wallet=PARTNER,
        session_keys=[session],
        atoken_address=ATOKEN,
    )
    assert result.passed
    d1 = next(c for c in result.checks if c.name == "DoD1_from")
    assert "session_key" in d1.detail


# ── evaluate_dod: 各 DoD の反例は FAIL ──────────────────────────
def test_dod1_fail_unknown_from() -> None:
    result = evaluate_dod(
        tx_from="0x9999999999999999999999999999999999999999",
        tx_input=REAL_SUPPLY_INPUT,
        logs=_real_logs(),
        partner_wallet=PARTNER,
        atoken_address=ATOKEN,
    )
    assert not result.passed
    d1 = next(c for c in result.checks if c.name == "DoD1_from")
    assert not d1.passed


def test_dod2_fail_onbehalfof_mismatch() -> None:
    other = "0x1111111111111111111111111111111111111111"
    bad_input = (
        "0x617ba037"
        "000000000000000000000000ba50cd2a20f6da35d788639e581bca8d0b5d4d5f"
        "00000000000000000000000000000000000000000000000000000000000f4240"
        + _addr_topic(other)[2:]
        + "00" * 32
    )
    result = evaluate_dod(
        tx_from=PARTNER,
        tx_input=bad_input,
        logs=_real_logs(),
        partner_wallet=PARTNER,
        atoken_address=ATOKEN,
    )
    d2 = next(c for c in result.checks if c.name == "DoD2_onBehalfOf")
    assert not d2.passed
    assert not result.passed


def test_dod3_fail_mint_to_other() -> None:
    other = "0x2222222222222222222222222222222222222222"
    logs = [
        {
            "address": ATOKEN,
            "topics": [TRANSFER_TOPIC, ZERO_TOPIC, _addr_topic(other)],
            "data": "0x0",
        }
    ]
    result = evaluate_dod(
        tx_from=PARTNER,
        tx_input=REAL_SUPPLY_INPUT,
        logs=logs,
        partner_wallet=PARTNER,
        atoken_address=ATOKEN,
    )
    d3 = next(c for c in result.checks if c.name == "DoD3_aUSDC_mint")
    assert not d3.passed


def test_dod4_fail_server_key_present_as_from() -> None:
    """致命ケース: サーバー鍵が from に出現 (= custodial 事故) → DoD4 FAIL。"""
    result = evaluate_dod(
        tx_from=SERVER_KEY,
        tx_input=REAL_SUPPLY_INPUT,
        logs=_real_logs(),
        partner_wallet=PARTNER,
        session_keys=[SERVER_KEY],  # 仮に session 登録されていても DoD4 で落とす
        atoken_address=ATOKEN,
    )
    d4 = next(c for c in result.checks if c.name == "DoD4_server_key_absent")
    assert not d4.passed
    assert SERVER_KEY.lower() in d4.detail.lower()
    assert not result.passed


def test_dod4_fail_server_key_in_logs() -> None:
    """サーバー鍵が internal transfer の relay 先として log に出現 → DoD4 FAIL。"""
    logs = _real_logs() + [
        {
            "address": USDC,
            "topics": [TRANSFER_TOPIC, _addr_topic(PARTNER), _addr_topic(SERVER_KEY)],
            "data": "0x0",
        }
    ]
    result = evaluate_dod(
        tx_from=PARTNER,
        tx_input=REAL_SUPPLY_INPUT,
        logs=logs,
        partner_wallet=PARTNER,
        atoken_address=ATOKEN,
    )
    d4 = next(c for c in result.checks if c.name == "DoD4_server_key_absent")
    assert not d4.passed


def test_default_server_keys_constant() -> None:
    assert SERVER_KEY in DEFAULT_SERVER_KEYS


@pytest.mark.parametrize("status_from", [PARTNER, PARTNER.lower(), PARTNER.upper()])
def test_evaluate_dod_case_insensitive_from(status_from: str) -> None:
    result = evaluate_dod(
        tx_from=status_from,
        tx_input=REAL_SUPPLY_INPUT,
        logs=_real_logs(),
        partner_wallet=PARTNER,
        atoken_address=ATOKEN,
    )
    assert result.passed
