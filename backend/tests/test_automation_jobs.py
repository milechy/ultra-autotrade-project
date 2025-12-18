# backend/tests/test_automation_jobs.py
from datetime import datetime, timezone

from app.automation.backup_service import BackupService
from app.automation.jobs import run_backup_only, run_daily_jobs, run_weekly_jobs
from app.automation.reporting_service import ReportingService
from app.notifications.schemas import NotificationChannel


class DummyNotificationService:
    def __init__(self) -> None:
        self.messages = []

    def send(self, message) -> None:
        self.messages.append(message)


class DummyBackupService(BackupService):
    def __init__(self) -> None:
        super().__init__()
        self.ran = False

    def run_backup(self):
        self.ran = True
        return super().run_backup()


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


def test_run_daily_jobs_sends_notification_and_optionally_runs_backup() -> None:
    reporter = ReportingService()
    notification = DummyNotificationService()
    backup = DummyBackupService()

    now = _utc(2025, 1, 2)

    # backup あり
    run_daily_jobs(
        reporter=reporter,
        notification_service=notification,
        backup_service=backup,
        channel=NotificationChannel.INTERNAL_LOG,
        now=now,
        run_backup=True,
    )

    assert len(notification.messages) == 1
    assert backup.ran is True


def test_run_weekly_jobs_sends_notification_without_backup_by_default() -> None:
    reporter = ReportingService()
    notification = DummyNotificationService()
    backup = DummyBackupService()

    now = _utc(2025, 1, 8)

    run_weekly_jobs(
        reporter=reporter,
        notification_service=notification,
        backup_service=backup,
        channel=NotificationChannel.INTERNAL_LOG,
        now=now,
        run_backup=False,
    )

    assert len(notification.messages) == 1
    assert backup.ran is False


def test_run_backup_only_uses_provided_service() -> None:
    backup = DummyBackupService()

    run_backup_only(backup_service=backup)

    assert backup.ran is True
