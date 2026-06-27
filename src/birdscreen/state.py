"""Local persistent state — a log of poster generations (SQLite, stdlib only).

Every time BirdScreen renders a poster we record *what went into it* (the dynamic
prompt fields: birds, location, season, weather), *why* it triggered, and where
the image landed. The status page reads this back as history, and the engine uses
it to decide timing (count today, last render time).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DB_PATH = Path("data/birdscreen.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS generations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    trigger     TEXT NOT NULL,            -- 'bird' | 'time' | 'manual'
    reason      TEXT,                     -- human-readable explanation
    birds       TEXT NOT NULL,            -- JSON array of common names
    location    TEXT,
    season      TEXT,
    weather     TEXT,
    model       TEXT NOT NULL,
    image_size  TEXT NOT NULL,
    output      TEXT,                      -- poster filename
    prompt      TEXT                       -- the full prompt sent to the image model
);
"""


@dataclass
class GenerationRecord:
    """One recorded poster generation (a row of the history log)."""

    trigger: str
    birds: list[str]
    model: str
    image_size: str
    reason: str | None = None
    location: str | None = None
    season: str | None = None
    weather: str | None = None
    output: str | None = None
    prompt: str | None = None
    id: int = 0  # set on read
    created_at: str = ""  # ISO; defaults to now on insert


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)
    return conn


def _row_to_record(row: sqlite3.Row) -> GenerationRecord:
    birds_raw = row["birds"]
    birds = json.loads(birds_raw) if birds_raw else []
    return GenerationRecord(
        id=row["id"],
        created_at=row["created_at"],
        trigger=row["trigger"],
        reason=row["reason"],
        birds=list(birds),
        location=row["location"],
        season=row["season"],
        weather=row["weather"],
        model=row["model"],
        image_size=row["image_size"],
        output=row["output"],
        prompt=row["prompt"],
    )


def record_generation(record: GenerationRecord) -> int:
    """Append a generation to the log; returns its row id (``record.id`` is ignored)."""
    created = record.created_at or datetime.now().isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO generations "
            "(created_at, trigger, reason, birds, location, season, weather, model, "
            "image_size, output, prompt) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                created,
                record.trigger,
                record.reason,
                json.dumps(record.birds),
                record.location,
                record.season,
                record.weather,
                record.model,
                record.image_size,
                record.output,
                record.prompt,
            ),
        )
        return int(cur.lastrowid or 0)


def recent_generations(limit: int = 50) -> list[GenerationRecord]:
    """The most recent generations, newest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM generations ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_record(row) for row in rows]


def last_generation() -> GenerationRecord | None:
    """The single most recent generation, or None."""
    found = recent_generations(limit=1)
    return found[0] if found else None


def count_generations_since(since: datetime) -> int:
    """How many generations since ``since`` (e.g. the current bird-day start)."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM generations WHERE created_at >= ?", (since.isoformat(),)
        ).fetchone()
    return int(row["n"]) if row else 0
