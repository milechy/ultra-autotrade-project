from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel


class MacroEvent(BaseModel):
    name: str
    event_date: datetime
    hours_before: int = 4
    hours_after: int = 2


class SafeModeStatus(BaseModel):
    active: bool
    reason: str
    active_event: Optional[MacroEvent] = None
    next_event: Optional[MacroEvent] = None


# Default macro events for 2026 (UTC)
DEFAULT_EVENTS_2026: list[MacroEvent] = [
    # FOMC meetings 2026
    MacroEvent(name="FOMC 2026-01", event_date=datetime(2026, 1, 28, 19, 0, tzinfo=timezone.utc)),
    MacroEvent(name="FOMC 2026-03", event_date=datetime(2026, 3, 18, 18, 0, tzinfo=timezone.utc)),
    MacroEvent(name="FOMC 2026-05", event_date=datetime(2026, 5, 6, 18, 0, tzinfo=timezone.utc)),
    MacroEvent(name="FOMC 2026-06", event_date=datetime(2026, 6, 17, 18, 0, tzinfo=timezone.utc)),
    MacroEvent(name="FOMC 2026-07", event_date=datetime(2026, 7, 29, 18, 0, tzinfo=timezone.utc)),
    MacroEvent(name="FOMC 2026-09", event_date=datetime(2026, 9, 16, 18, 0, tzinfo=timezone.utc)),
    MacroEvent(name="FOMC 2026-11", event_date=datetime(2026, 11, 4, 19, 0, tzinfo=timezone.utc)),
    MacroEvent(name="FOMC 2026-12", event_date=datetime(2026, 12, 16, 19, 0, tzinfo=timezone.utc)),
    # CPI releases 2026 (typically 8:30 AM ET = 13:30 UTC)
    MacroEvent(name="CPI 2026-01", event_date=datetime(2026, 1, 14, 13, 30, tzinfo=timezone.utc)),
    MacroEvent(name="CPI 2026-02", event_date=datetime(2026, 2, 11, 13, 30, tzinfo=timezone.utc)),
    MacroEvent(name="CPI 2026-03", event_date=datetime(2026, 3, 11, 13, 30, tzinfo=timezone.utc)),
    MacroEvent(name="CPI 2026-04", event_date=datetime(2026, 4, 10, 12, 30, tzinfo=timezone.utc)),
    MacroEvent(name="CPI 2026-05", event_date=datetime(2026, 5, 13, 12, 30, tzinfo=timezone.utc)),
    MacroEvent(name="CPI 2026-06", event_date=datetime(2026, 6, 10, 12, 30, tzinfo=timezone.utc)),
    MacroEvent(name="CPI 2026-07", event_date=datetime(2026, 7, 15, 12, 30, tzinfo=timezone.utc)),
    MacroEvent(name="CPI 2026-08", event_date=datetime(2026, 8, 12, 12, 30, tzinfo=timezone.utc)),
    MacroEvent(name="CPI 2026-09", event_date=datetime(2026, 9, 9, 12, 30, tzinfo=timezone.utc)),
    MacroEvent(name="CPI 2026-10", event_date=datetime(2026, 10, 14, 12, 30, tzinfo=timezone.utc)),
    MacroEvent(name="CPI 2026-11", event_date=datetime(2026, 11, 12, 13, 30, tzinfo=timezone.utc)),
    MacroEvent(name="CPI 2026-12", event_date=datetime(2026, 12, 9, 13, 30, tzinfo=timezone.utc)),
]


class MacroSafeMode:
    def __init__(self, events: Optional[list[MacroEvent]] = None) -> None:
        self.events: list[MacroEvent] = events if events is not None else DEFAULT_EVENTS_2026

    def is_safe_mode_active(self, now: Optional[datetime] = None) -> SafeModeStatus:
        """Check if safe mode should be active based on macro event windows."""
        if now is None:
            now = datetime.now(tz=timezone.utc)

        from datetime import timedelta

        for event in self.events:
            window_start = event.event_date - timedelta(hours=event.hours_before)
            window_end = event.event_date + timedelta(hours=event.hours_after)
            if window_start <= now <= window_end:
                next_event = self._get_next_event(now, exclude=event)
                return SafeModeStatus(
                    active=True,
                    reason=f"within {event.name} window ({window_start.isoformat()} - {window_end.isoformat()})",
                    active_event=event,
                    next_event=next_event,
                )

        next_event = self._get_next_event(now)
        return SafeModeStatus(
            active=False,
            reason="no active macro event window",
            active_event=None,
            next_event=next_event,
        )

    def _get_next_event(
        self, now: datetime, exclude: Optional[MacroEvent] = None
    ) -> Optional[MacroEvent]:
        future = [e for e in self.events if e.event_date > now and e is not exclude]
        if not future:
            return None
        return min(future, key=lambda e: e.event_date)

    def get_upcoming_events(
        self, now: Optional[datetime] = None, days: int = 7
    ) -> list[MacroEvent]:
        """Return events within the next `days` days."""
        if now is None:
            now = datetime.now(tz=timezone.utc)

        from datetime import timedelta

        cutoff = now + timedelta(days=days)
        return sorted(
            [e for e in self.events if now <= e.event_date <= cutoff],
            key=lambda e: e.event_date,
        )
