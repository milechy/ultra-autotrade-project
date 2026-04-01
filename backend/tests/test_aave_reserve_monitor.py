# Copyright (c) Ultra AutoTrade. All rights reserved.
"""
Tests for Aave V3 reserve pause/freeze/cap monitoring.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch


class TestCheckReserveStatus:
    """Tests for check_reserve_status()."""

    def _run(
        self,
        config_data: tuple,  # type: ignore[type-arg]
        get_paused_result: bool = False,
        caps_result: tuple = (0, 0),  # type: ignore[type-arg]
    ) -> "ReserveStatus":  # noqa: F821
        from app.aave.reserve_monitor import check_reserve_status

        mock_web3_module = MagicMock()
        mock_w3 = MagicMock()
        mock_contract = MagicMock()

        mock_web3_module.Web3.return_value = mock_w3
        mock_web3_module.Web3.HTTPProvider = MagicMock()
        mock_web3_module.Web3.to_checksum_address = lambda x: x

        mock_w3.eth.contract.return_value = mock_contract
        mock_contract.functions.getReserveConfigurationData.return_value.call.return_value = (
            config_data
        )
        mock_contract.functions.getPaused.return_value.call.return_value = get_paused_result
        mock_contract.functions.getReserveCaps.return_value.call.return_value = caps_result

        with patch.dict(sys.modules, {"web3": mock_web3_module}):
            result = check_reserve_status(
                chain_name="polygon",
                asset_address="0xABC",
                data_provider_address="0xDEF",
                rpc_url="http://localhost:8545",
            )
        return result  # type: ignore[return-value]

    def _make_config_data(
        self,
        *,
        borrowing_enabled: bool = True,
        is_active: bool = True,
        is_frozen: bool = False,
    ) -> tuple:  # type: ignore[type-arg]
        # (decimals, ltv, liqThreshold, liqBonus, reserveFactor,
        #  collateralEnabled, borrowingEnabled, stableBorrow, isActive, isFrozen)
        return (18, 7500, 8000, 10500, 1000, True, borrowing_enabled, False, is_active, is_frozen)

    def test_normal_reserve_no_alert(self) -> None:
        result = self._run(self._make_config_data())
        assert result is not None
        assert result.alert is False
        assert result.alert_reasons == []
        assert result.is_active is True
        assert result.is_frozen is False
        assert result.is_paused is False

    def test_paused_reserve_triggers_alert(self) -> None:
        result = self._run(self._make_config_data(), get_paused_result=True)
        assert result is not None
        assert result.alert is True
        assert "reserve is PAUSED" in result.alert_reasons

    def test_frozen_reserve_triggers_alert(self) -> None:
        result = self._run(self._make_config_data(is_frozen=True))
        assert result is not None
        assert result.alert is True
        assert "reserve is FROZEN" in result.alert_reasons

    def test_inactive_reserve_triggers_alert(self) -> None:
        result = self._run(self._make_config_data(is_active=False))
        assert result is not None
        assert result.alert is True
        assert "reserve is INACTIVE" in result.alert_reasons

    def test_multiple_anomalies(self) -> None:
        result = self._run(self._make_config_data(is_frozen=True, is_active=False))
        assert result is not None
        assert result.alert is True
        assert len(result.alert_reasons) == 2

    def test_caps_set(self) -> None:
        result = self._run(self._make_config_data(), caps_result=(1000, 5000))
        assert result is not None
        assert result.borrow_cap == 1000
        assert result.supply_cap == 5000

    def test_web3_not_installed_returns_none(self) -> None:
        from app.aave.reserve_monitor import check_reserve_status

        with patch.dict(sys.modules, {"web3": None}):  # type: ignore[dict-item]
            result = check_reserve_status(
                chain_name="polygon",
                asset_address="0xABC",
                data_provider_address="0xDEF",
                rpc_url="http://localhost:8545",
            )
        assert result is None

    def test_rpc_failure_returns_none(self) -> None:
        from app.aave.reserve_monitor import check_reserve_status

        mock_web3_module = MagicMock()
        mock_w3 = MagicMock()
        mock_contract = MagicMock()

        mock_web3_module.Web3.return_value = mock_w3
        mock_web3_module.Web3.HTTPProvider = MagicMock()
        mock_web3_module.Web3.to_checksum_address = lambda x: x
        mock_w3.eth.contract.return_value = mock_contract
        mock_contract.functions.getReserveConfigurationData.return_value.call.side_effect = (
            Exception("RPC error")
        )

        with patch.dict(sys.modules, {"web3": mock_web3_module}):
            result = check_reserve_status(
                chain_name="polygon",
                asset_address="0xABC",
                data_provider_address="0xDEF",
                rpc_url="http://localhost:8545",
            )
        assert result is None

    def test_chain_name_stored(self) -> None:
        result = self._run(self._make_config_data())
        assert result is not None
        assert result.chain_name == "polygon"
