# backend/tests/test_automation_backup_service.py
from app.automation.backup_service import (
    BackupService,
    BackupStatus,
    BackupTargetType,
)


def test_backup_service_success() -> None:
    calls = {}

    def backup_notion() -> int:
        calls["notion"] = True
        return 10

    def backup_ai() -> int:
        calls["ai"] = True
        return 5

    def backup_trades() -> int:
        calls["trades"] = True
        return 2

    service = BackupService(
        backup_notion=backup_notion,
        backup_ai_analysis=backup_ai,
        backup_trades=backup_trades,
    )

    result = service.run_backup()

    assert result.status == BackupStatus.SUCCESS
    assert len(result.items) == 3
    assert sum(item.items_backed_up for item in result.items) == 17
    assert all(item.error is None for item in result.items)
    assert calls == {"notion": True, "ai": True, "trades": True}


def test_backup_service_partial_failure() -> None:
    def backup_ok() -> int:
        return 3

    def backup_fail() -> int:
        raise RuntimeError("boom")

    service = BackupService(
        backup_notion=backup_ok,
        backup_ai_analysis=backup_fail,
    )

    result = service.run_backup()

    assert result.status == BackupStatus.PARTIAL
    assert len(result.items) == 2

    errors = [item for item in result.items if item.error]
    oks = [item for item in result.items if not item.error]

    assert len(errors) == 1
    assert len(oks) == 1
    assert "boom" in errors[0].error  # type: ignore[operator]


def test_backup_service_all_failure_when_no_handlers() -> None:
    service = BackupService()

    result = service.run_backup()

    assert result.status == BackupStatus.FAILURE
    assert result.items == []
    assert "No backup handlers configured" in result.message
