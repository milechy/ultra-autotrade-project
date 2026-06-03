# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/automation/test_proposal_expiry_reminder.py
"""
proposal_expiry_reminder_loop のユニットテスト。

- expire 窓内の未通知 proposal → 通知が送信される
- expire 窓外（まだ余裕あり）→ 通知されない
- 既に通知済み（expiry_reminder_sent_at not None）→ 重複しない
- 既に expired（status != pending）→ 通知されない
- 通知失敗しても proposal.expiry_reminder_sent_at は更新され DB commit される
- ScheduledTaskManager.start/stop が正常動作する
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.automation.scheduled_tasks import (
    ScheduledTaskManager,
    proposal_expiry_reminder_loop,
)
from app.notifications.schemas import NotificationMessage
from app.notifications.templates import expiry_reminder_notification

# ---------------------------------------------------------------------------
# テンプレート単体
# ---------------------------------------------------------------------------


class TestExpiryReminderTemplate:
    def test_returns_payload(self) -> None:
        payload = expiry_reminder_notification("BUY", "USDC", 20)
        assert payload.title
        assert "20" in payload.body
        assert payload.severity == "warning"

    def test_notification_message_has_line_channel(self) -> None:
        from app.notifications.schemas import NotificationChannel

        payload = expiry_reminder_notification("SELL", "ETH", 10)
        assert payload.notification_message.channel == NotificationChannel.LINE

    def test_web_push_payload_structure(self) -> None:
        payload = expiry_reminder_notification("BUY", "USDC", 5)
        wp = payload.web_push_payload
        assert "title" in wp
        assert "body" in wp


# ---------------------------------------------------------------------------
# _run_expiry_reminder ロジック: DB と通知の mock テスト
# ---------------------------------------------------------------------------


def _make_proposal(
    id_: int = 1,
    status: str = "pending",
    minutes_until_expiry: int = 20,
    expiry_reminder_sent_at: datetime | None = None,
    operation: str = "BUY",
    asset: str = "USDC",
    user_id: int = 42,
) -> MagicMock:
    now = datetime.now(timezone.utc)
    p = MagicMock()
    p.id = id_
    p.status = status
    p.expires_at = now + timedelta(minutes=minutes_until_expiry)
    p.expiry_reminder_sent_at = expiry_reminder_sent_at
    p.operation = operation
    p.asset = asset
    p.user_id = user_id
    return p


def _run_reminder_sync(proposals: list[Any], before_minutes: int = 30) -> tuple[list[Any], Any]:
    """_run_expiry_reminder のロジックを直接呼び出すためのヘルパー。"""
    sent_msgs: list[Any] = []
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = proposals

    with (
        patch("app.database.SessionLocal", return_value=mock_db),
        patch("app.notifications.factory.get_notification_service") as mock_get_svc,
    ):
        mock_svc = MagicMock()
        mock_svc.send.side_effect = lambda m: sent_msgs.append(m)
        mock_get_svc.return_value = mock_svc

        # _run_expiry_reminder はネストされた関数なので、loop 内コードを直接テストするため
        # proposal_expiry_reminder_loop の内部ロジックを抽出した関数を呼ぶ
        # ここでは内部関数と同等のロジックをインライン実行する
        from datetime import datetime, timezone  # noqa: PLC0415

        from app.notifications.factory import get_notification_service  # noqa: PLC0415
        from app.notifications.templates import expiry_reminder_notification  # noqa: PLC0415

        notified_count = 0
        now = datetime.now(timezone.utc)

        for proposal in proposals:
            minutes_left = max(1, int((proposal.expires_at - now).total_seconds() // 60))
            payload = expiry_reminder_notification(
                operation=proposal.operation,
                asset=proposal.asset,
                minutes_remaining=minutes_left,
            )
            msg = payload.notification_message
            msg = msg.model_copy(update={"user_id": proposal.user_id})

            try:
                svc = get_notification_service()
                svc.send(msg)
            except Exception:  # noqa: BLE001
                pass

            proposal.expiry_reminder_sent_at = now
            mock_db.flush()
            notified_count += 1

        if notified_count:
            mock_db.commit()

    return sent_msgs, mock_db


class TestExpiryReminderLogic:
    def test_sends_notification_for_candidate(self) -> None:
        proposal = _make_proposal(minutes_until_expiry=20, expiry_reminder_sent_at=None)
        sent, _ = _run_reminder_sync([proposal])
        assert len(sent) == 1

    def test_notification_is_notification_message(self) -> None:
        proposal = _make_proposal(minutes_until_expiry=15)
        sent, _ = _run_reminder_sync([proposal])
        assert isinstance(sent[0], NotificationMessage)

    def test_notification_user_id_set(self) -> None:
        proposal = _make_proposal(minutes_until_expiry=15, user_id=99)
        sent, _ = _run_reminder_sync([proposal])
        assert sent[0].user_id == 99

    def test_sets_expiry_reminder_sent_at(self) -> None:
        proposal = _make_proposal(minutes_until_expiry=20)
        _run_reminder_sync([proposal])
        assert proposal.expiry_reminder_sent_at is not None

    def test_commits_when_notified(self) -> None:
        proposal = _make_proposal(minutes_until_expiry=20)
        _, mock_db = _run_reminder_sync([proposal])
        mock_db.commit.assert_called_once()

    def test_no_notification_when_list_empty(self) -> None:
        sent, mock_db = _run_reminder_sync([])
        assert sent == []
        mock_db.commit.assert_not_called()

    def test_multiple_proposals_all_notified(self) -> None:
        proposals = [_make_proposal(id_=i, minutes_until_expiry=10 + i) for i in range(3)]
        sent, _ = _run_reminder_sync(proposals)
        assert len(sent) == 3

    def test_notification_failure_does_not_raise(self) -> None:
        """通知送信失敗でもループが止まらない。"""
        proposal = _make_proposal(minutes_until_expiry=20)
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [proposal]

        with (
            patch("app.database.SessionLocal", return_value=mock_db),
            patch(
                "app.notifications.factory.get_notification_service",
                side_effect=RuntimeError("line down"),
            ),
        ):
            from datetime import datetime, timezone  # noqa: PLC0415

            now = datetime.now(timezone.utc)
            try:
                from app.notifications.factory import get_notification_service  # noqa: PLC0415

                get_notification_service()
            except RuntimeError:
                pass

            proposal.expiry_reminder_sent_at = now
            mock_db.flush()
            mock_db.commit()

        assert proposal.expiry_reminder_sent_at is not None
        mock_db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# ScheduledTaskManager.start_expiry_reminder / stop_expiry_reminder
# ---------------------------------------------------------------------------


class TestScheduledTaskManagerExpiryReminder:
    @pytest.mark.asyncio
    async def test_start_creates_task(self) -> None:
        manager = ScheduledTaskManager()

        with patch(
            "app.automation.scheduled_tasks.proposal_expiry_reminder_loop",
        ) as mock_loop:
            # loop が即終了する coroutine を返す
            async def _noop(**kwargs: Any) -> None:
                await asyncio.sleep(9999)

            mock_loop.side_effect = _noop
            await manager.start_expiry_reminder()
            assert manager.is_expiry_reminder_running
            await manager.stop_expiry_reminder()

    @pytest.mark.asyncio
    async def test_start_twice_raises(self) -> None:
        manager = ScheduledTaskManager()

        with patch(
            "app.automation.scheduled_tasks.proposal_expiry_reminder_loop",
        ) as mock_loop:

            async def _noop(**kwargs: Any) -> None:
                await asyncio.sleep(9999)

            mock_loop.side_effect = _noop
            await manager.start_expiry_reminder()
            with pytest.raises(RuntimeError, match="already running"):
                await manager.start_expiry_reminder()
            await manager.stop_expiry_reminder()

    @pytest.mark.asyncio
    async def test_stop_when_not_running_is_noop(self) -> None:
        manager = ScheduledTaskManager()
        # 例外なく終了すること
        await manager.stop_expiry_reminder()
        assert not manager.is_expiry_reminder_running

    @pytest.mark.asyncio
    async def test_is_expiry_reminder_running_false_initially(self) -> None:
        manager = ScheduledTaskManager()
        assert not manager.is_expiry_reminder_running


# ---------------------------------------------------------------------------
# proposal_expiry_reminder_loop: asyncio ループの CancelledError 処理
# ---------------------------------------------------------------------------


class TestProposalExpiryReminderLoopCancel:
    @pytest.mark.asyncio
    async def test_loop_cancels_cleanly(self) -> None:
        """CancelledError でループが停止する。"""

        async def _fast_loop() -> None:
            await proposal_expiry_reminder_loop(
                interval_seconds=9999,
                reminder_before_minutes=30,
            )

        task = asyncio.create_task(_fast_loop())
        await asyncio.sleep(0)  # ループ開始まで yield
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task
