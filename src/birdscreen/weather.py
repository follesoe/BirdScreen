"""Current weather from the MET Norway (yr.no) Locationforecast API.

Keyless public API, but MET requires a descriptive ``User-Agent`` identifying the
application and a contact. See:
https://api.met.no/weatherapi/locationforecast/2.0/documentation
https://api.met.no/doc/TermsOfService
"""

from __future__ import annotations

from dataclasses import dataclass

import requests

MET_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
# MET API etiquette: identify the app + a contact address.
USER_AGENT = "BirdScreen/0.1 (https://github.com/follesoe/BirdScreen; jonas@follesoe.no)"

# Scene phrase for non-precipitation conditions.
_WEATHER_SCENE = {
    "clear": "clear skies",
    "partly_cloudy": "a few scattered clouds drifting across the sky",
    "cloudy": "an overcast, cloud-covered sky",
    "fog": "soft mist and fog hanging over the landscape",
    "thunder": "dramatic dark storm clouds and distant lightning",
}

# Scene phrase for precipitation, keyed by (condition, intensity).
_PRECIP_SCENE = {
    ("rain", "light"): "light drizzle, the ground glistening damp",
    ("rain", "moderate"): "steady rain, with raindrops and wet, glistening surfaces",
    ("rain", "heavy"): "heavy rain pouring down, puddles and rivulets forming",
    ("snow", "light"): "a few snowflakes drifting down",
    ("snow", "moderate"): "steadily falling snow settling over the scene",
    ("snow", "heavy"): "heavy snowfall blanketing everything in white",
    ("sleet", "light"): "cold light sleet, the ground wet and slushy",
    ("sleet", "moderate"): "cold sleet and slushy, wet ground",
    ("sleet", "heavy"): "driving sleet and deep, slushy wet ground",
}


@dataclass
class Weather:
    """A normalized snapshot of current conditions."""

    condition: str  # clear, partly_cloudy, cloudy, fog, rain, sleet, snow, thunder
    intensity: str | None = None  # light | moderate | heavy (precipitation only)
    symbol_code: str | None = None  # raw MET code, e.g. "partlycloudy_day"
    temperature_c: float | None = None
    wind_speed_ms: float | None = None
    is_day: bool | None = None

    def describe(self) -> str:
        """A natural-language scene phrase for the image prompt."""
        if self.condition in ("rain", "snow", "sleet"):
            intensity = self.intensity or "moderate"
            phrase = _PRECIP_SCENE.get((self.condition, intensity), f"{intensity} {self.condition}")
        else:
            phrase = _WEATHER_SCENE.get(self.condition, "fair weather")
        if self.temperature_c is not None:
            phrase += f" (about {round(self.temperature_c)}°C)"
        return phrase


# (keywords, condition), checked in order; anything unmatched is "clear".
_SYMBOL_CONDITIONS: list[tuple[tuple[str, ...], str]] = [
    (("thunder",), "thunder"),
    (("sleet",), "sleet"),
    (("snow",), "snow"),
    (("rain", "showers"), "rain"),
    (("fog",), "fog"),
    (("partlycloudy", "fair"), "partly_cloudy"),
    (("cloudy",), "cloudy"),
]


def normalize_symbol(symbol_code: str) -> str:
    """Map a MET symbol code (e.g. 'lightrainshowers_day') to a condition."""
    s = symbol_code.lower()
    for keywords, condition in _SYMBOL_CONDITIONS:
        if any(k in s for k in keywords):
            return condition
    return "clear"


def precipitation_intensity(symbol_code: str) -> str | None:
    """Light/moderate/heavy for precip symbols; None for non-precip."""
    s = symbol_code.lower()
    if not any(k in s for k in ("rain", "snow", "sleet", "showers")):
        return None
    if "heavy" in s:
        return "heavy"
    if "light" in s:
        return "light"
    return "moderate"


def fetch_current_weather(lat: float, lon: float, *, timeout: float = 10) -> Weather:
    """Fetch current conditions for a coordinate from MET Norway (yr.no)."""
    resp = requests.get(
        MET_URL,
        # MET asks clients to truncate coordinates to <= 4 decimals.
        params={"lat": round(lat, 4), "lon": round(lon, 4)},
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
    )
    resp.raise_for_status()
    series = resp.json()["properties"]["timeseries"][0]["data"]
    instant = series.get("instant", {}).get("details", {})

    symbol = None
    for window in ("next_1_hours", "next_6_hours", "next_12_hours"):
        block = series.get(window)
        if block and "summary" in block:
            symbol = block["summary"].get("symbol_code")
            if symbol:
                break

    is_day: bool | None = None
    if symbol and ("_day" in symbol or "_night" in symbol):
        is_day = symbol.endswith("_day")

    return Weather(
        condition=normalize_symbol(symbol or "clearsky"),
        intensity=precipitation_intensity(symbol) if symbol else None,
        symbol_code=symbol,
        temperature_c=instant.get("air_temperature"),
        wind_speed_ms=instant.get("wind_speed"),
        is_day=is_day,
    )
