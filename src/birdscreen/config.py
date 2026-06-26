"""BirdScreen runtime configuration (``config.yaml``).

Currently holds the generation **schedule** (cadence + presence windows). Designed
to grow — add location, TVs, model defaults, etc. as their settings screens land.
Missing file → defaults; the web UI reads and writes it.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

CONFIG_PATH = Path("config.yaml")


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


class BirdScreenConfig(BaseModel):
    """Top-level config; grows as more settings screens are added."""

    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    settings: SettingsConfig = Field(default_factory=SettingsConfig)


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
