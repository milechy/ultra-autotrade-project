# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/aave/test_liquidation_sentinel.py
"""
LiquidationSentinel のユニットテスト。

全外部呼び出し（RPC / Slack）はモック。金融計算は Decimal 精度で検証。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

from app.aave.liquidation_sentinel import (
    DEFICIT_ALERT_THRESHOLD,
    PoolHealthMonitor,
    PoolHealthReport,
    StressTestResult,
    StressTestScenario,
    _mask_address,
    get_stress_test,
    simulate_hf_at_price_drop,
)

# ---------------------------------------------------------------------------
# simulate_hf_at_price_drop — ユニットテスト
# ---------------------------------------------------------------------------


class TestSimulateHfAtPriceDropBasic:
    """simulate_hf_at_price_drop の基本計算テスト。"""

    def test_10pct_drop_hf2(self) -> None:
        """
        Collateral=$10000, Debt=$4000, LT=0.80, -10%
        HF = (10000 * 0.90 * 0.80) / 4000 = 7200 / 4000 = 1.80
        """
        result = simulate_hf_at_price_drop(
            collateral_usd=Decimal("10000"),
            debt_usd=Decimal("4000"),
            liquidation_threshold=Decimal("0.80"),
            price_drop_pct=Decimal("0.10"),
        )
        assert result is not None
        expected = Decimal("7200") / Decimal("4000")  # 1.80
        assert result == expected

    def test_20pct_drop_hf2(self) -> None:
        """
        Collateral=$10000, Debt=$4000, LT=0.80, -20%
        HF = (10000 * 0.80 * 0.80) / 4000 = 6400 / 4000 = 1.60
        """
        result = simulate_hf_at_price_drop(
            collateral_usd=Decimal("10000"),
            debt_usd=Decimal("4000"),
            liquidation_threshold=Decimal("0.80"),
            price_drop_pct=Decimal("0.20"),
        )
        assert result is not None
        expected = Decimal("6400") / Decimal("4000")  # 1.60
        assert result == expected

    def test_hf_at_hf2_no_debt(self) -> None:
        """debt_usd=0 の場合は None を返す（清算リスクなし）。"""
        result = simulate_hf_at_price_drop(
            collateral_usd=Decimal("10000"),
            debt_usd=Decimal("0"),
            liquidation_threshold=Decimal("0.80"),
            price_drop_pct=Decimal("0.10"),
        )
        assert result is None

    def test_decimal_precision_not_float(self) -> None:
        """結果は Decimal 型であること（float 混入禁止）。"""
        result = simulate_hf_at_price_drop(
            collateral_usd=Decimal("10000"),
            debt_usd=Decimal("3333"),
            liquidation_threshold=Decimal("0.80"),
            price_drop_pct=Decimal("0.10"),
        )
        assert result is not None
        assert isinstance(result, Decimal)


class TestSimulateHfAtPriceDropEdge:
    """境界値テスト。"""

    def test_hf_equals_2_0_initial(self) -> None:
        """
        HF=2.0、Collateral=$10000、LT=0.80 のとき debt を逆算して検証。
        HF = 2.0 = (10000 * 0.80) / debt → debt = 4000
        -10% 時: HF = (10000 * 0.90 * 0.80) / 4000 = 1.80
        """
        collateral = Decimal("10000")
        # HF = (collateral * LT) / debt = 2.0 → debt = (10000 * 0.80) / 2.0 = 4000
        lt = Decimal("0.80")
        debt = collateral * lt / Decimal("2.0")
        assert debt == Decimal("4000.0")

        result_10 = simulate_hf_at_price_drop(
            collateral_usd=collateral,
            debt_usd=debt,
            liquidation_threshold=lt,
            price_drop_pct=Decimal("0.10"),
        )
        assert result_10 == Decimal("1.8")

        result_20 = simulate_hf_at_price_drop(
            collateral_usd=collateral,
            debt_usd=debt,
            liquidation_threshold=lt,
            price_drop_pct=Decimal("0.20"),
        )
        assert result_20 == Decimal("1.6")

    def test_liquidation_risk_under_1(self) -> None:
        """
        -20% で HF < 1.0 になるケース（清算域）。
        Collateral=$5000, Debt=$4000, LT=0.80
        HF_now = (5000 * 0.80) / 4000 = 1.00
        -20%: HF = (5000 * 0.80 * 0.80) / 4000 = 0.80 (清算リスク)
        """
        result = simulate_hf_at_price_drop(
            collateral_usd=Decimal("5000"),
            debt_usd=Decimal("4000"),
            liquidation_threshold=Decimal("0.80"),
            price_drop_pct=Decimal("0.20"),
        )
        assert result is not None
        assert result < Decimal("1.0")


# ---------------------------------------------------------------------------
# get_stress_test — モックテスト
# ---------------------------------------------------------------------------


class TestGetStressTest:
    """get_stress_test のモックテスト（外部 RPC 呼び出しなし）。"""

    def test_dummy_mode_returns_result(self) -> None:
        """AAVE_CLIENT_TYPE=dummy の場合、DummyAaveClient のデータでシミュレーション。"""
        with patch.dict("os.environ", {"AAVE_CLIENT_TYPE": "dummy"}):
            result = get_stress_test("0xDEADBEEF1234567890abcdef1234567890abcdef")
        assert isinstance(result, StressTestResult)
        assert result.error is None
        # DummyAaveClient は collateral=10000, debt=3000, hf=2.5 を返す
        assert result.current_collateral_usd == Decimal("10000")
        assert result.current_debt_usd == Decimal("3000")
        # 2 シナリオ（-10%, -20%）があること
        assert len(result.scenarios) == 2
        # 各シナリオの simulated_hf は Decimal 型
        for sc in result.scenarios:
            assert isinstance(sc, StressTestScenario)
            assert sc.simulated_hf is None or isinstance(sc.simulated_hf, Decimal)

    def test_dummy_mode_10pct_scenario(self) -> None:
        """
        DummyAaveClient: collateral=10000, debt=3000, LT=0.80
        -10%: HF = (10000 * 0.90 * 0.80) / 3000 = 7200/3000 = 2.40
        """
        with patch.dict("os.environ", {"AAVE_CLIENT_TYPE": "dummy"}):
            result = get_stress_test("0xDEADBEEF1234567890abcdef1234567890abcdef")
        assert result.scenarios[0].price_drop_pct == Decimal("0.10")
        expected_hf = Decimal("7200") / Decimal("3000")
        assert result.scenarios[0].simulated_hf == expected_hf

    def test_dummy_mode_20pct_scenario(self) -> None:
        """
        DummyAaveClient: collateral=10000, debt=3000, LT=0.80
        -20%: HF = (10000 * 0.80 * 0.80) / 3000 = 6400/3000
        """
        with patch.dict("os.environ", {"AAVE_CLIENT_TYPE": "dummy"}):
            result = get_stress_test("0xDEADBEEF1234567890abcdef1234567890abcdef")
        assert result.scenarios[1].price_drop_pct == Decimal("0.20")
        expected_hf = Decimal("6400") / Decimal("3000")
        assert result.scenarios[1].simulated_hf == expected_hf

    def test_web3_mode_missing_rpc_falls_back_to_dummy(self) -> None:
        """web3 モードで RPC_URL 未設定の場合、dummy フォールバック。"""
        with patch.dict(
            "os.environ",
            {"AAVE_CLIENT_TYPE": "web3", "AAVE_RPC_URL": "", "AAVE_POOL_ADDRESS": ""},
        ):
            result = get_stress_test("0xDEADBEEF1234567890abcdef1234567890abcdef")
        # フォールバック後は dummy データが返る
        assert result.error is None
        assert result.current_collateral_usd is not None


# ---------------------------------------------------------------------------
# PoolHealthMonitor — モックテスト
# ---------------------------------------------------------------------------


class TestPoolHealthMonitorDummyMode:
    """DUMMY モードでは空レポートが返ること。"""

    def test_dummy_mode_returns_empty_report(self) -> None:
        with patch.dict("os.environ", {"AAVE_CLIENT_TYPE": "dummy"}):
            monitor = PoolHealthMonitor()
            report = monitor.check_pool_deficits("base")
        assert isinstance(report, PoolHealthReport)
        assert report.deficits == []
        assert report.alert_triggered is False
        assert report.error is None


class TestPoolHealthMonitorDeficitAlert:
    """deficit 閾値アラートのテスト。"""

    def _make_monitor_with_mock_fetch(
        self, deficit_value: Decimal
    ) -> tuple[PoolHealthMonitor, Any]:
        """deficit_value を返すモック付き PoolHealthMonitor を生成するヘルパー。"""
        monitor = PoolHealthMonitor()
        mock_fetch = MagicMock(return_value=deficit_value)
        return monitor, mock_fetch

    def test_deficit_below_threshold_no_alert(self) -> None:
        """deficit $9999 → アラートなし。"""
        monitor = PoolHealthMonitor()

        with (
            patch.dict(
                "os.environ",
                {
                    "AAVE_CLIENT_TYPE": "web3",
                    "AAVE_RPC_URL": "http://fake-rpc",
                    "AAVE_POOL_ADDRESS": "0xFakePool",
                },
            ),
            patch.object(monitor, "_fetch_reserve_deficit", return_value=Decimal("9999")),
            patch.object(monitor, "_send_deficit_alert") as mock_alert,
        ):
            # tokens に USDC のみ使用（base chain には USDC が存在）
            monitor._tokens = ["USDC"]
            report = monitor.check_pool_deficits("base")

        assert report.alert_triggered is False
        mock_alert.assert_not_called()
        assert len(report.deficits) == 1
        assert report.deficits[0].alert_triggered is False
        assert report.deficits[0].deficit_usd == Decimal("9999")

    def test_deficit_above_threshold_triggers_alert(self) -> None:
        """deficit $10001 → Slack アラート発火。"""
        monitor = PoolHealthMonitor()

        with (
            patch.dict(
                "os.environ",
                {
                    "AAVE_CLIENT_TYPE": "web3",
                    "AAVE_RPC_URL": "http://fake-rpc",
                    "AAVE_POOL_ADDRESS": "0xFakePool",
                },
            ),
            patch.object(monitor, "_fetch_reserve_deficit", return_value=Decimal("10001")),
            patch.object(monitor, "_send_deficit_alert") as mock_alert,
        ):
            monitor._tokens = ["USDC"]
            report = monitor.check_pool_deficits("base")

        assert report.alert_triggered is True
        mock_alert.assert_called_once_with("base", "USDC", Decimal("10001"))
        assert len(report.deficits) == 1
        assert report.deficits[0].alert_triggered is True

    def test_deficit_exactly_at_threshold_no_alert(self) -> None:
        """deficit = $10000 (閾値ちょうど) → アラートなし（threshold は「超える」ときのみ）。"""
        monitor = PoolHealthMonitor()

        with (
            patch.dict(
                "os.environ",
                {
                    "AAVE_CLIENT_TYPE": "web3",
                    "AAVE_RPC_URL": "http://fake-rpc",
                    "AAVE_POOL_ADDRESS": "0xFakePool",
                },
            ),
            patch.object(monitor, "_fetch_reserve_deficit", return_value=Decimal("10000")),
            patch.object(monitor, "_send_deficit_alert") as mock_alert,
        ):
            monitor._tokens = ["USDC"]
            report = monitor.check_pool_deficits("base")

        assert report.alert_triggered is False
        mock_alert.assert_not_called()


class TestPoolHealthMonitorSendAlert:
    """_send_deficit_alert の Slack 送信テスト。"""

    def test_send_alert_calls_slack_sender(self) -> None:
        """SLACK_WEBHOOK_URL が設定されている場合、SlackNotificationSender.send が呼ばれる。"""
        monitor = PoolHealthMonitor()

        with (
            patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"}),
            patch("app.notifications.slack_sender.SlackNotificationSender.send") as mock_send,
        ):
            monitor._send_deficit_alert("base", "USDC", Decimal("15000"))

        mock_send.assert_called_once()

    def test_send_alert_no_webhook_no_error(self) -> None:
        """SLACK_WEBHOOK_URL 未設定でも例外を投げない（fail-open）。"""
        monitor = PoolHealthMonitor()

        with patch.dict("os.environ", {}, clear=True):
            # 例外なしで完了すること
            monitor._send_deficit_alert("base", "USDC", Decimal("15000"))


# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------


class TestMaskAddress:
    def test_mask_normal_address(self) -> None:
        addr = "0x1234567890abcdef1234567890abcdef12345678"
        result = _mask_address(addr)
        assert result == "0x1234...5678"

    def test_mask_short_address(self) -> None:
        result = _mask_address("0x1")
        assert result == "****"

    def test_mask_empty(self) -> None:
        result = _mask_address("")
        assert result == "****"


# ---------------------------------------------------------------------------
# DEFICIT_ALERT_THRESHOLD 定数確認
# ---------------------------------------------------------------------------


class TestConstants:
    def test_threshold_is_decimal(self) -> None:
        """DEFICIT_ALERT_THRESHOLD は Decimal 型であること（float 禁止）。"""
        assert isinstance(DEFICIT_ALERT_THRESHOLD, Decimal)
        assert DEFICIT_ALERT_THRESHOLD == Decimal("10000")
