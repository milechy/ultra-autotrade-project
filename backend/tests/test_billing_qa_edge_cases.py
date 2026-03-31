# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_billing_qa_edge_cases.py
"""
Billing QA: 境界値・異常系テスト

利益ゼロ、損失、HWM 境界、最低運用額、バッチ処理の異常系、
日付境界（365日固定）、二重課金防止を検証する。
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.billing.models import FeeCalculation, FeeConfig, HighWaterMark
from app.billing.service import BillingService, BillingServiceError

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def svc() -> BillingService:
    """テスト対象の BillingService インスタンス。"""
    return BillingService()


def _make_fee_config(
    management_rate: Decimal = Decimal("0.005"),
    performance_rate: Decimal = Decimal("0.10"),
    hwm_enabled: bool = True,
    minimum_aum: Decimal = Decimal("3000"),
) -> FeeConfig:
    """テスト用 FeeConfig を生成するヘルパー。"""
    config = FeeConfig()
    config.management_fee_rate = management_rate
    config.performance_fee_rate = performance_rate
    config.high_water_mark_enabled = hwm_enabled
    config.minimum_aum = minimum_aum
    return config


def _make_batch_mock_db(initial_hwm_value: Decimal = Decimal("5000")) -> MagicMock:
    """バッチ処理用の汎用モック DB を生成するヘルパー。"""
    mock_db = MagicMock()

    def query_side_effect(model_class):  # type: ignore[no-untyped-def]
        q = MagicMock()
        if model_class is HighWaterMark:
            hwm = HighWaterMark()
            hwm.user_id = 0
            hwm.hwm_value = initial_hwm_value
            q.filter.return_value.first.return_value = hwm
        elif model_class is FeeCalculation:
            q.filter.return_value.order_by.return_value.all.return_value = []
        return q

    mock_db.query.side_effect = query_side_effect
    return mock_db


# ---------------------------------------------------------------------------
# TestZeroProfitBoundary
# ---------------------------------------------------------------------------


class TestZeroProfitBoundary:
    """利益ゼロ境界のテスト。"""

    def test_performance_fee_zero_when_current_equals_hwm(self, svc: BillingService) -> None:
        """current_value == hwm の場合、成果報酬は Decimal('0') であること。"""
        result = svc.calculate_performance_fee(
            current_value=Decimal("10000"),
            hwm=Decimal("10000"),
            rate=Decimal("0.10"),
        )
        assert result == Decimal("0")

    def test_management_fee_zero_when_aum_is_zero(self, svc: BillingService) -> None:
        """AUM=0 の場合、管理報酬は Decimal('0') であること。"""
        result = svc.calculate_daily_management_fee(
            aum=Decimal("0"),
            rate=Decimal("0.005"),
        )
        assert result == Decimal("0")
        assert isinstance(result, Decimal)


# ---------------------------------------------------------------------------
# TestLossScenarios
# ---------------------------------------------------------------------------


class TestLossScenarios:
    """損失（HWM 未満）シナリオのテスト。"""

    def test_performance_fee_zero_on_small_loss(self, svc: BillingService) -> None:
        """HWM より $1 下の損失 → 成果報酬ゼロ。"""
        result = svc.calculate_performance_fee(
            current_value=Decimal("9999"),
            hwm=Decimal("10000"),
            rate=Decimal("0.10"),
        )
        assert result == Decimal("0")

    def test_performance_fee_zero_on_large_loss(self, svc: BillingService) -> None:
        """HWM の半分以下への大幅な損失 → 成果報酬ゼロ。"""
        result = svc.calculate_performance_fee(
            current_value=Decimal("4000"),
            hwm=Decimal("10000"),
            rate=Decimal("0.10"),
        )
        assert result == Decimal("0")

    def test_performance_fee_result_nonnegative_on_loss(self, svc: BillingService) -> None:
        """損失時の成果報酬が負にならないこと（常に >= 0）。"""
        result = svc.calculate_performance_fee(
            current_value=Decimal("1"),
            hwm=Decimal("100000"),
            rate=Decimal("0.10"),
        )
        assert result >= Decimal("0")


# ---------------------------------------------------------------------------
# TestHWMBoundary
# ---------------------------------------------------------------------------


class TestHWMBoundary:
    """High Water Mark 境界値テスト。"""

    def test_hwm_created_on_first_call(self, svc: BillingService) -> None:
        """HWM レコードが存在しない場合、get_or_create_hwm で新規作成されること。"""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = svc.get_or_create_hwm(
            db=mock_db,
            user_id=42,
            initial_value=Decimal("10000"),
        )

        assert result.user_id == 42
        assert result.hwm_value == Decimal("10000")
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    def test_hwm_not_updated_when_value_equal(self, svc: BillingService) -> None:
        """current == hwm の場合、update_hwm は HWM を更新しないこと。"""
        existing_hwm = HighWaterMark()
        existing_hwm.user_id = 1
        existing_hwm.hwm_value = Decimal("10000")

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = existing_hwm

        result = svc.update_hwm(
            db=mock_db,
            user_id=1,
            new_value=Decimal("10000"),
        )

        assert result.hwm_value == Decimal("10000")

    def test_hwm_maintained_after_portfolio_decline(self, svc: BillingService) -> None:
        """HWM が $12,000 に達した後、AUM が $8,000 に下落しても HWM は $12,000 を維持すること。"""
        existing_hwm = HighWaterMark()
        existing_hwm.user_id = 1
        existing_hwm.hwm_value = Decimal("12000")

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = existing_hwm

        result = svc.update_hwm(
            db=mock_db,
            user_id=1,
            new_value=Decimal("8000"),
        )

        assert result.hwm_value == Decimal("12000"), "HWM must not decrease after portfolio decline"

    def test_hwm_update_raises_on_missing_record(self, svc: BillingService) -> None:
        """HWM レコードが存在しない場合、update_hwm は BillingServiceError を送出すること。"""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(BillingServiceError):
            svc.update_hwm(
                db=mock_db,
                user_id=99,
                new_value=Decimal("10000"),
            )


# ---------------------------------------------------------------------------
# TestMinimumAumBoundary
# ---------------------------------------------------------------------------


class TestMinimumAumBoundary:
    """最低運用額（$3,000）境界テスト。"""

    def test_batch_skips_aum_2999_99(self, svc: BillingService) -> None:
        """AUM=$2,999.99（最低額未満）→ バッチでスキップされ processed_count=0。"""
        mock_db = _make_batch_mock_db(initial_hwm_value=Decimal("2999.99"))
        fee_config = _make_fee_config(minimum_aum=Decimal("3000"))

        result = svc.run_daily_fee_batch(
            db=mock_db,
            user_aum_map={1: Decimal("2999.99")},
            fee_config=fee_config,
        )

        assert result.processed_count == 0
        assert result.failed_count == 0

    def test_batch_processes_aum_3000_00(self, svc: BillingService) -> None:
        """AUM=$3,000.00（最低額ちょうど）→ バッチで処理され processed_count=1。"""
        mock_db = _make_batch_mock_db(initial_hwm_value=Decimal("3000"))
        fee_config = _make_fee_config(minimum_aum=Decimal("3000"))

        result = svc.run_daily_fee_batch(
            db=mock_db,
            user_aum_map={1: Decimal("3000")},
            fee_config=fee_config,
        )

        assert result.processed_count == 1
        assert result.failed_count == 0


# ---------------------------------------------------------------------------
# TestBatchProcessing
# ---------------------------------------------------------------------------


class TestBatchProcessing:
    """バッチ処理の異常系テスト。"""

    def test_empty_users_all_zeros(self, svc: BillingService) -> None:
        """ユーザー 0 人 → BatchResult の全カウントが 0 であること。"""
        mock_db = _make_batch_mock_db()
        fee_config = _make_fee_config()

        result = svc.run_daily_fee_batch(
            db=mock_db,
            user_aum_map={},
            fee_config=fee_config,
        )

        assert result.processed_count == 0
        assert result.failed_count == 0
        assert result.errors == []

    def test_one_error_others_continue(self, svc: BillingService) -> None:
        """1 人のユーザーがエラーになっても、他のユーザーは正常処理されること。"""
        mock_db = _make_batch_mock_db()
        fee_config = _make_fee_config()

        original_record = svc.record_fee_calculation
        call_count = [0]

        def patched_record(*args, **kwargs):  # type: ignore[no-untyped-def]
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("Simulated first user error")
            return original_record(*args, **kwargs)

        svc.record_fee_calculation = patched_record  # type: ignore[method-assign]
        try:
            # user_id=1 が先にエラー、user_id=2 は正常処理
            result = svc.run_daily_fee_batch(
                db=mock_db,
                user_aum_map={1: Decimal("5000"), 2: Decimal("6000")},
                fee_config=fee_config,
            )
            assert result.processed_count == 1
            assert result.failed_count == 1
            assert len(result.errors) == 1
        finally:
            svc.record_fee_calculation = original_record  # type: ignore[method-assign]

    def test_all_users_fail_correct_counts(self, svc: BillingService) -> None:
        """全ユーザーがエラーの場合、failed_count == len(user_aum_map) かつ processed_count=0。"""
        mock_db = _make_batch_mock_db()
        fee_config = _make_fee_config()

        original_record = svc.record_fee_calculation

        def always_fail(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("Always fail")

        svc.record_fee_calculation = always_fail  # type: ignore[method-assign]
        try:
            result = svc.run_daily_fee_batch(
                db=mock_db,
                user_aum_map={
                    1: Decimal("5000"),
                    2: Decimal("6000"),
                    3: Decimal("7000"),
                },
                fee_config=fee_config,
            )
            assert result.processed_count == 0
            assert result.failed_count == 3
        finally:
            svc.record_fee_calculation = original_record  # type: ignore[method-assign]

    def test_errors_list_contains_user_id(self, svc: BillingService) -> None:
        """errors リストにエラーが発生したユーザー ID が含まれること。"""
        mock_db = _make_batch_mock_db()
        fee_config = _make_fee_config()

        original_record = svc.record_fee_calculation

        def always_fail(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("DB write failed")

        svc.record_fee_calculation = always_fail  # type: ignore[method-assign]
        try:
            result = svc.run_daily_fee_batch(
                db=mock_db,
                user_aum_map={999: Decimal("5000")},
                fee_config=fee_config,
            )
            assert result.failed_count == 1
            assert len(result.errors) == 1
            assert "999" in result.errors[0], (
                f"Error message should contain user_id=999, got: {result.errors[0]}"
            )
        finally:
            svc.record_fee_calculation = original_record  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# TestDateBoundary
# ---------------------------------------------------------------------------


class TestDateBoundary:
    """日付境界テスト。"""

    def test_management_fee_uses_365_not_366(self, svc: BillingService) -> None:
        """うるう年でも日割り計算の分母は 365（実装の定数）であること。

        AUM=365000, rate=0.005: 365000*0.005/365 = 5.000000
        もし 366 を使った場合: 1825/366 ≈ 4.986338... （5.000000 にならない）
        """
        result = svc.calculate_daily_management_fee(
            aum=Decimal("365000"),
            rate=Decimal("0.005"),
        )
        assert result == Decimal("5.000000"), (
            f"Expected 5.000000 (365-day denominator), got {result}. "
            "Validates hardcoded 365-day denominator, not leap-year 366."
        )

    def test_management_fee_annual_consistency(self, svc: BillingService) -> None:
        """日次手数料 × 365 が年間手数料に対して丸め誤差 1 未満の範囲で一致すること。"""
        aum = Decimal("100000")
        rate = Decimal("0.005")

        daily = svc.calculate_daily_management_fee(aum=aum, rate=rate)

        # 日次 × 365 ≈ 年間 (aum * rate = 500)
        annual_from_daily = daily * Decimal("365")
        expected_annual = aum * rate  # 100000 * 0.005 = 500

        diff = abs(annual_from_daily - expected_annual)
        assert diff < Decimal("1"), (
            f"Annual fee inconsistency too large: {annual_from_daily} vs {expected_annual} "
            f"(diff={diff})"
        )


# ---------------------------------------------------------------------------
# TestDoubleBatchSafety
# ---------------------------------------------------------------------------


class TestDoubleBatchSafety:
    """二重バッチ実行安全性テスト。"""

    def test_double_performance_fee_prevented_by_hwm(self, svc: BillingService) -> None:
        """HWM により、同じ利益に対して成果報酬が二重請求されないことを確認。

        1回目: HWM=$10,000, AUM=$11,000 → 成果報酬=$100
        2回目: HWM=$11,000（更新済み）, AUM=$11,000 → 成果報酬=$0
        合計: $100（二重課金なし）
        """
        rate = Decimal("0.10")

        # 1回目バッチ: HWM=10000, AUM=11000 → 利益$1,000 → 成果報酬$100
        fee_first_run = svc.calculate_performance_fee(
            current_value=Decimal("11000"),
            hwm=Decimal("10000"),
            rate=rate,
        )
        assert fee_first_run == Decimal("100.000000")

        # 2回目バッチ: HWM が 11000 に更新された想定で同じ AUM で計算
        fee_second_run = svc.calculate_performance_fee(
            current_value=Decimal("11000"),
            hwm=Decimal("11000"),  # 1回目バッチ後に更新済み
            rate=rate,
        )
        assert fee_second_run == Decimal("0")

        # 合計成果報酬は $100 のみ（二重課金なし）
        total_performance_fee = fee_first_run + fee_second_run
        assert total_performance_fee == Decimal("100.000000")
