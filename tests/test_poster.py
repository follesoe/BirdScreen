"""Tests for the prompt builder's pure logic (no network / API calls)."""

from datetime import datetime

from birdscreen.poster import (
    Bird,
    PosterContext,
    aspect_ratio,
    build_prompt,
    image_size_tier,
    parse_bird,
    parse_size,
)
from birdscreen.season import SeasonInfo


def test_aspect_ratio_picks_nearest_supported() -> None:
    assert aspect_ratio(3840, 2160) == "16:9"
    assert aspect_ratio(1024, 1024) == "1:1"
    assert aspect_ratio(2160, 3840) == "9:16"


def test_image_size_tier_bounds() -> None:
    assert image_size_tier(512, 512) == "512"
    assert image_size_tier(1280, 720) == "1K"
    assert image_size_tier(2560, 1440) == "2K"
    assert image_size_tier(3840, 2160) == "4K"


def test_parse_bird_with_and_without_common() -> None:
    assert parse_bird("Pica pica=Skjære") == Bird("Pica pica", "Skjære")
    assert parse_bird("Apus apus") == Bird("Apus apus", None)


def test_parse_size() -> None:
    assert parse_size("3840x2160") == (3840, 2160)
    assert parse_size("1024X768") == (1024, 768)


def _ctx(*, labels: bool) -> PosterContext:
    return PosterContext(
        latitude=63.4,
        longitude=10.4,
        when=datetime(2026, 6, 1, 12, 0),
        birds=[Bird("Pica pica", "Skjære")],
        location_name="Trondheim, Norway",
        labels=labels,
    )


_ENV = SeasonInfo(
    season="early summer", foliage="lush leaves", scenery="fjord", light="evening sun"
)


def test_build_prompt_labelled_includes_birds_and_title() -> None:
    prompt = build_prompt(_ctx(labels=True), _ENV)
    assert "Skjære (Pica pica)" in prompt
    assert "Hørt i dag" in prompt
    assert "16:9" in prompt


def test_build_prompt_no_labels_forbids_text_and_omits_title() -> None:
    prompt = build_prompt(_ctx(labels=False), _ENV)
    assert "NO text" in prompt
    assert "Hørt i dag" not in prompt  # title is composited by us, not the model
