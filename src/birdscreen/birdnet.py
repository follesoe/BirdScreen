"""BirdNET-Go observations client (best-effort).

BirdNET-Go's JSON API is recent and lightly documented, so this parses defensively
across a few likely field spellings and should be verified against your running
instance. It answers the engine's core question: which birds have been heard?
"""

from __future__ import annotations

from dataclasses import dataclass
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
        if detection.common_name not in seen:
            seen.add(detection.common_name)
            names.append(detection.common_name)
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
            names.append(str(common))
    return names


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
