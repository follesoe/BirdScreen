"""Image helpers for BirdScreen.

Currently focused on preparing posters for display on a Samsung The Frame TV,
but kept generic so it can grow with the project (poster generation, thumbnails,
etc.).
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from PIL import Image

# Native panel resolution of the Frame TVs we target (4K UHD, 16:9).
FRAME_UHD: tuple[int, int] = (3840, 2160)


def _sample_background(img: Image.Image) -> tuple[int, int, int]:
    """Average the four corner pixels to guess the image's background color."""
    rgb = img.convert("RGB")
    w, h = rgb.size
    corners = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
    r = g = b = 0
    for x, y in corners:
        pr, pg, pb = cast("tuple[int, int, int]", rgb.getpixel((x, y)))
        r, g, b = r + pr, g + pg, b + pb
    n = len(corners)
    return (r // n, g // n, b // n)


def prepare_for_frame(
    src: str | Path,
    dst: str | Path | None = None,
    *,
    size: tuple[int, int] = FRAME_UHD,
    background: tuple[int, int, int] | None = None,
    quality: int = 92,
) -> Path:
    """Convert an image to a Frame-ready JPEG.

    The image is scaled to fit ``size`` while preserving aspect ratio, then
    centered on a solid canvas (padding, never cropping or stretching). Alpha is
    flattened onto the background color. By default the background is sampled from
    the source corners so any padding blends with the artwork.

    Returns the path to the written JPEG.
    """
    src = Path(src)
    img: Image.Image = Image.open(src)

    if background is None:
        background = _sample_background(img)

    # Flatten any transparency onto the background color.
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        flat = Image.new("RGB", img.size, background)
        flat.paste(img, mask=img.split()[-1])
        img = flat
    else:
        img = img.convert("RGB")

    # Scale to fit within the target, preserving aspect ratio.
    target_w, target_h = size
    scale = min(target_w / img.width, target_h / img.height)
    new_size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
    img = img.resize(new_size, Image.Resampling.LANCZOS)

    # Center on a solid canvas of the exact target size.
    canvas = Image.new("RGB", size, background)
    offset = ((target_w - new_size[0]) // 2, (target_h - new_size[1]) // 2)
    canvas.paste(img, offset)

    if dst is None:
        dst = src.with_suffix(".jpg")
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dst, "JPEG", quality=quality)
    return dst
