# backend/tests/test_automation_jobs.py
from datetime import datetime, timezone
from unittest.mock import patch

from app.automation.backup_service import BackupService
from app.automation.jobs import _normalize_now, run_backup_only, run_daily_jobs, run_weekly_jobs
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


# ---------------------------------------------------------------------------
# _normalize_now
# ---------------------------------------------------------------------------


def test_normalize_now_returns_utc_when_none() -> None:
    result = _normalize_now(None)
    assert result.tzinfo is not None


def test_normalize_now_attaches_utc_to_naive() -> None:
    naive = datetime(2025, 6, 15, 12, 0, 0)
    result = _normalize_now(naive)
    assert result.tzinfo is not None
    assert result.year == 2025
    assert result.month == 6


def test_normalize_now_preserves_aware_datetime() -> None:
    aware = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    result = _normalize_now(aware)
    assert result == aware


# ---------------------------------------------------------------------------
# run_weekly_jobs with backup
# ---------------------------------------------------------------------------


def test_run_weekly_jobs_with_backup_enabled() -> None:
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
        run_backup=True,
    )

    assert len(notification.messages) == 1
    assert backup.ran is True


# ---------------------------------------------------------------------------
# main() CLI entry point
# ---------------------------------------------------------------------------


def test_main_daily_job() -> None:
    """main() with 'daily' arg runs run_daily_jobs."""
    with (
        patch("sys.argv", ["jobs", "daily"]),
        patch("app.automation.jobs.run_daily_jobs") as mock_daily,
        patch("app.automation.jobs.run_weekly_jobs") as mock_weekly,
        patch("app.automation.jobs.get_notification_service") as mock_notif_factory,
    ):
        mock_notif_factory.return_value = DummyNotificationService()
        from app.automation.jobs import main

        main()
        mock_daily.assert_called_once()
        mock_weekly.assert_not_called()


def test_main_weekly_job() -> None:
    """main() with 'weekly' arg runs run_weekly_jobs."""
    with (
        patch("sys.argv", ["jobs", "weekly"]),
        patch("app.automation.jobs.run_daily_jobs") as mock_daily,
        patch("app.automation.jobs.run_weekly_jobs") as mock_weekly,
        patch("app.automation.jobs.get_notification_service") as mock_notif_factory,
    ):
        mock_notif_factory.return_value = DummyNotificationService()
        from app.automation.jobs import main

        main()
        mock_weekly.assert_called_once()
        mock_daily.assert_not_called()


def test_main_backup_only_job() -> None:
    """main() with 'backup-only' arg runs run_backup_only via BackupService."""
    with (
        patch("sys.argv", ["jobs", "backup-only"]),
        patch("app.automation.jobs.BackupService") as mock_backup_cls,
        patch("app.automation.jobs.run_backup_only") as mock_backup_only,
        patch("app.automation.jobs.get_notification_service") as mock_notif_factory,
    ):
        mock_notif_factory.return_value = DummyNotificationService()
        mock_backup_cls.return_value = DummyBackupService()
        from app.automation.jobs import main

        main()
        mock_backup_only.assert_called_once()
