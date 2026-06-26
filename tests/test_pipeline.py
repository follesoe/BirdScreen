"""Tests for pipeline output naming (slug, filename, counter)."""

from datetime import datetime
from pathlib import Path

from birdscreen.pipeline import _next_indexed_base, _slug, default_filename
from birdscreen.poster import Bird


def test_slug_folds_norwegian_and_punctuation() -> None:
    assert _slug("Blåmeis") == "Blameis"
    assert _slug("Nøtteskrike") == "Notteskrike"
    assert _slug("Trondheim, Norway") == "Trondheim-Norway"


def test_default_filename_is_date_first_and_sortable() -> None:
    name = default_filename(
        datetime(2026, 2, 15, 12, 0),
        "Trondheim, Norway",
        [Bird("Pica pica", "Skjære")],
        "gemini-3-pro-image",
    )
    assert name == "2026-02-15T1200_Trondheim-Norway_Skjaere_gemini-3-pro-image"


def test_next_indexed_base_increments(tmp_path: Path) -> None:
    assert _next_indexed_base(tmp_path, "poster").name == "poster_01"
    (tmp_path / "poster_01.jpg").write_text("x")
    assert _next_indexed_base(tmp_path, "poster").name == "poster_02"
