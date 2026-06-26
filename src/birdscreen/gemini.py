"""Google Gemini image generation for BirdScreen.

Generates the daily bird poster from a text prompt using Gemini's native image
models ("Nano Banana"). The default is ``gemini-3-pro-image`` (Nano Banana Pro),
which is built for complex layouts and precise text rendering — important for
posters with species labels (Norwegian + Latin names).

Setup:
  1. Create an API key at https://aistudio.google.com/apikey
  2. Put it in a ``.env`` file:  GEMINI_API_KEY=your_key_here
  3. ``uv run generate-poster "your prompt" -o cache/poster.png``

The SDK reads ``GEMINI_API_KEY`` from the environment automatically; we also load
a local ``.env`` for convenience.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import cast

from dotenv import find_dotenv, load_dotenv
from google import genai
from google.genai import errors, types

from birdscreen.usage import Usage, summarize, usage_from_response

# Search upward from CWD so a project-root .env is found even when installed.
load_dotenv(find_dotenv(usecwd=True))

# Nano Banana Pro — best text rendering / complex layouts. Override with the
# BIRDSCREEN_IMAGE_MODEL env var or the --model flag.
DEFAULT_IMAGE_MODEL = os.environ.get("BIRDSCREEN_IMAGE_MODEL", "gemini-3-pro-image")
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
                print(
                    f"  transient error ({getattr(exc, 'code', type(exc).__name__)}); "
                    f"retrying in {wait:.0f}s [{attempt + 1}/{_MAX_RETRIES - 1}]",
                    file=sys.stderr,
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
        if "image" in name or "imagen" in name:
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

    if args.list_models:
        try:
            for name in list_image_models():
                print(name)
        except Exception as exc:
            print(f"✗ {exc}")
            sys.exit(1)
        sys.exit(0)

    prompt = args.prompt
    if args.prompt_file:
        prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    if not prompt:
        parser.error("provide a prompt (positional) or --prompt-file")

    usage: list[Usage] = []
    print(f"Generating with {args.model} ({args.aspect}, {args.size})...")
    try:
        out = generate_image(
            prompt,
            args.out,
            model=args.model,
            aspect_ratio=args.aspect,
            image_size=args.size,
            usage_sink=usage,
        )
    except Exception as exc:
        print(f"✗ Generation failed: {type(exc).__name__}: {exc}")
        sys.exit(1)

    print(f"✓ Saved {out} ({out.stat().st_size} bytes)")
    print("Token usage / estimated cost:")
    print(summarize(usage))
    sys.exit(0)


if __name__ == "__main__":
    main()
