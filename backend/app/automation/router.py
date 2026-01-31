# backend/app/automation/router.py

"""
Automation Dashboard APIs

Phase 10: 運用ダッシュボード向けの監視・レポートAPIを提供する。
- GET /api/automation/status: 自動運用ステータス
- GET /api/automation/dashboard: ダッシュボードスナップショット  
- GET /api/automation/reports/latest: 最新レポート

docs/04_api_design.md および docs/19_operations_runbook.md に準拠。
"""

from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query

from .monitoring_service import MonitoringService
from .reporting_service import ReportingService
from .schemas import (
    AutomationStatus,
    DashboardSnapshot,
    AutomationReportSummary,
    ReportPeriod,
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


@router.get(
    "/status",
    response_model=AutomationStatus,
    summary="自動運用基盤のステータスサマリを取得",
)
def get_automation_status(
    monitoring: MonitoringService = Depends(get_monitoring_service),
) -> AutomationStatus:
    """
    自動運用基盤の現在ステータスを返す。
    
    - 緊急停止状態かどうか
    - 直近のヘルスファクター・価格変動
    - 直近のイベント一覧
    
    運用者が「今この瞬間の全体状態」を把握するためのエンドポイント。
    docs/19_operations_runbook.md の「2.6 ダッシュボードの見方」を参照。
    """
    return monitoring.get_status()


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
    return monitoring.build_dashboard_snapshot(
        lookback=timedelta(hours=lookback_hours)
    )


@router.get(
    "/reports/latest",
    response_model=AutomationReportSummary,
    summary="最新のサマリレポート（定例確認用）",
)
def get_latest_report(
    period: Optional[ReportPeriod] = Query(
        default=None,
        description=(
            "レポート期間。未指定の場合は DAILY として扱う。"
            "DAILY: 当日分、WEEKLY: 直近7日分。"
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
