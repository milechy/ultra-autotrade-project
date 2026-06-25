# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_proposal_protocol_dispatch.py
"""custodial 自動執行の protocol 振り分け (_dispatch_custodial_execution) のテスト。

[v4][Phase D] proposal.protocol で aave/lido/pendle を振り分ける。Lido/Pendle の
on-chain 実行は HUMAN-REVIEW 未配線のため ProtocolExecutionNotWiredError を送出し、
Aave 経路で誤実行しないことを保証する。
"""

import os
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-proposal-dispatch")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin@example.com")

import app.proposals.router as router_mod  # noqa: E402
from app.proposals.router import (  # noqa: E402
    ProtocolExecutionNotWiredError,
    _dispatch_custodial_execution,
)


def _mk_proposal(protocol: object) -> MagicMock:
    p = MagicMock()
    p.id = 1
    p.protocol = protocol
    p.operation = "SUPPLY"
    return p


def test_dispatch_aave_calls_aave_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, bool] = {}
    monkeypatch.setattr(
        router_mod, "_execute_aave_for_proposal", lambda p, db: called.setdefault("aave", True)
    )
    _dispatch_custodial_execution(_mk_proposal("aave"), MagicMock())
    assert called.get("aave") is True


def test_dispatch_none_protocol_defaults_to_aave(monkeypatch: pytest.MonkeyPatch) -> None:
    """protocol 無指定 (None) は従来どおり Aave 経路 (後方互換)。"""
    called: dict[str, bool] = {}
    monkeypatch.setattr(
        router_mod, "_execute_aave_for_proposal", lambda p, db: called.setdefault("aave", True)
    )
    _dispatch_custodial_execution(_mk_proposal(None), MagicMock())
    assert called.get("aave") is True


def test_dispatch_lido_not_wired_and_does_not_call_aave(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lido は未配線で raise し、Aave 経路を呼ばない (誤実行防止)。"""

    def _must_not_run(p: object, db: object) -> None:
        raise AssertionError("Lido 提案で Aave 経路を実行してはならない")

    monkeypatch.setattr(router_mod, "_execute_aave_for_proposal", _must_not_run)
    with pytest.raises(ProtocolExecutionNotWiredError):
        _dispatch_custodial_execution(_mk_proposal("lido"), MagicMock())


def test_dispatch_pendle_not_wired_and_does_not_call_aave(monkeypatch: pytest.MonkeyPatch) -> None:
    def _must_not_run(p: object, db: object) -> None:
        raise AssertionError("Pendle 提案で Aave 経路を実行してはならない")

    monkeypatch.setattr(router_mod, "_execute_aave_for_proposal", _must_not_run)
    with pytest.raises(ProtocolExecutionNotWiredError):
        _dispatch_custodial_execution(_mk_proposal("pendle"), MagicMock())


def test_dispatch_unknown_protocol_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def _must_not_run(p: object, db: object) -> None:
        raise AssertionError("未知 protocol で Aave 経路を実行してはならない")

    monkeypatch.setattr(router_mod, "_execute_aave_for_proposal", _must_not_run)
    with pytest.raises(ProtocolExecutionNotWiredError):
        _dispatch_custodial_execution(_mk_proposal("compound"), MagicMock())
