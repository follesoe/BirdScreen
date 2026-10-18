"""Tests for the config schema."""

import pytest
from pydantic import ValidationError

from birdscreen.config import SettingsConfig


def test_default_image_model_is_nano_banana_21() -> None:
    assert SettingsConfig().model == "gemini-nano-banana-2.1"


def test_pro_image_model_is_still_selectable() -> None:
    assert SettingsConfig.model_validate({"model": "gemini-3-pro-image"}).model == (
        "gemini-3-pro-image"
    )


def test_retired_image_model_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SettingsConfig.model_validate({"model": "gemini-2.5-flash-image"})
