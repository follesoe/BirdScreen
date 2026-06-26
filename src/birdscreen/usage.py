"""Token-usage accounting and rough cost estimation for Gemini calls.

Prices are USD per 1,000,000 tokens (paid/standard tier), from
https://ai.google.dev/gemini-api/docs/pricing — update if Google changes them.
For image models the "output" rate is the image-token rate (e.g. a 4K
gemini-3-pro-image is ~2000 image tokens ≈ $0.24).
"""

from __future__ import annotations

from dataclasses import dataclass

# USD per 1M tokens: {model: {"input": ..., "output": ...}}.
# For image models "output" is the image-token rate.
PRICING: dict[str, dict[str, float]] = {
    "gemini-3-pro-image": {"input": 2.00, "output": 120.00},
    "gemini-3.1-flash-image": {"input": 0.50, "output": 60.00},
    "gemini-2.5-flash-image": {"input": 0.30, "output": 30.00},
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
}


def _price(model: str) -> dict[str, float] | None:
    name = model.removeprefix("models/")
    if name in PRICING:
        return PRICING[name]
    # tolerate suffixes like "-preview"
    for key, value in PRICING.items():
        if name.startswith(key):
            return value
    return None


@dataclass
class Usage:
    model: str
    input_tokens: int
    output_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def cost_usd(self) -> float | None:
        price = _price(self.model)
        if price is None:
            return None
        return self.input_tokens / 1e6 * price["input"] + self.output_tokens / 1e6 * price["output"]

    def __str__(self) -> str:
        cost = self.cost_usd()
        cost_str = f"${cost:.4f}" if cost is not None else "n/a (no price for model)"
        return (
            f"{self.model}: {self.input_tokens} in + {self.output_tokens} out "
            f"= {self.total_tokens} tokens, est. {cost_str}"
        )


def usage_from_response(model: str, response: object) -> Usage:
    """Extract a Usage from a google-genai response's usage_metadata."""
    meta = getattr(response, "usage_metadata", None)
    return Usage(
        model=model,
        input_tokens=getattr(meta, "prompt_token_count", 0) or 0,
        output_tokens=getattr(meta, "candidates_token_count", 0) or 0,
    )


def summarize(usages: list[Usage]) -> str:
    """One line per call plus an aggregate total + estimated cost."""
    if not usages:
        return "no usage recorded"
    lines = [f"  - {u}" for u in usages]
    total_tokens = sum(u.total_tokens for u in usages)
    costs = [u.cost_usd() for u in usages]
    known = [c for c in costs if c is not None]
    total_cost = sum(known)
    suffix = "" if len(known) == len(costs) else " (+ unpriced calls)"
    lines.append(f"  = {total_tokens} tokens total, est. ${total_cost:.4f}{suffix}")
    return "\n".join(lines)
