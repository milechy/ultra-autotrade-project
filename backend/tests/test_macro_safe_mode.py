# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Tests for MacroSafeMode."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.automation.macro_safe_mode import MacroEvent, MacroSafeMode

FOMC_DATE = datetime(2026, 3, 18, 18, 0, tzinfo=timezone.utc)

SINGLE_EVENT = [MacroEvent(name="FOMC Test", event_date=FOMC_DATE, hours_before=4, hours_after=2)]


@pytest.fixture
def mode() -> MacroSafeMode:
    return MacroSafeMode(events=SINGLE_EVENT)


def test_active_before_event(mode: MacroSafeMode) -> None:
    """Safe mode active 2h before FOMC."""
    now = FOMC_DATE - timedelta(hours=2)
    status = mode.is_safe_mode_active(now=now)
    assert status.active is True
    assert status.active_event is not None
    assert status.active_event.name == "FOMC Test"


def test_active_after_event(mode: MacroSafeMode) -> None:
    """Safe mode active 1h after FOMC."""
    now = FOMC_DATE + timedelta(hours=1)
    status = mode.is_safe_mode_active(now=now)
    assert status.active is True


def test_inactive_well_before_event(mode: MacroSafeMode) -> None:
    """Safe mode NOT active 5h before FOMC (outside 4h window)."""
    now = FOMC_DATE - timedelta(hours=5)
    status = mode.is_safe_mode_active(now=now)
    assert status.active is False
    assert status.active_event is None


def test_inactive_well_after_event(mode: MacroSafeMode) -> None:
    """Safe mode NOT active 3h after FOMC (outside 2h window)."""
    now = FOMC_DATE + timedelta(hours=3)
    status = mode.is_safe_mode_active(now=now)
    assert status.active is False


def test_no_events(mode: MacroSafeMode) -> None:
    """Empty event list → always inactive."""
    empty_mode = MacroSafeMode(events=[])
    status = empty_mode.is_safe_mode_active(now=FOMC_DATE)
    assert status.active is False
    assert status.next_event is None


def test_upcoming_events(mode: MacroSafeMode) -> None:
    """get_upcoming_events returns events within window."""
    now = FOMC_DATE - timedelta(days=3)
    events = mode.get_upcoming_events(now=now, days=7)
    assert len(events) == 1
    assert events[0].name == "FOMC Test"


def test_upcoming_events_outside_window(mode: MacroSafeMode) -> None:
    """get_upcoming_events returns nothing if event is beyond days window."""
    now = FOMC_DATE - timedelta(days=10)
    events = mode.get_upcoming_events(now=now, days=7)
    assert len(events) == 0


def test_next_event_populated(mode: MacroSafeMode) -> None:
    """next_event is populated when safe mode is inactive."""
    now = FOMC_DATE - timedelta(hours=5)
    status = mode.is_safe_mode_active(now=now)
    assert status.active is False
    assert status.next_event is not None
    assert status.next_event.name == "FOMC Test"