# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_userop_verify.py
"""verify_userop_receipt（ERC-4337 UserOp receipt 検証 / スライス2）の単体テスト。

bundler JSON-RPC は rpc_call 注入でモックし、ネットワーク・sleep に依存しない。
設計: docs/privy-aa-paymaster-design.md §6.2 スライス2。
"""

from typing import Any, Optional

import pytest

import app.proposals.userop_verify as uv
from app.proposals.userop_verify import UserOpVerificationError, verify_userop_receipt

SENDER = "0x23e5A23b935C6c23d2Ff3A427d37eD80114239f2"
HASH = "0x" + "a" * 64


def _resp(result: Optional[dict] = None, error: Optional[dict] = None) -> dict[str, Any]:
    if error is not None:
        return {"error": error}
    return {"result": result}


def _ok_result(success: bool = True, sender: str = SENDER) -> dict[str, Any]:
    return {
        "success": success,
        "sender": sender,
        "actualGasCost": "0x1234",
        "userOpHash": HASH,
    }


def test_success_returns_result() -> None:
    calls: list[tuple[str, list]] = []

    def rpc(method: str, params: list) -> dict:
        calls.append((method, params))
        return _resp(result=_ok_result())

    out = verify_userop_receipt(HASH, SENDER, "http://bundler", rpc_call=rpc)
    assert out["success"] is True
    assert calls[0][0] == "eth_getUserOperationReceipt"
    assert calls[0][1] == [HASH]


def test_revert_raises() -> None:
    def rpc(method: str, params: list) -> dict:
        return _resp(result=_ok_result(success=False))

    with pytest.raises(UserOpVerificationError):
        verify_userop_receipt(HASH, SENDER, "u", rpc_call=rpc)


def test_sender_mismatch_raises() -> None:
    def rpc(method: str, params: list) -> dict:
        return _resp(result=_ok_result(sender="0x" + "0" * 40))

    with pytest.raises(UserOpVerificationError):
        verify_userop_receipt(HASH, SENDER, "u", rpc_call=rpc)


def test_sender_case_insensitive_match() -> None:
    def rpc(method: str, params: list) -> dict:
        return _resp(result=_ok_result(sender=SENDER.lower()))

    out = verify_userop_receipt(HASH, SENDER.upper(), "u", rpc_call=rpc)
    assert out["success"] is True


def test_bundler_error_raises() -> None:
    def rpc(method: str, params: list) -> dict:
        return _resp(error={"code": -32000, "message": "boom"})

    with pytest.raises(UserOpVerificationError):
        verify_userop_receipt(HASH, SENDER, "u", rpc_call=rpc)


def test_pending_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(uv.time, "sleep", lambda _s: None)
    seq = iter([_resp(result=None), _resp(result=None), _resp(result=_ok_result())])

    def rpc(method: str, params: list) -> dict:
        return next(seq)

    out = verify_userop_receipt(HASH, SENDER, "u", rpc_call=rpc, poll_interval=0.01, max_wait=10.0)
    assert out["success"] is True


def test_pending_timeout_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(uv.time, "sleep", lambda _s: None)

    def rpc(method: str, params: list) -> dict:
        return _resp(result=None)  # 常に pending

    with pytest.raises(UserOpVerificationError):
        verify_userop_receipt(HASH, SENDER, "u", rpc_call=rpc, poll_interval=0.01, max_wait=0.05)


def test_userop_verification_error_is_valueerror() -> None:
    # 既存 submit-tx の except(ValueError → 400/422) 経路と互換であること。
    assert issubclass(UserOpVerificationError, ValueError)
