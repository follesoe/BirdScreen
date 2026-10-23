"""FastAPI backend: browse generated posters and view recent logs.

Run with:  uv run --extra web birdscreen-web
The React frontend (built to ``frontend/dist``) is served at ``/``.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import requests
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel

from birdscreen import birdnet, engine, gemini, generate, state
from birdscreen.config import ScheduleConfig, SettingsConfig, TvConfig, load_config, save_config
from birdscreen.geocode import reverse_geocode
from birdscreen.images import prepare_for_frame
from birdscreen.logging_config import recent_logs, setup_logging
from birdscreen.samsung_tv import art_state, get_device_info, is_reachable, replace_art
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
# Quick "is the TV awake?" check before an automatic upload. A sleeping Frame drops off
# the network, and a plain upload then burns ~2.5 min on two 75 s connect timeouts.
_TV_PROBE_TIMEOUT_S = 5.0
_TV_ASLEEP = "no answer, the TV is off or asleep"
_tv_lock = threading.Lock()  # one push to the TVs at a time (generation, retry, manual)
# A TV that answers but still rejects a retried poster (e.g. an 'Allow' popup is waiting)
# is tried again after this long, and given up on after a few failures.
_RETRY_BACKOFF_S = 600
_RETRY_MAX_FAILURES = 3


@dataclass
class _RetryBackoff:
    """Failed retries of the poster waiting for one TV."""

    poster: str
    failures: int = 0
    not_before: float = 0.0  # time.monotonic()


_retry_backoff: dict[str, _RetryBackoff] = {}  # TV ip → its waiting poster's failed tries


class _SchedulerState:
    """Mutable state for the background auto-generation loop (avoids module globals)."""

    started = False
    pending_since: datetime | None = None  # when new species first appeared (debounce)
    # Passive Gemini signal: the classified outcome of the last real generation attempt.
    # Set when a paint fails, cleared on success — so "out of credits" surfaces for free,
    # from an actual attempt, with no extra probe. (None kind = no failure on record.)
    last_error_kind: str | None = None
    last_error_message: str | None = None
    last_error_detail: str | None = None
    last_error_at: datetime | None = None


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
    detail: str | None = None  # full error text (shown behind a "details" toggle)
    server_ip: str | None = None  # the server's own IP on the route toward this TV
    subnet_mismatch: bool = False  # server and TV look to be on different subnets


class BirdnetStatus(BaseModel):
    """Reachability of the configured BirdNET-Go server."""

    connected: bool
    status_code: int | None = None
    server: str | None = None  # the Server response header, if any
    message: str | None = None
    detail: str | None = None  # full error text (shown behind a "details" toggle)


class GeminiStatus(BaseModel):
    """Whether Gemini can generate right now (key valid + credits available).

    Two signals feed this: the *passive* outcome of the last real generation attempt
    (free — a failed paint already told us we're out of credits) and an on-demand
    *live probe* (one tiny billable call, ``checked_live``), used to confirm a top-up
    when no real generation has run since.
    """

    kind: str  # 'ok' | 'out_of_credits' | 'rate_limited' | 'no_key' | 'auth' | 'error' | 'unknown'
    out_of_credits: bool  # prepaid billing depleted (needs a top-up, not self-healing)
    checked_live: bool  # True = fresh billable probe; False = passive last-known state
    model: str  # the configured image model (what generation actually uses)
    message: str
    detail: str | None = None  # full error text (shown behind a "details" toggle)
    since: str | None = None  # ISO time the reported state was observed


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
    pending_species: list[str]  # new birds since the last poster that will trigger the next paint
    next_light_refresh: str | None
    next_light_refresh_kind: str | None
    weather: str | None
    location_name: str | None
    birdnet_connected: bool
    species_today: list[str]
    last_generation: GenerationLogEntry | None
    tvs: list[TvConfig]
    waiting_tvs: list[str] = []  # enabled TVs that missed a poster; it hangs when they wake


class GenerateResult(BaseModel):
    """Outcome of a manual 'generate now' request."""

    started: bool
    message: str


class SendResult(BaseModel):
    """Outcome of hanging a poster on the configured Frame TV(s)."""

    ok: bool
    message: str


class StorageInfo(BaseModel):
    """Disk usage and where BirdScreen is running from."""

    working_dir: str
    posters_bytes: int
    posters_count: int
    database_bytes: int


def _storage_info() -> StorageInfo:
    """Poster-folder + database sizes and the current working directory."""
    posters_bytes = posters_count = 0
    if POSTERS_DIR.is_dir():
        for path in POSTERS_DIR.iterdir():
            if path.is_file() and path.suffix.lower() in _IMAGE_SUFFIXES:
                posters_bytes += path.stat().st_size
                posters_count += 1
    db_dir = state.DB_PATH.parent
    db_bytes = (
        sum(p.stat().st_size for p in db_dir.glob(f"{state.DB_PATH.name}*") if p.is_file())
        if db_dir.is_dir()
        else 0
    )
    return StorageInfo(
        working_dir=str(Path.cwd()),
        posters_bytes=posters_bytes,
        posters_count=posters_count,
        database_bytes=db_bytes,
    )


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


def _poster_path(name: str) -> Path | None:
    """Resolve ``name`` inside ``posters/`` (guarding against path traversal), or None."""
    path = (POSTERS_DIR / name).resolve()
    if not name or POSTERS_DIR.resolve() not in path.parents or not path.is_file():
        return None
    return path


def _safe_poster_path(name: str) -> Path:
    """Like ``_poster_path`` but a 404 for the API when there's no such poster."""
    path = _poster_path(name)
    if path is None:
        raise HTTPException(status_code=404, detail="poster not found")
    return path


def _latest_poster_path() -> Path:
    """The most recently modified poster image, or 404 if there are none yet."""
    candidates = (
        [p for p in POSTERS_DIR.iterdir() if p.is_file() and p.suffix.lower() in _IMAGE_SUFFIXES]
        if POSTERS_DIR.is_dir()
        else []
    )
    if not candidates:
        raise HTTPException(status_code=404, detail="no posters yet")
    return max(candidates, key=lambda p: p.stat().st_mtime)


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


def _tv_file(kind: str, ip: str) -> Path:
    """Per-TV state file, e.g. ``.tv-art-192-168-1-219`` (so TVs don't clobber each other)."""
    return Path(f".tv-{kind}-{ip.replace('.', '-').replace(':', '-')}")


def _tv_token_file(ip: str) -> Path:
    """Per-TV Art-websocket token file."""
    return _tv_file("token", ip)


def _tv_art_file(ip: str) -> Path:
    """Per-TV file caching the content_id of the poster currently hung on it."""
    return _tv_file("art", ip)


def _tv_pending_file(ip: str) -> Path:
    """Per-TV file naming a poster that missed the TV and is waiting to be hung.

    A file (not memory) so a restart doesn't forget it. Cleared by any successful hang.
    """
    return _tv_file("pending", ip)


def _tv_paired(ip: str) -> bool:
    """True once the TV's 'Allow' popup has been accepted (a token is cached)."""
    token = _tv_token_file(ip)
    return token.exists() and token.stat().st_size > 0


# Durable copy of the passive Gemini error so it survives a process restart. Without it,
# a depleted-credits state would reset to a falsely-healthy "ok" on every restart until
# the next paint fails again (which may be hours away, outside an active window).
_GEMINI_ERROR_FILE = Path("cache/gemini_error.json")


def _write_gemini_error(payload: dict[str, str]) -> None:
    try:
        _GEMINI_ERROR_FILE.parent.mkdir(parents=True, exist_ok=True)
        _GEMINI_ERROR_FILE.write_text(json.dumps(payload), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not persist Gemini error state: %s", exc)


def _persisted_gemini_error() -> dict[str, str] | None:
    try:
        raw = _GEMINI_ERROR_FILE.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    return {str(key): str(value) for key, value in data.items()}


def _record_gemini_error(exc: BaseException) -> None:
    """Remember a *Gemini* generation failure as the passive signal (durably).

    No-ops for non-Gemini failures (image processing, TV upload, a missing location) so a
    downstream error is never mislabeled as a Gemini/credits problem in Settings.
    """
    if not gemini.is_gemini_error(exc):
        return
    kind, message = gemini.classify_api_error(exc)
    detail = str(exc)
    at = datetime.now()
    _scheduler.last_error_kind = kind
    _scheduler.last_error_message = message
    _scheduler.last_error_detail = detail
    _scheduler.last_error_at = at
    _write_gemini_error({"kind": kind, "message": message, "detail": detail, "at": at.isoformat()})


def _clear_gemini_error() -> None:
    """Forget any recorded failure (a Gemini call has since succeeded)."""
    _scheduler.last_error_kind = None
    _scheduler.last_error_message = None
    _scheduler.last_error_detail = None
    _scheduler.last_error_at = None
    try:
        _GEMINI_ERROR_FILE.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Could not clear persisted Gemini error state: %s", exc)


def _gemini_status(*, probe: bool = False) -> GeminiStatus:
    """Report whether Gemini can generate right now.

    The API key exposes no credit-balance endpoint, so "out of credits" can only be
    learned by *attempting* a billable call and reading the error. This has two modes:

    - passive (default): report the outcome of the last *real* generation attempt —
      free, and already accurate whenever the scheduler has recently tried to paint.
    - ``probe``: make one tiny billable call now (a cheap text model that shares the key
      + billing with the image model) to confirm live — e.g. right after a top-up.
    """
    model = load_config().settings.model

    if probe:
        try:
            gemini.check_health()
        except Exception as exc:
            _record_gemini_error(exc)
            kind, message = gemini.classify_api_error(exc)
            logger.warning("Gemini probe failed (%s): %s", kind, exc)
            return GeminiStatus(
                kind=kind,
                out_of_credits=kind == "out_of_credits",
                checked_live=True,
                model=model,
                message=message,
                detail=str(exc),
                since=_scheduler.last_error_at.isoformat() if _scheduler.last_error_at else None,
            )
        _clear_gemini_error()
        return GeminiStatus(
            kind="ok",
            out_of_credits=False,
            checked_live=True,
            model=model,
            message="Connected — API key valid and credits available.",
            since=datetime.now().isoformat(),
        )

    # Passive: surface the last real failure — from memory, or the persisted copy that
    # survives a restart (so a depleted-credits state isn't forgotten on reboot)…
    error_kind = _scheduler.last_error_kind
    error_message = _scheduler.last_error_message
    error_detail = _scheduler.last_error_detail
    error_at = _scheduler.last_error_at.isoformat() if _scheduler.last_error_at else None
    if error_kind is None:
        persisted = _persisted_gemini_error()
        if persisted is not None:
            error_kind = persisted.get("kind")
            error_message = persisted.get("message")
            error_detail = persisted.get("detail")
            error_at = persisted.get("at")
    if error_kind is not None:
        return GeminiStatus(
            kind=error_kind,
            out_of_credits=error_kind == "out_of_credits",
            checked_live=False,
            model=model,
            message=error_message or "Gemini generation failed.",
            detail=error_detail,
            since=error_at,
        )

    # …otherwise fall back to the last successful paint, or "not tested yet".
    last = state.last_generation()
    if last is not None and last.output:
        return GeminiStatus(
            kind="ok",
            out_of_credits=False,
            checked_live=False,
            model=model,
            message="Last poster generated successfully — no errors since.",
            since=last.created_at,
        )
    return GeminiStatus(
        kind="unknown",
        out_of_credits=False,
        checked_live=False,
        model=model,
        message="No generation attempted yet — run a test to check credits.",
    )


def _local_ip_toward(host: str) -> str | None:
    """The server's own source IP the OS would use to reach ``host`` (sends nothing).

    A UDP ``connect`` only resolves the route locally — no packets leave — so this is
    cheap and works even when ``host`` is unreachable, as long as a route exists.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect((host, 9))  # port 9 (discard) is never actually contacted
            return str(sock.getsockname()[0])
    except OSError:
        return None


def _different_subnet(server_ip: str | None, tv_ip: str) -> bool:
    """Best-effort: True if server and TV look to be on different /24 subnets.

    Uses a /24 mask — the near-universal home-LAN case. Only meant as a hint when the
    TV is unreachable, so on a wider-mask network (where /24 would over-report) it never
    becomes a false alarm because the UI shows it only alongside a failed connection.
    Returns False when either address isn't a plain IPv4 literal (e.g. a hostname).
    """
    if not server_ip:
        return False
    try:
        net = ipaddress.ip_network(f"{server_ip}/24", strict=False)
        return ipaddress.ip_address(tv_ip) not in net
    except ValueError:
        return False


def _tv_status(ip: str, *, pair: bool = False) -> TvStatus:
    """REST device info, plus authoritative Art-mode state over the websocket.

    The REST ``FrameTVSupport`` flag is unreliable on older Frames, so once we have
    a token (or ``pair`` is requested) we read ``supports``/``in art mode`` from the
    Art websocket. ``pair=True`` will trigger the TV's Allow popup if not yet paired;
    auto-checks pass ``pair=False`` so they never pop up.
    """
    logger.info("Checking TV at %s", ip)
    # Compute this first: a subnet mismatch makes the REST/websocket calls below fail, so
    # the hint has to ride along on the unreachable path too (it's the likely cause).
    server_ip = _local_ip_toward(ip)
    subnet_mismatch = _different_subnet(server_ip, ip)
    try:
        info = get_device_info(ip)
    except Exception as exc:
        logger.warning("TV %s unreachable: %s", ip, exc)
        return TvStatus(
            connected=False,
            message="Could not reach the TV.",
            detail=str(exc),
            server_ip=server_ip,
            subnet_mismatch=subnet_mismatch,
        )
    device = info.get("device", {})

    def truthy(value: object) -> bool:
        return str(value).lower() == "true"

    token = _tv_token_file(ip)
    paired = _tv_paired(ip)
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
        server_ip=server_ip,
        subnet_mismatch=subnet_mismatch,
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
        return BirdnetStatus(
            connected=False, message="Could not reach BirdNET-Go.", detail=str(exc)
        )
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

    # What the next poster is waiting on. When "ready", show whether new birds are pending
    # and *when* it will actually paint (after the debounce) — not just "now".
    last_today = last is not None and last_at is not None and last_at >= day_start
    pending = sorted(set(species) - set(last.birds)) if (last_today and last) else sorted(species)
    next_at = plan.eligible_at
    next_reason = plan.reason
    if plan.state == "ready":
        if pending:
            started = _scheduler.pending_since or now
            next_at = started + timedelta(minutes=schedule.debounce_minutes)
            count = len(pending)
            next_reason = (
                f"{count} new bird{'s' if count != 1 else ''} heard — "
                f"painting after a {schedule.debounce_minutes}-min debounce."
            )
        else:
            next_at = None
            next_reason = "Up to date — will paint when a new bird is heard."

    return StatusResponse(
        now=now.isoformat(),
        bird_day_start=day_start.isoformat(),
        in_active_window=window is not None,
        current_window=f"{window.start}–{window.end}" if window else None,
        next_window_start=upcoming.isoformat() if upcoming else None,
        generations_today=gens_today,
        daily_cap=schedule.daily_cap,
        next_state=plan.state,
        next_eligible_at=next_at.isoformat() if next_at else None,
        next_reason=next_reason,
        pending_species=pending,
        next_light_refresh=light_at,
        next_light_refresh_kind=light_kind,
        weather=weather_text,
        location_name=location_name,
        birdnet_connected=birdnet_connected,
        species_today=species,
        last_generation=_to_log_entry(last) if last else None,
        tvs=config.tvs,
        waiting_tvs=[tv.name for tv in _waiting_tvs(config.tvs)],
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
        _clear_gemini_error()  # Gemini produced an image → credits/key are fine
        if record.output:
            result = _send_to_tvs(record.output, automatic=True)
            logger.info("Sent %s to TVs — %s", record.output, result.message)
    except Exception as exc:
        logger.exception("Generation failed (%s)", trigger)
        _record_gemini_error(exc)  # no-ops unless exc is a genuine Gemini error
    finally:
        _generation_lock.release()


def _frame_ready(poster: Path) -> Path:
    """Write the Frame-ready JPEG of ``poster`` (the one uploaded to the TVs)."""
    Path("cache").mkdir(exist_ok=True)
    return prepare_for_frame(poster, dst=Path("cache/birdscreen.jpg"))


def _hang_on_tv(tv: TvConfig, name: str, frame_ready: Path, *, quick_check: bool) -> str | None:
    """Hang one poster on one TV. Returns None on success, else the error text.

    The caller must hold ``_tv_lock``. With ``quick_check`` a TV that doesn't answer
    within a few seconds fails at once, instead of after ~2.5 min of connect timeouts.
    A successful hang supersedes any poster still waiting for this TV.
    """
    if quick_check and not is_reachable(tv.ip, timeout=_TV_PROBE_TIMEOUT_S):
        logger.warning("Could not hang %s on %s: %s", name, tv.name, _TV_ASLEEP)
        return _TV_ASLEEP
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
    except Exception as exc:
        logger.warning("Could not hang %s on %s: %s", name, tv.name, exc)
        return str(exc)
    art_file.write_text(content_id, encoding="utf-8")
    _tv_pending_file(tv.ip).unlink(missing_ok=True)
    _retry_backoff.pop(tv.ip, None)
    logger.info("Hung %s on %s (content_id=%s)", name, tv.name, content_id)
    return None


def _send_to_tvs(name: str, *, automatic: bool = False) -> SendResult:
    """Hang ``name`` on the configured TVs, overwriting BirdScreen's previous poster.

    ``automatic`` is the after-generation push: only TVs whose 'update' toggle is on,
    a quick is-it-awake check first, and a TV that can't be reached is queued to get
    the poster when it wakes (see ``_retry_pending_hangs``). The manual button targets
    every configured TV, waits out the full connect timeout, and queues nothing.
    """
    poster = _safe_poster_path(name)
    tvs = load_config().tvs
    if automatic:
        tvs = [tv for tv in tvs if tv.enabled]
    if not tvs:
        msg = "No TVs are enabled for updates." if automatic else "No Frame TVs are configured yet."
        return SendResult(ok=False, message=msg)

    # The automatic push waits its turn; a manual click shouldn't hang the request
    # behind a slow upload that's already running.
    if not _tv_lock.acquire(blocking=automatic):
        return SendResult(
            ok=False, message="A poster is being hung on the TV right now. Try again in a minute."
        )
    hung: list[str] = []
    failed: list[str] = []
    try:
        frame_ready = _frame_ready(poster)
        for tv in tvs:
            error = _hang_on_tv(tv, name, frame_ready, quick_check=automatic)
            if error is None:
                hung.append(tv.name)
                continue
            failed.append(f"{tv.name} ({error})")
            if automatic:
                _tv_pending_file(tv.ip).write_text(name, encoding="utf-8")
                logger.info("Will hang %s on %s when it is back online", name, tv.name)
    finally:
        _tv_lock.release()

    later = " Will retry when it's back online." if automatic else ""
    if hung and not failed:
        return SendResult(ok=True, message=f"Hung on {', '.join(hung)}.")
    if hung:
        return SendResult(
            ok=True,
            message=f"Hung on {', '.join(hung)}; couldn't reach {', '.join(failed)}.{later}",
        )
    return SendResult(
        ok=False,
        message=(
            f"Couldn't reach {', '.join(failed)}. "
            "If the TV shows an 'Allow' popup, accept it with the remote and try again."
            f"{later}"
        ),
    )


def _pending_poster(tv: TvConfig) -> Path | None:
    """The poster still waiting to be hung on ``tv``, or None (nothing, or it's gone)."""
    pending_file = _tv_pending_file(tv.ip)
    if not pending_file.exists():
        return None
    return _poster_path(pending_file.read_text(encoding="utf-8").strip())


def _waiting_tvs(tvs: list[TvConfig]) -> list[TvConfig]:
    """Enabled TVs with a poster still waiting to be hung."""
    return [tv for tv in tvs if tv.enabled and _pending_poster(tv) is not None]


def _drop_pending(tv: TvConfig, why: str) -> None:
    logger.info("No longer waiting to hang a poster on %s: %s", tv.name, why)
    _tv_pending_file(tv.ip).unlink(missing_ok=True)
    _retry_backoff.pop(tv.ip, None)


def _retry_failed(tv: TvConfig, poster: Path, error: str) -> None:
    """The TV answered but the hang failed: back off, and give up after a few tries."""
    if not is_reachable(tv.ip, timeout=_TV_PROBE_TIMEOUT_S):
        return  # it went back to sleep mid-try: keep waiting, that's not a failure
    backoff = _retry_backoff.get(tv.ip)
    if backoff is None or backoff.poster != poster.name:
        backoff = _retry_backoff[tv.ip] = _RetryBackoff(poster.name)
    backoff.failures += 1
    if backoff.failures >= _RETRY_MAX_FAILURES:
        _drop_pending(tv, f"gave up after {backoff.failures} failed tries ({error})")
    else:
        backoff.not_before = time.monotonic() + _RETRY_BACKOFF_S


def _retry_hang(tv: TvConfig, poster: Path) -> None:
    """Hang ``poster`` on ``tv`` if it's awake, idle in Art Mode, and not backing off."""
    backoff = _retry_backoff.get(tv.ip)
    if backoff and backoff.poster == poster.name and time.monotonic() < backoff.not_before:
        return
    if not is_reachable(tv.ip, timeout=_TV_PROBE_TIMEOUT_S):
        logger.debug("%s is still asleep; %s is waiting", tv.name, poster.name)
        return
    if not _tv_lock.acquire(blocking=False):
        return  # another push is running (likely a newer poster); look again next tick
    try:
        if _pending_poster(tv) != poster:
            return  # superseded while we were checking
        try:
            _supported, in_art_mode = art_state(tv.ip, str(_tv_token_file(tv.ip)))
        except Exception as exc:
            _retry_failed(tv, poster, str(exc))
            return
        if in_art_mode is False:
            # Someone just turned it on to watch something; don't yank it into Art Mode.
            logger.debug("%s is on but not in Art Mode; %s is waiting", tv.name, poster.name)
            return
        logger.info("%s is back in Art Mode; hanging %s", tv.name, poster.name)
        error = _hang_on_tv(tv, poster.name, _frame_ready(poster), quick_check=False)
        if error is not None:
            _retry_failed(tv, poster, error)
    finally:
        _tv_lock.release()


def _retry_pending_hangs() -> None:
    """Hang posters that missed a TV (e.g. it was asleep) once it is back in Art Mode.

    Runs every scheduler tick, also outside the active windows: it costs no tokens, just
    a quick connection check while the TV is still away.
    """
    for tv in load_config().tvs:
        if not _tv_pending_file(tv.ip).exists():
            continue
        poster = _pending_poster(tv)
        if poster is None:
            _drop_pending(tv, "the poster is gone")
        elif not tv.enabled:
            _drop_pending(tv, "updates are paused")  # the next poster after resuming wins
        elif not _tv_paired(tv.ip):
            _drop_pending(tv, "not paired")  # never pop the 'Allow' dialog in the background
        else:
            _retry_hang(tv, poster)


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
        # After the tick, so a poster it just painted supersedes the one that was waiting.
        try:
            _retry_pending_hangs()
        except Exception:
            logger.exception("Retrying a missed TV hang failed")


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

    @app.get("/api/posters/latest.jpg")
    def latest_poster() -> FileResponse:
        """The newest poster at a stable URL — handy for an iPhone photo widget.

        Content changes over time, so it's marked uncacheable.
        """
        return FileResponse(_latest_poster_path(), headers={"Cache-Control": "no-store"})

    @app.get("/api/posters/{name}/image")
    def poster_image(name: str) -> FileResponse:
        return FileResponse(_safe_poster_path(name))

    @app.get("/api/posters/{name}/thumb")
    def poster_thumb(name: str) -> FileResponse:
        return FileResponse(_thumbnail(name))

    @app.get("/api/logs")
    def logs() -> dict[str, list[str]]:
        return {"lines": recent_logs()}

    @app.get("/api/storage")
    def storage() -> StorageInfo:
        return _storage_info()

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

    @app.get("/api/gemini/status")
    def gemini_status(probe: bool = False) -> GeminiStatus:
        return _gemini_status(probe=probe)

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
