# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/automation/router.py

"""
Automation Dashboard APIs

Phase 10: 運用ダッシュボード向けの監視・レポートAPIを提供する。
- GET /api/automation/status: 自動運用ステータス
- GET /api/automation/dashboard: ダッシュボードスナップショット
- GET /api/automation/reports/latest: 最新レポート

docs/04_api_design.md および docs/19_operations_runbook.md に準拠。
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.models import AIDecision
from app.ai.service import AIService
from app.auth.constants import ExecutionPolicy
from app.automation.workflow import process_pending_knowledge
from app.database import get_db
from app.exchange.router import get_exchange_service
from app.knowledge.service import KnowledgeService

from .monitoring_service import MonitoringService
from .reporting_service import ReportingService
from .schemas import (
    AutomationReportSummary,
    AutomationStatus,
    DashboardSnapshot,
    ReportPeriod,
    WorkflowRunResult,
)
from .state import get_monitoring_service

router = APIRouter(tags=["automation"])


def get_reporting_service(
    monitoring: MonitoringService = Depends(get_monitoring_service),
) -> ReportingService:
    """
    ReportingService の依存性注入用ファクトリ。

    MonitoringService に依存するため、Depends で取得する。
    """
    return ReportingService(monitoring=monitoring)


def _compute_next_scheduled_run(db: Session) -> Optional[datetime]:
    """ai_decisions の最新 created_at から次回スケジューラー実行時刻を算出する。"""
    stmt = select(AIDecision.created_at).order_by(AIDecision.created_at.desc()).limit(1)
    last_run: Optional[datetime] = db.scalars(stmt).first()
    if last_run is None:
        return None

    interval_hours = int(os.getenv("AI_JUDGMENT_INTERVAL_HOURS", "4"))
    next_run = last_run + timedelta(hours=interval_hours)

    now = datetime.now(timezone.utc)
    # Ensure next_run is timezone-aware
    if next_run.tzinfo is None:
        next_run = next_run.replace(tzinfo=timezone.utc)

    # If the computed time is already past, return now (run is imminent)
    if next_run <= now:
        return now

    return next_run


@router.get(
    "/status",
    response_model=AutomationStatus,
    summary="自動運用基盤のステータスサマリを取得",
)
def get_automation_status(
    monitoring: MonitoringService = Depends(get_monitoring_service),
    db: Session = Depends(get_db),
) -> AutomationStatus:
    """
    自動運用基盤の現在ステータスを返す。

    - 緊急停止状態かどうか
    - 直近のヘルスファクター・価格変動
    - 直近のイベント一覧

    運用者が「今この瞬間の全体状態」を把握するためのエンドポイント。
    docs/19_operations_runbook.md の「2.6 ダッシュボードの見方」を参照。
    """
    status = monitoring.get_status()
    next_run = _compute_next_scheduled_run(db)
    return status.model_copy(update={"next_scheduled_run": next_run})


@router.get(
    "/dashboard",
    response_model=DashboardSnapshot,
    summary="ダッシュボード用スナップショット（一定期間の集計 + 現在ステータス）",
)
def get_dashboard_snapshot(
    lookback_hours: int = Query(
        default=1,
        ge=1,
        le=24,
        description="集計対象期間（時間）。1〜24の範囲で指定。",
    ),
    monitoring: MonitoringService = Depends(get_monitoring_service),
) -> DashboardSnapshot:
    """
    監視ダッシュボード向けのスナップショットを生成する。

    - 現在の AutomationStatus
    - 直近 lookback_hours 時間に発生したメトリクスの集計結果

    Grafana やフロントエンドダッシュボードから定期的にポーリングして、
    運用状態を可視化するためのエンドポイント。

    docs/08_automation_rules.md の「6. 監視メトリクス一覧」で定義された
    メトリクスID（latency_*, portfolio_value_change_1d_pct,
    aave_health_factor_current など）を前提にしている。
    """
    return monitoring.build_dashboard_snapshot(lookback=timedelta(hours=lookback_hours))


@router.get(
    "/reports/latest",
    response_model=AutomationReportSummary,
    summary="最新のサマリレポート（定例確認用）",
)
def get_latest_report(
    period: Optional[ReportPeriod] = Query(
        default=None,
        description=(
            "レポート期間。未指定の場合は DAILY として扱う。DAILY: 当日分、WEEKLY: 直近7日分。"
        ),
    ),
    reporter: ReportingService = Depends(get_reporting_service),
) -> AutomationReportSummary:
    """
    直近のサマリレポートを取得する。

    - 対象期間（daily / weekly）のイベント件数・ヘルスファクター履歴を集計
    - 運用者が定例確認（毎日 / 毎週）で参照するためのエンドポイント

    実際の通知送信は `automation/jobs.py` 経由で行われるが、
    このエンドポイントからも同じ構造のレポートを取得できる。

    docs/19_operations_runbook.md の「2.6 ダッシュボードの見方」を参照。
    """
    if period is None:
        period = ReportPeriod.DAILY

    return reporter.generate_summary_report(period=period)


@router.post(
    "/workflow/run",
    response_model=WorkflowRunResult,
    summary="ペンディング知識アイテムに対して E2E ワークフローを実行",
)
def run_workflow(
    dry_run: bool = Query(default=True, description="If true, simulate trades"),
    db: Session = Depends(get_db),
    monitoring: MonitoringService = Depends(get_monitoring_service),
) -> WorkflowRunResult:
    """Trigger E2E workflow for pending knowledge items."""
    knowledge_service = KnowledgeService()
    ai_service = AIService()
    exchange_service = get_exchange_service()

    run_result = process_pending_knowledge(
        db,
        knowledge_service=knowledge_service,
        ai_service=ai_service,
        exchange_service=exchange_service,
        monitoring_service=monitoring,
        dry_run=dry_run,
        execution_policy=ExecutionPolicy.AUTO_EXECUTE.value,
    )

    # Sanitize error messages (no internal details in API response)
    sanitized_errors = [
        err.model_copy(update={"message": err.message[:200]}) for err in run_result.errors
    ]

    return run_result.model_copy(update={"errors": sanitized_errors})
