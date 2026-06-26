"""End-to-end BirdScreen pipeline.

From coordinates + time + a list of birds, build the dynamic prompt, generate the
poster image with Gemini, downscale it to the TV's native resolution, and
optionally upload it to a Frame TV.

    uv run make-poster --lat 63.446827 --lon 10.421906 \
        --bird "Pica pica=Skjære" --bird "Apus apus=Tårnseiler"
    # ...add --tv 192.168.1.219 --token-file .tv-token-219 to push to the 55".

Posters are written to ``posters/`` with a lexically-sortable, descriptive name:
``<date>T<time>_<location>_<species...>.jpg`` (date first so files sort by time).
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

from birdscreen.gemini import DEFAULT_IMAGE_MODEL, generate_image
from birdscreen.images import prepare_for_frame
from birdscreen.poster import (
    Bird,
    DEFAULT_LANGUAGE,
    DEFAULT_TITLE,
    _parse_bird,
    aspect_ratio,
    build_daily_prompt,
    image_size_tier,
)

DEFAULT_OUT_DIR = "posters"


def _slug(text: str) -> str:
    """Filesystem-safe ASCII slug (folds Norwegian å/ø/æ etc.)."""
    for src, dst in (("ø", "o"), ("Ø", "O"), ("æ", "ae"), ("Æ", "Ae")):
        text = text.replace(src, dst)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")


def default_filename(
    when: datetime, location_name: str | None, birds: list[Bird], model: str
) -> str:
    """Date-first, sortable stem (no counter / extension):

    2026-02-15T1200_Trondheim-Norway_Dompap-Blameis-..._gemini-3-pro-image
    """
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


def make_poster(
    latitude: float,
    longitude: float,
    when: datetime,
    birds: list[Bird],
    *,
    language: str = DEFAULT_LANGUAGE,
    title: str = DEFAULT_TITLE,
    width: int = 3840,
    height: int = 2160,
    model: str = DEFAULT_IMAGE_MODEL,
    image_size: str | None = None,
    scale: bool = True,
    out: str | Path | None = None,
    out_dir: str | Path = DEFAULT_OUT_DIR,
    location_name: str | None = None,
    weather=None,
    fetch_weather: bool = True,
    usage_sink: list | None = None,
):
    """Build the prompt, generate the image, and save it.

    Returns (image_path, prompt, ctx, env). ``image_size`` overrides the Gemini
    size tier (else derived from ``width``x``height``). With ``scale=True`` the
    image is downscaled to exactly ``width``x``height`` (TV native); with
    ``scale=False`` Gemini's actual output is saved as-is.
    """
    prompt, ctx, env = build_daily_prompt(
        latitude, longitude, when, birds,
        language=language, title=title, width=width, height=height,
        location_name=location_name, weather=weather,
        fetch_weather=fetch_weather, usage_sink=usage_sink,
    )

    if out is not None:
        base = Path(out).with_suffix("")
        base.parent.mkdir(parents=True, exist_ok=True)
    else:
        directory = Path(out_dir)
        directory.mkdir(parents=True, exist_ok=True)
        base = _next_indexed_base(directory, default_filename(when, ctx.location_name, birds, model))
    base.with_suffix(".txt").write_text(prompt, encoding="utf-8")  # prompt alongside

    tier = image_size or image_size_tier(width, height)
    raw = base.with_suffix(".raw")
    generate_image(
        prompt, raw, model=model,
        aspect_ratio=aspect_ratio(width, height),
        image_size=tier,
        usage_sink=usage_sink,
    )

    if scale:
        # Downscale to the exact native panel size.
        final = Path(out) if out is not None else base.with_suffix(".jpg")
        prepare_for_frame(raw, dst=final, size=(width, height))
        raw.unlink(missing_ok=True)
    else:
        # Keep Gemini's actual output; just give it the right extension.
        from PIL import Image

        with Image.open(raw) as im:
            fmt = (im.format or "PNG").lower()
        ext = ".jpg" if fmt in ("jpeg", "jpg") else f".{fmt}"
        final = Path(out) if out is not None else base.with_suffix(ext)
        raw.replace(final)
    return final, prompt, ctx, env


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="make-poster",
        description="End-to-end: coordinates + birds -> poster image (-> optional TV).",
    )
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--when", help="Local date/time ISO 8601. Default: now.")
    parser.add_argument(
        "--bird", action="append", default=[], metavar="SCI[=COMMON]",
        help="A bird, repeatable. e.g. --bird 'Pica pica=Skjære'",
    )
    parser.add_argument("--language", default=DEFAULT_LANGUAGE)
    parser.add_argument("--title", default=DEFAULT_TITLE)
    parser.add_argument("--size", default="3840x2160", help="Native pixel size WxH (aspect + downscale target).")
    parser.add_argument("--image-size", choices=["512", "1K", "2K", "4K"],
                        help="Gemini render tier (default derived from --size).")
    parser.add_argument("--no-scale", action="store_true",
                        help="Save Gemini's actual output (no downscale to native).")
    parser.add_argument("--model", default=DEFAULT_IMAGE_MODEL)
    parser.add_argument("--location", help="Override reverse-geocoded place name.")
    parser.add_argument("--no-weather", action="store_true")
    parser.add_argument(
        "--weather-condition",
        choices=["clear", "partly_cloudy", "cloudy", "fog", "rain", "sleet", "snow", "thunder"],
        help="Override the weather instead of fetching from yr.no.",
    )
    parser.add_argument("--weather-temp", type=float, help="Override temperature in °C.")
    parser.add_argument("--weather-intensity", choices=["light", "moderate", "heavy"],
                        help="Precipitation intensity for the weather override.")
    parser.add_argument("-o", "--out", help="Explicit output path (default: auto-named in posters/).")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR, help="Directory for auto-named posters.")
    parser.add_argument("--tv", help="TV IP to upload+display the poster on (optional).")
    parser.add_argument("--token-file", default=".tv-token", help="TV auth token file.")
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

    weather = None
    if args.weather_condition:
        from birdscreen.weather import Weather

        weather = Weather(
            condition=args.weather_condition,
            intensity=args.weather_intensity,
            temperature_c=args.weather_temp,
        )

    tier = args.image_size or image_size_tier(width, height)
    usage: list[Usage] = []
    print(f"[1/3] Building prompt (aspect {aspect_ratio(width, height)}, render tier {tier}, "
          f"{'no scaling' if args.no_scale else f'downscale to {width}x{height}'})...")
    print(f"[2/3] Generating image with {args.model} (this can take a while)...")
    try:
        image_path, prompt, ctx, env = make_poster(
            args.lat, args.lon, when, birds,
            language=args.language, title=args.title,
            width=width, height=height, model=args.model,
            image_size=args.image_size, scale=not args.no_scale,
            out=args.out, out_dir=args.out_dir, location_name=args.location,
            weather=weather, fetch_weather=not args.no_weather, usage_sink=usage,
        )
    except Exception as exc:
        print(f"✗ Failed: {type(exc).__name__}: {exc}")
        sys.exit(1)

    from PIL import Image

    with Image.open(image_path) as _im:
        actual_w, actual_h = _im.size
    print(f"      location: {ctx.location_name} | season: {env.season}")
    print(f"      weather:  {ctx.weather.describe() if ctx.weather else '(skipped)'}")
    print(f"✓ Image:  {image_path} ({image_path.stat().st_size} bytes, {actual_w}x{actual_h})")
    print(f"  Prompt: {image_path.with_suffix('.txt')}")
    print("Token usage / estimated cost:")
    print(summarize(usage))

    if args.tv:
        from birdscreen.samsung_tv import upload_image

        print(f"[3/3] Uploading to TV {args.tv} (accept the popup if shown)...")
        try:
            content_id = upload_image(args.tv, image_path, token_file=args.token_file)
            print(f"✓ Uploaded + displayed on {args.tv}: {content_id}")
        except Exception as exc:
            print(f"✗ TV upload failed: {type(exc).__name__}: {exc}")
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
