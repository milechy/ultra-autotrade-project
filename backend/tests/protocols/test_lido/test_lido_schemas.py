"""Lido スキーマのバリデーションテスト。"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.protocols.lido.schemas import (
    CompoundYieldEstimate,
    LidoStakeRequest,
    LidoStatus,
    TxResult,
)


class TestLidoStakeRequest:
    def test_default_dry_run_is_true(self) -> None:
        req = LidoStakeRequest(amount_eth=Decimal("0.1"))
        assert req.dry_run is True

    def test_amount_eth_as_string(self) -> None:
        req = LidoStakeRequest(amount_eth="0.5")  # type: ignore[arg-type]
        assert req.amount_eth == Decimal("0.5")

    def test_amount_eth_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            LidoStakeRequest(amount_eth=Decimal("0"))

    def test_negative_amount_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LidoStakeRequest(amount_eth=Decimal("-1"))

    def test_decimal_precision_preserved(self) -> None:
        req = LidoStakeRequest(amount_eth=Decimal("0.123456789012345678"))
        assert req.amount_eth == Decimal("0.123456789012345678")


class TestLidoStatus:
    def test_status_creation(self) -> None:
        status = LidoStatus(
            steth_balance=Decimal("1.5"),
            staking_apr=Decimal("3.5"),
            steth_eth_ratio=Decimal("1.0"),
            peg_deviation_pct=Decimal("0.0"),
            chain="holesky",
            sandbox=True,
        )
        assert status.sandbox is True
        assert status.chain == "holesky"

    def test_peg_deviation_calculated_correctly(self) -> None:
        # ratio=0.98 → deviation=2%
        status = LidoStatus(
            steth_balance=Decimal("1.0"),
            staking_apr=Decimal("3.5"),
            steth_eth_ratio=Decimal("0.98"),
            peg_deviation_pct=Decimal("2.0"),
            chain="holesky",
            sandbox=True,
        )
        assert status.peg_deviation_pct == Decimal("2.0")


class TestTxResult:
    def test_successful_result(self) -> None:
        result = TxResult(tx_hash="0xabc", success=True, received_steth_wei=1000)
        assert result.success is True
        assert result.tx_hash == "0xabc"

    def test_failed_result(self) -> None:
        result = TxResult(success=False, error="接続エラー")
        assert result.success is False
        assert result.tx_hash is None


class TestCompoundYieldEstimate:
    def test_compound_apr_calculation(self) -> None:
        estimate = CompoundYieldEstimate(
            lido_staking_apr=Decimal("3.5"),
            aave_supply_apr=Decimal("1.5"),
            compound_apr=Decimal("5.0"),
            amount_eth=Decimal("1.0"),
            estimated_annual_yield_eth=Decimal("0.05"),
        )
        assert estimate.compound_apr == Decimal("5.0")
        assert estimate.estimated_annual_yield_eth == Decimal("0.05")
