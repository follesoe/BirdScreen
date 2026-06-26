"""Tests for weather symbol normalization and scene descriptions."""

from birdscreen.weather import Weather, normalize_symbol, precipitation_intensity


def test_normalize_symbol() -> None:
    assert normalize_symbol("heavyrain") == "rain"
    assert normalize_symbol("lightsnow_day") == "snow"
    assert normalize_symbol("partlycloudy_night") == "partly_cloudy"
    assert normalize_symbol("clearsky_day") == "clear"
    assert normalize_symbol("fog") == "fog"
    assert normalize_symbol("thunderstorm") == "thunder"
    assert normalize_symbol("something_unknown") == "clear"


def test_precipitation_intensity() -> None:
    assert precipitation_intensity("heavyrain") == "heavy"
    assert precipitation_intensity("lightsnow") == "light"
    assert precipitation_intensity("rain") == "moderate"
    assert precipitation_intensity("clearsky_day") is None


def test_weather_describe_precip_includes_temperature() -> None:
    text = Weather(condition="rain", intensity="heavy", temperature_c=-3.4).describe()
    assert "heavy rain" in text
    assert "-3°C" in text  # rounded


def test_weather_describe_clear_without_temp() -> None:
    assert Weather(condition="clear").describe() == "clear skies"
