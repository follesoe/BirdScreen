"""FastAPI backend: browse generated posters and view recent logs.

Run with:  uv run --extra web birdscreen-web
The React frontend (built to ``frontend/dist``) is served at ``/``.
"""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import requests
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel

from birdscreen import birdnet, engine, generate, state
from birdscreen.config import ScheduleConfig, SettingsConfig, TvConfig, load_config, save_config
from birdscreen.geocode import reverse_geocode
from birdscreen.images import prepare_for_frame
from birdscreen.logging_config import recent_logs, setup_logging
from birdscreen.samsung_tv import art_state, get_device_info, replace_art
from birdscreen.weather import fetch_current_weather

logger = logging.getLogger(__name__)

POSTERS_DIR = Path("posters")
THUMB_DIR = Path("cache/thumbs")
FRONTEND_DIST = Path("frontend/dist")
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
_THUMB_MAX = 480
_SERVER_ERROR_STATUS = 500  # HTTP 5xx → treat the server as unhealthy
_generation_lock = threading.Lock()  # prevents overlapping manual/auto generations
_geocode_cache: dict[tuple[float, float], str | None] = {}  # coords → place name (stable)
_coords_cache: dict[str, tuple[float, float] | None] = {}  # birdnet_url → lat/lon (stable)
_SCHEDULER_INTERVAL_S = 120  # how often the auto-generation loop re-checks the rules


class _SchedulerState:
    """Mutable state for the background auto-generation loop (avoids module globals)."""

    started = False
    pending_since: datetime | None = None  # when new species first appeared (debounce)


_scheduler = _SchedulerState()


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
    prompt: str | None
    total_tokens: int | None
    cost_usd: float | None


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
    next_light_refresh: str | None
    next_light_refresh_kind: str | None
    weather: str | None
    location_name: str | None
    birdnet_connected: bool
    species_today: list[str]
    last_generation: GenerationLogEntry | None
    tvs: list[TvConfig]


class GenerateResult(BaseModel):
    """Outcome of a manual 'generate now' request."""

    started: bool
    message: str


class SendResult(BaseModel):
    """Outcome of hanging a poster on the configured Frame TV(s)."""

    ok: bool
    message: str


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


def _tv_art_file(ip: str) -> Path:
    """Per-TV file caching the content_id of the poster currently hung on it."""
    return Path(f".tv-art-{ip.replace('.', '-').replace(':', '-')}")


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


def _resolve_coords(settings: SettingsConfig) -> tuple[tuple[float, float] | None, str]:
    """(lat, lon), source — manual override, else read from BirdNET-Go (cached; stable)."""
    if settings.latitude is not None and settings.longitude is not None:
        return (settings.latitude, settings.longitude), "settings"
    if not settings.birdnet_url:
        return None, "none"
    if settings.birdnet_url not in _coords_cache:
        try:
            _coords_cache[settings.birdnet_url] = birdnet.fetch_location(settings.birdnet_url)
        except Exception as exc:
            logger.warning("BirdNET-Go location lookup failed: %s", exc)
            return None, "none"
    coords = _coords_cache[settings.birdnet_url]
    return coords, ("birdnet" if coords else "none")


def _geocode_name(coords: tuple[float, float] | None) -> str | None:
    """Reverse-geocode a place name, cached by (rounded) coordinates — location is stable."""
    if coords is None:
        return None
    key = (round(coords[0], 3), round(coords[1], 3))
    if key not in _geocode_cache:
        try:
            _geocode_cache[key] = reverse_geocode(coords[0], coords[1])
        except Exception as exc:
            logger.warning("Reverse geocode failed: %s", exc)
            return None
    return _geocode_cache[key]


def _weather_text(settings: SettingsConfig, coords: tuple[float, float] | None) -> str | None:
    if not settings.use_weather or coords is None:
        return None
    try:
        return fetch_current_weather(coords[0], coords[1]).describe()
    except Exception as exc:
        logger.warning("Weather fetch failed: %s", exc)
        return None


def _birdnet_species(
    settings: SettingsConfig, day_start: datetime, now: datetime
) -> tuple[list[str], bool]:
    """(species common names for the bird-day, reachable?) — high-confidence only."""
    if not settings.birdnet_url:
        return [], False
    try:
        species = [
            c for _s, c in birdnet.birds_for_day(settings.birdnet_url, start=day_start, now=now)
        ]
    except Exception as exc:
        logger.warning("BirdNET-Go species fetch failed: %s", exc)
        return [], False
    return species, True


def _resolve_location(settings: SettingsConfig) -> LocationInfo:
    """Location from the manual override, else read from BirdNET-Go; + a place name."""
    coords, source = _resolve_coords(settings)
    return LocationInfo(
        latitude=coords[0] if coords else None,
        longitude=coords[1] if coords else None,
        name=_geocode_name(coords),
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
        prompt=record.prompt,
        total_tokens=record.total_tokens,
        cost_usd=record.cost_usd,
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
    plan = engine.plan_next(
        now,
        schedule,
        generations_today=gens_today,
        last_generation_at=last_at,
        has_enabled_tv=any(tv.enabled for tv in config.tvs),
    )

    # BirdNET-Go is the slow part (~5s each for location + species), so run those two
    # in parallel; the geocode + weather lookups are fast (and cached) and need the
    # coordinates, so they follow once coords resolve.
    with ThreadPoolExecutor(max_workers=2) as pool:
        coords_future = pool.submit(_resolve_coords, settings)
        species_future = pool.submit(_birdnet_species, settings, day_start, now)
        coords, _source = coords_future.result()
        species, birdnet_connected = species_future.result()
    location_name = _geocode_name(coords)
    weather_text = _weather_text(settings, coords)

    # The next sun-driven light/weather refresh still to come today (if enabled).
    light_at: str | None = None
    light_kind: str | None = None
    tz = now.astimezone().tzinfo
    if schedule.light_refresh and coords is not None and tz is not None:
        upcoming_moments = sorted(
            (moment, name)
            for name, moment in engine.key_moments(coords[0], coords[1], now.date(), tz).items()
            if moment > now
        )
        if upcoming_moments:
            light_at = upcoming_moments[0][0].isoformat()
            light_kind = upcoming_moments[0][1]

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
        next_light_refresh=light_at,
        next_light_refresh_kind=light_kind,
        weather=weather_text,
        location_name=location_name,
        birdnet_connected=birdnet_connected,
        species_today=species,
        last_generation=_to_log_entry(last) if last else None,
        tvs=config.tvs,
    )


def _run_generation_locked(trigger: str, reason: str) -> None:
    """Generate one poster and auto-hang it on the enabled TV(s).

    The single choke point for *all* generation (manual + scheduler). The caller MUST
    already hold ``_generation_lock``; this releases it. Because every path acquires
    that lock first, two generations can never run at the same time.
    """
    _scheduler.pending_since = None
    try:
        logger.info("Generating (%s) — %s", trigger, reason)
        record = generate.generate_now(trigger=trigger, reason=reason)
        if record.output:
            result = _send_to_tvs(record.output, enabled_only=True)
            logger.info("Hung %s — %s", record.output, result.message)
    except Exception:
        logger.exception("Generation failed (%s)", trigger)
    finally:
        _generation_lock.release()


def _send_to_tvs(name: str, *, enabled_only: bool = False) -> SendResult:
    """Hang ``name`` on the configured TVs, overwriting BirdScreen's previous poster.

    With ``enabled_only`` the push is limited to TVs whose 'update' toggle is on — used
    by automatic generation; the manual button targets all configured TVs.
    """
    poster = _safe_poster_path(name)
    tvs = load_config().tvs
    if enabled_only:
        tvs = [tv for tv in tvs if tv.enabled]
    if not tvs:
        msg = (
            "No TVs are enabled for updates."
            if enabled_only
            else "No Frame TVs are configured yet."
        )
        return SendResult(ok=False, message=msg)

    Path("cache").mkdir(exist_ok=True)
    frame_ready = prepare_for_frame(poster, dst=Path("cache/birdscreen.jpg"))

    hung: list[str] = []
    failed: list[str] = []
    for tv in tvs:
        art_file = _tv_art_file(tv.ip)
        # BirdScreen's own last upload on this TV; only this is deleted, so the user's
        # personal photos are never touched.
        previous = art_file.read_text(encoding="utf-8").strip() if art_file.exists() else None
        try:
            content_id = replace_art(
                tv.ip,
                frame_ready,
                token_file=str(_tv_token_file(tv.ip)),
                previous_id=previous or None,
            )
            art_file.write_text(content_id, encoding="utf-8")
            hung.append(tv.name)
            logger.info("Hung %s on %s (content_id=%s)", name, tv.name, content_id)
        except Exception as exc:
            failed.append(f"{tv.name} ({exc})")
            logger.warning("Could not hang %s on %s: %s", name, tv.name, exc)

    if hung and not failed:
        return SendResult(ok=True, message=f"Hung on {', '.join(hung)}.")
    if hung:
        return SendResult(
            ok=True, message=f"Hung on {', '.join(hung)}; couldn't reach {', '.join(failed)}."
        )
    return SendResult(
        ok=False,
        message=(
            f"Couldn't reach {', '.join(failed)}. "
            "If the TV shows an 'Allow' popup, accept it with the remote and try again."
        ),
    )


def _auto_generate(trigger: str, reason: str) -> None:
    """Acquire the generation lock and run one generation; skip if one is already running."""
    if not _generation_lock.acquire(blocking=False):
        logger.info("Scheduler: skipping (%s) — a generation is already running", trigger)
        return
    _run_generation_locked(trigger, reason)


def _species_to_paint(
    settings: SettingsConfig,
    day_start: datetime,
    now: datetime,
    last: state.GenerationRecord | None,
    last_at: datetime | None,
) -> set[str]:
    """Species warranting a render: new ones since today's last poster, or all if none yet."""
    if not settings.birdnet_url:
        return set()
    try:
        species = {
            c for _s, c in birdnet.birds_for_day(settings.birdnet_url, start=day_start, now=now)
        }
    except Exception as exc:
        logger.warning("Scheduler: species fetch failed: %s", exc)
        return set()
    last_today = last is not None and last_at is not None and last_at >= day_start
    if not (last_today and last):
        return species  # first poster of the day → paint whatever has been heard
    return species - set(last.birds)


def _tick() -> None:
    """One scheduler pass: apply the rules and auto-generate when warranted."""
    config = load_config()
    schedule, settings = config.schedule, config.settings
    now = datetime.now()
    day_start = engine.bird_day_start(now, schedule.day_reset)
    last = state.last_generation()
    last_at = datetime.fromisoformat(last.created_at) if last else None
    plan = engine.plan_next(
        now,
        schedule,
        generations_today=state.count_generations_since(day_start),
        last_generation_at=last_at,
        has_enabled_tv=any(tv.enabled for tv in config.tvs),
    )

    if plan.state != "ready":
        logger.info("Scheduler tick: %s", plan.state)
        _scheduler.pending_since = None
        return

    new_species = _species_to_paint(settings, day_start, now, last, last_at)
    logger.info("Scheduler tick: ready — %d new species", len(new_species))

    # New species → debounce a burst, then paint (bird trigger).
    if new_species:
        if _scheduler.pending_since is None:
            _scheduler.pending_since = now
            logger.info(
                "Scheduler: %d new species — debouncing %d min",
                len(new_species),
                schedule.debounce_minutes,
            )
            return
        if (now - _scheduler.pending_since).total_seconds() >= schedule.debounce_minutes * 60:
            first_today = last is None or last_at is None or last_at < day_start
            trigger = "time" if first_today else "bird"
            reason = (
                "First poster of the day"
                if first_today
                else f"New birds heard: {', '.join(sorted(new_species))}"
            )
            _auto_generate(trigger, reason)
        return

    # No new species → repaint at a sun key-moment to refresh light + weather.
    _scheduler.pending_since = None
    coords, _src = _resolve_coords(settings)
    tz = now.astimezone().tzinfo
    if schedule.light_refresh and coords is not None and tz is not None:
        due = engine.due_refresh(coords[0], coords[1], now, last_at, tz)
        if due:
            _auto_generate("time", f"{due.capitalize()} light & weather refresh")


def _scheduler_loop() -> None:
    while True:
        time.sleep(_SCHEDULER_INTERVAL_S)
        try:
            _tick()
        except Exception:
            logger.exception("Scheduler tick failed")


def _start_scheduler() -> None:
    """Start the background auto-generation loop once (disabled by BIRDSCREEN_NO_SCHEDULER)."""
    if _scheduler.started or os.environ.get("BIRDSCREEN_NO_SCHEDULER"):
        return
    _scheduler.started = True
    threading.Thread(target=_scheduler_loop, daemon=True).start()
    logger.info("Auto-generation scheduler started (every %ds)", _SCHEDULER_INTERVAL_S)


def create_app() -> FastAPI:
    setup_logging()
    _start_scheduler()
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

    @app.post("/api/generate")
    def generate_now_endpoint() -> GenerateResult:
        if not _generation_lock.acquire(blocking=False):
            return GenerateResult(started=False, message="A generation is already in progress.")
        threading.Thread(
            target=_run_generation_locked,
            args=("manual", "Generated from the dashboard"),
            daemon=True,
        ).start()
        return GenerateResult(started=True, message="Generation started.")

    @app.post("/api/tvs/send")
    def send_to_tvs_endpoint(name: str) -> SendResult:
        return _send_to_tvs(name)

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
