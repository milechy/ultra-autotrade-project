# backend/app/automation/jobs.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.automation.reporting_service import ReportingService
from app.automation.schemas import ReportPeriod
from app.notifications.factory import get_notification_service
from app.notifications.schemas import NotificationChannel
from app.notifications.service import CompositeNotificationService

from .backup_service import BackupService


def _normalize_now(now: Optional[datetime]) -> datetime:
    """
    naive な datetime が渡された場合でも UTC として扱うヘルパー。
    """
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now


def run_daily_jobs(
    *,
    reporter: Optional[ReportingService] = None,
    notification_service: Optional[CompositeNotificationService] = None,
    backup_service: Optional[BackupService] = None,
    channel: NotificationChannel = NotificationChannel.INTERNAL_LOG,
    now: Optional[datetime] = None,
    run_backup: bool = False,
) -> None:
    """
    日次の自動ジョブを実行する。

    - MonitoringService のイベントを集計して AutomationReportSummary を生成
    - そのサマリから NotificationMessage を構築して通知送信
    - オプションでバックアップ処理を実行
    """
    reporter = reporter or ReportingService()
    notification_service = notification_service or get_notification_service()
    now_norm = _normalize_now(now)

    summary = reporter.generate_summary_report(ReportPeriod.DAILY, now=now_norm)
    message = ReportingService.build_notification_message(summary, channel=channel)
    notification_service.send(message)

    if run_backup and backup_service is not None:
        backup_service.run_backup()


def run_weekly_jobs(
    *,
    reporter: Optional[ReportingService] = None,
    notification_service: Optional[CompositeNotificationService] = None,
    backup_service: Optional[BackupService] = None,
    channel: NotificationChannel = NotificationChannel.INTERNAL_LOG,
    now: Optional[datetime] = None,
    run_backup: bool = False,
) -> None:
    """
    週次の自動ジョブを実行する。

    現時点では日次ジョブと同様に:
    - サマリレポート生成
    - 通知送信
    - （オプションで）バックアップ実行
    を行う。
    """
    reporter = reporter or ReportingService()
    notification_service = notification_service or get_notification_service()
    now_norm = _normalize_now(now)

    summary = reporter.generate_summary_report(ReportPeriod.WEEKLY, now=now_norm)
    message = ReportingService.build_notification_message(summary, channel=channel)
    notification_service.send(message)

    if run_backup and backup_service is not None:
        backup_service.run_backup()


def run_backup_only(*, backup_service: BackupService) -> None:
    """
    バックアップだけを実行するシンプルなヘルパー。

    cron などから「バックアップだけ走らせたい」場合に利用する。
    """
    backup_service.run_backup()


def main() -> None:
    """
    簡易 CLI エントリーポイント。

    例:
        python -m app.automation.jobs daily
        python -m app.automation.jobs weekly
        python -m app.automation.jobs backup-only

    本番運用では、scripts/backup.sh / scripts/monitor.sh から呼び出す想定。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Automation jobs runner")
    parser.add_argument(
        "job",
        choices=["daily", "weekly", "backup-only"],
        help="実行するジョブ種別",
    )
    args = parser.parse_args()

    reporter = ReportingService()
    notification_service = get_notification_service()

    if args.job == "daily":
        run_daily_jobs(
            reporter=reporter,
            notification_service=notification_service,
        )
    elif args.job == "weekly":
        run_weekly_jobs(
            reporter=reporter,
            notification_service=notification_service,
        )
    elif args.job == "backup-only":
        # バックアップの具体的なハンドラは、後続フェーズで注入する想定。
        backup_service = BackupService()
        run_backup_only(backup_service=backup_service)


if __name__ == "__main__":
    main()
