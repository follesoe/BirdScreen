"""Local AI super-resolution upscaling (Real-ESRGAN via spandrel + torch).

Takes a lower-resolution Gemini image (e.g. a cheap flash render at 1344x768) up
to the Samsung Frame's native 3840x2160. Runs on the Apple GPU (MPS) when
available, else CPU.

This is an *optional* feature — install the deps with ``uv sync --extra upscale``.
The module is imported lazily by the pipeline so the rest of the package works
without torch/spandrel installed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import numpy as np
import requests
import torch
from PIL import Image
from spandrel import ImageModelDescriptor, ModelLoader

from birdscreen.images import prepare_for_frame

# Real-ESRGAN model weights (downloaded on first use).
MODELS: dict[str, str] = {
    "realesrgan-x4plus": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
    "realesrgan-x4plus-anime": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth",
}
DEFAULT_MODEL = "realesrgan-x4plus"
MODEL_DIR = Path("models")
DEFAULT_TARGET = (3840, 2160)


def _model_path(model: str) -> Path:
    if model not in MODELS:
        raise ValueError(f"unknown model {model!r}; choices: {', '.join(MODELS)}")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    path = MODEL_DIR / (MODELS[model].rsplit("/", 1)[-1])
    if not path.exists():
        url = MODELS[model]
        print(f"  downloading {model} weights ({url.rsplit('/', 1)[-1]})...")
        with requests.get(url, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            with path.open("wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    fh.write(chunk)
    return path


def _select_device(prefer: str | None = None) -> str:
    if prefer:
        return prefer
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _run_tiled(descriptor: Any, tensor: Any, scale: int, dev: str, tile: int, overlap: int) -> Any:
    """Tiled SR (output accumulated on CPU) so memory stays bounded."""
    _, channels, height, width = tensor.shape
    out = torch.zeros((1, channels, height * scale, width * scale), dtype=torch.float32)
    with torch.inference_mode():
        for y in range(0, height, tile):
            for x in range(0, width, tile):
                ys, xs = max(0, y - overlap), max(0, x - overlap)
                ye, xe = min(height, y + tile + overlap), min(width, x + tile + overlap)
                sr = descriptor(tensor[:, :, ys:ye, xs:xe].to(dev)).to("cpu")
                top, left = (y - ys) * scale, (x - xs) * scale
                h, w = min(tile, height - y) * scale, min(tile, width - x) * scale
                out[:, :, y * scale : y * scale + h, x * scale : x * scale + w] = sr[
                    :, :, top : top + h, left : left + w
                ]
    return out


def super_resolve(
    src: str | Path,
    model: str = DEFAULT_MODEL,
    *,
    device: str | None = None,
    tile: int = 512,
    overlap: int = 32,
) -> Image.Image:
    """Run the SR model on ``src`` and return the upscaled PIL image."""
    dev = _select_device(device)
    descriptor = ModelLoader().load_from_file(str(_model_path(model)))
    if not isinstance(descriptor, ImageModelDescriptor):
        raise TypeError(f"{model} is not a single-image SR model")
    descriptor.to(dev).eval()
    scale = descriptor.scale

    img = Image.open(src).convert("RGB")
    arr = np.asarray(img, dtype=np.float32) / 255.0
    tensor = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0)  # CPU

    try:
        out = _run_tiled(descriptor, tensor, scale, dev, tile, overlap)
    except RuntimeError as exc:  # e.g. MPS out-of-memory -> retry whole thing on CPU
        if dev == "cpu":
            raise
        print(f"  {dev} failed ({exc}); retrying on CPU...")
        descriptor.to("cpu")
        out = _run_tiled(descriptor, tensor, scale, "cpu", tile, overlap)

    out = out.squeeze(0).clamp(0, 1).permute(1, 2, 0).numpy()
    return Image.fromarray((out * 255 + 0.5).astype("uint8"))


def upscale_image(
    src: str | Path,
    dst: str | Path | None = None,
    *,
    target: tuple[int, int] | None = DEFAULT_TARGET,
    model: str = DEFAULT_MODEL,
    device: str | None = None,
) -> Path:
    """Upscale ``src`` with Real-ESRGAN and fit it to ``target`` (default 4K UHD).

    With ``target=None`` the raw 4x SR output is saved. Returns the output path.
    """
    sr = super_resolve(src, model, device=device)

    src = Path(src)
    if dst is None:
        dst = src.with_name(f"{src.stem}_upscaled.jpg")
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)

    if target is None:
        sr.save(dst, "JPEG", quality=92)
    else:
        # Reuse the Frame-fit (aspect-preserving, padded) on the SR result.
        tmp = dst.with_suffix(".srtmp.png")
        sr.save(tmp)
        prepare_for_frame(tmp, dst=dst, size=target)
        tmp.unlink(missing_ok=True)
    return dst


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="upscale",
        description="AI-upscale an image to the TV's native resolution (Real-ESRGAN).",
    )
    parser.add_argument("src", help="Source image.")
    parser.add_argument("-o", "--out", help="Output path (default: <src>_upscaled.jpg).")
    parser.add_argument("--model", default=DEFAULT_MODEL, choices=list(MODELS))
    parser.add_argument("--size", default="3840x2160", help="Target WxH, or 'native' to keep 4x.")
    parser.add_argument("--device", help="Force device: mps | cpu | cuda.")
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    target: tuple[int, int] | None
    if args.size.lower() == "native":
        target = None
    else:
        try:
            w, h = (int(x) for x in args.size.lower().split("x"))
            target = (w, h)
        except ValueError:
            parser.error("--size must look like 3840x2160 or 'native'")

    print(f"Upscaling {args.src} with {args.model} (device: {args.device or 'auto'})...")
    out = upscale_image(args.src, args.out, target=target, model=args.model, device=args.device)
    with Image.open(out) as im:
        size = im.size
    print(f"✓ Saved {out} ({out.stat().st_size} bytes, {size[0]}x{size[1]})")
    sys.exit(0)


if __name__ == "__main__":
    main()
