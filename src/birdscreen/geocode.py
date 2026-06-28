"""Reverse geocoding via OpenStreetMap Nominatim (keyless).

Turns a (lat, lon) into a human place name like "Trondheim, Norway" for the
prompt. Nominatim's usage policy requires a descriptive User-Agent and at most
~1 request/second — fine for a once-daily poster.
https://operations.osmfoundation.org/policies/nominatim/
"""

from __future__ import annotations

import os

import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
# Nominatim's policy requires a descriptive User-Agent; deployers should set their own
# contact via BIRDSCREEN_USER_AGENT (see https://operations.osmfoundation.org/policies/nominatim/).
USER_AGENT = os.environ.get(
    "BIRDSCREEN_USER_AGENT", "BirdScreen (+https://github.com/follesoe/BirdScreen)"
)

# Address keys to try, most-specific first, for a concise place label.
_PLACE_KEYS = ("city", "town", "village", "municipality", "suburb", "county", "state")


def reverse_geocode(
    lat: float, lon: float, *, language: str = "en", timeout: float = 10
) -> str | None:
    """Return a concise "Place, Country" name for the coordinate, or None.

    ``language`` is an ISO code or comma list for Nominatim's ``accept-language``
    (defaults to English for clean, prompt-friendly names).
    """
    params: dict[str, str | float] = {
        "format": "jsonv2",
        "lat": round(lat, 5),
        "lon": round(lon, 5),
        "zoom": 12,  # city/town level
        "accept-language": language,
    }
    try:
        resp = requests.get(
            NOMINATIM_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=timeout
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        return None

    address = data.get("address", {})
    place = next((address[k] for k in _PLACE_KEYS if address.get(k)), None)
    country = address.get("country")
    if place and country:
        return f"{place}, {country}"
    if place:
        return str(place)
    display_name = data.get("display_name")
    return display_name if isinstance(display_name, str) else None
