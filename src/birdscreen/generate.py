"""Generate a poster now and record it in the history log.

Gathers the current inputs — location, today's high-confidence species, weather
and season (resolved inside the pipeline) — renders a poster, names it by a
lexically-sortable timestamp, and writes a history record (with the full prompt
and all input params). TV upload is intentionally not wired here yet.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from birdscreen import birdnet, engine, state
from birdscreen.config import ModelCost, SettingsConfig, load_config
from birdscreen.pipeline import make_poster
from birdscreen.poster import Bird, PosterRequest
from birdscreen.usage import Usage, summarize

logger = logging.getLogger(__name__)

POSTERS_DIR = Path("posters")
_UPSCALE_MODEL = "realesrgan-x4plus"


def _resolve_location(settings: SettingsConfig) -> tuple[float, float] | None:
    if settings.latitude is not None and settings.longitude is not None:
        return (settings.latitude, settings.longitude)
    if settings.birdnet_url:
        try:
            return birdnet.fetch_location(settings.birdnet_url)
        except Exception as exc:
            logger.warning("BirdNET-Go location lookup failed: %s", exc)
    return None


def _upscale_model(settings: SettingsConfig) -> str | None:
    """The Real-ESRGAN model name when upscaling is enabled, else None."""
    return _UPSCALE_MODEL if settings.upscale else None


def _rate_for(pricing: dict[str, ModelCost], model: str) -> ModelCost | None:
    name = model.removeprefix("models/")
    if name in pricing:
        return pricing[name]
    return next((rate for key, rate in pricing.items() if name.startswith(key)), None)


def _tally_cost(usages: list[Usage], pricing: dict[str, ModelCost]) -> tuple[int, float | None]:
    """Total tokens and estimated USD cost for a batch of Gemini calls (None if unpriced)."""
    total_tokens = sum(u.total_tokens for u in usages)
    cost = 0.0
    priced = False
    for usage in usages:
        rate = _rate_for(pricing, usage.model)
        if rate is None:
            continue
        cost += usage.input_tokens / 1e6 * rate.input + usage.output_tokens / 1e6 * rate.output
        priced = True
    return total_tokens, (round(cost, 6) if priced else None)


def generate_now(*, trigger: str = "manual", reason: str | None = None) -> state.GenerationRecord:
    """Render a poster from the current state and append it to the history log."""
    config = load_config()
    settings = config.settings

    coords = _resolve_location(settings)
    if coords is None:
        raise RuntimeError("No location configured — set it in Settings or in BirdNET-Go.")
    lat, lon = coords

    when = datetime.now()
    day_start = engine.bird_day_start(when, config.schedule.day_reset)
    birds = [
        Bird(scientific=s, common=c)
        for s, c in birdnet.birds_for_day(settings.birdnet_url, start=day_start, now=when)
    ]
    timestamp = when.strftime("%Y-%m-%dT%H%M%S")
    output = POSTERS_DIR / f"{timestamp}.jpg"

    request = PosterRequest(
        latitude=lat,
        longitude=lon,
        when=when,
        birds=birds,
        model=settings.model,
        image_size=settings.image_size,
        upscale=_upscale_model(settings),
        out=str(output),
    )
    logger.info("Generating now (%s): %d species, model %s", trigger, len(birds), settings.model)
    usage: list[Usage] = []
    result = make_poster(request, usage_sink=usage)

    # Keep only the final timestamped image in posters/ (drop the prompt sidecar,
    # the pre-upscale original, etc. — the metadata lives in the history DB).
    for extra in POSTERS_DIR.glob(f"{timestamp}.*"):
        if extra != result.image_path:
            extra.unlink(missing_ok=True)

    total_tokens, cost_usd = _tally_cost(usage, config.pricing)
    logger.info("Generation token usage:\n%s", summarize(usage))

    record = state.GenerationRecord(
        trigger=trigger,
        reason=reason,
        birds=[b.common or b.scientific for b in birds],
        model=settings.model,
        image_size=settings.image_size,
        prompt=result.prompt,
        location=result.context.location_name,
        season=result.environment.season,
        weather=result.context.weather.describe() if result.context.weather else None,
        output=result.image_path.name,
        total_tokens=total_tokens,
        cost_usd=cost_usd,
        created_at=when.isoformat(),
    )
    state.record_generation(record)
    logger.info("Recorded generation: %s", result.image_path.name)
    return record
