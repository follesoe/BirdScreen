"""Tests for token-usage cost estimation."""

from google.genai import types

from birdscreen.config import ModelCost
from birdscreen.usage import Usage, summarize, tally_cost, usage_from_response


def test_cost_pro_image() -> None:
    # input 400/1e6*$2 + 2000 image tokens/1e6*$120 = 0.0008 + 0.24
    usage = Usage("gemini-3-pro-image", input_tokens=400, output_tokens=2000, image_tokens=2000)
    assert usage.total_tokens == 2400
    assert round(usage.cost_usd() or 0.0, 4) == 0.2408


def test_cost_nano_banana_21_poster() -> None:
    # A real 2K poster (2026-10-18): 706 in, 2963 out of which 1680 image, 1169 thinking.
    # 706*$1.50 + 1680*$30 + (1283 + 1169)*$7.50 per 1M = 0.001059 + 0.0504 + 0.01839
    usage = Usage(
        "gemini-nano-banana-2.1",
        input_tokens=706,
        output_tokens=2963,
        image_tokens=1680,
        thinking_tokens=1169,
    )
    assert usage.total_tokens == 706 + 2963 + 1169
    assert round(usage.cost_usd() or 0.0, 4) == 0.0698


def test_cost_text_model_bills_thinking_at_output_rate() -> None:
    # 238*$0.75 + (124 + 575)*$3.75 per 1M
    usage = Usage("gemini-3.8-flash", input_tokens=238, output_tokens=124, thinking_tokens=575)
    assert round(usage.cost_usd() or 0.0, 4) == 0.0028


def test_usage_from_response_splits_image_and_thinking() -> None:
    # usage_metadata exactly as returned for a 1K nano-banana-2.1 render.
    response = types.GenerateContentResponse(
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=20,
            candidates_token_count=1510,
            candidates_tokens_details=[
                types.ModalityTokenCount(modality=types.MediaModality.IMAGE, token_count=1120)
            ],
            thoughts_token_count=865,
            total_token_count=2395,
        )
    )
    usage = usage_from_response("gemini-nano-banana-2.1", response)
    assert (usage.input_tokens, usage.output_tokens) == (20, 1510)
    assert (usage.image_tokens, usage.thinking_tokens) == (1120, 865)
    assert usage.total_tokens == 2395  # matches Google's total_token_count
    assert round(usage.cost_usd() or 0.0, 4) == 0.0430


def test_pricing_without_text_rate_uses_output_rate() -> None:
    # config.yaml entries written before output_text existed keep their old meaning.
    legacy = {"gemini-3-pro-image": ModelCost(input=0.0, output=120.0)}
    usage = Usage("gemini-3-pro-image", 0, 1_000_000, image_tokens=500_000)
    assert usage.cost_usd(legacy) == 120.0


def test_cost_unknown_model_is_none() -> None:
    assert Usage(model="mystery-model", input_tokens=1, output_tokens=1).cost_usd() is None


def test_price_lookup_tolerates_preview_suffix() -> None:
    preview = Usage("gemini-3-pro-image-preview", 0, 1_000_000, image_tokens=1_000_000)
    assert preview.cost_usd() == 120.0


def test_tally_cost_skips_unpriced_calls() -> None:
    usages = [
        Usage("gemini-3.8-flash", 238, 124, thinking_tokens=575),
        Usage("mystery-model", 10, 10),
    ]
    total_tokens, cost = tally_cost(usages)
    assert total_tokens == 238 + 124 + 575 + 20
    assert cost == round((238 * 0.75 + 699 * 3.75) / 1e6, 6)
    assert tally_cost([Usage("mystery-model", 1, 1)]) == (2, None)


def test_summarize_aggregates_tokens_and_cost() -> None:
    usages = [
        Usage("gemini-3.8-flash", 200, 50, thinking_tokens=100),
        Usage("gemini-3-pro-image", 400, 2000, image_tokens=2000),
    ]
    out = summarize(usages)
    assert "(2000 image)" in out
    assert "+ 100 thinking" in out
    assert "2750 tokens total" in out
    assert "$" in out
