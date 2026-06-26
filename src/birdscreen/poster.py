"""Build the dynamic Gemini prompt for the daily bird poster.

A :class:`PosterRequest` bundles everything needed to render one poster (the
per-render config object). :func:`build_daily_prompt` resolves the dynamic inputs
(reverse-geocoded place name, yr.no weather, Gemini-derived environment) and
assembles the full image prompt.

The environment (:class:`~birdscreen.season.SeasonInfo`) is a plain serializable
object, so it can be cached or precomputed per location.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from google import genai

from birdscreen.gemini import DEFAULT_IMAGE_MODEL
from birdscreen.geocode import reverse_geocode
from birdscreen.logging_config import setup_logging
from birdscreen.season import SeasonInfo, describe_environment_llm
from birdscreen.usage import Usage, summarize
from birdscreen.weather import Weather, fetch_current_weather

logger = logging.getLogger(__name__)

DEFAULT_TITLE = "Hørt i dag"
DEFAULT_LANGUAGE = "Norwegian"
DEFAULT_OUT_DIR = "posters"
DEFAULT_STYLE = (
    "scientific field-guide illustration in the style of a classic ornithological "
    "reference plate — delicate pencil/graphite linework with soft, naturalistic "
    "watercolor washes"
)

# Aspect ratios Gemini's image models accept (width:height).
_SUPPORTED_RATIOS: list[tuple[int, int]] = [
    (1, 1),
    (2, 3),
    (3, 2),
    (3, 4),
    (4, 3),
    (4, 5),
    (5, 4),
    (9, 16),
    (16, 9),
    (21, 9),
]


@dataclass
class Bird:
    """A bird to feature. ``common`` is the local name; ``scientific`` is Latin."""

    scientific: str
    common: str | None = None


@dataclass
class PosterRequest:
    """Everything needed to render one poster — the per-render config object."""

    latitude: float
    longitude: float
    when: datetime
    birds: list[Bird] = field(default_factory=list)
    location_name: str | None = None  # reverse-geocoded if not provided
    language: str = DEFAULT_LANGUAGE
    title: str = DEFAULT_TITLE
    labels: bool = True  # if False, the model paints no text; we composite labels ourselves
    width: int = 3840
    height: int = 2160
    style: str = DEFAULT_STYLE
    # Generation / output (used by the pipeline).
    model: str = DEFAULT_IMAGE_MODEL
    image_size: str | None = None
    scale: bool = True
    upscale: str | None = None
    fetch_weather: bool = True
    out: str | None = None
    out_dir: str = DEFAULT_OUT_DIR


@dataclass
class PosterContext:
    """Resolved subject + scene for prompt assembly (after geocode/weather)."""

    latitude: float
    longitude: float
    when: datetime
    birds: list[Bird] = field(default_factory=list)
    location_name: str | None = None
    weather: Weather | None = None
    width: int = 3840
    height: int = 2160
    title: str = DEFAULT_TITLE
    language: str = DEFAULT_LANGUAGE
    style: str = DEFAULT_STYLE
    labels: bool = True


def aspect_ratio(width: int, height: int) -> str:
    """Nearest Gemini-supported aspect ratio for a pixel size, as 'W:H'."""
    target = width / height
    best = min(_SUPPORTED_RATIOS, key=lambda r: abs(r[0] / r[1] - target))
    return f"{best[0]}:{best[1]}"


# Upper pixel bound (longest edge) for each Gemini image-size tier.
_SIZE_TIERS: list[tuple[int, str]] = [(640, "512"), (1280, "1K"), (2560, "2K")]


def image_size_tier(width: int, height: int) -> str:
    """Gemini image-size tier ('512' | '1K' | '2K' | '4K') for a pixel size."""
    longest = max(width, height)
    for bound, tier in _SIZE_TIERS:
        if longest <= bound:
            return tier
    return "4K"


def _bird_line(bird: Bird) -> str:
    return f"  - {bird.common} ({bird.scientific})" if bird.common else f"  - {bird.scientific}"


def _bird_blocks(ctx: PosterContext, bird_lines: str) -> tuple[str, str, str]:
    """Return (title_block, bird_block, text_rule) for the labelled/unlabelled modes."""
    if ctx.labels:
        title_block = f'\n\nTitle across the top in an elegant serif typeface: "{ctx.title}".'
        bird_block = (
            "\n\nFeature the following birds, each accurately and recognisably rendered to "
            "scale and arranged naturally within a single cohesive scene (perched on "
            "branches, resting on shoreline rocks, wading, or in flight as best suits each "
            "species). Label each bird with a small serif caption: its common name in "
            f"{ctx.language} on top, and beneath it its scientific (Latin) name in italics:\n"
            f"{bird_lines}"
        )
        return title_block, bird_block, "no text other than the title and the species labels."

    bird_block = (
        "\n\nFeature the following birds, each accurately and recognisably rendered to "
        "scale and arranged naturally within a single cohesive scene (perched on "
        "branches, resting on shoreline rocks, wading, or in flight as best suits each "
        f"species):\n{bird_lines}\n\n"
        "IMPORTANT: render absolutely NO text of any kind — no title, no captions, no "
        "species names, no labels, no letters or numbers anywhere in the image. Paint "
        "only the birds and the natural scenery. Compose it as a centred natural-history "
        "illustration with comfortable empty margin around all four edges, keeping the "
        "birds and key scenery well inside the frame (the title and species labels are "
        "added separately afterwards, around the artwork)."
    )
    return "", bird_block, "absolutely no text, letters or numbers of any kind."


def build_prompt(ctx: PosterContext, env: SeasonInfo) -> str:
    """Assemble the full Gemini image prompt from a context and environment."""
    aspect = aspect_ratio(ctx.width, ctx.height)
    weather_phrase = ctx.weather.describe() if ctx.weather else "calm, fair weather"
    place = ctx.location_name or f"the area at {ctx.latitude:.4f}, {ctx.longitude:.4f}"
    date_str = f"{ctx.when.day} {ctx.when:%B %Y}"
    bird_lines = "\n".join(_bird_line(b) for b in ctx.birds)
    # Lowercase the season's first letter so it reads "It is mid-summer ...".
    season = (env.season[:1].lower() + env.season[1:]) if env.season else env.season

    setting = (
        f"Setting: the natural scenery around {place} — {env.scenery}. It is {season} "
        f"({date_str}); render the vegetation accordingly — {env.foliage}. The weather is "
        f"{weather_phrase}, lit by {env.light}. Keep the foliage, scenery and sky "
        "botanically and seasonally accurate for this place and time of year."
    )
    title_block, bird_block, text_rule = _bird_blocks(ctx, bird_lines)
    composition = (
        "\n\nComposition: a calm, balanced field-guide plate on a soft parchment-toned "
        "background, with the birds as the clear focus and natural foliage framing the "
        "edges. Fine, detailed linework with gentle watercolor washes; no harsh outlines, "
        f"no photographic realism, {text_rule}"
    )
    return f"Create a {aspect} {ctx.style}.\n\n{setting}{title_block}{bird_block}{composition}"


def build_daily_prompt(
    request: PosterRequest,
    *,
    weather: Weather | None = None,
    environment: SeasonInfo | None = None,
    client: genai.Client | None = None,
    usage_sink: list[Usage] | None = None,
) -> tuple[str, PosterContext, SeasonInfo]:
    """Resolve the dynamic inputs for ``request`` and build the image prompt.

    Reverse-geocodes the location, fetches current weather (yr.no), derives the
    environment via Gemini, and returns ``(prompt, context, environment)``. Pass
    ``weather`` and/or ``environment`` to reuse cached values.
    """
    location_name = request.location_name or reverse_geocode(request.latitude, request.longitude)
    if weather is None and request.fetch_weather:
        weather = fetch_current_weather(request.latitude, request.longitude)

    ctx = PosterContext(
        latitude=request.latitude,
        longitude=request.longitude,
        when=request.when,
        birds=request.birds,
        location_name=location_name,
        weather=weather,
        width=request.width,
        height=request.height,
        title=request.title,
        language=request.language,
        style=request.style,
        labels=request.labels,
    )
    if environment is None:
        environment = describe_environment_llm(
            ctx.location_name or f"{request.latitude:.4f}, {request.longitude:.4f}",
            request.latitude,
            request.longitude,
            request.when,
            client=client,
            usage_sink=usage_sink,
        )
    return build_prompt(ctx, environment), ctx, environment


# --------------------------------------------------------------------------- CLI


def parse_bird(value: str) -> Bird:
    """Parse a CLI ``--bird`` value: 'Scientific' or 'Scientific=Common'."""
    if "=" in value:
        scientific, common = value.split("=", 1)
        return Bird(scientific.strip(), common.strip() or None)
    return Bird(value.strip())


def parse_size(value: str) -> tuple[int, int]:
    """Parse a 'WIDTHxHEIGHT' string into a (width, height) tuple."""
    width, height = (int(x) for x in value.lower().split("x"))
    return width, height


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build-prompt",
        description="Build the dynamic bird-poster image prompt from coordinates, time and birds.",
    )
    parser.add_argument("--lat", type=float, required=True, help="Latitude.")
    parser.add_argument("--lon", type=float, required=True, help="Longitude.")
    parser.add_argument("--when", help="Local date/time ISO 8601. Default: now.")
    parser.add_argument(
        "--bird",
        action="append",
        default=[],
        metavar="SCI[=COMMON]",
        help="A bird, repeatable. e.g. --bird 'Pica pica=Skjære'",
    )
    parser.add_argument("--language", default=DEFAULT_LANGUAGE, help="Common-name language.")
    parser.add_argument("--title", default=DEFAULT_TITLE, help="Poster title.")
    parser.add_argument("--size", default="3840x2160", help="Pixel size WxH.")
    parser.add_argument("--location", help="Override the reverse-geocoded place name.")
    parser.add_argument("--no-weather", action="store_true", help="Skip the yr.no weather fetch.")
    parser.add_argument("-o", "--out", help="Write the prompt to a file instead of stdout.")
    return parser


def main() -> None:
    setup_logging()
    parser = _build_parser()
    args = parser.parse_args()

    when = datetime.fromisoformat(args.when) if args.when else datetime.now()
    try:
        width, height = parse_size(args.size)
    except ValueError:
        parser.error("--size must look like 3840x2160")
    if not args.bird:
        parser.error("provide at least one --bird")

    request = PosterRequest(
        latitude=args.lat,
        longitude=args.lon,
        when=when,
        birds=[parse_bird(b) for b in args.bird],
        location_name=args.location,
        language=args.language,
        title=args.title,
        width=width,
        height=height,
        fetch_weather=not args.no_weather,
    )
    usage: list[Usage] = []
    prompt, ctx, env = build_daily_prompt(request, usage_sink=usage)

    weather_text = ctx.weather.describe() if ctx.weather else "(skipped)"
    logger.info(
        "location=%s | when=%s | %dx%d -> %s/%s | season=%s | weather=%s | usage: %s",
        ctx.location_name,
        f"{when:%Y-%m-%d %H:%M}",
        width,
        height,
        aspect_ratio(width, height),
        image_size_tier(width, height),
        env.season,
        weather_text,
        summarize(usage),
    )

    if args.out:
        Path(args.out).write_text(prompt, encoding="utf-8")
        logger.info("Wrote prompt to %s", args.out)
    else:
        print(prompt)  # data output to stdout


if __name__ == "__main__":
    main()
