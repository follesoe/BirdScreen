"""BirdNET-Go observations client (best-effort).

BirdNET-Go's JSON API is recent and lightly documented, so this parses defensively
across a few likely field spellings and should be verified against your running
instance. It answers the engine's core question: which birds have been heard?
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import requests

_DETECTIONS_PATH = "/api/v2/detections"
_DAILY_SPECIES_PATH = "/api/v2/analytics/species/daily"
_BIRDNET_SETTINGS_PATH = "/api/v2/settings/birdnet"


@dataclass
class Detection:
    common_name: str
    scientific_name: str | None
    confidence: float | None
    when: str | None


def _first(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = item.get(key)
        if value:
            return value
    return None


def _opt_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def _opt_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _cap(name: str) -> str:
    """Capitalise the first letter — BirdNET-Go returns lowercase common names."""
    return name[:1].upper() + name[1:] if name else name


def fetch_recent_detections(
    base_url: str, *, limit: int = 100, timeout: float = 6.0
) -> list[Detection]:
    """Recent detections from BirdNET-Go (raises ``requests`` errors on failure)."""
    base = base_url.rstrip("/")
    resp = requests.get(f"{base}{_DETECTIONS_PATH}", params={"numResults": limit}, timeout=timeout)
    resp.raise_for_status()
    payload: Any = resp.json()
    rows: Any = payload
    if isinstance(payload, dict):
        rows = payload.get("data") or payload.get("detections") or []

    detections: list[Detection] = []
    for item in rows or []:
        if not isinstance(item, dict):
            continue
        common = _first(item, "commonName", "common_name", "species", "comName")
        if not common:
            continue
        detections.append(
            Detection(
                common_name=str(common),
                scientific_name=_opt_str(
                    _first(item, "scientificName", "scientific_name", "sciName")
                ),
                confidence=_opt_float(item.get("confidence")),
                when=_opt_str(_first(item, "date", "timestamp", "beginTime", "time")),
            )
        )
    return detections


def recent_species(base_url: str, *, limit: int = 200) -> list[str]:
    """Unique common names from recent detections, in first-seen order."""
    seen: set[str] = set()
    names: list[str] = []
    for detection in fetch_recent_detections(base_url, limit=limit):
        name = _cap(detection.common_name)
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names


def today_species(
    base_url: str, *, high_confidence_only: bool = True, timeout: float = 6.0
) -> list[str]:
    """Common names of species heard so far today (BirdNET-Go daily analytics)."""
    base = base_url.rstrip("/")
    resp = requests.get(f"{base}{_DAILY_SPECIES_PATH}", timeout=timeout)
    resp.raise_for_status()
    rows: Any = resp.json()
    names: list[str] = []
    for item in rows or []:
        if not isinstance(item, dict):
            continue
        common = _first(item, "common_name", "commonName")
        if common and (item.get("high_confidence", True) or not high_confidence_only):
            names.append(_cap(str(common)))
    return names


def today_birds(
    base_url: str, *, high_confidence_only: bool = True, timeout: float = 6.0
) -> list[tuple[str, str]]:
    """(scientific_name, common_name) pairs for species heard so far today."""
    base = base_url.rstrip("/")
    resp = requests.get(f"{base}{_DAILY_SPECIES_PATH}", timeout=timeout)
    resp.raise_for_status()
    rows: Any = resp.json()
    birds: list[tuple[str, str]] = []
    for item in rows or []:
        if not isinstance(item, dict):
            continue
        common = _first(item, "common_name", "commonName")
        scientific = _first(item, "scientific_name", "scientificName")
        if common and (item.get("high_confidence", True) or not high_confidence_only):
            birds.append((str(scientific or common), _cap(str(common))))
    return birds


def birds_for_day(
    base_url: str,
    *,
    start: datetime,
    now: datetime,
    high_confidence_only: bool = True,
    timeout: float = 6.0,
) -> list[tuple[str, str]]:
    """(scientific, common) species heard within the bird-day window [start, now].

    Uses the daily analytics' per-hour buckets so the window honours the configured
    day-reset (e.g. 04:00) instead of calendar midnight, spanning across midnight.
    """
    base = base_url.rstrip("/")
    birds: dict[str, str] = {}
    day = start.date()
    while day <= now.date():
        resp = requests.get(
            f"{base}{_DAILY_SPECIES_PATH}", params={"date": day.isoformat()}, timeout=timeout
        )
        resp.raise_for_status()
        rows: Any = resp.json()
        first_hour = start.hour if day == start.date() else 0
        last_hour = now.hour if day == now.date() else 23
        for item in rows or []:
            if not isinstance(item, dict):
                continue
            if high_confidence_only and not item.get("high_confidence", True):
                continue
            counts = item.get("hourly_counts") or []
            if not any(counts[h] for h in range(first_hour, last_hour + 1) if h < len(counts)):
                continue
            common = _first(item, "common_name", "commonName")
            scientific = _first(item, "scientific_name", "scientificName")
            if common:
                birds.setdefault(str(scientific or common), _cap(str(common)))
        day += timedelta(days=1)
    return list(birds.items())


def fetch_location(base_url: str, *, timeout: float = 6.0) -> tuple[float, float] | None:
    """Read the configured (latitude, longitude) from BirdNET-Go, or None."""
    base = base_url.rstrip("/")
    resp = requests.get(f"{base}{_BIRDNET_SETTINGS_PATH}", timeout=timeout)
    resp.raise_for_status()
    data: Any = resp.json()
    if not isinstance(data, dict):
        return None
    lat = data.get("latitude")
    lon = data.get("longitude")
    numeric = (int, float)
    if isinstance(lat, numeric) and isinstance(lon, numeric) and not isinstance(lat, bool):
        return (float(lat), float(lon))
    return None
