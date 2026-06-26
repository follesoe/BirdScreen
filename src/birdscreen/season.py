"""Derive the natural environment (season, foliage, scenery, light) for a place
and moment, using a small Gemini *text* call.

This makes the poster work anywhere on Earth — it reasons about hemisphere,
latitude, altitude and biome (boreal, temperate, Mediterranean, tropical,
arctic) rather than assuming Northern-hemisphere months.

:class:`SeasonInfo` is a plain serializable model, so descriptions can be cached
or precomputed up front per location (lat/lon) rather than derived on every run.
"""

from __future__ import annotations

import os
from datetime import datetime

from google import genai
from google.genai import types
from pydantic import BaseModel

from birdscreen.gemini import get_client
from birdscreen.usage import Usage, usage_from_response

# Cheap/fast text model for the environment description. Override via env.
SEASON_MODEL = os.environ.get("BIRDSCREEN_TEXT_MODEL", "gemini-2.5-flash")


class SeasonInfo(BaseModel):
    """A concrete, visual description of the environment at a place and time."""

    season: str  # local season / phenological phase, e.g. "early summer"
    foliage: str  # current state of trees and plants
    scenery: str  # typical natural landscape / habitat of this location
    light: str  # quality and colour of daylight at this date/time/latitude


def _prompt(location_name: str, latitude: float, longitude: float, when: datetime) -> str:
    return (
        "You are a field naturalist helping create a botanically accurate nature "
        "illustration. Describe the CURRENT natural environment as it would really "
        "appear outdoors at this location and moment.\n\n"
        f"Location: {location_name} (latitude {latitude:.4f}, longitude {longitude:.4f})\n"
        f"Local date and time: {when:%A %d %B %Y, %H:%M}\n\n"
        "Take hemisphere, latitude, altitude and the local climate/biome into account "
        "(e.g. boreal, temperate, Mediterranean, tropical wet/dry, arctic). Answer with "
        "concise, concrete, visual phrases — short sentence fragments, NOT full "
        "sentences. Do not begin with 'It is', 'The', 'Currently' and do not end with a "
        "period.\n"
        "- season: the local season or phenological phase right now\n"
        "- foliage: the current state of trees and plants (leaf size and colour, "
        "blossom, bare branches, snow cover, etc.)\n"
        "- scenery: the typical natural landscape and habitat around this location\n"
        "- light: the quality and colour of daylight at this date, time and latitude "
        "(consider day length, golden hour, polar day/night)."
    )


def _clean(text: str, *, drop_lead: bool = False) -> str:
    """Trim a model-returned phrase to splice cleanly into the prompt template."""
    cleaned = text.strip()
    if drop_lead:
        for lead in ("it is ", "it's ", "currently ", "the season is ", "the "):
            if cleaned.lower().startswith(lead):
                cleaned = cleaned[len(lead) :]
                break
    return cleaned.rstrip(" .").strip()


def describe_environment_llm(
    location_name: str,
    latitude: float,
    longitude: float,
    when: datetime,
    *,
    client: genai.Client | None = None,
    model: str = SEASON_MODEL,
    usage_sink: list[Usage] | None = None,
) -> SeasonInfo:
    """Ask Gemini for a structured environment description. Raises on failure."""
    client = client or get_client()
    response = client.models.generate_content(
        model=model,
        contents=_prompt(location_name, latitude, longitude, when),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SeasonInfo,
        ),
    )
    if usage_sink is not None:
        usage_sink.append(usage_from_response(model, response))

    info = response.parsed
    if not isinstance(info, SeasonInfo):
        raise TypeError("season model returned no structured data")
    info.season = _clean(info.season, drop_lead=True)
    info.foliage = _clean(info.foliage)
    info.scenery = _clean(info.scenery)
    info.light = _clean(info.light)
    return info
