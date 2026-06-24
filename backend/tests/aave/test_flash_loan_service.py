# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/aave/test_flash_loan_service.py
"""FlashLoanSelfLiquidator（executor サービス層）の単体テスト（Asana 1215620828227794 第2スライス）。

dry_run=True のみが実装されていること、HF 読み取りに副作用がない（write 系メソッド未呼び出し）こと、
fail-closed 経路、Decimal 型保持、trigger_hf 注入による発動境界を検証する。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

import pytest

from app.aave.client import AaveClientBase, AccountData, DummyAaveClient
from app.aave.flash_loan_service import FlashLoanSelfLiquidator


class _StubAaveClient(AaveClientBase):
    """get_account_data だけを差し替えるテスト用 stub。

    write 系メソッド（deposit/withdraw/borrow/repay 相当）が呼ばれたら即座に失敗させ、
    HF 読み取りに副作用がないことを保証する。
    """

    def __init__(self, account: AccountData) -> None:
        self._account = account
        self.write_calls: list[str] = []

    def get_account_data(self, wallet_address: str) -> AccountData:
        return self._account

    # --- read-only: HF だけは別経路でも提供する（呼ばれても副作用なし） ---
    def get_health_factor(self, wallet_address: str = "") -> Decimal:
        return self._account.health_factor

    def get_user_emode(self, wallet_address: str) -> int:
        return 0

    # --- write 系: 呼ばれてはならない ---
    def deposit(
        self,
        asset_address: str,
        amount: Decimal,
        wallet_address: str,
        private_key: str,
        dry_run: bool = False,
    ) -> dict:
        self.write_calls.append("deposit")
        raise AssertionError("deposit must not be called by self-liquidation read path")

    def withdraw(
        self,
        asset_address: str,
        amount: Decimal,
        wallet_address: str,
        private_key: str,
        dry_run: bool = False,
    ) -> dict:
        self.write_calls.append("withdraw")
        raise AssertionError("withdraw must not be called by self-liquidation read path")

    def build_set_emode_tx(
        self, category_id: int, wallet_address: str, dry_run: bool = False
    ) -> dict:
        self.write_calls.append("build_set_emode_tx")
        raise AssertionError("build_set_emode_tx must not be called")


def _account(
    *,
    collateral: str,
    debt: str,
    hf: str,
    lt: Optional[str] = "0.80",
) -> AccountData:
    return AccountData(
        total_collateral_usd=Decimal(collateral),
        total_debt_usd=Decimal(debt),
        available_borrows_usd=Decimal("0"),
        health_factor=Decimal(hf),
        liquidation_threshold=Decimal(lt) if lt is not None else None,
    )


_WALLET = "0xWALLET"


def test_dry_run_low_hf_executes_simulation() -> None:
    """HF=1.1 → dry_run=True で executed=True / tx_hash None / quote.feasible。"""
    # collateral=10000, debt=7273, lt=0.80 → HF ≈ 1.1
    client = _StubAaveClient(_account(collateral="10000", debt="7273", hf="1.1"))
    sut = FlashLoanSelfLiquidator(client)

    result = sut.execute_self_liquidation(_WALLET, dry_run=True)

    assert result.executed is True
    assert result.dry_run is True
    assert result.tx_hash is None
    assert result.quote is not None
    assert result.quote.feasible is True
    assert result.reason == "dry-run: flash loan deleverage simulated"
    assert client.write_calls == []


def test_safe_hf_no_protection_needed() -> None:
    """DummyAaveClient（HF=2.5）→ executed=False / "no protection needed" / write 未呼び出し。"""
    client = DummyAaveClient()
    sut = FlashLoanSelfLiquidator(client)

    result = sut.execute_self_liquidation(_WALLET, dry_run=True)

    assert result.executed is False
    assert result.tx_hash is None
    assert result.quote is None
    assert "no protection needed" in result.reason
    assert result.before_health_factor == Decimal("2.5")


def test_dry_run_false_raises_not_implemented() -> None:
    """dry_run=False は on-chain 実行スライス未実装のため NotImplementedError。"""
    client = _StubAaveClient(_account(collateral="10000", debt="7273", hf="1.1"))
    sut = FlashLoanSelfLiquidator(client)

    with pytest.raises(NotImplementedError, match="HUMAN-REVIEW"):
        sut.execute_self_liquidation(_WALLET, dry_run=False)

    assert client.write_calls == []


def test_infeasible_quote_propagates_reason() -> None:
    """担保不足で quote.feasible=False → executed=False / quote の reason を継承。"""
    # 担保が債務をほぼ上回らない極端なケース（lt 高・HF 危険域）→ 返済+手数料分の担保を
    # 引き出せず target HF を回復できない（fail-closed）。HF=1.00 < trigger(1.3) で発動経路に入る。
    client = _StubAaveClient(_account(collateral="100", debt="99.99", hf="1.00", lt="0.9999"))
    sut = FlashLoanSelfLiquidator(client)

    result = sut.execute_self_liquidation(_WALLET, dry_run=True)

    assert result.executed is False
    assert result.quote is not None
    assert result.quote.feasible is False
    assert result.reason == result.quote.reason
    assert "insufficient collateral" in result.reason
    assert client.write_calls == []


def test_missing_liquidation_threshold_fails_closed() -> None:
    """liquidation_threshold=None → fail-closed で executed=False。"""
    client = _StubAaveClient(_account(collateral="10000", debt="7273", hf="1.1", lt=None))
    sut = FlashLoanSelfLiquidator(client)

    result = sut.execute_self_liquidation(_WALLET, dry_run=True)

    assert result.executed is False
    assert result.quote is None
    assert result.reason == "liquidation_threshold unavailable"
    assert client.write_calls == []


def test_decimal_types_preserved() -> None:
    """quote.repay_debt_usd / before_health_factor が Decimal 型で保持される。"""
    client = _StubAaveClient(_account(collateral="10000", debt="7273", hf="1.1"))
    sut = FlashLoanSelfLiquidator(client)

    result = sut.execute_self_liquidation(_WALLET, dry_run=True)

    assert result.quote is not None
    assert isinstance(result.quote.repay_debt_usd, Decimal)
    assert isinstance(result.before_health_factor, Decimal)


def test_no_write_side_effects_on_read_path() -> None:
    """発動経路でも write 系（deposit/withdraw/build_set_emode_tx）が呼ばれない。"""
    client = _StubAaveClient(_account(collateral="10000", debt="7273", hf="1.1"))
    sut = FlashLoanSelfLiquidator(client)

    sut.execute_self_liquidation(_WALLET, dry_run=True)

    assert client.write_calls == []


def test_custom_trigger_hf_boundary() -> None:
    """trigger_hf=1.2 注入: HF=1.15 → 発動 / HF=1.25 → 不発火。"""
    # collateral/debt/lt は固定で HF だけ AccountData に明示。
    triggering = _StubAaveClient(_account(collateral="10000", debt="6957", hf="1.15"))
    sut_trigger = FlashLoanSelfLiquidator(triggering, trigger_hf=Decimal("1.2"))
    result_trigger = sut_trigger.execute_self_liquidation(_WALLET, dry_run=True)
    assert result_trigger.executed is True
    assert result_trigger.dry_run is True

    not_triggering = _StubAaveClient(_account(collateral="10000", debt="6400", hf="1.25"))
    sut_safe = FlashLoanSelfLiquidator(not_triggering, trigger_hf=Decimal("1.2"))
    result_safe = sut_safe.execute_self_liquidation(_WALLET, dry_run=True)
    assert result_safe.executed is False
    assert "no protection needed" in result_safe.reason
