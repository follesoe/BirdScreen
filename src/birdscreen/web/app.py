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

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel

from birdscreen.config import ScheduleConfig, SettingsConfig, TvConfig, load_config, save_config
from birdscreen.logging_config import recent_logs, setup_logging
from birdscreen.samsung_tv import get_device_info

logger = logging.getLogger(__name__)

POSTERS_DIR = Path("posters")
THUMB_DIR = Path("cache/thumbs")
FRONTEND_DIST = Path("frontend/dist")
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
_THUMB_MAX = 480


class PosterInfo(BaseModel):
    """Metadata for one generated poster in the gallery."""

    name: str
    date: str | None  # ISO date parsed from the filename, if recognisable
    modified: str  # ISO mtime
    size_bytes: int


class TvStatus(BaseModel):
    """Live status for a TV, queried over REST (no pairing popup)."""

    connected: bool
    name: str | None = None
    model: str | None = None
    resolution: str | None = None
    firmware: str | None = None
    art_mode: bool = False  # reports Frame/Art-Mode support
    token_auth: bool = False
    message: str | None = None


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


def _tv_status(ip: str) -> TvStatus:
    """Query a TV's REST device info (no pairing popup) and map it to TvStatus."""
    try:
        info = get_device_info(ip)
    except Exception as exc:
        return TvStatus(connected=False, message=f"Could not reach the TV: {exc}")
    device = info.get("device", {})

    def truthy(value: object) -> bool:
        return str(value).lower() == "true"

    return TvStatus(
        connected=True,
        name=device.get("name"),
        model=device.get("modelName"),
        resolution=device.get("resolution"),
        firmware=info.get("version") or device.get("firmwareVersion"),
        art_mode=truthy(device.get("FrameTVSupport")),
        token_auth=truthy(device.get("TokenAuthSupport")),
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
    def tv_status(ip: str) -> TvStatus:
        return _tv_status(ip)

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
