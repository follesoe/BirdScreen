"""FastAPI backend: browse generated posters and view recent logs.

Run with:  uv run --extra web birdscreen-web
The React frontend (built to ``frontend/dist``) is served at ``/``.
"""

from __future__ import annotations

import logging
import os
import socket
from datetime import datetime
from pathlib import Path

import requests
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel

from birdscreen import birdnet, engine, state
from birdscreen.config import ScheduleConfig, SettingsConfig, TvConfig, load_config, save_config
from birdscreen.geocode import reverse_geocode
from birdscreen.logging_config import recent_logs, setup_logging
from birdscreen.samsung_tv import art_state, get_device_info
from birdscreen.weather import fetch_current_weather

logger = logging.getLogger(__name__)

POSTERS_DIR = Path("posters")
THUMB_DIR = Path("cache/thumbs")
FRONTEND_DIST = Path("frontend/dist")
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
_THUMB_MAX = 480
_SERVER_ERROR_STATUS = 500  # HTTP 5xx → treat the server as unhealthy


class PosterInfo(BaseModel):
    """Metadata for one generated poster in the gallery."""

    name: str
    date: str | None  # ISO date parsed from the filename, if recognisable
    modified: str  # ISO mtime
    size_bytes: int


class TvStatus(BaseModel):
    """Live status for a TV (REST device info, plus Art-websocket state once paired)."""

    connected: bool
    name: str | None = None
    model: str | None = None
    resolution: str | None = None
    firmware: str | None = None
    supports_art_mode: bool = False  # the TV *supports* Art Mode
    art_mode_on: bool | None = None  # currently *in* Art Mode (None = unknown / not paired)
    paired: bool = False  # we have a cached Art-websocket token for this TV
    token_auth: bool = False
    message: str | None = None


class BirdnetStatus(BaseModel):
    """Reachability of the configured BirdNET-Go server."""

    connected: bool
    status_code: int | None = None
    server: str | None = None  # the Server response header, if any
    message: str | None = None


class LocationInfo(BaseModel):
    """Resolved location (from settings override or BirdNET-Go) + a place name."""

    latitude: float | None = None
    longitude: float | None = None
    name: str | None = None
    source: str = "none"  # 'settings' | 'birdnet' | 'none'


class GenerationLogEntry(BaseModel):
    """One past poster generation (a row of the history log)."""

    id: int
    created_at: str
    trigger: str
    reason: str | None
    birds: list[str]
    location: str | None
    season: str | None
    weather: str | None
    model: str
    image_size: str
    output: str | None


class StatusResponse(BaseModel):
    """Everything a human wants to know about what the engine is doing right now."""

    now: str
    bird_day_start: str
    in_active_window: bool
    current_window: str | None
    next_window_start: str | None
    generations_today: int
    daily_cap: int
    next_state: str
    next_eligible_at: str | None
    next_reason: str
    weather: str | None
    location_name: str | None
    birdnet_connected: bool
    species_today: list[str]
    last_generation: GenerationLogEntry | None
    tvs: list[TvConfig]


def _parse_date(name: str) -> str | None:
    token = name.split("_", 1)[0]
    try:
        return datetime.strptime(token, "%Y-%m-%dT%H%M").isoformat()
    except ValueError:
        return None


def list_posters() -> list[PosterInfo]:
    """All poster images in ``posters/``, newest first."""
    if not POSTERS_DIR.is_dir():
        return []
    items = [
        PosterInfo(
            name=path.name,
            date=_parse_date(path.name),
            modified=datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
            size_bytes=path.stat().st_size,
        )
        for path in POSTERS_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in _IMAGE_SUFFIXES
    ]
    return sorted(items, key=lambda p: p.modified, reverse=True)


def _safe_poster_path(name: str) -> Path:
    """Resolve ``name`` inside ``posters/``, guarding against path traversal."""
    path = (POSTERS_DIR / name).resolve()
    if POSTERS_DIR.resolve() not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="poster not found")
    return path


def _thumbnail(name: str) -> Path:
    source = _safe_poster_path(name)
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    thumb = THUMB_DIR / f"{source.stem}.jpg"
    if not thumb.exists() or thumb.stat().st_mtime < source.stat().st_mtime:
        with Image.open(source) as img:
            rgb = img.convert("RGB")
            rgb.thumbnail((_THUMB_MAX, _THUMB_MAX), Image.Resampling.LANCZOS)
            rgb.save(thumb, "JPEG", quality=82)
    return thumb


def _tv_token_file(ip: str) -> Path:
    """Per-TV Art-websocket token file (so multiple TVs don't clobber each other)."""
    return Path(f".tv-token-{ip.replace('.', '-').replace(':', '-')}")


def _tv_status(ip: str, *, pair: bool = False) -> TvStatus:
    """REST device info, plus authoritative Art-mode state over the websocket.

    The REST ``FrameTVSupport`` flag is unreliable on older Frames, so once we have
    a token (or ``pair`` is requested) we read ``supports``/``in art mode`` from the
    Art websocket. ``pair=True`` will trigger the TV's Allow popup if not yet paired;
    auto-checks pass ``pair=False`` so they never pop up.
    """
    logger.info("Checking TV at %s", ip)
    try:
        info = get_device_info(ip)
    except Exception as exc:
        logger.warning("TV %s unreachable: %s", ip, exc)
        return TvStatus(connected=False, message=f"Could not reach the TV: {exc}")
    device = info.get("device", {})

    def truthy(value: object) -> bool:
        return str(value).lower() == "true"

    token = _tv_token_file(ip)
    paired = token.exists() and token.stat().st_size > 0
    supports = truthy(device.get("FrameTVSupport"))
    art_mode_on: bool | None = None
    if pair or paired:
        try:
            supported_ws, art_mode_on = art_state(ip, str(token))
            supports = supports or supported_ws
            paired = True
        except Exception as exc:
            logger.warning("TV %s Art websocket failed: %s", ip, exc)

    status = TvStatus(
        connected=True,
        name=device.get("name"),
        model=device.get("modelName"),
        resolution=device.get("resolution"),
        firmware=info.get("version") or device.get("firmwareVersion"),
        supports_art_mode=supports,
        art_mode_on=art_mode_on,
        paired=paired,
        token_auth=truthy(device.get("TokenAuthSupport")),
    )
    logger.info(
        "TV %s: %s (supports Art Mode: %s, in Art Mode: %s)",
        ip,
        status.model,
        status.supports_art_mode,
        status.art_mode_on,
    )
    return status


def _birdnet_status(url: str) -> BirdnetStatus:
    """Check the configured BirdNET-Go server is reachable (server-side HTTP GET)."""
    base = url.rstrip("/")
    if not base:
        return BirdnetStatus(connected=False, message="No BirdNET-Go URL set.")
    logger.info("Checking BirdNET-Go at %s", base)
    try:
        resp = requests.get(base, timeout=5)
    except requests.RequestException as exc:
        logger.warning("BirdNET-Go %s unreachable: %s", base, exc)
        return BirdnetStatus(connected=False, message=f"Could not reach BirdNET-Go: {exc}")
    reachable = resp.status_code < _SERVER_ERROR_STATUS
    logger.info(
        "BirdNET-Go %s: HTTP %s (%s)", base, resp.status_code, "reachable" if reachable else "error"
    )
    return BirdnetStatus(
        connected=reachable,
        status_code=resp.status_code,
        server=resp.headers.get("Server"),
        message="Reachable." if reachable else f"Server returned {resp.status_code}.",
    )


def _resolve_location(settings: SettingsConfig) -> LocationInfo:
    """Location from the manual override, else read from BirdNET-Go; + a place name."""
    coords: tuple[float, float] | None = None
    source = "none"
    if settings.latitude is not None and settings.longitude is not None:
        coords = (settings.latitude, settings.longitude)
        source = "settings"
    elif settings.birdnet_url:
        try:
            coords = birdnet.fetch_location(settings.birdnet_url)
            source = "birdnet" if coords else "none"
        except Exception as exc:
            logger.warning("BirdNET-Go location lookup failed: %s", exc)
    name: str | None = None
    if coords is not None:
        try:
            name = reverse_geocode(coords[0], coords[1])
        except Exception as exc:
            logger.warning("Reverse geocode failed: %s", exc)
    return LocationInfo(
        latitude=coords[0] if coords else None,
        longitude=coords[1] if coords else None,
        name=name,
        source=source,
    )


def _to_log_entry(record: state.GenerationRecord) -> GenerationLogEntry:
    return GenerationLogEntry(
        id=record.id,
        created_at=record.created_at,
        trigger=record.trigger,
        reason=record.reason,
        birds=record.birds,
        location=record.location,
        season=record.season,
        weather=record.weather,
        model=record.model,
        image_size=record.image_size,
        output=record.output,
    )


def _compute_status() -> StatusResponse:
    config = load_config()
    schedule = config.schedule
    settings = config.settings
    now = datetime.now()

    day_start = engine.bird_day_start(now, schedule.day_reset)
    window = engine.active_window(now, schedule)
    upcoming = engine.next_window_start(now, schedule)
    gens_today = state.count_generations_since(day_start)
    last = state.last_generation()
    last_at = datetime.fromisoformat(last.created_at) if last else None
    plan = engine.plan_next(now, schedule, generations_today=gens_today, last_generation_at=last_at)

    location = _resolve_location(settings)
    weather_text: str | None = None
    if settings.use_weather and location.latitude is not None and location.longitude is not None:
        try:
            weather_text = fetch_current_weather(location.latitude, location.longitude).describe()
        except Exception as exc:
            logger.warning("Weather fetch failed: %s", exc)

    birdnet_connected = False
    species: list[str] = []
    if settings.birdnet_url:
        try:
            # High-confidence species only — low-confidence detections (e.g. a lone
            # 0.65 sothøne) are intentionally dropped to avoid false positives.
            species = birdnet.today_species(settings.birdnet_url)
            birdnet_connected = True
        except Exception as exc:
            logger.warning("BirdNET-Go species fetch failed: %s", exc)

    return StatusResponse(
        now=now.isoformat(),
        bird_day_start=day_start.isoformat(),
        in_active_window=window is not None,
        current_window=f"{window.start}–{window.end}" if window else None,
        next_window_start=upcoming.isoformat() if upcoming else None,
        generations_today=gens_today,
        daily_cap=schedule.daily_cap,
        next_state=plan.state,
        next_eligible_at=plan.eligible_at.isoformat() if plan.eligible_at else None,
        next_reason=plan.reason,
        weather=weather_text,
        location_name=location.name,
        birdnet_connected=birdnet_connected,
        species_today=species,
        last_generation=_to_log_entry(last) if last else None,
        tvs=config.tvs,
    )


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(title="BirdScreen", version="0.1.0")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/posters")
    def posters() -> list[PosterInfo]:
        return list_posters()

    @app.get("/api/posters/{name}/image")
    def poster_image(name: str) -> FileResponse:
        return FileResponse(_safe_poster_path(name))

    @app.get("/api/posters/{name}/thumb")
    def poster_thumb(name: str) -> FileResponse:
        return FileResponse(_thumbnail(name))

    @app.get("/api/logs")
    def logs() -> dict[str, list[str]]:
        return {"lines": recent_logs()}

    @app.get("/api/config/schedule")
    def get_schedule() -> ScheduleConfig:
        return load_config().schedule

    @app.put("/api/config/schedule")
    def put_schedule(schedule: ScheduleConfig) -> ScheduleConfig:
        config = load_config()
        config.schedule = schedule
        save_config(config)
        return config.schedule

    @app.get("/api/config/settings")
    def get_settings() -> SettingsConfig:
        return load_config().settings

    @app.put("/api/config/settings")
    def put_settings(settings: SettingsConfig) -> SettingsConfig:
        config = load_config()
        config.settings = settings
        save_config(config)
        return config.settings

    @app.get("/api/config/tvs")
    def get_tvs() -> list[TvConfig]:
        return load_config().tvs

    @app.put("/api/config/tvs")
    def put_tvs(tvs: list[TvConfig]) -> list[TvConfig]:
        config = load_config()
        config.tvs = tvs
        save_config(config)
        return config.tvs

    @app.get("/api/tvs/status")
    def tv_status(ip: str, pair: bool = False) -> TvStatus:
        return _tv_status(ip, pair=pair)

    @app.get("/api/birdnet/status")
    def birdnet_status(url: str) -> BirdnetStatus:
        return _birdnet_status(url)

    @app.get("/api/birdnet/location")
    def birdnet_location() -> LocationInfo:
        return _resolve_location(load_config().settings)

    @app.get("/api/status")
    def status() -> StatusResponse:
        return _compute_status()

    @app.get("/api/generations")
    def generations() -> list[GenerationLogEntry]:
        return [_to_log_entry(record) for record in state.recent_generations(limit=50)]

    if FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
    else:

        @app.get("/")
        def placeholder() -> HTMLResponse:
            return HTMLResponse(
                "<h1>BirdScreen</h1><p>Frontend not built yet — run "
                "<code>npm --prefix frontend run build</code>.</p>"
            )

    return app


def _lan_ip() -> str:
    """Best-effort primary LAN IP (for logging a reachable URL)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))  # no packets sent; just selects the egress interface
        return str(sock.getsockname()[0])
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def main() -> None:
    setup_logging()
    # Bind all interfaces by default so other devices on the LAN can reach the UI;
    # override with BIRDSCREEN_WEB_HOST / BIRDSCREEN_WEB_PORT.
    host = os.environ.get("BIRDSCREEN_WEB_HOST", "0.0.0.0")
    port = int(os.environ.get("BIRDSCREEN_WEB_PORT", "8000"))
    logger.info(
        "Starting BirdScreen web — local: http://127.0.0.1:%d  LAN: http://%s:%d",
        port,
        _lan_ip(),
        port,
    )
    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    main()
