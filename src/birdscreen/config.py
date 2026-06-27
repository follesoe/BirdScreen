"""BirdScreen runtime configuration (``config.yaml``).

Currently holds the generation **schedule** (cadence + presence windows). Designed
to grow — add location, TVs, model defaults, etc. as their settings screens land.
Missing file → defaults; the web UI reads and writes it.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

# Override with BIRDSCREEN_CONFIG (used by tests so they never touch the real file).
CONFIG_PATH = Path(os.environ.get("BIRDSCREEN_CONFIG", "config.yaml"))


class ActiveWindow(BaseModel):
    """A daily time range (HH:MM) during which posters may be generated."""

    start: str = "06:00"
    end: str = "23:00"


class ScheduleConfig(BaseModel):
    """When and how often the daily poster regenerates."""

    day_reset: str = "04:00"  # the "new day" boundary (deep-night lull)
    daily_cap: int = 12  # hard ceiling on generations per day
    debounce_minutes: int = 15  # batch a burst of new species into one render
    min_spacing_minutes: int = 30  # minimum gap between renders
    weekday_windows: list[ActiveWindow] = Field(
        default_factory=lambda: [
            ActiveWindow(start="06:00", end="09:00"),
            ActiveWindow(start="16:00", end="23:00"),
        ]
    )
    weekend_windows: list[ActiveWindow] = Field(
        default_factory=lambda: [ActiveWindow(start="06:00", end="23:00")]
    )


class SettingsConfig(BaseModel):
    """General settings — rendering, the BirdNET-Go source, and weather. Grows over time."""

    model: str = "gemini-3-pro-image"
    image_size: str = "2K"
    upscale: bool = True
    birdnet_url: str = "http://localhost:8080"
    use_weather: bool = True
    latitude: float | None = None  # for weather + the season/scene; manual for now
    longitude: float | None = None


class TvConfig(BaseModel):
    """A Samsung Frame TV that displays the posters."""

    name: str = "Frame TV"
    ip: str = ""
    # Master switch: push posters to this TV. Off = keep it configured but don't
    # update it (e.g. you're using the TV for something else for a while).
    enabled: bool = True
    # Only paint when the TV is in Art Mode; also a cue to watch for it entering
    # Art Mode so we can render a fresh picture while it's ready to show one.
    monitor_art_mode: bool = True


class BirdScreenConfig(BaseModel):
    """Top-level config; grows as more settings screens are added."""

    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    settings: SettingsConfig = Field(default_factory=SettingsConfig)
    tvs: list[TvConfig] = Field(default_factory=list)


def load_config() -> BirdScreenConfig:
    """Load ``config.yaml`` (or defaults if it doesn't exist yet)."""
    if CONFIG_PATH.exists():
        data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
        return BirdScreenConfig.model_validate(data)
    return BirdScreenConfig()


def save_config(config: BirdScreenConfig) -> None:
    """Write ``config.yaml``."""
    CONFIG_PATH.write_text(
        yaml.safe_dump(config.model_dump(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
