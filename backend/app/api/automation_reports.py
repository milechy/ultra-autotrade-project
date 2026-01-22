from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.automation.reporting_service import ReportingService
from app.automation.schemas import AutomationReportSummary

logger = logging.getLogger(__name__)

router = APIRouter(tags=["automation-reports"])


def get_reporting_service() -> ReportingService:
    return ReportingService()


@router.get(
    "/latest",
    response_model=AutomationReportSummary,
    summary="Get latest automation summary report",
)
def get_latest_report(
    reporting_service: ReportingService = Depends(get_reporting_service),
) -> AutomationReportSummary:
    """
    latest 用エンドポイント。

    - generate_summary_report(period=...) の period 必須問題を避けるため、
      generate_latest_summary() を呼ぶ。
    """
    try:
        return reporting_service.generate_latest_summary()
    except Exception as e:
        logger.exception("Failed to generate summary report")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate summary report: {e}",
        ) from e
