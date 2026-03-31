# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_gas_estimator.py
"""GasEstimator のユニットテスト。"""

from decimal import Decimal
from unittest.mock import MagicMock

from app.aave.gas_estimator import (
    DEFAULT_FALLBACK_GAS_APPROVE,
    ETH_USD_FALLBACK_PRICE,
    GasEstimator,
)


class TestEstimateGasWithBuffer:
    def test_returns_estimated_with_buffer(self) -> None:
        """見積もり値の1.2倍が返ること"""
        mock_w3 = MagicMock()
        mock_w3.eth.estimate_gas.return_value = 100000
        estimator = GasEstimator(mock_w3)
        result = estimator.estimate_gas_with_buffer({}, fallback_gas=50000)
        assert result == 120000  # 100000 * 1.2

    def test_fallback_on_estimate_failure(self) -> None:
        """estimate_gas 失敗時にフォールバック値を返すこと"""
        mock_w3 = MagicMock()
        mock_w3.eth.estimate_gas.side_effect = Exception("RPC error")
        estimator = GasEstimator(mock_w3)
        result = estimator.estimate_gas_with_buffer({}, fallback_gas=DEFAULT_FALLBACK_GAS_APPROVE)
        assert result == DEFAULT_FALLBACK_GAS_APPROVE

    def test_buffer_multiplier_decimal_precision(self) -> None:
        """Decimal精度の確認（float禁止）"""
        mock_w3 = MagicMock()
        mock_w3.eth.estimate_gas.return_value = 83333
        estimator = GasEstimator(mock_w3)
        result = estimator.estimate_gas_with_buffer({}, fallback_gas=100000)
        assert result == int(Decimal("83333") * Decimal("1.20"))


class TestGasCostUsd:
    def test_gas_cost_usd_calculation(self) -> None:
        """wei → ETH → USD の換算が正しいこと"""
        mock_w3 = MagicMock()
        # gas_price = 20 Gwei = 20e9 wei
        mock_w3.eth.gas_price = 20_000_000_000
        estimator = GasEstimator(mock_w3)
        # 100000 gas * 20 Gwei = 0.002 ETH
        # 0.002 ETH * $2000/ETH = $4.00
        cost = estimator.estimate_gas_cost_usd(100000, eth_usd_price=Decimal("2000.00"))
        assert cost == Decimal("4.000000000000000000")  # exact Decimal

    def test_uses_fallback_price_when_none(self) -> None:
        """eth_usd_price=None のとき ETH_USD_FALLBACK_PRICE を使うこと"""
        mock_w3 = MagicMock()
        mock_w3.eth.gas_price = 10_000_000_000  # 10 Gwei
        estimator = GasEstimator(mock_w3)
        cost_with_none = estimator.estimate_gas_cost_usd(50000, eth_usd_price=None)
        cost_with_fallback = estimator.estimate_gas_cost_usd(
            50000, eth_usd_price=ETH_USD_FALLBACK_PRICE
        )
        assert cost_with_none == cost_with_fallback


class TestGasCostAcceptable:
    def test_acceptable_cost(self) -> None:
        """ガスコストが上限以下なら True"""
        mock_w3 = MagicMock()
        mock_w3.eth.gas_price = 1_000_000_000  # 1 Gwei（安い）
        estimator = GasEstimator(mock_w3)
        # 100000 gas * 1 Gwei = 1e-7 ETH = very cheap
        assert estimator.is_gas_cost_acceptable(100000, eth_usd_price=Decimal("2000.00")) is True

    def test_max_gas_cap_rejection(self) -> None:
        """上限超過時に False を返すこと"""
        mock_w3 = MagicMock()
        # 非常に高いガス代を設定（上限 $50 を超える）
        mock_w3.eth.gas_price = 500_000_000_000  # 500 Gwei
        estimator = GasEstimator(mock_w3)
        # 300000 gas * 500 Gwei = 0.15 ETH * $4000 = $600 > $50
        assert estimator.is_gas_cost_acceptable(300000, eth_usd_price=Decimal("4000.00")) is False


class TestIsProfitable:
    def test_profitable_when_benefit_exceeds_cost(self) -> None:
        mock_w3 = MagicMock()
        estimator = GasEstimator(mock_w3)
        assert (
            estimator.is_profitable(
                gas_cost_usd=Decimal("5.00"),
                expected_benefit_usd=Decimal("10.00"),
            )
            is True
        )

    def test_not_profitable_when_cost_exceeds_benefit(self) -> None:
        mock_w3 = MagicMock()
        estimator = GasEstimator(mock_w3)
        assert (
            estimator.is_profitable(
                gas_cost_usd=Decimal("15.00"),
                expected_benefit_usd=Decimal("5.00"),
            )
            is False
        )

    def test_not_profitable_when_equal(self) -> None:
        mock_w3 = MagicMock()
        estimator = GasEstimator(mock_w3)
        assert (
            estimator.is_profitable(
                gas_cost_usd=Decimal("10.00"),
                expected_benefit_usd=Decimal("10.00"),
            )
            is False
        )
