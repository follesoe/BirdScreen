"""Tests for token-usage cost estimation."""

from birdscreen.usage import Usage, summarize


def test_cost_pro_image() -> None:
    # input 400/1e6*$2 + output 2000/1e6*$120 = 0.0008 + 0.24
    usage = Usage(model="gemini-3-pro-image", input_tokens=400, output_tokens=2000)
    assert usage.total_tokens == 2400
    assert round(usage.cost_usd() or 0.0, 4) == 0.2408


def test_cost_unknown_model_is_none() -> None:
    assert Usage(model="mystery-model", input_tokens=1, output_tokens=1).cost_usd() is None


def test_price_lookup_tolerates_preview_suffix() -> None:
    preview = Usage(model="gemini-3-pro-image-preview", input_tokens=0, output_tokens=1_000_000)
    assert preview.cost_usd() == 120.0


def test_summarize_aggregates_tokens_and_cost() -> None:
    usages = [
        Usage("gemini-2.5-flash", 200, 50),
        Usage("gemini-3-pro-image", 400, 2000),
    ]
    out = summarize(usages)
    assert "2650 tokens total" in out
    assert "$" in out
