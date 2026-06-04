# Copyright (c) Ultra AutoTrade. All rights reserved.
"""
Tests for app.automation.oracle_monitor.OracleMonitor.

監視ロジック単体テスト:
- check_once で feed_results が埋まる
- staleness 検出 + HF 警告域で emergency_stop 自動発火 (AND モード)
- HF 正常域では oracle 異常のみでは発火しない (false positive 抑制)
- extreme staleness は HF に関わらず発火 (fail-safe)
- require_hf_confirmation=False で oracle 異常のみで発火
- RPC 失敗フィードは fetch_failures に積まれて他のフィードは継続処理
- 不正なコンストラクタ引数で ValueError
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, cast
from unittest.mock import MagicMock

import pytest

from app.aave.oracle_checker import OracleCheckResult
from app.automation import oracle_monitor as om_mod
from app.automation.monitoring_service import MonitoringService
from app.automation.oracle_monitor import OracleFeedConfig, OracleMonitor


def _new_monitoring_service() -> MonitoringService:
    return MonitoringService(_internal=True, enable_state_sync=False)


def _feed(name: str = "USDC") -> OracleFeedConfig:
    return OracleFeedConfig(
        name=name,
        feed_address="0x" + name.encode("ascii").hex().ljust(40, "0")[:40],
        rpc_url="http://localhost:8545",
    )


def _stub_result(
    *,
    is_stale: bool = False,
    is_circuit_breaker: bool = False,
    age_seconds: Optional[int] = 60,
    price: Optional[Decimal] = Decimal("1.0"),
    deviation_pct: Optional[Decimal] = None,
    reasons: Optional[List[str]] = None,
) -> OracleCheckResult:
    return OracleCheckResult(
        feed_address="0xFEED",
        is_stale=is_stale,
        is_circuit_breaker=is_circuit_breaker,
        updated_at=datetime.now(timezone.utc),
        price=price,
        age_seconds=age_seconds,
        deviation_pct=deviation_pct,
        should_hold=is_stale or is_circuit_breaker,
        reasons=reasons or [],
    )


class TestOracleMonitorConstruction:
    def test_requires_at_least_one_feed(self) -> None:
        with pytest.raises(ValueError, match="at least one feed"):
            OracleMonitor(_new_monitoring_service(), feeds=[])

    def test_rejects_non_positive_staleness(self) -> None:
        with pytest.raises(ValueError, match="staleness_threshold_seconds"):
            OracleMonitor(
                _new_monitoring_service(),
                feeds=[_feed()],
                staleness_threshold_seconds=0,
            )

    def test_rejects_non_positive_deviation(self) -> None:
        with pytest.raises(ValueError, match="deviation_threshold_pct"):
            OracleMonitor(
                _new_monitoring_service(),
                feeds=[_feed()],
                deviation_threshold_pct=Decimal("0"),
            )

    def test_rejects_extreme_below_normal_thresholds(self) -> None:
        with pytest.raises(ValueError, match="extreme_staleness_threshold_seconds"):
            OracleMonitor(
                _new_monitoring_service(),
                feeds=[_feed()],
                staleness_threshold_seconds=3600,
                extreme_staleness_threshold_seconds=1800,
            )
        with pytest.raises(ValueError, match="extreme_deviation_pct"):
            OracleMonitor(
                _new_monitoring_service(),
                feeds=[_feed()],
                deviation_threshold_pct=Decimal("10"),
                extreme_deviation_pct=Decimal("5"),
            )

    def test_feeds_property_returns_copy(self) -> None:
        feeds = [_feed("USDC"), _feed("WETH")]
        monitor = OracleMonitor(_new_monitoring_service(), feeds=feeds)
        snapshot = monitor.feeds
        snapshot.clear()
        assert len(monitor.feeds) == 2


class TestCheckOnce:
    def test_no_anomaly_does_not_trigger(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ms = _new_monitoring_service()
        calls: list[str] = []

        def fake_check(*, feed_address: str, **_kwargs: object) -> OracleCheckResult:
            calls.append(feed_address)
            return _stub_result(is_stale=False)

        monkeypatch.setattr(om_mod, "check_oracle_staleness", fake_check)

        monitor = OracleMonitor(ms, feeds=[_feed("USDC"), _feed("WETH")])
        report = monitor.check_once()

        assert report.anomaly_detected is False
        assert report.emergency_triggered is False
        assert report.reasons == []
        assert set(report.feed_results.keys()) == {"USDC", "WETH"}
        assert ms.is_trading_allowed() is True
        assert len(calls) == 2

    def test_stale_oracle_with_unhealthy_hf_triggers_emergency_stop(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ms = _new_monitoring_service()
        ms.record_health_factor(Decimal("1.5"))

        def fake_check(**_kwargs: object) -> OracleCheckResult:
            return _stub_result(
                is_stale=True,
                age_seconds=7200,
                reasons=["oracle price is stale"],
            )

        monkeypatch.setattr(om_mod, "check_oracle_staleness", fake_check)

        monitor = OracleMonitor(
            ms,
            feeds=[_feed("USDC")],
            hf_guard_threshold=Decimal("1.8"),
        )
        report = monitor.check_once()

        assert report.anomaly_detected is True
        assert report.emergency_triggered is True
        assert ms.is_trading_allowed() is False
        status = ms.get_status()
        assert status.emergency_reason is not None
        assert "Aave oracle anomaly" in status.emergency_reason
        assert "oracle_and_hf" in status.emergency_reason

    def test_stale_oracle_with_healthy_hf_does_not_trigger(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ms = _new_monitoring_service()
        ms.record_health_factor(Decimal("2.5"))

        def fake_check(**_kwargs: object) -> OracleCheckResult:
            return _stub_result(
                is_stale=True,
                age_seconds=7200,
                reasons=["oracle price is stale"],
            )

        monkeypatch.setattr(om_mod, "check_oracle_staleness", fake_check)

        monitor = OracleMonitor(ms, feeds=[_feed("USDC")])
        report = monitor.check_once()

        assert report.anomaly_detected is True
        assert report.emergency_triggered is False
        assert ms.is_trading_allowed() is True

    def test_stale_oracle_with_missing_hf_does_not_trigger(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ms = _new_monitoring_service()  # no HF recorded

        def fake_check(**_kwargs: object) -> OracleCheckResult:
            return _stub_result(
                is_stale=True,
                age_seconds=7200,
                reasons=["oracle price is stale"],
            )

        monkeypatch.setattr(om_mod, "check_oracle_staleness", fake_check)

        monitor = OracleMonitor(ms, feeds=[_feed("USDC")])
        report = monitor.check_once()

        assert report.anomaly_detected is True
        assert report.emergency_triggered is False
        assert ms.is_trading_allowed() is True

    def test_extreme_staleness_triggers_regardless_of_hf(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ms = _new_monitoring_service()
        ms.record_health_factor(Decimal("3.0"))  # healthy HF

        def fake_check(**_kwargs: object) -> OracleCheckResult:
            return _stub_result(
                is_stale=True,
                age_seconds=48 * 3600,  # 48h
                reasons=["very old"],
            )

        monkeypatch.setattr(om_mod, "check_oracle_staleness", fake_check)

        monitor = OracleMonitor(
            ms,
            feeds=[_feed("USDC")],
            extreme_staleness_threshold_seconds=24 * 3600,
        )
        report = monitor.check_once()

        assert report.anomaly_detected is True
        assert report.emergency_triggered is True
        status = ms.get_status()
        assert status.emergency_reason is not None
        assert "extreme" in status.emergency_reason

    def test_extreme_deviation_triggers_regardless_of_hf(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ms = _new_monitoring_service()
        ms.record_health_factor(Decimal("3.0"))  # healthy

        def fake_check(**_kwargs: object) -> OracleCheckResult:
            return _stub_result(
                is_circuit_breaker=True,
                deviation_pct=Decimal("45"),
                reasons=["deviation 45%"],
            )

        monkeypatch.setattr(om_mod, "check_oracle_staleness", fake_check)

        monitor = OracleMonitor(
            ms,
            feeds=[_feed("USDC")],
            deviation_threshold_pct=Decimal("10"),
            extreme_deviation_pct=Decimal("30"),
        )
        report = monitor.check_once()

        assert report.emergency_triggered is True

    def test_require_hf_false_triggers_on_any_anomaly(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ms = _new_monitoring_service()
        ms.record_health_factor(Decimal("3.0"))  # healthy

        def fake_check(**_kwargs: object) -> OracleCheckResult:
            return _stub_result(is_stale=True, reasons=["stale"])

        monkeypatch.setattr(om_mod, "check_oracle_staleness", fake_check)

        monitor = OracleMonitor(
            ms,
            feeds=[_feed("USDC")],
            require_hf_confirmation=False,
        )
        report = monitor.check_once()

        assert report.emergency_triggered is True
        status = ms.get_status()
        assert status.emergency_reason is not None
        assert "oracle_only" in status.emergency_reason

    def test_rpc_failure_records_in_fetch_failures_and_continues(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ms = _new_monitoring_service()

        def fake_check(*, feed_address: str, **_kwargs: object) -> Optional[OracleCheckResult]:
            if "USDC" in feed_address.upper() or feed_address.lower().startswith(
                "0x55534443"
            ):  # "USDC" ascii hex
                return None  # RPC failed
            return _stub_result()

        monkeypatch.setattr(om_mod, "check_oracle_staleness", fake_check)

        monitor = OracleMonitor(ms, feeds=[_feed("USDC"), _feed("WETH")])
        report = monitor.check_once()

        assert "USDC" in report.fetch_failures
        assert "WETH" in report.feed_results
        assert report.emergency_triggered is False

    def test_check_raises_is_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ms = _new_monitoring_service()

        def fake_check(**_kwargs: object) -> OracleCheckResult:
            raise RuntimeError("simulated RPC error")

        monkeypatch.setattr(om_mod, "check_oracle_staleness", fake_check)

        monitor = OracleMonitor(ms, feeds=[_feed("USDC")])
        report = monitor.check_once()

        assert report.fetch_failures == ["USDC"]
        assert report.feed_results == {}
        assert report.emergency_triggered is False

    def test_previous_price_cached_for_next_check(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ms = _new_monitoring_service()
        observed_previous: list[Optional[Decimal]] = []

        def fake_check(
            *,
            previous_price: Optional[Decimal] = None,
            **_kwargs: object,
        ) -> OracleCheckResult:
            observed_previous.append(previous_price)
            return _stub_result(price=Decimal("2000"))

        monkeypatch.setattr(om_mod, "check_oracle_staleness", fake_check)

        monitor = OracleMonitor(ms, feeds=[_feed("WETH")])
        monitor.check_once()
        monitor.check_once()

        assert observed_previous == [None, Decimal("2000")]

    def test_activate_emergency_stop_failure_does_not_propagate(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ms = _new_monitoring_service()
        ms.record_health_factor(Decimal("1.4"))

        def fake_check(**_kwargs: object) -> OracleCheckResult:
            return _stub_result(is_stale=True, reasons=["stale"])

        monkeypatch.setattr(om_mod, "check_oracle_staleness", fake_check)

        broken_ms = cast(MonitoringService, MagicMock(spec=MonitoringService))
        broken_status = MagicMock()
        broken_status.last_health_factor = Decimal("1.4")
        cast(MagicMock, broken_ms.get_status).return_value = broken_status
        cast(MagicMock, broken_ms.activate_emergency_stop).side_effect = RuntimeError(
            "notify failed"
        )

        monitor = OracleMonitor(broken_ms, feeds=[_feed("USDC")])
        report = monitor.check_once()

        assert report.anomaly_detected is True
        assert report.emergency_triggered is False  # set only on success


class TestMonitorLoop:
    @pytest.mark.asyncio
    async def test_loop_calls_check_and_sleeps(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ms = _new_monitoring_service()

        def fake_check(**_kwargs: object) -> OracleCheckResult:
            return _stub_result()

        monkeypatch.setattr(om_mod, "check_oracle_staleness", fake_check)

        monitor = OracleMonitor(ms, feeds=[_feed("USDC")])
        call_count = {"n": 0}
        original_check_once = monitor.check_once

        def counting_check() -> object:
            call_count["n"] += 1
            return original_check_once()

        monkeypatch.setattr(monitor, "check_once", counting_check)

        sleep_calls: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)
            if len(sleep_calls) >= 2:
                raise asyncio.CancelledError()

        import asyncio  # noqa: PLC0415

        monkeypatch.setattr(om_mod.asyncio, "sleep", fake_sleep)

        with pytest.raises(asyncio.CancelledError):
            await monitor.monitor_loop(interval_seconds=5)

        assert call_count["n"] >= 2
        assert sleep_calls == [5, 5]

    @pytest.mark.asyncio
    async def test_loop_rejects_non_positive_interval(self) -> None:
        ms = _new_monitoring_service()
        monitor = OracleMonitor(ms, feeds=[_feed("USDC")])
        with pytest.raises(ValueError, match="interval_seconds"):
            await monitor.monitor_loop(interval_seconds=0)

    @pytest.mark.asyncio
    async def test_loop_recovers_from_check_exception(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ms = _new_monitoring_service()
        monitor = OracleMonitor(ms, feeds=[_feed("USDC")])

        call_count = {"n": 0}

        def boom() -> object:
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("simulated")
            return None

        monkeypatch.setattr(monitor, "check_once", boom)

        import asyncio  # noqa: PLC0415

        sleep_calls = {"n": 0}

        async def fake_sleep(_seconds: float) -> None:
            sleep_calls["n"] += 1
            if sleep_calls["n"] >= 2:
                raise asyncio.CancelledError()

        monkeypatch.setattr(om_mod.asyncio, "sleep", fake_sleep)

        with pytest.raises(asyncio.CancelledError):
            await monitor.monitor_loop(interval_seconds=1)

        assert call_count["n"] >= 2
