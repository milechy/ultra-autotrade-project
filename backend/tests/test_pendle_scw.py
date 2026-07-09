# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_pendle_scw.py
"""[Phase D / D3] build_pendle_swap_calls — Pendle swap を ERC-5792 calls に変換。

approve → swap の順で ``{to,value,data}`` を生成し、approve calldata が正しく ABI エンコード
されること、spender≠Router / 欠損は fail-closed になることを検証する（broadcast しない）。
"""

import pytest
from web3 import Web3

from app.proposals.pendle_scw import PendleScwCallsError, build_pendle_swap_calls
from app.protocols.pendle.schemas import RouterV4Approval, RouterV4SwapResult

_ROUTER = "0x888888888889758F76e7103c6CbF23ABbF58F946"
_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
_SWAP_DATA = "0x" + "de" * 120
# approve(address,uint256) セレクタ
_APPROVE_SELECTOR = "0x095ea7b3"


def _result(**overrides: object) -> RouterV4SwapResult:
    base: dict[str, object] = {
        "success": True,
        "to": _ROUTER,
        "calldata": _SWAP_DATA,
        "approvals": [RouterV4Approval(token=_USDC, spender=_ROUTER, amount="100000000")],
    }
    base.update(overrides)
    return RouterV4SwapResult(**base)  # type: ignore[arg-type]


def test_builds_approve_then_swap() -> None:
    calls = build_pendle_swap_calls(_result())
    assert len(calls) == 2
    approve_call, swap_call = calls

    # approve は USDC 宛・approve セレクタ・value 0。
    assert approve_call["to"] == Web3.to_checksum_address(_USDC)
    assert approve_call["value"] == "0x0"
    assert approve_call["data"].startswith(_APPROVE_SELECTOR)
    # spender(Router) と amount(100000000) が calldata に埋まっている。
    assert _ROUTER.lower()[2:] in approve_call["data"].lower()
    assert hex(100000000)[2:] in approve_call["data"].lower()

    # swap は Router 宛・SDK calldata そのまま。
    assert swap_call["to"] == Web3.to_checksum_address(_ROUTER)
    assert swap_call["value"] == "0x0"
    assert swap_call["data"] == _SWAP_DATA


def test_no_approvals_only_swap() -> None:
    """approvals が空でも swap 単体は組む（既に approve 済みのケース）。"""
    calls = build_pendle_swap_calls(_result(approvals=[]))
    assert len(calls) == 1
    assert calls[0]["to"] == Web3.to_checksum_address(_ROUTER)


def test_fail_when_result_unsuccessful() -> None:
    with pytest.raises(PendleScwCallsError):
        build_pendle_swap_calls(_result(success=False, error="boom"))


def test_fail_when_missing_to() -> None:
    with pytest.raises(PendleScwCallsError):
        build_pendle_swap_calls(_result(to=None))


def test_fail_when_missing_calldata() -> None:
    with pytest.raises(PendleScwCallsError):
        build_pendle_swap_calls(_result(calldata=""))


def test_fail_when_spender_not_router() -> None:
    """approve の spender が swap 宛先 Router と異なる → 任意コントラクト approve を拒否。"""
    bad = RouterV4Approval(
        token=_USDC, spender="0x00000000000000000000000000000000deadbeef", amount="1"
    )
    with pytest.raises(PendleScwCallsError):
        build_pendle_swap_calls(_result(approvals=[bad]))


def test_fail_when_approval_amount_missing() -> None:
    bad = RouterV4Approval(token=_USDC, spender=_ROUTER, amount=None)
    with pytest.raises(PendleScwCallsError):
        build_pendle_swap_calls(_result(approvals=[bad]))
