"""Build the dynamic Gemini prompt for the daily bird poster.

Public entry point: :func:`build_daily_prompt`, which takes the essential dynamic
inputs and assembles a full image prompt:

  - latitude / longitude        -> reverse-geocoded place name + weather (yr.no)
  - date & time                 -> environment (season / foliage / scenery / light)
  - list of birds               -> labelled subjects (scientific + common name)
  - language                    -> language of the common-name labels (default Norwegian)
  - desired pixel size          -> aspect ratio (and Gemini image-size tier)
  - title                       -> poster heading (default "Hørt i dag")

The environment is derived by a small Gemini text call (:mod:`birdscreen.season`)
so it works anywhere on Earth. The resulting :class:`~birdscreen.season.SeasonInfo`
is a plain serializable object, so it can be cached or precomputed per location
later (e.g. derive descriptions up front once a lat/lon is known).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from google import genai

from birdscreen.geocode import reverse_geocode
from birdscreen.season import SeasonInfo, describe_environment_llm
from birdscreen.weather import Weather, fetch_current_weather

DEFAULT_TITLE = "Hørt i dag"
DEFAULT_LANGUAGE = "Norwegian"
DEFAULT_STYLE = (
    "scientific field-guide illustration in the style of a classic ornithological "
    "reference plate — delicate pencil/graphite linework with soft, naturalistic "
    "watercolor washes"
)

# Aspect ratios Gemini's image models accept (width:height).
_SUPPORTED_RATIOS: list[tuple[int, int]] = [
    (1, 1), (2, 3), (3, 2), (3, 4), (4, 3), (4, 5), (5, 4),
    (9, 16), (16, 9), (21, 9),
]


@dataclass
class Bird:
    """A bird to feature. ``common`` is the local name; ``scientific`` is Latin."""

    scientific: str
    common: str | None = None


@dataclass
class PosterContext:
    latitude: float
    longitude: float
    when: datetime
    birds: list[Bird] = field(default_factory=list)
    location_name: str | None = None  # reverse-geocoded if not provided
    weather: Weather | None = None
    width: int = 3840
    height: int = 2160
    title: str = DEFAULT_TITLE
    language: str = DEFAULT_LANGUAGE
    style: str = DEFAULT_STYLE
    labels: bool = True  # if False, the model paints no text; we composite labels ourselves


def aspect_ratio(width: int, height: int) -> str:
    """Nearest Gemini-supported aspect ratio for a pixel size, as 'W:H'."""
    target = width / height
    best = min(_SUPPORTED_RATIOS, key=lambda r: abs(r[0] / r[1] - target))
    return f"{best[0]}:{best[1]}"


def image_size_tier(width: int, height: int) -> str:
    """Gemini image-size tier ('512' | '1K' | '2K' | '4K') for a pixel size."""
    longest = max(width, height)
    if longest <= 640:
        return "512"
    if longest <= 1280:
        return "1K"
    if longest <= 2560:
        return "2K"
    return "4K"


def _bird_line(bird: Bird) -> str:
    return f"  - {bird.common} ({bird.scientific})" if bird.common else f"  - {bird.scientific}"


def build_prompt(ctx: PosterContext, env: SeasonInfo) -> str:
    """Assemble the full Gemini image prompt from a context and environment.

    ``env`` is kept as a separate argument so it can be cached/precomputed and
    reused without re-deriving it on every render.
    """
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
        text_rule = "no text other than the title and the species labels."
    else:
        title_block = ""
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
        text_rule = "absolutely no text, letters or numbers of any kind."

    composition = (
        "\n\nComposition: a calm, balanced field-guide plate on a soft parchment-toned "
        "background, with the birds as the clear focus and natural foliage framing the "
        "edges. Fine, detailed linework with gentle watercolor washes; no harsh outlines, "
        f"no photographic realism, {text_rule}"
    )

    return f"Create a {aspect} {ctx.style}.\n\n{setting}{title_block}{bird_block}{composition}"


def build_daily_prompt(
    latitude: float,
    longitude: float,
    when: datetime,
    birds: list[Bird],
    *,
    language: str = DEFAULT_LANGUAGE,
    title: str = DEFAULT_TITLE,
    labels: bool = True,
    width: int = 3840,
    height: int = 2160,
    location_name: str | None = None,
    weather: Weather | None = None,
    environment: SeasonInfo | None = None,
    fetch_weather: bool = True,
    client: genai.Client | None = None,
    style: str = DEFAULT_STYLE,
    usage_sink: list | None = None,
) -> tuple[str, PosterContext, SeasonInfo]:
    """Top-level API: from coordinates + time + birds, build the image prompt.

    Reverse-geocodes the location, fetches current weather (yr.no), derives the
    environment via Gemini, and returns ``(prompt, context, environment)``.

    Pass ``environment`` (a cached/precomputed :class:`SeasonInfo`) and/or
    ``weather`` to skip the corresponding lookups.
    """
    if location_name is None:
        location_name = reverse_geocode(latitude, longitude)
    if weather is None and fetch_weather:
        weather = fetch_current_weather(latitude, longitude)

    ctx = PosterContext(
        latitude=latitude,
        longitude=longitude,
        when=when,
        birds=birds,
        location_name=location_name,
        weather=weather,
        width=width,
        height=height,
        title=title,
        language=language,
        style=style,
        labels=labels,
    )
    if environment is None:
        environment = describe_environment_llm(
            ctx.location_name or f"{latitude:.4f}, {longitude:.4f}",
            latitude,
            longitude,
            when,
            client=client,
            usage_sink=usage_sink,
        )
    return build_prompt(ctx, environment), ctx, environment


# --------------------------------------------------------------------------- CLI


def _parse_bird(value: str) -> Bird:
    # "Scientific" or "Scientific=Common"
    if "=" in value:
        scientific, common = value.split("=", 1)
        return Bird(scientific.strip(), common.strip() or None)
    return Bird(value.strip())


def main() -> None:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="build-prompt",
        description="Build the dynamic bird-poster image prompt from coordinates, time and birds.",
    )
    parser.add_argument("--lat", type=float, required=True, help="Latitude.")
    parser.add_argument("--lon", type=float, required=True, help="Longitude.")
    parser.add_argument(
        "--when", help="Local date/time ISO 8601 (e.g. 2026-06-26T21:00). Default: now."
    )
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
    args = parser.parse_args()

    when = datetime.fromisoformat(args.when) if args.when else datetime.now()
    try:
        width, height = (int(x) for x in args.size.lower().split("x"))
    except ValueError:
        parser.error("--size must look like 3840x2160")
    if not args.bird:
        parser.error("provide at least one --bird")
    birds = [_parse_bird(b) for b in args.bird]

    from birdscreen.usage import Usage, summarize

    usage: list[Usage] = []
    prompt, ctx, env = build_daily_prompt(
        args.lat,
        args.lon,
        when,
        birds,
        language=args.language,
        title=args.title,
        width=width,
        height=height,
        location_name=args.location,
        fetch_weather=not args.no_weather,
        usage_sink=usage,
    )

    # Diagnostics to stderr so stdout is just the prompt (pipe-friendly).
    print(
        f"[location] {ctx.location_name}\n"
        f"[when]     {when:%Y-%m-%d %H:%M}\n"
        f"[size]     {width}x{height} -> {aspect_ratio(width, height)} / {image_size_tier(width, height)}\n"
        f"[season]   {env.season}\n"
        f"[weather]  {ctx.weather.describe() if ctx.weather else '(skipped)'}\n"
        f"[usage]    {summarize(usage)}",
        file=sys.stderr,
    )

    if args.out:
        from pathlib import Path

        Path(args.out).write_text(prompt, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(prompt)


if __name__ == "__main__":
    main()
