# backend/app/api/automation_dashboard.py
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from app.automation.monitoring_service import MonitoringService
from app.automation.reporting_service import ReportingService
from app.automation.schemas import (
    AutomationReportSummary,
    AutomationStatus,
    DashboardSnapshot,
)

router = APIRouter(tags=["automation-dashboard"])


# Dependency providers (Phase11)
# - テスト時に FastAPI dependency_overrides で差し替え可能にする
def get_monitoring_service() -> MonitoringService:
    return MonitoringService()


def get_reporting_service() -> ReportingService:
    return ReportingService()


@router.get(
    "/dashboard",
    response_model=DashboardSnapshot,
    summary="Get automation dashboard snapshot",
)
def get_dashboard_snapshot(
    lookback_hours: int = Query(
        1,
        ge=1,
        le=24,
        description="Lookback window in hours for dashboard metrics",
    ),
    monitoring_service: MonitoringService = Depends(get_monitoring_service),
) -> DashboardSnapshot:
    """
    Phase10までに確立した DashboardSnapshot 契約をそのまま返す。
    """
    now = datetime.now(timezone.utc)
    try:
        # Phase10 仕様: build_dashboard_snapshot(lookback, now)
        return monitoring_service.build_dashboard_snapshot(
            lookback=lookback_hours,
            now=now,
        )
    except Exception as e:
        # API層の責務：例外をHTTPに変換（内部事情はdetailに閉じ込める）
        raise HTTPException(status_code=500, detail=f"Failed to build dashboard snapshot: {e}") from e


@router.get(
    "/status",
    response_model=AutomationStatus,
    summary="Get current automation status",
)
def get_automation_status(
    monitoring_service: MonitoringService = Depends(get_monitoring_service),
) -> AutomationStatus:
    """
    Phase10までに確立した AutomationStatus 契約をそのまま返す。
    """
    try:
        return monitoring_service.get_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get automation status: {e}") from e


@router.get(
    "/reports/latest",
    response_model=AutomationReportSummary,
    summary="Get latest automation summary report",
)
def get_latest_report(
    reporting_service: ReportingService = Depends(get_reporting_service),
) -> AutomationReportSummary:
    """
    Phase10までに確立した AutomationReportSummary 契約をそのまま返す。
    """
    try:
        return reporting_service.generate_summary_report()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate summary report: {e}") from e
