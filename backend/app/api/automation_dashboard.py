# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai.service import AIService
from app.auth.dependencies import require_active_user, require_admin, require_viewer
from app.auth.models import User
from app.automation.monitoring_service import MonitoringService
from app.automation.reporting_service import ReportingService
from app.automation.schemas import (
    AutomationReportSummary,
    AutomationStatus,
    DashboardSnapshot,
    WorkflowRunResult,
)
from app.automation.state import get_monitoring_service
from app.automation.workflow import process_pending_knowledge
from app.database import get_db
from app.exchange.router import get_exchange_service
from app.knowledge.service import KnowledgeService

router = APIRouter(tags=["automation-dashboard"])


# Dependency providers (Phase11)
# - テスト時に FastAPI dependency_overrides で差し替え可能にする
# - get_monitoring_service は state.py のシングルトンを使用（毎回新規生成しない）


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
    current_user: User = Depends(require_viewer),
) -> DashboardSnapshot:
    """
    Phase10までに確立した DashboardSnapshot 契約をそのまま返す。

    重要:
    - MonitoringService.build_dashboard_snapshot は lookback: timedelta を受け取る前提。
    - API層で lookback_hours(int) -> timedelta(hours=lookback_hours) に変換して渡す。
    """
    now = datetime.now(timezone.utc)
    try:
        lookback = timedelta(hours=lookback_hours)
        return monitoring_service.build_dashboard_snapshot(
            lookback=lookback,
            now=now,
        )
    except Exception as e:
        # API層の責務：例外をHTTPに変換（内部事情はdetailに閉じ込める）
        raise HTTPException(
            status_code=500,
            detail=f"Failed to build dashboard snapshot: {e}",
        ) from e


@router.get(
    "/status",
    response_model=AutomationStatus,
    summary="Get current automation status",
)
def get_automation_status(
    monitoring_service: MonitoringService = Depends(get_monitoring_service),
    current_user: User = Depends(require_viewer),
) -> AutomationStatus:
    """
    Phase10までに確立した AutomationStatus 契約をそのまま返す。
    """
    try:
        return monitoring_service.get_status()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get automation status: {e}",
        ) from e


@router.get(
    "/reports/latest",
    response_model=AutomationReportSummary,
    summary="Get latest automation summary report",
)
def get_latest_report(
    reporting_service: ReportingService = Depends(get_reporting_service),
    current_user: User = Depends(require_viewer),
) -> AutomationReportSummary:
    """
    Phase10までに確立した AutomationReportSummary 契約をそのまま返す。

    重要:
    - ReportingService.generate_summary_report は period 必須のため、
      latest 用の専用メソッド generate_latest_summary() を呼ぶ。
    """
    try:
        return reporting_service.generate_latest_summary()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate summary report: {e}",
        ) from e


@router.post(
    "/workflow/run",
    response_model=WorkflowRunResult,
    summary="ペンディング知識アイテムに対して E2E ワークフローを実行",
)
def run_workflow(
    dry_run: bool = Query(default=True, description="If true, simulate trades"),
    db: Session = Depends(get_db),
    monitoring_service: MonitoringService = Depends(get_monitoring_service),
    current_user: User = Depends(require_admin),
) -> WorkflowRunResult:
    """Knowledge Hub の pending アイテムを RAG→AI→Exchange の E2E パイプラインで処理する。"""
    knowledge_service = KnowledgeService()
    ai_service = AIService()
    exchange_service = get_exchange_service()

    run_result = process_pending_knowledge(
        db,
        knowledge_service=knowledge_service,
        ai_service=ai_service,
        exchange_service=exchange_service,
        monitoring_service=monitoring_service,
        dry_run=dry_run,
    )

    sanitized_errors = [
        err.model_copy(update={"message": err.message[:200]}) for err in run_result.errors
    ]
    return run_result.model_copy(update={"errors": sanitized_errors})


class EmergencyStopRequest(BaseModel):
    """POST /emergency-stop のリクエストボディ。"""

    reason: str = "Manual emergency stop via API"


@router.post(
    "/emergency-stop",
    summary="緊急停止",
)
def emergency_stop_api(
    request: EmergencyStopRequest = Body(default=EmergencyStopRequest()),
    monitoring_service: MonitoringService = Depends(get_monitoring_service),
    current_user: User = Depends(require_active_user),
) -> dict[str, Any]:
    """全ての自動取引を即時停止する。"""
    monitoring_service.activate_emergency_stop(
        reason=f"{request.reason} (user_id={current_user.id})"
    )
    return {
        "status": "stopped",
        "message": "緊急停止が実行されました。全ての自動取引が停止されています。",
    }


@router.post("/emergency-stop/resume", summary="緊急停止解除")
def resume_emergency_stop_api(
    monitoring_service: MonitoringService = Depends(get_monitoring_service),
    current_user: User = Depends(require_active_user),
) -> dict[str, Any]:
    """
    手動緊急停止を解除する。
    HF < 1.6 など自動トリガーによる停止は、HF が改善しない限り再度停止される。
    """
    monitoring_service.clear_emergency_stop()
    return {
        "status": "resumed",
        "message": "緊急停止を解除しました。HF等の自動条件が未改善の場合は再停止される可能性があります。",
    }


@router.post("/pause", summary="ユーザー運用一時停止")
def pause_automation(
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """ユーザー単位の運用を一時停止する（全体緊急停止とは別）。"""
    current_user.is_active = False
    db.add(current_user)
    db.commit()
    return {"message": "paused", "is_active": False}


@router.post("/resume", summary="ユーザー運用再開")
def resume_automation(
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """ユーザー単位の運用を再開する。"""
    current_user.is_active = True
    db.add(current_user)
    db.commit()
    return {"message": "resumed", "is_active": True}
