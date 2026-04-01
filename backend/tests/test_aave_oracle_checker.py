# Copyright (c) Ultra AutoTrade. All rights reserved.
"""
Tests for Aave V3 oracle staleness and circuit breaker checks.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch


def _make_round_data(updated_at_ts: int, answer: int = 200000000000) -> tuple:  # type: ignore[type-arg]
    # (roundId, answer, startedAt, updatedAt, answeredInRound)
    return (1, answer, updated_at_ts, updated_at_ts, 1)


def _make_web3_mock(round_data: tuple) -> MagicMock:  # type: ignore[type-arg]
    mock_web3_module = MagicMock()
    mock_w3 = MagicMock()
    mock_contract = MagicMock()

    mock_web3_module.Web3.return_value = mock_w3
    mock_web3_module.Web3.HTTPProvider = MagicMock()
    mock_web3_module.Web3.to_checksum_address = lambda x: x
    mock_w3.eth.contract.return_value = mock_contract
    mock_contract.functions.latestRoundData.return_value.call.return_value = round_data

    return mock_web3_module


class TestCheckOracleStaleness:
    """Tests for check_oracle_staleness()."""

    def test_fresh_oracle_no_hold(self) -> None:
        from app.aave.oracle_checker import check_oracle_staleness

        # 10 minutes ago — fresh
        now_ts = int(datetime.now(timezone.utc).timestamp())
        updated_ts = now_ts - 600
        mock_mod = _make_web3_mock(_make_round_data(updated_ts))

        with patch.dict(sys.modules, {"web3": mock_mod}):
            result = check_oracle_staleness(
                feed_address="0xFEED",
                rpc_url="http://localhost:8545",
                staleness_threshold_seconds=3600,
            )

        assert result is not None
        assert result.is_stale is False
        assert result.should_hold is False
        assert result.reasons == []

    def test_stale_oracle_triggers_hold(self) -> None:
        from app.aave.oracle_checker import check_oracle_staleness

        # 2 hours ago — stale (threshold: 1 hour)
        now_ts = int(datetime.now(timezone.utc).timestamp())
        updated_ts = now_ts - 7200
        mock_mod = _make_web3_mock(_make_round_data(updated_ts))

        with patch.dict(sys.modules, {"web3": mock_mod}):
            result = check_oracle_staleness(
                feed_address="0xFEED",
                rpc_url="http://localhost:8545",
                staleness_threshold_seconds=3600,
            )

        assert result is not None
        assert result.is_stale is True
        assert result.should_hold is True
        assert len(result.reasons) > 0

    def test_circuit_breaker_large_deviation(self) -> None:
        from app.aave.oracle_checker import check_oracle_staleness

        # Price is 2000 USD (200000000000 / 10^8 = 2000)
        now_ts = int(datetime.now(timezone.utc).timestamp())
        updated_ts = now_ts - 60  # fresh
        mock_mod = _make_web3_mock(_make_round_data(updated_ts, answer=200000000000))

        with patch.dict(sys.modules, {"web3": mock_mod}):
            result = check_oracle_staleness(
                feed_address="0xFEED",
                rpc_url="http://localhost:8545",
                staleness_threshold_seconds=3600,
                deviation_threshold_pct=Decimal("10"),
                previous_price=Decimal("1000"),  # 100% deviation
            )

        assert result is not None
        assert result.is_circuit_breaker is True
        assert result.should_hold is True

    def test_no_circuit_breaker_small_deviation(self) -> None:
        from app.aave.oracle_checker import check_oracle_staleness

        # Price is 2000, previous is 1990 (0.5% deviation)
        now_ts = int(datetime.now(timezone.utc).timestamp())
        updated_ts = now_ts - 60
        mock_mod = _make_web3_mock(_make_round_data(updated_ts, answer=200000000000))

        with patch.dict(sys.modules, {"web3": mock_mod}):
            result = check_oracle_staleness(
                feed_address="0xFEED",
                rpc_url="http://localhost:8545",
                staleness_threshold_seconds=3600,
                deviation_threshold_pct=Decimal("10"),
                previous_price=Decimal("1990"),
            )

        assert result is not None
        assert result.is_circuit_breaker is False
        assert result.should_hold is False

    def test_web3_not_installed_returns_none(self) -> None:
        from app.aave.oracle_checker import check_oracle_staleness

        with patch.dict(sys.modules, {"web3": None}):  # type: ignore[dict-item]
            result = check_oracle_staleness(
                feed_address="0xFEED",
                rpc_url="http://localhost:8545",
            )
        assert result is None

    def test_rpc_failure_returns_none(self) -> None:
        from app.aave.oracle_checker import check_oracle_staleness

        mock_web3_module = MagicMock()
        mock_w3 = MagicMock()
        mock_contract = MagicMock()
        mock_web3_module.Web3.return_value = mock_w3
        mock_web3_module.Web3.HTTPProvider = MagicMock()
        mock_web3_module.Web3.to_checksum_address = lambda x: x
        mock_w3.eth.contract.return_value = mock_contract
        mock_contract.functions.latestRoundData.return_value.call.side_effect = Exception(
            "connection refused"
        )

        with patch.dict(sys.modules, {"web3": mock_web3_module}):
            result = check_oracle_staleness(
                feed_address="0xFEED",
                rpc_url="http://localhost:8545",
            )
        assert result is None

    def test_price_calculated_correctly(self) -> None:
        from app.aave.oracle_checker import check_oracle_staleness

        # answer=300000000000 → 3000.00 USD
        now_ts = int(datetime.now(timezone.utc).timestamp())
        updated_ts = now_ts - 60
        mock_mod = _make_web3_mock(_make_round_data(updated_ts, answer=300000000000))

        with patch.dict(sys.modules, {"web3": mock_mod}):
            result = check_oracle_staleness(
                feed_address="0xFEED",
                rpc_url="http://localhost:8545",
                staleness_threshold_seconds=3600,
            )

        assert result is not None
        assert result.price == Decimal("3000")

    def test_age_seconds_calculated(self) -> None:
        from app.aave.oracle_checker import check_oracle_staleness

        now_ts = int(datetime.now(timezone.utc).timestamp())
        updated_ts = now_ts - 300  # 5 minutes ago
        mock_mod = _make_web3_mock(_make_round_data(updated_ts))

        with patch.dict(sys.modules, {"web3": mock_mod}):
            result = check_oracle_staleness(
                feed_address="0xFEED",
                rpc_url="http://localhost:8545",
                staleness_threshold_seconds=3600,
            )

        assert result is not None
        assert result.age_seconds is not None
        assert 290 <= result.age_seconds <= 310  # Allow small clock drift


class TestCheckSequencerUptime:
    """Tests for check_sequencer_uptime()."""

    def test_sequencer_up_returns_true(self) -> None:
        from app.aave.oracle_checker import check_sequencer_uptime

        now_ts = int(datetime.now(timezone.utc).timestamp())
        # answer=0 = UP, startedAt (index 2) = ignored, started_at_ts (index 3) = 2 hours ago
        # (past grace period)
        started_at = now_ts - 7200
        round_data = (1, 0, now_ts, started_at, 1)
        mock_mod = _make_web3_mock(round_data)

        with patch.dict(sys.modules, {"web3": mock_mod}):
            result = check_sequencer_uptime(
                sequencer_feed_address="0xSEQ",
                rpc_url="http://localhost:8545",
            )
        assert result is True

    def test_sequencer_down_returns_false(self) -> None:
        from app.aave.oracle_checker import check_sequencer_uptime

        now_ts = int(datetime.now(timezone.utc).timestamp())
        # answer=1 = DOWN; started_at_ts does not matter since answer != 0 early-exits
        round_data = (1, 1, now_ts, now_ts - 7200, 1)
        mock_mod = _make_web3_mock(round_data)

        with patch.dict(sys.modules, {"web3": mock_mod}):
            result = check_sequencer_uptime(
                sequencer_feed_address="0xSEQ",
                rpc_url="http://localhost:8545",
            )
        assert result is False

    def test_sequencer_in_grace_period_returns_false(self) -> None:
        from app.aave.oracle_checker import check_sequencer_uptime

        now_ts = int(datetime.now(timezone.utc).timestamp())
        # answer=0 = UP, started_at_ts (index 3) = 30 mins ago (within grace period)
        started_at = now_ts - 1800
        round_data = (1, 0, now_ts, started_at, 1)
        mock_mod = _make_web3_mock(round_data)

        with patch.dict(sys.modules, {"web3": mock_mod}):
            result = check_sequencer_uptime(
                sequencer_feed_address="0xSEQ",
                rpc_url="http://localhost:8545",
            )
        assert result is False

    def test_web3_not_installed_fail_open(self) -> None:
        from app.aave.oracle_checker import check_sequencer_uptime

        with patch.dict(sys.modules, {"web3": None}):  # type: ignore[dict-item]
            result = check_sequencer_uptime(
                sequencer_feed_address="0xSEQ",
                rpc_url="http://localhost:8545",
            )
        # fail-open: returns True
        assert result is True

    def test_rpc_failure_fail_open(self) -> None:
        from app.aave.oracle_checker import check_sequencer_uptime

        mock_web3_module = MagicMock()
        mock_w3 = MagicMock()
        mock_contract = MagicMock()
        mock_web3_module.Web3.return_value = mock_w3
        mock_web3_module.Web3.HTTPProvider = MagicMock()
        mock_web3_module.Web3.to_checksum_address = lambda x: x
        mock_w3.eth.contract.return_value = mock_contract
        mock_contract.functions.latestRoundData.return_value.call.side_effect = Exception(
            "timeout"
        )

        with patch.dict(sys.modules, {"web3": mock_web3_module}):
            result = check_sequencer_uptime(
                sequencer_feed_address="0xSEQ",
                rpc_url="http://localhost:8545",
            )
        # fail-open
        assert result is True
