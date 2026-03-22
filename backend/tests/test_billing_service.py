# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_billing_service.py
"""
BillingService のユニットテスト。

conftest.py には触らず、このファイル内で fixture を定義する。
DB 操作は MagicMock でモックする。
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.billing.models import FeeCalculation, FeeConfig, HighWaterMark
from app.billing.service import BillingService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    """モック DB セッション。"""
    return MagicMock()


@pytest.fixture
def billing_service():
    """テスト対象の BillingService インスタンス。"""
    return BillingService()


@pytest.fixture
def default_fee_config():
    """デフォルト値の FeeConfig インスタンス。"""
    config = FeeConfig()
    config.management_fee_rate = Decimal("0.005")
    config.performance_fee_rate = Decimal("0.10")
    config.high_water_mark_enabled = True
    config.minimum_aum = Decimal("3000")
    return config


# ---------------------------------------------------------------------------
# TestCalculateDailyManagementFee
# ---------------------------------------------------------------------------


class TestCalculateDailyManagementFee:
    """日次管理報酬計算のテスト。"""

    def test_basic_calculation(self, billing_service: BillingService) -> None:
        """基本計算: 365,000 * 0.005 / 365 = 5.0"""
        aum = Decimal("365000")
        rate = Decimal("0.005")
        result = billing_service.calculate_daily_management_fee(aum, rate)
        assert result == Decimal("5.000000")

    def test_zero_aum(self, billing_service: BillingService) -> None:
        """AUM=0 の場合は 0 を返す。"""
        result = billing_service.calculate_daily_management_fee(Decimal("0"), Decimal("0.005"))
        assert result == Decimal("0.000000")

    def test_decimal_precision(self, billing_service: BillingService) -> None:
        """小数点以下 6 桁で丸められること。"""
        aum = Decimal("10000")
        rate = Decimal("0.005")
        result = billing_service.calculate_daily_management_fee(aum, rate)
        # 10000 * 0.005 / 365 = 0.136986...
        assert isinstance(result, Decimal)
        # 小数点以下の桁数確認（sign=0, digits, exponent で確認）
        sign, digits, exponent = result.as_tuple()
        assert exponent >= -6

    def test_no_float_in_result(self, billing_service: BillingService) -> None:
        """結果が float でないこと（Decimal であること）を確認。"""
        result = billing_service.calculate_daily_management_fee(Decimal("50000"), Decimal("0.01"))
        assert isinstance(result, Decimal)
        assert not isinstance(result, float)


# ---------------------------------------------------------------------------
# TestCalculatePerformanceFee
# ---------------------------------------------------------------------------


class TestCalculatePerformanceFee:
    """成果報酬計算のテスト。"""

    def test_profit_above_hwm(self, billing_service: BillingService) -> None:
        """HWM 超過時に手数料が発生する。"""
        result = billing_service.calculate_performance_fee(
            current_value=Decimal("11000"),
            hwm=Decimal("10000"),
            rate=Decimal("0.10"),
        )
        # (11000 - 10000) * 0.10 = 100
        assert result == Decimal("100.000000")

    def test_no_profit_at_hwm(self, billing_service: BillingService) -> None:
        """current == hwm の場合は手数料ゼロ。"""
        result = billing_service.calculate_performance_fee(
            current_value=Decimal("10000"),
            hwm=Decimal("10000"),
            rate=Decimal("0.10"),
        )
        assert result == Decimal("0")

    def test_loss_below_hwm(self, billing_service: BillingService) -> None:
        """HWM 未満の場合は手数料ゼロ。"""
        result = billing_service.calculate_performance_fee(
            current_value=Decimal("9000"),
            hwm=Decimal("10000"),
            rate=Decimal("0.10"),
        )
        assert result == Decimal("0")

    def test_decimal_precision(self, billing_service: BillingService) -> None:
        """精度テスト: Decimal で正確に計算されること。"""
        result = billing_service.calculate_performance_fee(
            current_value=Decimal("10001"),
            hwm=Decimal("10000"),
            rate=Decimal("0.20"),
        )
        # (10001 - 10000) * 0.20 = 0.2
        assert result == Decimal("0.200000")
        assert isinstance(result, Decimal)


# ---------------------------------------------------------------------------
# TestHighWaterMark
# ---------------------------------------------------------------------------


class TestHighWaterMark:
    """HWM 更新ロジックのテスト。"""

    def test_hwm_updates_when_value_increases(
        self, billing_service: BillingService, mock_db: MagicMock
    ) -> None:
        """新値が既存より大きい場合、HWM が更新される。"""
        existing_hwm = HighWaterMark()
        existing_hwm.user_id = 1
        existing_hwm.hwm_value = Decimal("10000")

        mock_db.query.return_value.filter.return_value.first.return_value = existing_hwm

        result = billing_service.update_hwm(mock_db, user_id=1, new_value=Decimal("12000"))

        assert result.hwm_value == Decimal("12000")

    def test_hwm_does_not_update_when_value_decreases(
        self, billing_service: BillingService, mock_db: MagicMock
    ) -> None:
        """新値が既存より小さい場合、HWM は更新されない。"""
        existing_hwm = HighWaterMark()
        existing_hwm.user_id = 1
        existing_hwm.hwm_value = Decimal("10000")

        mock_db.query.return_value.filter.return_value.first.return_value = existing_hwm

        result = billing_service.update_hwm(mock_db, user_id=1, new_value=Decimal("8000"))

        assert result.hwm_value == Decimal("10000")

    def test_hwm_does_not_update_when_value_equal(
        self, billing_service: BillingService, mock_db: MagicMock
    ) -> None:
        """新値が既存と同じ場合、HWM は更新されない。"""
        existing_hwm = HighWaterMark()
        existing_hwm.user_id = 1
        existing_hwm.hwm_value = Decimal("10000")

        mock_db.query.return_value.filter.return_value.first.return_value = existing_hwm

        result = billing_service.update_hwm(mock_db, user_id=1, new_value=Decimal("10000"))

        assert result.hwm_value == Decimal("10000")


# ---------------------------------------------------------------------------
# TestRunDailyFeeBatch
# ---------------------------------------------------------------------------


class TestRunDailyFeeBatch:
    """日次バッチ処理のテスト。"""

    def _make_fee_config(self) -> FeeConfig:
        config = FeeConfig()
        config.management_fee_rate = Decimal("0.005")
        config.performance_fee_rate = Decimal("0.10")
        config.high_water_mark_enabled = True
        config.minimum_aum = Decimal("3000")
        return config

    def _make_mock_db_for_batch(self) -> MagicMock:
        """バッチ処理用のモック DB を構築する。"""
        mock_db = MagicMock()

        # get_active_fee_config 用クエリ
        mock_fee_config = self._make_fee_config()

        # get_or_create_hwm / update_hwm 用
        def query_side_effect(model_class):
            q = MagicMock()
            if model_class is FeeConfig:
                q.order_by.return_value.first.return_value = mock_fee_config
            elif model_class is HighWaterMark:
                hwm = HighWaterMark()
                hwm.user_id = 0
                hwm.hwm_value = Decimal("5000")
                q.filter.return_value.first.return_value = hwm
            elif model_class is FeeCalculation:
                q.filter.return_value.order_by.return_value.all.return_value = []
            return q

        mock_db.query.side_effect = query_side_effect
        return mock_db

    def test_batch_processes_all_users(self, billing_service: BillingService) -> None:
        """全ユーザーが処理されること。"""
        mock_db = self._make_mock_db_for_batch()
        fee_config = self._make_fee_config()

        user_aum_map = {
            1: Decimal("10000"),
            2: Decimal("8000"),
        }

        result = billing_service.run_daily_fee_batch(
            db=mock_db,
            user_aum_map=user_aum_map,
            fee_config=fee_config,
        )

        assert result.processed_count == 2
        assert result.failed_count == 0

    def test_batch_skips_users_below_minimum_aum(self, billing_service: BillingService) -> None:
        """minimum_aum 未満のユーザーはスキップされること。"""
        mock_db = self._make_mock_db_for_batch()
        fee_config = self._make_fee_config()  # minimum_aum = 3000

        user_aum_map = {
            1: Decimal("5000"),  # 処理される
            2: Decimal("2999"),  # スキップされる
        }

        result = billing_service.run_daily_fee_batch(
            db=mock_db,
            user_aum_map=user_aum_map,
            fee_config=fee_config,
        )

        assert result.processed_count == 1
        assert result.failed_count == 0

    def test_batch_returns_correct_counts(self, billing_service: BillingService) -> None:
        """processed_count と failed_count が正しく返ること。"""
        mock_db = self._make_mock_db_for_batch()
        fee_config = self._make_fee_config()

        # record_fee_calculation で例外を発生させてエラーを模擬
        original_record = billing_service.record_fee_calculation

        call_count = [0]

        def patched_record(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("Simulated error")
            return original_record(*args, **kwargs)

        billing_service.record_fee_calculation = patched_record  # type: ignore[method-assign]

        try:
            user_aum_map = {
                1: Decimal("5000"),
                2: Decimal("6000"),
            }
            result = billing_service.run_daily_fee_batch(
                db=mock_db,
                user_aum_map=user_aum_map,
                fee_config=fee_config,
            )
            assert result.processed_count == 1
            assert result.failed_count == 1
            assert len(result.errors) == 1
        finally:
            billing_service.record_fee_calculation = original_record  # type: ignore[method-assign]

    def test_batch_with_empty_user_map(self, billing_service: BillingService) -> None:
        """空の user_aum_map では 0 件処理。"""
        mock_db = self._make_mock_db_for_batch()
        fee_config = self._make_fee_config()

        result = billing_service.run_daily_fee_batch(
            db=mock_db,
            user_aum_map={},
            fee_config=fee_config,
        )

        assert result.processed_count == 0
        assert result.failed_count == 0
        assert result.errors == []


# ---------------------------------------------------------------------------
# TestGetUserFeeSummary
# ---------------------------------------------------------------------------


class TestGetUserFeeSummary:
    """ユーザー手数料サマリーのテスト。"""

    def test_summary_aggregates_correctly(
        self, billing_service: BillingService, mock_db: MagicMock
    ) -> None:
        """複数レコードの集計が正しく行われること。"""
        # SQLAlchemy の aggregate result を模擬
        mock_row = MagicMock()
        mock_row.total_management_fee = Decimal("15.000000")
        mock_row.total_performance_fee = Decimal("50.000000")
        mock_row.total_fee = Decimal("65.000000")
        mock_row.calculation_count = 3

        mock_db.query.return_value.filter.return_value.one.return_value = mock_row

        result = billing_service.get_user_fee_summary(db=mock_db, user_id=1)

        assert result.user_id == 1
        assert result.total_management_fee == Decimal("15.000000")
        assert result.total_performance_fee == Decimal("50.000000")
        assert result.total_fee == Decimal("65.000000")
        assert result.calculation_count == 3

    def test_summary_returns_zero_for_new_user(
        self, billing_service: BillingService, mock_db: MagicMock
    ) -> None:
        """レコードがないユーザーはゼロ値のサマリーを返す。"""
        mock_row = MagicMock()
        mock_row.total_management_fee = Decimal("0")
        mock_row.total_performance_fee = Decimal("0")
        mock_row.total_fee = Decimal("0")
        mock_row.calculation_count = 0

        mock_db.query.return_value.filter.return_value.one.return_value = mock_row

        result = billing_service.get_user_fee_summary(db=mock_db, user_id=999)

        assert result.user_id == 999
        assert result.total_fee == Decimal("0")
        assert result.calculation_count == 0
