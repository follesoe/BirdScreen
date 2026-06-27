"""The generation engine's read-only status model.

Pure functions that answer the questions the status page asks: where is the
bird-day boundary, are we inside an active window, when is the next render
eligible, and why. The (future) generation loop will *act* on these; for now the
status page just *shows* them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from birdscreen.config import ActiveWindow, ScheduleConfig

_SATURDAY = 5  # datetime.weekday(): Mon=0 … Sat=5, Sun=6
_DAY_MINUTES = 24 * 60


def _minutes(value: str) -> int:
    """Minutes since midnight (0–1440). Accepts '24:00' as end-of-day."""
    hour, _, minute = value.partition(":")
    total = max(int(hour or 0), 0) * 60 + max(int(minute or 0), 0)
    return min(total, _DAY_MINUTES)


def _at(day: datetime, minutes: int) -> datetime:
    """A datetime on ``day`` at ``minutes`` since midnight (capped at 23:59)."""
    hour, minute = divmod(min(minutes, _DAY_MINUTES - 1), 60)
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0)


def bird_day_start(now: datetime, day_reset: str) -> datetime:
    """The most recent day-reset boundary at or before ``now``."""
    boundary = _at(now, _minutes(day_reset))
    if now < boundary:
        boundary -= timedelta(days=1)
    return boundary


def windows_for_day(day: datetime, schedule: ScheduleConfig) -> list[ActiveWindow]:
    """Weekend vs weekday active windows for the weekday of ``day``."""
    is_weekend = day.weekday() >= _SATURDAY
    return schedule.weekend_windows if is_weekend else schedule.weekday_windows


def active_window(now: datetime, schedule: ScheduleConfig) -> ActiveWindow | None:
    """The active window containing ``now``, or None if outside all of them."""
    current = now.hour * 60 + now.minute
    for window in windows_for_day(now, schedule):
        if _minutes(window.start) <= current <= _minutes(window.end):
            return window
    return None


def next_window_start(now: datetime, schedule: ScheduleConfig) -> datetime | None:
    """Start of the next active window strictly after ``now`` (searches 8 days)."""
    for offset in range(8):
        day = now + timedelta(days=offset)
        windows = sorted(windows_for_day(day, schedule), key=lambda w: _minutes(w.start))
        for window in windows:
            start = _at(day, _minutes(window.start))
            if start > now:
                return start
    return None


@dataclass
class NextGeneration:
    """When/whether the next poster can be painted, and why."""

    state: str  # 'ready' | 'outside_window' | 'cooldown' | 'cap_reached'
    eligible_at: datetime | None
    reason: str


def plan_next(
    now: datetime,
    schedule: ScheduleConfig,
    *,
    generations_today: int,
    last_generation_at: datetime | None,
) -> NextGeneration:
    """Decide the next-render state from the schedule, today's count and last render."""
    if generations_today >= schedule.daily_cap:
        return NextGeneration(
            state="cap_reached",
            eligible_at=bird_day_start(now, schedule.day_reset) + timedelta(days=1),
            reason=f"Daily limit of {schedule.daily_cap} reached; resets at the next day boundary.",
        )

    if active_window(now, schedule) is None:
        upcoming = next_window_start(now, schedule)
        return NextGeneration(
            state="outside_window",
            eligible_at=upcoming,
            reason="Outside active hours — holding until the next window.",
        )

    if last_generation_at is not None:
        earliest = last_generation_at + timedelta(minutes=schedule.min_spacing_minutes)
        if now < earliest:
            mins = schedule.min_spacing_minutes
            return NextGeneration(
                state="cooldown",
                eligible_at=earliest,
                reason=f"Cooling down — at least {mins} min between renders.",
            )

    return NextGeneration(
        state="ready",
        eligible_at=now,
        reason=(
            f"Ready — will paint when a new bird is heard "
            f"(after a {schedule.debounce_minutes} min debounce)."
        ),
    )
