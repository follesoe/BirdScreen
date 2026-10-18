"""Token-usage accounting and cost estimation for Gemini calls.

Prices are USD per 1,000,000 tokens (paid/standard tier); the defaults come from
:func:`birdscreen.config.default_pricing` and config.yaml's ``pricing`` overrides them.

Google bills a call as: input tokens at the input rate, image tokens at the image
rate, and every other response token *plus the thinking tokens* at the text rate.
E.g. a 2K gemini-nano-banana-2.1 poster is 1680 image tokens ($0.0504) plus ~2,500
text + thinking tokens (~$0.02).
"""

from __future__ import annotations

from dataclasses import dataclass

from birdscreen.config import ModelCost, default_pricing


def rate_for(pricing: dict[str, ModelCost], model: str) -> ModelCost | None:
    """A model's rates (tolerating suffixes like ``-preview``), or None if unpriced."""
    name = model.removeprefix("models/")
    if name in pricing:
        return pricing[name]
    return next((rate for key, rate in pricing.items() if name.startswith(key)), None)


@dataclass
class Usage:
    model: str
    input_tokens: int
    output_tokens: int  # response tokens, image + text (thinking is reported separately)
    image_tokens: int = 0  # the image-modality share of output_tokens
    thinking_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.thinking_tokens

    def cost_with(self, rate: ModelCost) -> float:
        """USD for this call: image tokens at the image rate, the rest at the text rate."""
        text_rate = rate.output if rate.output_text is None else rate.output_text
        text_tokens = self.output_tokens - self.image_tokens + self.thinking_tokens
        return (
            self.input_tokens * rate.input
            + self.image_tokens * rate.output
            + text_tokens * text_rate
        ) / 1e6

    def cost_usd(self, pricing: dict[str, ModelCost] | None = None) -> float | None:
        """Estimated USD (default prices unless ``pricing`` is given); None if unpriced."""
        rate = rate_for(default_pricing() if pricing is None else pricing, self.model)
        return None if rate is None else self.cost_with(rate)

    def describe(self, pricing: dict[str, ModelCost] | None = None) -> str:
        cost = self.cost_usd(pricing)
        cost_str = f"${cost:.4f}" if cost is not None else "n/a (no price for model)"
        tokens = f"{self.input_tokens} in + {self.output_tokens} out"
        if self.image_tokens:
            tokens += f" ({self.image_tokens} image)"
        if self.thinking_tokens:
            tokens += f" + {self.thinking_tokens} thinking"
        return f"{self.model}: {tokens} = {self.total_tokens} tokens, est. {cost_str}"

    def __str__(self) -> str:
        return self.describe()


def usage_from_response(model: str, response: object) -> Usage:
    """Extract a Usage from a google-genai response's usage_metadata."""
    meta = getattr(response, "usage_metadata", None)
    details = getattr(meta, "candidates_tokens_details", None) or []
    return Usage(
        model=model,
        input_tokens=getattr(meta, "prompt_token_count", 0) or 0,
        output_tokens=getattr(meta, "candidates_token_count", 0) or 0,
        image_tokens=sum(
            getattr(detail, "token_count", 0) or 0
            for detail in details
            if getattr(detail, "modality", None) == "IMAGE"
        ),
        thinking_tokens=getattr(meta, "thoughts_token_count", 0) or 0,
    )


def tally_cost(
    usages: list[Usage], pricing: dict[str, ModelCost] | None = None
) -> tuple[int, float | None]:
    """Total tokens and estimated USD for a batch of calls (None if none is priced)."""
    total_tokens = sum(u.total_tokens for u in usages)
    costs = [cost for u in usages if (cost := u.cost_usd(pricing)) is not None]
    return total_tokens, (round(sum(costs), 6) if costs else None)


def summarize(usages: list[Usage], pricing: dict[str, ModelCost] | None = None) -> str:
    """One line per call plus an aggregate total + estimated cost."""
    if not usages:
        return "no usage recorded"
    lines = [f"  - {u.describe(pricing)}" for u in usages]
    total_tokens, total_cost = tally_cost(usages, pricing)
    priced = sum(1 for u in usages if u.cost_usd(pricing) is not None)
    suffix = "" if priced == len(usages) else " (+ unpriced calls)"
    lines.append(f"  = {total_tokens} tokens total, est. ${total_cost or 0.0:.4f}{suffix}")
    return "\n".join(lines)
