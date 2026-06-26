"""FastAPI backend: browse generated posters and view recent logs.

Run with:  uv run --extra web birdscreen-web
The React frontend (built to ``frontend/dist``) is served at ``/``.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel

from birdscreen.logging_config import recent_logs, setup_logging

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


def main() -> None:
    setup_logging()
    logger.info("Starting BirdScreen web on http://127.0.0.1:8000")
    uvicorn.run(create_app(), host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
