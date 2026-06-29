"""Tests for the scheduling engine — windows, plan_next, and sun-driven refreshes."""

from datetime import datetime, timedelta, timezone

from birdscreen import engine
from birdscreen.config import ActiveWindow, ScheduleConfig

CET = timezone(timedelta(hours=1))
OSLO = (59.91, 10.75)


def test_active_window_handles_midnight_wrap() -> None:
    win = [ActiveWindow(start="06:00", end="02:00")]
    sched = ScheduleConfig(weekday_windows=win, weekend_windows=win)
    # 01:00 falls inside the previous evening's 06:00 → 02:00 window
    assert engine.active_window(datetime(2026, 6, 29, 1, 0), sched) is not None
    # 03:00 is the gap between windows
    assert engine.active_window(datetime(2026, 6, 29, 3, 0), sched) is None


def test_plan_next_no_tvs_is_highest_priority() -> None:
    plan = engine.plan_next(
        datetime(2026, 6, 28, 12, 0),
        ScheduleConfig(),
        generations_today=0,
        last_generation_at=None,
        has_enabled_tv=False,
    )
    assert plan.state == "no_tvs"


def test_key_moments_ordered() -> None:
    moments = engine.key_moments(*OSLO, datetime(2026, 3, 20).date(), CET)  # equinox: all exist
    assert {"midday", "evening", "dusk"} <= set(moments)
    assert moments["midday"] < moments["evening"] < moments["dusk"]


def test_due_refresh_picks_latest_unpainted_moment() -> None:
    day = datetime(2026, 3, 20).date()
    midday = engine.key_moments(*OSLO, day, CET)["midday"]
    dusk = engine.key_moments(*OSLO, day, CET)["dusk"]
    # before midday → nothing due
    assert engine.due_refresh(*OSLO, midday - timedelta(minutes=1), None, CET) is None
    # just after midday, last painted two hours earlier → midday due
    assert (
        engine.due_refresh(*OSLO, midday + timedelta(minutes=1), midday - timedelta(hours=2), CET)
        == "midday"
    )
    # after dusk, last painted at midday → the latest crossed moment (dusk) is due
    assert engine.due_refresh(*OSLO, dusk + timedelta(minutes=1), midday, CET) == "dusk"
    # already painted after dusk → nothing due
    assert (
        engine.due_refresh(*OSLO, dusk + timedelta(minutes=1), dusk + timedelta(minutes=5), CET)
        is None
    )
