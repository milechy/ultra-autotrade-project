# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/automation/test_funding_detection.py
"""run_funding_detection_once (S2 着金検知) のユニットテスト。

- 残高 >= amount_usd → approved + approved_at + 着金通知1件
- 残高 < amount_usd → awaiting_funds のまま・通知なし
- 残高取得失敗(None) → skip (awaiting_funds のまま)
- funding window 切れ(expires_at < now) → expired (残高に関わらず)
ScheduledTaskManager.start/stop_funding_detection の二重起動 guard も検証。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pytest

from app.automation.scheduled_tasks import (
    ScheduledTaskManager,
    run_funding_detection_once,
)


def _make_awaiting_proposal(
    id_: int = 1,
    amount_usd: Decimal = Decimal("1000"),
    minutes_until_expiry: int = 60,
    user_id: int = 42,
) -> MagicMock:
    now = datetime.now(timezone.utc)
    p = MagicMock()
    p.id = id_
    p.status = "awaiting_funds"
    p.amount_usd = amount_usd
    p.expires_at = now + timedelta(minutes=minutes_until_expiry)
    p.user_id = user_id
    p.operation = "SUPPLY"
    p.asset = "USDC"
    p.approved_at = None
    return p


def _run_once(
    proposals: list[Any],
    balance: Optional[Decimal],
    wallet: str = "0xabc0000000000000000000000000000000000000",
) -> tuple[int, list[Any], MagicMock]:
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = proposals
    mock_user = MagicMock()
    mock_user.smart_wallet_address = wallet
    mock_user.wallet_address = None
    mock_db.get.return_value = mock_user
    sent: list[Any] = []
    with (
        patch("app.database.SessionLocal", return_value=mock_db),
        patch("app.aave.balance.read_wallet_usdc_balance", return_value=balance),
        patch("app.notifications.factory.get_notification_service") as mock_get_svc,
    ):
        mock_get_svc.return_value.send.side_effect = lambda m: sent.append(m)
        changed = run_funding_detection_once()
    return changed, sent, mock_db


class TestRunFundingDetectionOnce:
    def test_approves_when_balance_sufficient(self) -> None:
        p = _make_awaiting_proposal(amount_usd=Decimal("1000"))
        changed, sent, db = _run_once([p], balance=Decimal("1500"))
        assert p.status == "approved"
        assert p.approved_at is not None
        assert changed == 1
        assert len(sent) == 1  # 着金通知
        db.commit.assert_called()

    def test_approves_at_exact_amount(self) -> None:
        p = _make_awaiting_proposal(amount_usd=Decimal("1000"))
        changed, _sent, _db = _run_once([p], balance=Decimal("1000"))
        assert p.status == "approved"  # >= なので一致でも承認
        assert changed == 1

    def test_stays_awaiting_when_insufficient(self) -> None:
        p = _make_awaiting_proposal(amount_usd=Decimal("1000"))
        changed, sent, _db = _run_once([p], balance=Decimal("999.99"))
        assert p.status == "awaiting_funds"
        assert changed == 0
        assert len(sent) == 0

    def test_skips_when_balance_none(self) -> None:
        p = _make_awaiting_proposal()
        changed, sent, _db = _run_once([p], balance=None)
        assert p.status == "awaiting_funds"
        assert changed == 0
        assert len(sent) == 0

    def test_expires_when_funding_window_passed(self) -> None:
        # expires_at が過去 → 残高十分でも expired(残高チェック前に倒れる)
        p = _make_awaiting_proposal(minutes_until_expiry=-10)
        changed, _sent, _db = _run_once([p], balance=Decimal("9999"))
        assert p.status == "expired"
        assert changed == 1


class TestFundingDetectionManager:
    @pytest.mark.asyncio
    async def test_start_stop(self) -> None:
        mgr = ScheduledTaskManager()
        assert not mgr.is_funding_detection_running
        await mgr.start_funding_detection(interval_seconds=3600)
        assert mgr.is_funding_detection_running
        with pytest.raises(RuntimeError):
            await mgr.start_funding_detection(interval_seconds=3600)  # 二重起動 guard
        await mgr.stop_funding_detection()
        assert not mgr.is_funding_detection_running
