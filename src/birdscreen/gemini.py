"""Google Gemini image generation for BirdScreen.

Generates the daily bird poster from a text prompt using Gemini's native image
models ("Nano Banana"). The default is ``gemini-nano-banana-2.1`` (Nano Banana 2.1),
which renders text accurately — important for posters with species labels
(Norwegian + Latin names) — at about a third of the cost of ``gemini-3-pro-image``
(Nano Banana Pro), the premium alternative.

Setup:
  1. Create an API key at https://aistudio.google.com/apikey
  2. Put it in a ``.env`` file:  GEMINI_API_KEY=your_key_here
  3. ``uv run generate-poster "your prompt" -o cache/poster.png``

The SDK reads ``GEMINI_API_KEY`` from the environment automatically; we also load
a local ``.env`` for convenience.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import cast

from dotenv import find_dotenv, load_dotenv
from google import genai
from google.genai import errors, types

from birdscreen.logging_config import setup_logging
from birdscreen.usage import Usage, summarize, usage_from_response

logger = logging.getLogger(__name__)

# Search upward from CWD so a project-root .env is found even when installed.
load_dotenv(find_dotenv(usecwd=True))

# Nano Banana 2.1 — correct labels and natural scale at ~$0.07 per 2K poster. Override
# with the BIRDSCREEN_IMAGE_MODEL env var or the --model flag.
DEFAULT_IMAGE_MODEL = os.environ.get("BIRDSCREEN_IMAGE_MODEL", "gemini-nano-banana-2.1")
# The Frame is a 4K 16:9 panel; 2K is a good cost/quality default for iteration.
DEFAULT_ASPECT_RATIO = "16:9"
DEFAULT_IMAGE_SIZE = "2K"
_RETRYABLE_CODES = (429, 500, 502, 503, 504)
_MAX_RETRIES = 4
_RETRY_DELAY = 8.0


def _is_transient(exc: Exception) -> bool:
    """True for retryable API errors (rate limits / server spikes)."""
    code = getattr(exc, "code", None)
    return isinstance(exc, errors.ServerError) or code in _RETRYABLE_CODES


def get_client(api_key: str | None = None) -> genai.Client:
    """Create a Gemini client, reading GEMINI_API_KEY/GOOGLE_API_KEY if needed."""
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError(
            "No Gemini API key found. Set GEMINI_API_KEY (e.g. in a .env file).\n"
            "Create one at https://aistudio.google.com/apikey"
        )
    return genai.Client(api_key=key)


# A cheap text model, used only for the health/credits probe. It shares the API key and
# prepaid billing with the image model, so on a billing-enabled key a depleted balance
# 429s here too. Caveat: if the account keeps free-tier quota for this text model that the
# paid image model lacks, a live probe can read "ok" while image generation still fails.
PROBE_MODEL = os.environ.get("BIRDSCREEN_TEXT_MODEL", "gemini-3.8-flash")

# Substrings Google uses when *prepaid billing is depleted* (as opposed to a plain,
# self-healing rate limit) — both surface as HTTP 429 RESOURCE_EXHAUSTED.
_CREDIT_MARKERS = ("credit", "billing", "depleted", "prepay")
_TOO_MANY_REQUESTS = 429  # HTTP 429 RESOURCE_EXHAUSTED (rate limit *or* billing depleted)
_AUTH_CODES = (401, 403)  # invalid/insufficient API key


def classify_api_error(exc: BaseException) -> tuple[str, str]:
    """Map a Gemini failure to ``(kind, human message)``.

    ``kind`` is one of: ``out_of_credits`` (billing depleted — needs a top-up),
    ``rate_limited`` (transient), ``no_key``, ``auth``, ``error``.
    """
    text = str(exc)
    low = text.lower()
    code = getattr(exc, "code", None)
    if isinstance(exc, RuntimeError) and "api key" in low:
        return ("no_key", "No Gemini API key configured — set GEMINI_API_KEY.")
    if code == _TOO_MANY_REQUESTS or "resource_exhausted" in low:
        if any(marker in low for marker in _CREDIT_MARKERS):
            return (
                "out_of_credits",
                "Out of Gemini credits — top up billing in Google AI Studio to resume painting.",
            )
        return (
            "rate_limited",
            "Gemini is rate-limiting requests right now; it should recover on its own.",
        )
    if code in _AUTH_CODES or "permission" in low or "api key not valid" in low:
        return ("auth", "Gemini rejected the API key — check it's valid and billing is enabled.")
    return ("error", "Couldn't reach Gemini.")


def is_gemini_error(exc: BaseException) -> bool:
    """True only when ``exc`` is attributable to the Gemini API itself.

    Lets callers distinguish a real Gemini failure (quota, auth, server) from an
    unrelated downstream failure in the same code path (image processing, TV upload,
    a missing location) so the latter is never mislabeled as a Gemini/credits problem.
    """
    if isinstance(exc, errors.APIError):
        return True
    # get_client() raises this when the key is missing — genuinely a Gemini problem.
    return isinstance(exc, RuntimeError) and "gemini api key" in str(exc).lower()


def check_health(*, model: str = PROBE_MODEL, client: genai.Client | None = None) -> None:
    """Make a minimal billable request to confirm the key works and credits remain.

    Returns normally on success; raises the underlying error on failure (callers
    classify it via :func:`classify_api_error`). Deliberately tiny — a one-token reply
    — so probing costs next to nothing.
    """
    client = client or get_client()
    client.models.generate_content(
        model=model,
        contents="ping",
        config=types.GenerateContentConfig(max_output_tokens=1),
    )


def _extract_image_bytes(response: types.GenerateContentResponse) -> bytes | None:
    for candidate in response.candidates or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            if inline is not None and inline.data:
                return cast("bytes", inline.data)
    return None


def _extract_text(response: types.GenerateContentResponse) -> str:
    chunks: list[str] = []
    for candidate in response.candidates or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            if getattr(part, "text", None):
                chunks.append(part.text)
    return "\n".join(chunks)


def generate_image(
    prompt: str,
    out_path: str | Path,
    *,
    model: str = DEFAULT_IMAGE_MODEL,
    aspect_ratio: str = DEFAULT_ASPECT_RATIO,
    image_size: str = DEFAULT_IMAGE_SIZE,
    client: genai.Client | None = None,
    usage_sink: list[Usage] | None = None,
) -> Path:
    """Generate an image from ``prompt`` and write it to ``out_path``.

    Retries transient API errors (rate limits / 5xx server spikes) with linear
    backoff. Returns the output path. Raises RuntimeError if the model returns no
    image (e.g. blocked by safety filters), surfacing any text the model returned.
    """
    client = client or get_client()
    config = types.GenerateContentConfig(
        response_modalities=[types.Modality.IMAGE],
        image_config=types.ImageConfig(
            aspect_ratio=aspect_ratio,
            image_size=image_size,
        ),
    )
    for attempt in range(_MAX_RETRIES):
        try:
            response = client.models.generate_content(model=model, contents=prompt, config=config)
            break
        except Exception as exc:
            if _is_transient(exc) and attempt < _MAX_RETRIES - 1:
                wait = _RETRY_DELAY * (attempt + 1)
                logger.warning(
                    "Transient error (%s); retrying in %.0fs [%d/%d]",
                    getattr(exc, "code", type(exc).__name__),
                    wait,
                    attempt + 1,
                    _MAX_RETRIES - 1,
                )
                time.sleep(wait)
                continue
            raise

    if usage_sink is not None:
        usage_sink.append(usage_from_response(model, response))

    image_bytes = _extract_image_bytes(response)
    if image_bytes is None:
        raise RuntimeError(
            f"Gemini returned no image. Model text (if any): {_extract_text(response)!r}"
        )
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(image_bytes)
    return out


def list_image_models(client: genai.Client | None = None) -> list[str]:
    """Return model IDs that can output images (best-effort filtering)."""
    client = client or get_client()
    names: list[str] = []
    for model in client.models.list():
        name = (model.name or "").removeprefix("models/")
        if "image" in name or "banana" in name:
            names.append(name)
    return names


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="generate-poster",
        description="Generate an image with Google Gemini (Nano Banana).",
    )
    parser.add_argument("prompt", nargs="?", help="Text prompt for the image.")
    parser.add_argument(
        "--prompt-file", help="Read the prompt from a file instead of the argument."
    )
    parser.add_argument("-o", "--out", default="cache/poster.png", help="Output image path.")
    parser.add_argument("--model", default=DEFAULT_IMAGE_MODEL, help="Model ID.")
    parser.add_argument("--aspect", default=DEFAULT_ASPECT_RATIO, help="Aspect ratio.")
    parser.add_argument("--size", default=DEFAULT_IMAGE_SIZE, help="Image size: 512, 1K, 2K, 4K.")
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List available image models and exit (requires API key).",
    )
    args = parser.parse_args()
    setup_logging()

    if args.list_models:
        try:
            for name in list_image_models():
                print(name)  # data output to stdout
        except Exception:
            logger.exception("Could not list models")
            sys.exit(1)
        sys.exit(0)

    prompt = args.prompt
    if args.prompt_file:
        prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    if not prompt:
        parser.error("provide a prompt (positional) or --prompt-file")

    usage: list[Usage] = []
    logger.info("Generating with %s (%s, %s)...", args.model, args.aspect, args.size)
    try:
        out = generate_image(
            prompt,
            args.out,
            model=args.model,
            aspect_ratio=args.aspect,
            image_size=args.size,
            usage_sink=usage,
        )
    except Exception:
        logger.exception("Generation failed")
        sys.exit(1)

    logger.info("Saved %s (%d bytes)", out, out.stat().st_size)
    logger.info("Token usage / estimated cost:\n%s", summarize(usage))
    sys.exit(0)


if __name__ == "__main__":
    main()
