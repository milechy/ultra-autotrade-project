# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_billing_router.py
"""
Billing ルーターの FastAPI TestClient テスト。

billing_router を独立した FastAPI アプリに登録してテストする。
conftest.py の client fixture（main.py ベース）は使用しない。
認証依存性は dependency_overrides で差し替え、サービス層は mock で対応する。
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import require_admin, require_viewer
from app.auth.models import User, UserRole
from app.billing.models import FeeCalculation, FeeConfig
from app.billing.router import router as billing_router
from app.billing.schemas import (
    AdminFeeMonthlyEntry,
    AdminFeeRefundResponse,
    AdminFeeUserRow,
    AdminMonthlyAggregate,
    BatchResult,
    FeeSummaryResponse,
)
from app.database import get_db

# ---------------------------------------------------------------------------
# Helper: テスト用ユーザー
# ---------------------------------------------------------------------------


def _make_admin_user() -> User:
    user = User()
    user.id = 1
    user.email = "admin@example.com"
    user.username = "admin"
    user.role = UserRole.ADMIN.value
    user.is_active = True
    return user


def _make_viewer_user() -> User:
    user = User()
    user.id = 2
    user.email = "viewer@example.com"
    user.username = "viewer"
    user.role = UserRole.VIEWER.value
    user.is_active = True
    return user


def _make_fee_calculation(user_id: int = 1) -> FeeCalculation:
    calc = FeeCalculation()
    calc.id = 1
    calc.user_id = user_id
    calc.calculation_date = date(2026, 3, 22)
    calc.period_type = "daily"
    calc.aum_snapshot = Decimal("10000.000000")
    calc.management_fee = Decimal("0.136986")
    calc.performance_fee = Decimal("0.000000")
    calc.total_fee = Decimal("0.136986")
    calc.profit_since_hwm = Decimal("0.000000")
    calc.high_water_mark = Decimal("10000.000000")
    calc.created_at = datetime(2026, 3, 22, 0, 0, 0, tzinfo=timezone.utc)
    return calc


def _make_fee_config() -> FeeConfig:
    config = FeeConfig()
    config.id = 1
    config.management_fee_rate = Decimal("0.005000")
    config.performance_fee_rate = Decimal("0.100000")
    config.high_water_mark_enabled = True
    config.minimum_aum = Decimal("3000.000000")
    config.created_at = datetime(2026, 3, 22, 0, 0, 0, tzinfo=timezone.utc)
    config.updated_at = datetime(2026, 3, 22, 0, 0, 0, tzinfo=timezone.utc)
    return config


# ---------------------------------------------------------------------------
# Test App fixtures
# ---------------------------------------------------------------------------


def _make_viewer_app() -> FastAPI:
    """viewer 権限でアクセスできる独立アプリ。"""
    app = FastAPI()
    app.include_router(billing_router)
    viewer = _make_viewer_user()
    app.dependency_overrides[require_viewer] = lambda: viewer
    app.dependency_overrides[get_db] = lambda: None
    return app


def _make_admin_app() -> FastAPI:
    """admin 権限でアクセスできる独立アプリ。"""
    app = FastAPI()
    app.include_router(billing_router)
    admin = _make_admin_user()
    app.dependency_overrides[require_admin] = lambda: admin
    app.dependency_overrides[get_db] = lambda: None
    return app


@pytest.fixture
def viewer_client() -> TestClient:
    """viewer 権限の TestClient。"""
    return TestClient(_make_viewer_app())


@pytest.fixture
def admin_client() -> TestClient:
    """admin 権限の TestClient。"""
    return TestClient(_make_admin_app())


# ---------------------------------------------------------------------------
# TestGetFeesEndpoint
# ---------------------------------------------------------------------------


class TestGetFeesEndpoint:
    """GET /api/billing/fees のテスト。"""

    def test_get_fees_endpoint(self, viewer_client: TestClient) -> None:
        """正常系: 手数料履歴が返ること。"""
        calc = _make_fee_calculation(user_id=1)

        with patch(
            "app.billing.router._billing_service.get_user_fee_history",
            return_value=[calc],
        ):
            response = viewer_client.get(
                "/api/billing/fees",
                params={"user_id": 1},
            )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["user_id"] == 1
        assert data[0]["period_type"] == "daily"

    def test_get_fees_endpoint_with_period_filter(self, viewer_client: TestClient) -> None:
        """クエリパラメータ period を指定してもエラーにならないこと。"""
        with patch(
            "app.billing.router._billing_service.get_user_fee_history",
            return_value=[],
        ):
            response = viewer_client.get(
                "/api/billing/fees",
                params={"user_id": 1, "period": "daily"},
            )

        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# TestGetSummaryEndpoint
# ---------------------------------------------------------------------------


class TestGetSummaryEndpoint:
    """GET /api/billing/summary のテスト。"""

    def test_get_summary_endpoint(self, viewer_client: TestClient) -> None:
        """正常系: サマリーが返ること。"""
        summary = FeeSummaryResponse(
            user_id=1,
            total_management_fee=Decimal("5.000000"),
            total_performance_fee=Decimal("10.000000"),
            total_fee=Decimal("15.000000"),
            calculation_count=3,
        )

        with patch(
            "app.billing.router._billing_service.get_user_fee_summary",
            return_value=summary,
        ):
            response = viewer_client.get(
                "/api/billing/summary",
                params={"user_id": 1},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == 1
        assert data["calculation_count"] == 3
        assert Decimal(data["total_fee"]) == Decimal("15.000000")


# ---------------------------------------------------------------------------
# TestGetConfigEndpoint
# ---------------------------------------------------------------------------


class TestGetConfigEndpoint:
    """GET /api/billing/config のテスト。"""

    def test_get_config_endpoint(self, viewer_client: TestClient) -> None:
        """正常系: FeeConfig が返ること。"""
        config = _make_fee_config()

        with patch(
            "app.billing.router._billing_service.get_active_fee_config",
            return_value=config,
        ):
            response = viewer_client.get("/api/billing/config")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["high_water_mark_enabled"] is True
        assert Decimal(data["management_fee_rate"]) == Decimal("0.005000")


# ---------------------------------------------------------------------------
# TestBatchDailyEndpoint
# ---------------------------------------------------------------------------


class TestBatchDailyEndpoint:
    """POST /api/billing/batch/daily のテスト。"""

    def test_batch_daily_admin_only(self, admin_client: TestClient) -> None:
        """管理者が実行した場合、正常に BatchResult が返ること。"""
        batch_result = BatchResult(processed_count=2, failed_count=0, errors=[])

        with patch(
            "app.billing.router._billing_service.run_daily_fee_batch",
            return_value=batch_result,
        ):
            response = admin_client.post(
                "/api/billing/batch/daily",
                json={"1": "10000.00", "2": "5000.00"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["processed_count"] == 2
        assert data["failed_count"] == 0
        assert data["errors"] == []

    def test_batch_daily_invalid_aum_value(self, admin_client: TestClient) -> None:
        """AUM 値が無効な場合は 422 を返すこと。"""
        response = admin_client.post(
            "/api/billing/batch/daily",
            json={"1": "not-a-number"},
        )
        assert response.status_code == 422

    def test_batch_daily_empty_map(self, admin_client: TestClient) -> None:
        """空の user_aum_map でも正常に 0 件処理として返ること。"""
        batch_result = BatchResult(processed_count=0, failed_count=0, errors=[])

        with patch(
            "app.billing.router._billing_service.run_daily_fee_batch",
            return_value=batch_result,
        ):
            response = admin_client.post(
                "/api/billing/batch/daily",
                json={},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["processed_count"] == 0


# ---------------------------------------------------------------------------
# TestAdminEndpoints (F-12)
# ---------------------------------------------------------------------------


class TestAdminUsersFees:
    """GET /api/billing/admin/users のテスト。"""

    def test_list_users_fees(self, admin_client: TestClient) -> None:
        """正常系: 全ユーザー手数料サマリーが返ること。"""
        rows = [
            AdminFeeUserRow(
                user_id=1,
                username="alice",
                email="alice@example.com",
                tier="LOWER",
                risk_mode="conservative",
                total_management_fee=Decimal("100.000000"),
                total_performance_fee=Decimal("50.000000"),
                total_fee=Decimal("150.000000"),
                last_calculation_date=date(2026, 4, 1),
                calculation_count=10,
            )
        ]
        with patch(
            "app.billing.router._billing_service.get_all_users_fee_overview",
            return_value=rows,
        ):
            response = admin_client.get("/api/billing/admin/users")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["user_id"] == 1
        assert data[0]["username"] == "alice"
        assert Decimal(data[0]["total_fee"]) == Decimal("150.000000")


class TestAdminMonthlyEntries:
    """GET /api/billing/admin/monthly-entries のテスト。"""

    def test_list_monthly_entries(self, admin_client: TestClient) -> None:
        """正常系: 月次明細が返ること。"""
        entries = [
            AdminFeeMonthlyEntry(
                id=1,
                user_id=1,
                username="alice",
                email="alice@example.com",
                tier="LOWER",
                risk_mode="conservative",
                aum_snapshot=Decimal("10000.000000"),
                management_fee=Decimal("0.136986"),
                performance_fee=Decimal("0.000000"),
                total_fee=Decimal("0.136986"),
                calculation_date=date(2026, 4, 1),
                period_type="daily",
            )
        ]
        with patch(
            "app.billing.router._billing_service.get_monthly_fee_entries",
            return_value=entries,
        ):
            response = admin_client.get(
                "/api/billing/admin/monthly-entries",
                params={"month": "2026-04"},
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["period_type"] == "daily"

    def test_invalid_month_format(self, admin_client: TestClient) -> None:
        """不正な月フォーマットは 422 を返すこと。"""
        response = admin_client.get(
            "/api/billing/admin/monthly-entries",
            params={"month": "2026/04"},
        )
        assert response.status_code == 422


class TestAdminMonthlySummary:
    """GET /api/billing/admin/monthly-summary のテスト。"""

    def test_get_monthly_summary(self, admin_client: TestClient) -> None:
        """正常系: 月次集計が返ること。"""
        summary = AdminMonthlyAggregate(
            month="2026-04",
            total_management_fee=Decimal("500.000000"),
            total_performance_fee=Decimal("200.000000"),
            total_fee=Decimal("700.000000"),
            user_count=3,
            entry_count=30,
        )
        with patch(
            "app.billing.router._billing_service.get_monthly_aggregate",
            return_value=summary,
        ):
            response = admin_client.get(
                "/api/billing/admin/monthly-summary",
                params={"month": "2026-04"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["month"] == "2026-04"
        assert data["user_count"] == 3
        assert Decimal(data["total_fee"]) == Decimal("700.000000")


class TestAdminRefund:
    """POST /api/billing/admin/{user_id}/refund のテスト。"""

    def test_create_refund(self, admin_client: TestClient) -> None:
        """正常系: リファンドが作成されること。"""
        refund_resp = AdminFeeRefundResponse(
            success=True,
            user_id=1,
            refund_amount=Decimal("5000"),
            reason="手数料過剰徴収のため",
            created_at=datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc),
        )
        with patch(
            "app.billing.router._billing_service.create_refund",
            return_value=refund_resp,
        ):
            response = admin_client.post(
                "/api/billing/admin/1/refund",
                json={"amount": "5000", "reason": "手数料過剰徴収のため"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert Decimal(data["refund_amount"]) == Decimal("5000")

    def test_refund_zero_amount_rejected(self, admin_client: TestClient) -> None:
        """amount=0 は 422 を返すこと。"""
        response = admin_client.post(
            "/api/billing/admin/1/refund",
            json={"amount": "0", "reason": "test"},
        )
        assert response.status_code == 422


class TestAdminExportCsv:
    """GET /api/billing/admin/export-csv のテスト。"""

    def test_export_csv(self, admin_client: TestClient) -> None:
        """正常系: CSV が返ること。"""
        csv_content = "user_id,username\n1,alice\n"
        with patch(
            "app.billing.router._billing_service.export_monthly_csv",
            return_value=csv_content,
        ):
            response = admin_client.get(
                "/api/billing/admin/export-csv",
                params={"month": "2026-04"},
            )

        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")
        assert "fees_2026-04.csv" in response.headers.get("content-disposition", "")
