"""End-to-end BirdScreen pipeline.

From a :class:`~birdscreen.poster.PosterRequest`, build the dynamic prompt,
generate the poster image with Gemini, normalise it to the TV's native
resolution (downscale, upscale, or leave as-is), optionally composite our own
labels, and optionally upload it to a Frame TV.

Posters are written to ``posters/`` with a lexically-sortable, descriptive name:
``<date>T<time>_<location>_<species...>_<model>_NN.jpg``.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image

from birdscreen.gemini import DEFAULT_IMAGE_MODEL, generate_image
from birdscreen.images import prepare_for_frame
from birdscreen.labels import compose_poster
from birdscreen.logging_config import setup_logging
from birdscreen.poster import (
    DEFAULT_LANGUAGE,
    DEFAULT_OUT_DIR,
    DEFAULT_TITLE,
    Bird,
    PosterContext,
    PosterRequest,
    aspect_ratio,
    build_daily_prompt,
    image_size_tier,
    parse_bird,
    parse_size,
)
from birdscreen.samsung_tv import upload_image
from birdscreen.season import SeasonInfo
from birdscreen.usage import Usage, summarize
from birdscreen.weather import Weather

_WEATHER_CONDITIONS = [
    "clear",
    "partly_cloudy",
    "cloudy",
    "fog",
    "rain",
    "sleet",
    "snow",
    "thunder",
]


logger = logging.getLogger(__name__)


@dataclass
class RenderResult:
    """The output of a poster render."""

    image_path: Path
    prompt: str
    context: PosterContext
    environment: SeasonInfo


def _slug(text: str) -> str:
    """Filesystem-safe ASCII slug (folds Norwegian å/ø/æ etc.)."""
    for src, dst in (("ø", "o"), ("Ø", "O"), ("æ", "ae"), ("Æ", "Ae")):
        text = text.replace(src, dst)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")


def default_filename(
    when: datetime, location_name: str | None, birds: list[Bird], model: str
) -> str:
    """Date-first, sortable stem: 2026-02-15T1200_Trondheim-Norway_...gemini-3-pro-image."""
    date = when.strftime("%Y-%m-%dT%H%M")
    location = _slug(location_name or "unknown") or "unknown"
    species = "-".join(_slug(b.common or b.scientific) for b in birds)
    return f"{date}_{location}_{species}_{_slug(model)}"


def _next_indexed_base(directory: Path, stem: str) -> Path:
    """Return ``directory/<stem>_NN`` for the next free counter (any extension)."""
    n = 1
    while any(directory.glob(f"{stem}_{n:02d}.*")):
        n += 1
    return directory / f"{stem}_{n:02d}"


def _output_base(request: PosterRequest, location_name: str | None) -> Path:
    """Where to write this render (explicit ``out`` path, or auto-named in ``out_dir``)."""
    if request.out is not None:
        base = Path(request.out).with_suffix("")
        base.parent.mkdir(parents=True, exist_ok=True)
        return base
    directory = Path(request.out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stem = default_filename(request.when, location_name, request.birds, request.model)
    return _next_indexed_base(directory, stem)


def _finalize_image(request: PosterRequest, base: Path, raw: Path, orig_ext: str) -> Path:
    """Turn the raw Gemini render into the final image (upscale / downscale / as-is)."""
    size = (request.width, request.height)
    explicit = Path(request.out) if request.out is not None else None

    if request.upscale:
        # Keep the raw render as the "original", then AI-upscale to native size.
        original = base.with_suffix(orig_ext)
        raw.replace(original)
        from birdscreen.upscale import super_resolve  # noqa: PLC0415 — optional torch dep

        sr_tmp = base.with_suffix(".srtmp.png")
        super_resolve(original, model=request.upscale).save(sr_tmp)
        final = explicit or base.with_name(
            f"{base.name}_upscaled-{_slug(request.upscale)}"
        ).with_suffix(".jpg")
        prepare_for_frame(sr_tmp, dst=final, size=size)
        sr_tmp.unlink(missing_ok=True)
        return final

    if request.scale:
        final = explicit or base.with_suffix(".jpg")
        prepare_for_frame(raw, dst=final, size=size)
        raw.unlink(missing_ok=True)
        return final

    final = explicit or base.with_suffix(orig_ext)
    raw.replace(final)
    return final


def make_poster(
    request: PosterRequest,
    *,
    weather: Weather | None = None,
    usage_sink: list[Usage] | None = None,
) -> RenderResult:
    """Build the prompt, generate the image, normalise it, and save it."""
    size = (request.width, request.height)
    tier = request.image_size or image_size_tier(*size)
    logger.info(
        "Resolving scene + building prompt (aspect %s, tier %s)...", aspect_ratio(*size), tier
    )
    prompt, ctx, env = build_daily_prompt(request, weather=weather, usage_sink=usage_sink)
    logger.info("Location: %s | season: %s", ctx.location_name, env.season)

    base = _output_base(request, ctx.location_name)
    base.with_suffix(".txt").write_text(prompt, encoding="utf-8")  # prompt alongside

    logger.info("Generating image with %s...", request.model)
    raw = base.with_suffix(".raw")
    generate_image(
        prompt,
        raw,
        model=request.model,
        aspect_ratio=aspect_ratio(*size),
        image_size=tier,
        usage_sink=usage_sink,
    )

    with Image.open(raw) as im:
        fmt = (im.format or "PNG").lower()
    orig_ext = ".jpg" if fmt in ("jpeg", "jpg") else f".{fmt}"

    final = _finalize_image(request, base, raw, orig_ext)
    if not request.labels:
        labeled = final.with_name(f"{final.stem}_labeled.jpg")
        final = compose_poster(final, labeled, title=request.title, birds=request.birds, size=size)
    logger.info("Saved poster: %s", final)
    return RenderResult(final, prompt, ctx, env)


# --------------------------------------------------------------------------- CLI


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="make-poster",
        description="End-to-end: coordinates + birds -> poster image (-> optional TV).",
    )
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--when", help="Local date/time ISO 8601. Default: now.")
    parser.add_argument(
        "--bird",
        action="append",
        default=[],
        metavar="SCI[=COMMON]",
        help="A bird, repeatable. e.g. --bird 'Pica pica=Skjære'",
    )
    parser.add_argument("--language", default=DEFAULT_LANGUAGE)
    parser.add_argument("--title", default=DEFAULT_TITLE)
    parser.add_argument(
        "--no-labels",
        action="store_true",
        help="Have the model paint no text; composite the title + species labels ourselves.",
    )
    parser.add_argument("--size", default="3840x2160", help="Native pixel size WxH.")
    parser.add_argument(
        "--image-size",
        choices=["512", "1K", "2K", "4K"],
        help="Gemini render tier (default derived from --size).",
    )
    parser.add_argument(
        "--no-scale", action="store_true", help="Save Gemini's actual output (no downscale)."
    )
    parser.add_argument(
        "--upscale",
        action="store_true",
        help="AI-upscale to native res with Real-ESRGAN (needs the 'upscale' extra).",
    )
    parser.add_argument("--upscale-model", default="realesrgan-x4plus", help="Upscaler model.")
    parser.add_argument("--model", default=DEFAULT_IMAGE_MODEL)
    parser.add_argument("--location", help="Override reverse-geocoded place name.")
    parser.add_argument("--no-weather", action="store_true")
    parser.add_argument(
        "--weather-condition",
        choices=_WEATHER_CONDITIONS,
        help="Override the weather instead of fetching from yr.no.",
    )
    parser.add_argument("--weather-temp", type=float, help="Override temperature in °C.")
    parser.add_argument(
        "--weather-intensity",
        choices=["light", "moderate", "heavy"],
        help="Precipitation intensity for the weather override.",
    )
    parser.add_argument("-o", "--out", help="Explicit output path (default: auto-named).")
    parser.add_argument(
        "--out-dir", default=DEFAULT_OUT_DIR, help="Directory for auto-named posters."
    )
    parser.add_argument("--tv", help="TV IP to upload+display the poster on (optional).")
    parser.add_argument("--token-file", default=".tv-token", help="TV auth token file.")
    return parser


def _request_from_args(
    args: argparse.Namespace, when: datetime, size: tuple[int, int]
) -> PosterRequest:
    return PosterRequest(
        latitude=args.lat,
        longitude=args.lon,
        when=when,
        birds=[parse_bird(b) for b in args.bird],
        location_name=args.location,
        language=args.language,
        title=args.title,
        labels=not args.no_labels,
        width=size[0],
        height=size[1],
        model=args.model,
        image_size=args.image_size,
        scale=not args.no_scale,
        upscale=(args.upscale_model if args.upscale else None),
        fetch_weather=not args.no_weather,
        out=args.out,
        out_dir=args.out_dir,
    )


def _report(result: RenderResult, usage: list[Usage]) -> None:
    with Image.open(result.image_path) as im:
        actual_w, actual_h = im.size
    weather = result.context.weather
    logger.info("Weather: %s", weather.describe() if weather else "(skipped)")
    logger.info(
        "Image: %s (%d bytes, %dx%d)",
        result.image_path,
        result.image_path.stat().st_size,
        actual_w,
        actual_h,
    )
    logger.info("Token usage / estimated cost:\n%s", summarize(usage))


def main() -> None:
    setup_logging()
    parser = _build_parser()
    args = parser.parse_args()

    when = datetime.fromisoformat(args.when) if args.when else datetime.now()
    try:
        size = parse_size(args.size)
    except ValueError:
        parser.error("--size must look like 3840x2160")
    if not args.bird:
        parser.error("provide at least one --bird")

    weather = (
        Weather(
            condition=args.weather_condition,
            intensity=args.weather_intensity,
            temperature_c=args.weather_temp,
        )
        if args.weather_condition
        else None
    )
    request = _request_from_args(args, when, size)

    usage: list[Usage] = []
    try:
        result = make_poster(request, weather=weather, usage_sink=usage)
    except Exception:
        logger.exception("Poster generation failed")
        sys.exit(1)
    _report(result, usage)

    if args.tv:
        logger.info("Uploading to TV %s (accept the popup if shown)...", args.tv)
        try:
            content_id = upload_image(args.tv, result.image_path, token_file=args.token_file)
            logger.info("Uploaded + displayed on %s: %s", args.tv, content_id)
        except Exception:
            logger.exception("TV upload failed")
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
